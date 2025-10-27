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
        note: str = ""
) -> Tuple[bool, str]:
    """Добавляет новое оборудование.

    Args:
        db: Объект базы данных
        category_id: ID категории
        name: Название оборудования
        note: Примечание (по умолчанию пустая строка)

    Returns:
        Tuple[bool, str]: (Успех, Сообщение)
    """
    if not name or not name.strip():
        return False, "Название оборудования не может быть пустым"

    if not category_exists(db, category_id):
        return False, f"Категория ID {category_id} не существует"

    name = name.strip()
    note = note.strip()

    query = """
        INSERT INTO equipment (category, name_equip, note) 
        VALUES (%s, %s, %s) 
        RETURNING id;
    """
    try:
        result = db.execute_query(query, (category_id, name, note), fetch_results=True, commit=True)

        if result and isinstance(result, list) and len(result) > 0:
            return True, f"Оборудование '{name}' успешно добавлено"
        return False, "Ошибка при добавлении оборудования"
    except Exception as e:
        logger.error(
            f"Ошибка при добавлении оборудования '{name}': {e}",
            exc_info=True
        )
        return False, "Внутренняя ошибка при добавлении оборудования"


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
        db: Объект базы данных
        equipment_id: ID оборудования

    Returns:
        Tuple[bool, str]: (Успех, Сообщение)
    """
    conn = None
    try:
        conn = db.get_connection()
        conn.autocommit = False

        # Проверка использования
        if check_equipment_usage(conn, equipment_id):
            name = get_equipment_name_by_id(conn, equipment_id) or f"ID {equipment_id}"
            return False, const.MSG_EQUIP_DELETE_FAIL_USED.replace('{equipment_name}', f"'{name}'")

        # Получение информации об оборудовании
        equip_info = get_equipment_info_by_id(conn, equipment_id)
        if not equip_info:
            return False, const.MSG_EQUIP_DELETE_FAIL_NOT_FOUND

        name = equip_info.get('name_equip', f"ID {equipment_id}")
        category_id = equip_info.get('category')

        # Удаление оборудования
        query_delete = "DELETE FROM equipment WHERE id = %s;"
        conn.execute(query_delete, (equipment_id,))

        # Проверка и удаление пустой категории
        category_msg = ""
        if category_id:
            query_check = "SELECT 1 FROM equipment WHERE category = %s LIMIT 1;"
            conn.execute(query_check, (category_id,))
            if not conn.fetchone():
                query_delete_cat = "DELETE FROM cat WHERE id = %s;"
                conn.execute(query_delete_cat, (category_id,))
                category_msg = " и его пустая категория"

        conn.commit()
        return True, (
                const.MSG_EQUIP_DELETE_SUCCESS.replace('{equipment_name}', f"'{name}'") +
                category_msg
        )
    except Exception as e:
        if conn: conn.rollback()
        logger.error(
            f"Ошибка при удалении оборудования ID {equipment_id}: {e}",
            exc_info=True
        )
        return False, const.MSG_EQUIP_DELETE_FAIL_DB
    finally:
        if conn:
            conn.autocommit = True
            db.release_connection(conn)

# --- END OF FILE equipment_service.py ---