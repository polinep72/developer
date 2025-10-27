# --- START OF FILE equipment_service.py ---

from database import Database, QueryResult
from logger import logger
from typing import List, Tuple, Optional, Dict, Any
import logging
import constants as const

# Типы для аннотаций
EquipmentRow = Dict[str, Any]
CategoryRow = Dict[str, Any]


def category_exists(db: Database, category_id: int) -> bool:
    """Проверяет существование категории по ID.

    Args:
        db: Объект базы данных
        category_id: ID проверяемой категории

    Returns:
        bool: True если категория существует, False если нет или произошла ошибка
    """
    query = "SELECT 1 FROM cat WHERE id = %s LIMIT 1;"
    try:
        result = db.execute_query(query, (category_id,), fetch_results=True)
        return bool(result)
    except Exception as e:
        logger.error(f"Ошибка проверки категории ID {category_id}: {e}", exc_info=True)
        return False


def get_all_categories(db: Database) -> List[CategoryRow]:
    """Получает все категории оборудования.

    Args:
        db: Объект базы данных

    Returns:
        List[CategoryRow]: Список категорий или пустой список при ошибке
    """
    query = "SELECT id, name_cat FROM cat ORDER BY name_cat ASC;"
    try:
        result = db.execute_query(query, fetch_results=True)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error(f"Ошибка при получении всех категорий: {e}", exc_info=True)
        return []


def get_equipment_by_category(db: Database, category_id: int) -> List[EquipmentRow]:
    """Получает оборудование по ID категории.

    Args:
        db: Объект базы данных
        category_id: ID категории

    Returns:
        List[EquipmentRow]: Список оборудования или пустой список при ошибке
    """
    query = """
        SELECT id, name_equip, note 
        FROM equipment 
        WHERE category = %s 
        ORDER BY name_equip ASC;
    """
    try:
        result = db.execute_query(query, (category_id,), fetch_results=True)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error(
            f"Ошибка при получении оборудования для категории ID={category_id}: {e}",
            exc_info=True
        )
        return []


def get_all_equipment(db: Database) -> List[EquipmentRow]:
    """Получает все оборудование.

    Args:
        db: Объект базы данных

    Returns:
        List[EquipmentRow]: Список всего оборудования или пустой список при ошибке
    """
    query = "SELECT id, name_equip, category, note FROM equipment ORDER BY name_equip ASC;"
    try:
        result = db.execute_query(query, fetch_results=True)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error(f"Ошибка при получении всего оборудования: {e}", exc_info=True)
        return []


def get_equipment_info_by_id(db: Database, equipment_id: int) -> Optional[EquipmentRow]:
    """Получает полную информацию об оборудовании по ID.

    Args:
        db: Объект базы данных
        equipment_id: ID оборудования

    Returns:
        Optional[EquipmentRow]: Словарь с данными оборудования или None при ошибке
    """
    query = """
        SELECT id, name_equip, category, note 
        FROM equipment 
        WHERE id = %s;
    """
    try:
        result = db.execute_query(query, (equipment_id,), fetch_results=True)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        logger.warning(f"Оборудование с ID {equipment_id} не найдено.")
        return None
    except Exception as e:
        logger.error(
            f"Ошибка при получении информации об оборудовании ID {equipment_id}: {e}",
            exc_info=True
        )
        return None


def get_equipment_name_by_id(db: Database, equipment_id: int) -> Optional[str]:
    """Получает название оборудования по ID.

    Args:
        db: Объект базы данных
        equipment_id: ID оборудования

    Returns:
        Optional[str]: Название оборудования или None при ошибке
    """
    info = get_equipment_info_by_id(db, equipment_id)
    return info.get('name_equip') if info else None


def get_category_name_by_id(db: Database, category_id: int) -> Optional[str]:
    """Получает название категории по ID.

    Args:
        db: Объект базы данных
        category_id: ID категории

    Returns:
        Optional[str]: Название категории или None при ошибке
    """
    query = "SELECT name_cat FROM cat WHERE id = %s;"
    try:
        result = db.execute_query(query, (category_id,), fetch_results=True)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get('name_cat')
        return None
    except Exception as e:
        logger.error(
            f"Ошибка при получении имени категории ID {category_id}: {e}",
            exc_info=True
        )
        return None


