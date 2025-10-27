# project_root/import_csv_to_db.py
import csv
import psycopg2
from psycopg2 import sql
import logging
import os
import sys
import datetime  # Для парсинга дат

# ... (код для добавления пути и импорта config_loader остается тем же) ...
try:
    from chipdip_parser import config_loader
except ImportError:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    try:
        from chipdip_parser import config_loader
    except ImportError:
        sys.path.insert(0, os.path.dirname(__file__))
        from chipdip_parser import config_loader

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_db_connection(app_config):
    # ... (остается без изменений) ...
    try:
        conn = psycopg2.connect(
            dbname=app_config['db_name'],
            user=app_config['db_user'],
            password=app_config['db_password'],
            host=app_config['db_host'],
            port=app_config['db_port']
        )
        logger.info(
            f"Успешное подключение к PostgreSQL: {app_config['db_host']}:{app_config['db_port']}, БД: {app_config['db_name']}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Ошибка подключения к PostgreSQL: {e}", exc_info=True)
        raise


def import_data_from_csv(conn, csv_filepath, date_format_in_header):
    logger.info(f"Начало импорта данных из CSV: {csv_filepath}")
    products_imported_count = 0
    products_skipped_count = 0
    stock_history_imported_count = 0
    stock_history_skipped_count = 0

    if not os.path.exists(csv_filepath):
        logger.error(f"Файл CSV не найден: {csv_filepath}")
        return

    try:
        # Укажите правильную кодировку, если это не utf-8 или utf-8-sig
        # Например, encoding='cp1251' для Windows-1251
        with open(csv_filepath, mode='r', encoding='cp1251') as csvfile:  # ИЗМЕНИТЕ КОДИРОВКУ при необходимости
            reader = csv.reader(csvfile, delimiter=';')
            try:
                header = next(reader)
                logger.info(f"Заголовки CSV: {header}")
            except StopIteration:
                logger.error("CSV файл пуст или не содержит заголовков.")
                return

            try:
                internal_sku_col_idx = header.index('Name')
                url_col_idx = header.index('Link')
                # Колонки с историей начинаются с 4-й позиции (индекс 3)
                history_start_col_idx = 3
            except ValueError as e:
                logger.error(
                    f"Ошибка в заголовках CSV: {e}. Убедитесь, что колонки 'Name', 'Link' и колонки с датами существуют.")
                return

            # Парсим метки времени из заголовков исторических данных
            history_timestamps = []
            for col_name in header[history_start_col_idx:]:
                try:
                    # Убедитесь, что date_format_in_header соответствует формату в CSV
                    # Пример из вашего лога: '%d-%m-%Y %H:%M:%S'
                    dt_obj = datetime.datetime.strptime(col_name.strip(), date_format_in_header)
                    history_timestamps.append(dt_obj)
                except ValueError:
                    logger.warning(
                        f"Не удалось распарсить дату из заголовка колонки: '{col_name}'. Пропуск этой колонки для истории.")
                    history_timestamps.append(None)  # Добавляем None, чтобы индексы совпадали

            if not any(history_timestamps):  # Если ни одну дату не удалось распарсить
                logger.warning("Не найдено корректных дат в заголовках для импорта истории остатков.")

            with conn.cursor() as cur:
                for row_num, row in enumerate(reader, start=2):
                    if not row or len(row) <= max(internal_sku_col_idx, url_col_idx):
                        logger.warning(f"Строка {row_num}: Недостаточно данных или пустая строка, пропуск: {row}")
                        products_skipped_count += 1
                        continue

                    internal_sku = row[internal_sku_col_idx].strip()
                    url = row[url_col_idx].strip()
                    product_name_from_csv = internal_sku  # Имя = артикул по умолчанию

                    if not url:
                        logger.warning(f"Строка {row_num}: URL отсутствует для SKU '{internal_sku}', пропуск.")
                        products_skipped_count += 1
                        continue

                    product_id_in_db = None
                    try:
                        # 1. Добавляем/находим товар в таблице products
                        cur.execute("SELECT id FROM products WHERE url = %s", (url,))
                        existing_product_row = cur.fetchone()

                        if existing_product_row:
                            product_id_in_db = existing_product_row[0]
                            logger.debug(
                                f"Строка {row_num}: Товар с URL '{url}' уже существует (ID={product_id_in_db}).")
                            # Можно добавить логику обновления `internal_sku` или `name` если они изменились в CSV
                        else:
                            cur.execute(
                                """
                                INSERT INTO products (name, url, internal_sku, is_active)
                                VALUES (%s, %s, %s, %s) RETURNING id; 
                                """,
                                (product_name_from_csv, url, internal_sku, True)
                            )
                            product_id_in_db = cur.fetchone()[0]
                            products_imported_count += 1
                            logger.debug(
                                f"Строка {row_num}: Добавлен товар: Name='{product_name_from_csv}', SKU='{internal_sku}', URL='{url}', New DB ID={product_id_in_db}")

                        # 2. Импортируем историю остатков для этого товара
                        if product_id_in_db and any(history_timestamps):
                            for i, stock_value_str in enumerate(row[history_start_col_idx:]):
                                if i < len(history_timestamps) and history_timestamps[i] is not None:
                                    check_ts = history_timestamps[i]
                                    try:
                                        stock_level = int(stock_value_str.strip())

                                        # Проверяем, нет ли уже такой записи для этого product_id и timestamp
                                        # Это важно, чтобы не дублировать историю при повторном запуске импорта
                                        cur.execute(
                                            "SELECT id FROM stock_history WHERE product_id = %s AND check_timestamp = %s",
                                            (product_id_in_db, check_ts)
                                        )
                                        if cur.fetchone():
                                            logger.debug(
                                                f"История для product_id={product_id_in_db} и timestamp={check_ts} уже существует. Пропуск.")
                                            stock_history_skipped_count += 1
                                            continue

                                        cur.execute(
                                            """
                                            INSERT INTO stock_history (product_id, check_timestamp, stock_level, raw_text, status)
                                            VALUES (%s, %s, %s, %s, %s)
                                            """,
                                            (product_id_in_db, check_ts, stock_level, stock_value_str.strip(),
                                             'imported_from_csv')
                                        )
                                        stock_history_imported_count += 1
                                    except ValueError:
                                        logger.warning(
                                            f"Строка {row_num}, колонка истории {i + history_start_col_idx + 1}: Не удалось преобразовать остаток '{stock_value_str}' в число. Пропуск этой записи истории.")
                                        stock_history_skipped_count += 1
                                    except psycopg2.Error as e_hist:
                                        logger.error(
                                            f"Строка {row_num}: Ошибка psycopg2 при добавлении истории для product_id={product_id_in_db}, ts={check_ts}: {e_hist}")
                                        conn.rollback()  # Откатываем только эту вставку истории, если нужно
                                        stock_history_skipped_count += 1
                                else:
                                    if i >= len(history_timestamps):  # Больше данных об остатках, чем распарсенных дат
                                        logger.warning(
                                            f"Строка {row_num}: Значение остатка '{stock_value_str}' без соответствующей даты в заголовке. Пропуск.")
                                    # Если history_timestamps[i] is None, значит дата не распарсилась - уже залогировано

                    except psycopg2.Error as e_prod:
                        logger.error(
                            f"Строка {row_num}: Ошибка psycopg2 при обработке товара SKU='{internal_sku}', URL='{url}': {e_prod}")
                        conn.rollback()
                        products_skipped_count += 1
                    except Exception as e_gen:
                        logger.error(
                            f"Строка {row_num}: Неожиданная ошибка при обработке SKU='{internal_sku}', URL='{url}': {e_gen}",
                            exc_info=True)
                        products_skipped_count += 1

                conn.commit()  # Фиксируем все изменения после обработки файла
        logger.info(
            f"Импорт завершен. Товаров добавлено: {products_imported_count}, Товаров пропущено/существовало: {products_skipped_count}")
        logger.info(
            f"Записей истории остатков добавлено: {stock_history_imported_count}, Записей истории пропущено: {stock_history_skipped_count}")

    except FileNotFoundError:
        logger.error(f"Файл CSV не найден: {csv_filepath}")
    except Exception as e:
        logger.error(f"Общая ошибка при импорте CSV: {e}", exc_info=True)
        if conn:
            conn.rollback()


