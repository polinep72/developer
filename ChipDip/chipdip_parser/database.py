# ChipDip/chipdip_parser/database.py
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
import logging
from chipdip_parser.config_loader import get_config

logger = logging.getLogger(__name__)

# ... (get_db_connection, get_product_to_parse, update_product_check_time, save_stock_history, update_product_details_in_db - остаются как были)


def get_db_connection():
    config = get_config()
    try:
        conn = psycopg2.connect(
            dbname=config['db_name'],
            user=config['db_user'],
            password=config['db_password'],
            host=config['db_host'],
            port=config['db_port']
        )
        logger.info(
            f"Успешное подключение к PostgreSQL: {config['db_host']}:{config['db_port']}, БД: {config['db_name']}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}", exc_info=True)
        raise ConnectionError(f"Не удалось подключиться к БД: {e}")


def get_product_to_parse(conn):
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Диагностика: логируем базовые метрики
            try:
                cur.execute("SELECT COUNT(*) AS cnt FROM products WHERE COALESCE(is_active, TRUE)=TRUE")
                active_cnt = cur.fetchone()["cnt"]
                cur.execute("SELECT MAX(check_timestamp) AS mx FROM stock_history")
                max_check = cur.fetchone()["mx"]
                cur.execute("SELECT now() AS db_now, current_setting('TimeZone') AS tz")
                row_now = cur.fetchone()
                db_now = row_now["db_now"]
                db_tz = row_now["tz"]
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM (
                      SELECT p.id
                      FROM products p
                      LEFT JOIN LATERAL (
                        SELECT sh.check_timestamp AS last_check
                        FROM stock_history sh
                        WHERE sh.product_id = p.id
                        ORDER BY sh.check_timestamp DESC
                        LIMIT 1
                      ) lc ON TRUE
                      WHERE COALESCE(p.is_active, TRUE)=TRUE
                        AND (lc.last_check IS NULL OR lc.last_check <= clock_timestamp() - INTERVAL '12 hours')
                    ) t
                    """
                )
                eligible_cnt = cur.fetchone()["cnt"]
                logger.info(
                    f"Диагностика парсинга: активных товаров={active_cnt}, подходящих под 12ч={eligible_cnt}, макс. check_timestamp={max_check}, db_now={db_now} ({db_tz})"
                )
            except Exception:
                # Диагностика не должна ломать основной поток
                pass

            query = sql.SQL("""
                SELECT p.id, p.url, p.name, p.internal_sku, p.current_price
                FROM products p
                LEFT JOIN LATERAL (
                  SELECT sh.check_timestamp AS last_check
                  FROM stock_history sh
                  WHERE sh.product_id = p.id
                  ORDER BY sh.check_timestamp DESC
                  LIMIT 1
                ) lc ON TRUE
                WHERE COALESCE(p.is_active, TRUE) = TRUE
                  AND (
                    lc.last_check IS NULL
                    OR lc.last_check <= clock_timestamp() - INTERVAL '12 hours'
                  )
                ORDER BY lc.last_check ASC NULLS FIRST, RANDOM()
                LIMIT 1;
            """)
            cur.execute(query)
            product = cur.fetchone()
            if product:
                logger.info(f"Выбран товар для парсинга: ID={product['id']}, URL='{product['url']}'")
            else:
                logger.info("Нет товаров, требующих парсинга (ограничение 12 часов по stock_history).")
            return product
    except psycopg2.Error as e:
        logger.error(f"Ошибка при выборе товара для парсинга: {e}", exc_info=True)
        return None


def update_product_check_time(conn, product_id):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE products SET last_checked_at = NOW() WHERE id = %s",
                (product_id,)
            )
            conn.commit()
            logger.debug(f"Время последней проверки обновлено для product_id: {product_id}")
    except psycopg2.Error as e:
        logger.error(f"Ошибка обновления last_checked_at для product_id {product_id}: {e}", exc_info=True)
        if conn and not conn.closed: conn.rollback()


def save_stock_history(conn, product_id, stock_level, raw_text_data, status_msg, error_msg_text=None, price=None):
    try:
        with conn.cursor() as cur:
            # Нормализуем stock_level: избегаем NULL в БД
            normalized_stock_level = stock_level
            if normalized_stock_level is None:
                # По договоренности не используем -1/NULL. Ставим 0 и статус отражает причину (timeout/ошибка).
                normalized_stock_level = 0
            else:
                try:
                    normalized_stock_level = int(normalized_stock_level)
                except (TypeError, ValueError):
                    normalized_stock_level = 0
            if price is not None:
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    logger.warning(
                        f"Некорректное значение цены '{price}' для product_id {product_id} в истории. Цена не будет сохранена.")
                    price = None

            cur.execute(
                """
                INSERT INTO stock_history (product_id, check_timestamp, stock_level, raw_text, status, error_message, price)
                VALUES (%s, NOW(), %s, %s, %s, %s, %s)
                """,
                (product_id, normalized_stock_level, raw_text_data, status_msg, error_msg_text, price)
            )
            conn.commit()
            logger.info(
                f"Сохранена история: product_id={product_id}, stock={normalized_stock_level}, price={price}, status={status_msg}")
    except psycopg2.Error as e:
        logger.error(f"Ошибка сохранения истории остатков для product_id {product_id}: {e}", exc_info=True)
        if conn and not conn.closed: conn.rollback()


def update_product_details_in_db(conn, product_id, new_name=None, new_notes=None, new_price=None,
                                 current_db_price=None):
    fields_to_update = []
    params = []
    updated_fields_log = []

    if new_name is not None:
        fields_to_update.append(sql.SQL("name = %s"))
        params.append(new_name)
        updated_fields_log.append("name")

    if new_notes is not None:
        fields_to_update.append(sql.SQL("notes = %s"))
        params.append(new_notes)
        updated_fields_log.append("notes")

    if new_price is not None:
        try:
            price_to_set = float(new_price)
            db_price_float = None
            if current_db_price is not None:
                try:
                    db_price_float = float(current_db_price)
                except (TypeError, ValueError):
                    logger.warning(
                        f"Не удалось преобразовать current_db_price '{current_db_price}' во float для сравнения. Цена будет обновлена.")
            if db_price_float is None or abs(price_to_set - db_price_float) > 0.001:
                fields_to_update.append(sql.SQL("current_price = %s"))
                params.append(price_to_set)
                updated_fields_log.append("current_price")
            else:
                logger.debug(
                    f"Цена для product_id {product_id} не изменилась ({price_to_set}). Обновление не требуется.")
        except (ValueError, TypeError):
            logger.warning(
                f"Некорректное значение новой цены '{new_price}' для product_id {product_id}. Цена не будет обновлена.")

    # Добавляем обновление updated_at
    fields_to_update.append(sql.SQL("updated_at = NOW()"))
    updated_fields_log.append("updated_at")

    if not fields_to_update:
        logger.debug(f"Нет новых деталей (name/notes/price) для обновления для product_id: {product_id}")
        return

    params.append(product_id)

    try:
        with conn.cursor() as cur:
            query = sql.SQL("UPDATE products SET {} WHERE id = %s").format(sql.SQL(', ').join(fields_to_update))
            cur.execute(query, tuple(params))
            conn.commit()
            logger.info(f"Детали ({', '.join(updated_fields_log)}) обновлены для product_id: {product_id}.")
    except psycopg2.Error as e:
        logger.error(f"Ошибка обновления деталей для product_id {product_id}: {e}", exc_info=True)
        if conn and not conn.closed: conn.rollback()

# --- НОВАЯ ФУНКЦИЯ ---
def deactivate_product(conn, product_id):
    """Устанавливает is_active = FALSE для указанного product_id."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE products SET is_active = FALSE, last_checked_at = NOW() WHERE id = %s",
                (product_id,)
            )
            conn.commit()
            logger.info(f"Товар ID: {product_id} деактивирован (is_active = FALSE).")
    except psycopg2.Error as e:
        logger.error(f"Ошибка деактивации товара ID {product_id}: {e}", exc_info=True)
        if conn and not conn.closed: conn.rollback()
# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---