def check_equipment_exists(
        db: Database,
        category_id: int,
        name: str,
        note: Optional[str] = None
) -> bool:
    """Проверяет существование оборудования в категории.

    Args:
        db: Объект базы данных
        category_id: ID категории
        name: Название оборудования
        note: Примечание (опционально)

    Returns:
        bool: True если оборудование существует, False если нет или ошибка
    """
    query = """
        SELECT 1 FROM equipment 
        WHERE category = %s AND name_equip = %s
    """
    params = [category_id, name.strip()]

    if note is not None:
        query += " AND note = %s"
        params.append(note.strip())

    query += " LIMIT 1;"

    try:
        result = db.execute_query(query, tuple(params), fetch_results=True)
        return bool(result)
    except Exception as e:
        logger.error(
            f"Ошибка при проверке существования оборудования '{name}' в категории ID={category_id}: {e}",
            exc_info=True
        )
        return True


def find_or_create_category(db: Database, category_name: str) -> Optional[int]:
    """Находит или создает категорию оборудования.

    Args:
        db: Объект базы данных
        category_name: Название категории

    Returns:
        Optional[int]: ID категории или None при ошибке
    """
    if not category_name or not category_name.strip():
        logger.warning("Пустое имя категории в find_or_create_category")
        return None

    name = category_name.strip()
    query_find = "SELECT id FROM cat WHERE name_cat = %s;"

    try:
        # Поиск существующей категории
        result = db.execute_query(query_find, (name,), fetch_results=True)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get('id')

        # Создание новой категории
        query_insert = "INSERT INTO cat (name_cat) VALUES (%s) RETURNING id;"
        result = db.execute_query(query_insert, (name,), fetch_results=True, commit=True)

        if result and isinstance(result, list) and len(result) > 0:
            return result[0].get('id')
        return None
    except Exception as e:
        logger.error(
            f"Исключение при поиске/создании категории '{name}': {e}",
            exc_info=True
        )
        return None


def add_equipment(
        db: Database,
        category_id: int,
        name: str,
        note: Optional[str] = None # Изменяем значение по умолчанию на None
) -> Tuple[bool, str]:
    """Добавляет новое оборудование.

    Args:
        db: Объект базы данных
        category_id: ID категории
        name: Название оборудования
        note: Примечание (опционально, None если пропущено)

    Returns:
        Tuple[bool, str]: (Успех, Сообщение)
    """
    # Валидация имени оборудования
    if not name or not name.strip():
        return False, "Название оборудования не может быть пустым"

    # Проверка существования категории
    if not category_exists(db, category_id):
        return False, f"Категория ID {category_id} не существует"

    name = name.strip()
    # Обрабатываем примечание: вызываем strip() только если note - это строка, иначе оставляем None
    processed_note = note.strip() if isinstance(note, str) else note

    query = """
        INSERT INTO equipment (category, name_equip, note)
        VALUES (%s, %s, %s)
        RETURNING id;
    """
    try:
        # Передаем обработанное примечание (может быть None или строка без пробелов по краям)
        result = db.execute_query(query, (category_id, name, processed_note), fetch_results=True, commit=True)

        if result and isinstance(result, list) and len(result) > 0:
            # Получаем имя категории для красивого сообщения об успехе
            category_name = get_category_name_by_id(db, category_id) or f"ID {category_id}"
            # Используем константу для сообщения
            success_msg = const.MSG_EQUIP_ADD_SUCCESS.format(
                equipment_name=f"'{name}'",
                category_name=f"'{category_name}'"
            )
            return True, success_msg
        else:
            # Если INSERT не вернул ID (маловероятно при успехе, но возможно)
            logger.error(f"Не удалось получить ID после добавления оборудования '{name}' в категорию {category_id}.")
            # Используем константу для сообщения об ошибке
            fail_msg = const.MSG_EQUIP_ADD_FAIL.format(equipment_name=f"'{name}'")
            return False, fail_msg + " (ошибка записи в БД)"

    except Exception as e:
        # Ловим другие возможные ошибки БД (например, дубликат при гонке потоков, хотя проверка есть раньше)
        logger.error(
            f"Ошибка при добавлении оборудования '{name}' в категорию {category_id}: {e}",
            exc_info=True
        )
        # Используем константу для сообщения об ошибке
        fail_msg = const.MSG_EQUIP_ADD_FAIL.format(equipment_name=f"'{name}'")
        return False, fail_msg + " (внутренняя ошибка)"