if __name__ == "__main__":
    logger.info("Запуск скрипта импорта CSV (включая историю остатков) в БД PostgreSQL.")

    try:
        app_conf = config_loader.load_app_config()
    except SystemExit:
        logger.critical("Не удалось загрузить конфигурацию. Скрипт импорта не может продолжить.")
        sys.exit(1)

    # Путь к CSV файлу (ожидается рядом со скриптом import_csv_to_db.py)
    csv_file_to_import = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'products_data.csv')

    # Формат даты и времени в заголовках колонок CSV с историей остатков
    # Пример: '22-11-2024 15:09:34' -> '%d-%m-%Y %H:%M:%S'
    # ВАЖНО: Этот формат должен точно соответствовать вашему CSV!
    csv_header_date_format = '%d-%m-%Y %H:%M:%S'  # Возьмем из вашего лога
    # Если формат в .env, то: app_conf.get('csv_header_date_format', '%d-%m-%Y %H:%M:%S')

    connection = None
    try:
        connection = get_db_connection(app_conf)
        if connection:
            import_data_from_csv(connection, csv_file_to_import, csv_header_date_format)
    except ConnectionError:
        logger.error("Не удалось установить соединение с БД. Импорт прерван.")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка во время выполнения скрипта импорта: {e}", exc_info=True)
    finally:
        if connection:
            connection.close()
            logger.info("Соединение с PostgreSQL закрыто.")
    logger.info("Скрипт импорта CSV (с историей) завершил работу.")