def check_equipment_usage(db: Database, equipment_id: int) -> bool:
    """Проверяет использование оборудования в бронированиях.

    Args:
        db: Объект базы данных
        equipment_id: ID оборудования

    Returns:
        bool: True если оборудование используется, False если нет или ошибка
    """
    query = "SELECT 1 FROM bookings WHERE equip_id = %s LIMIT 1;"
    try:
        result = db.execute_query(query, (equipment_id,), fetch_results=True)
        usage = bool(result)
        logger.info(f"Оборудование ID {equipment_id} {'используется' if usage else 'не используется'}")
        return usage
    except Exception as e:
        logger.error(
            f"Ошибка при проверке использования оборудования ID {equipment_id}: {e}",
            exc_info=True
        )
        return True


def delete_equipment_if_unused(db: Database, equipment_id: int) -> Tuple[bool, str]:
    """Удаляет неиспользуемое оборудование и пустые категории.

    Args:
        db: Объект базы данных (ВАШ КЛАСС Database)
        equipment_id: ID оборудования

    Returns:
        Tuple[bool, str]: (Успех, Сообщение)
    """
    conn = None # Инициализируем переменную для соединения
    try:
        # Получаем сырое соединение для управления транзакцией
        conn = db.get_connection()
        # Отключаем автокоммит для транзакции
        conn.autocommit = False
        logger.debug(f"delete_equipment_if_unused: Начало транзакции для удаления ID {equipment_id}")

        # --- ИСПРАВЛЕНИЕ: Передаем 'db', а не 'conn' ---
        # Проверка использования (используем объект db для вызова execute_query)
        logger.debug(f"delete_equipment_if_unused: Проверка использования ID {equipment_id} через check_equipment_usage(db, ...)")
        if check_equipment_usage(db, equipment_id): # <--- ИСПРАВЛЕНО
            # Получаем имя для сообщения об ошибке (тоже через db)
            name = get_equipment_name_by_id(db, equipment_id) or f"ID {equipment_id}" # <--- ИСПРАВЛЕНО
            logger.warning(f"delete_equipment_if_unused: Попытка удаления используемого оборудования ID {equipment_id} ('{name}')")
            return False, const.MSG_EQUIP_DELETE_FAIL_USED.format(equipment_name=f"'{name}'")
        logger.debug(f"delete_equipment_if_unused: Оборудование ID {equipment_id} не используется.")

        # --- ИСПРАВЛЕНИЕ: Передаем 'db', а не 'conn' ---
        # Получение информации об оборудовании (используем объект db)
        logger.debug(f"delete_equipment_if_unused: Получение информации об ID {equipment_id} через get_equipment_info_by_id(db, ...)")
        equip_info = get_equipment_info_by_id(db, equipment_id) # <--- ИСПРАВЛЕНО
        if not equip_info:
            logger.warning(f"delete_equipment_if_unused: Оборудование ID {equipment_id} не найдено.")
            return False, const.MSG_EQUIP_DELETE_FAIL_NOT_FOUND

        name = equip_info.get('name_equip', f"ID {equipment_id}")
        category_id = equip_info.get('category')
        logger.debug(f"delete_equipment_if_unused: Получена информация: name='{name}', category_id={category_id}")

        # Удаление оборудования (используем сырой курсор из conn для транзакции)
        query_delete = "DELETE FROM equipment WHERE id = %s;"
        logger.debug(f"delete_equipment_if_unused: Выполнение DELETE для equipment ID {equipment_id}...")
        with conn.cursor() as cursor: # Используем курсор для выполнения
             cursor.execute(query_delete, (equipment_id,))
             logger.debug(f"delete_equipment_if_unused: DELETE equipment выполнен. Rows affected: {cursor.rowcount}")

        # Проверка и удаление пустой категории (используем сырой курсор из conn)
        category_msg = ""
        if category_id:
            logger.debug(f"delete_equipment_if_unused: Проверка категории ID {category_id} на пустоту...")
            query_check = "SELECT 1 FROM equipment WHERE category = %s LIMIT 1;"
            is_category_empty = False
            with conn.cursor() as cursor:
                cursor.execute(query_check, (category_id,))
                is_category_empty = cursor.fetchone() is None # Пустая, если fetchone вернул None
                logger.debug(f"delete_equipment_if_unused: Категория ID {category_id} {'пустая' if is_category_empty else 'не пустая'}.")

            if is_category_empty:
                query_delete_cat = "DELETE FROM cat WHERE id = %s;"
                logger.debug(f"delete_equipment_if_unused: Выполнение DELETE для пустой категории ID {category_id}...")
                with conn.cursor() as cursor:
                     cursor.execute(query_delete_cat, (category_id,))
                     logger.debug(f"delete_equipment_if_unused: DELETE cat выполнен. Rows affected: {cursor.rowcount}")
                category_msg = " и его пустая категория"

        # Если все успешно, коммитим транзакцию
        logger.debug(f"delete_equipment_if_unused: Коммит транзакции для удаления ID {equipment_id}")
        conn.commit()
        logger.info(f"delete_equipment_if_unused: Оборудование ID {equipment_id} ('{name}') и категория (если пустая) успешно удалены.")
        # Формируем сообщение об успехе
        success_msg = const.MSG_EQUIP_DELETE_SUCCESS.replace('{equipment_name}', f"'{name}'") + category_msg
        return True, success_msg

    except Exception as e:
        # Если произошла ошибка, откатываем транзакцию
        if conn:
            logger.error(f"delete_equipment_if_unused: Ошибка в транзакции удаления ID {equipment_id}, откат. Ошибка: {e}", exc_info=True)
            try:
                conn.rollback()
                logger.info(f"delete_equipment_if_unused: Транзакция для ID {equipment_id} отменена.")
            except Exception as e_rollback:
                 logger.error(f"delete_equipment_if_unused: Ошибка при откате транзакции для ID {equipment_id}: {e_rollback}")
        else:
             logger.error(f"delete_equipment_if_unused: Ошибка до получения соединения для ID {equipment_id}: {e}", exc_info=True)
        # Возвращаем сообщение об ошибке
        return False, const.MSG_EQUIP_DELETE_FAIL_DB
    finally:
        # Всегда возвращаем соединение в пул
        if conn:
            # Важно вернуть autocommit в True перед возвратом в пул
            try:
                conn.autocommit = True
            except Exception as e_autocommit:
                 logger.error(f"delete_equipment_if_unused: Не удалось включить autocommit для соединения перед возвратом в пул: {e_autocommit}")
            db.release_connection(conn)
            logger.debug(f"delete_equipment_if_unused: Соединение возвращено в пул после операции с ID {equipment_id}")

# --- START OF NEW FUNCTION to add in equipment_service.py ---

def add_category(db: Database, category_name: str) -> Optional[int]:
    """
    Добавляет новую категорию оборудования, если она еще не существует.

    Args:
        db: Объект базы данных
        category_name: Название новой категории

    Returns:
        Optional[int]: ID новой категории в случае успеха, None если категория
                       уже существует или произошла ошибка.
    """
    # Проверка на пустое имя
    if not category_name or not category_name.strip():
        logger.warning("Попытка добавить категорию с пустым именем.")
        return None

    name = category_name.strip()

    # 1. Проверка на существование
    query_find = "SELECT id FROM cat WHERE name_cat = %s LIMIT 1;"
    try:
        existing = db.execute_query(query_find, (name,), fetch_results=True)
        # Если категория уже существует
        if existing and isinstance(existing, list) and len(existing) > 0:
            logger.warning(f"Попытка добавить существующую категорию: '{name}'")
            return None # Возвращаем None, чтобы указать на дубликат
    except Exception as e_find:
        logger.error(
            f"Ошибка при проверке существования категории '{name}': {e_find}",
            exc_info=True
        )
        # В случае ошибки проверки считаем, что добавить не можем
        return None

    # 2. Добавление новой категории
    query_insert = "INSERT INTO cat (name_cat) VALUES (%s) RETURNING id;"
    try:
        result = db.execute_query(query_insert, (name,), fetch_results=True, commit=True)
        # Проверяем результат вставки
        if result and isinstance(result, list) and len(result) > 0:
            new_id = result[0].get('id')
            logger.info(f"Успешно добавлена новая категория '{name}' с ID: {new_id}")
            return new_id
        else:
            # Если RETURNING id не вернул результат (маловероятно при успехе)
            logger.error(f"Не удалось получить ID после добавления категории '{name}'.")
            return None
    except Exception as e_insert:
        # Обработка возможных ошибок БД (например, UNIQUE constraint violation при гонке потоков)
        logger.error(
            f"Ошибка при добавлении новой категории '{name}': {e_insert}",
            exc_info=True
        )
        return None

# --- END OF NEW FUNCTION ---
# --- END OF FILE equipment_service.py ---