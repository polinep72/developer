# --- START OF FILE conference_room_service.py ---

# conference_room_service.py
# (Переименовано из equipment_service.py)

from database import Database, QueryResult
from logger import logger
from typing import List, Tuple, Optional, Dict, Any
import logging
import constants as const # Используем обновленные константы

# Тип для аннотации строк с данными о комнате
ConferenceRoomRow = Dict[str, Any]


def get_all_conference_rooms(db: Database) -> List[ConferenceRoomRow]:
    """Получает все переговорные комнаты.

    Args:
        db: Объект базы данных

    Returns:
        List[ConferenceRoomRow]: Список комнат или пустой список при ошибке
    """
    # Запрос к таблице conferenceroom
    query = "SELECT id, cr_name, cr_note FROM conferenceroom ORDER BY cr_name ASC;"
    try:
        result = db.execute_query(query, fetch_results=True)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.error(f"Ошибка при получении всех переговорных комнат: {e}", exc_info=True)
        return []


def get_conference_room_info_by_id(db: Database, cr_id: int) -> Optional[ConferenceRoomRow]:
    """Получает полную информацию о переговорной комнате по ID.

    Args:
        db: Объект базы данных
        cr_id: ID переговорной комнаты

    Returns:
        Optional[ConferenceRoomRow]: Словарь с данными комнаты или None при ошибке/отсутствии
    """
    # Запрос к таблице conferenceroom
    query = """
        SELECT id, cr_name, cr_note
        FROM conferenceroom
        WHERE id = %s;
    """
    try:
        result = db.execute_query(query, (cr_id,), fetch_results=True)
        if result and isinstance(result, list) and len(result) > 0:
            return result[0]
        logger.debug(f"Переговорная комната с ID {cr_id} не найдена.")
        return None
    except Exception as e:
        logger.error(
            f"Ошибка при получении информации о комнате ID {cr_id}: {e}",
            exc_info=True
        )
        return None


def get_conference_room_name_by_id(db: Database, cr_id: int) -> Optional[str]:
    """Получает название переговорной комнаты по ID.

    Args:
        db: Объект базы данных
        cr_id: ID переговорной комнаты

    Returns:
        Optional[str]: Название комнаты или None при ошибке/отсутствии
    """
    info = get_conference_room_info_by_id(db, cr_id)
    # Получаем 'cr_name' из словаря
    return info.get('cr_name') if info else None


def check_conference_room_exists(db: Database, name: str) -> bool:
    """Проверяет существование переговорной комнаты по названию.

    Args:
        db: Объект базы данных
        name: Название комнаты

    Returns:
        bool: True если комната существует, False если нет или ошибка
    """
    query = "SELECT 1 FROM conferenceroom WHERE cr_name = %s LIMIT 1;"
    try:
        result = db.execute_query(query, (name.strip(),), fetch_results=True)
        return bool(result)
    except Exception as e:
        logger.error(
            f"Ошибка при проверке существования комнаты '{name}': {e}",
            exc_info=True
        )
        # В случае ошибки считаем, что проверить не удалось (лучше не добавлять дубликат)
        return True


def add_conference_room(db: Database, name: str, note: Optional[str] = None) -> Tuple[bool, str]:
    """Добавляет новую переговорную комнату."""
    # Валидация имени
    if not name or not name.strip():
        return False, "Название переговорной комнаты не может быть пустым."

    processed_name = name.strip()
    processed_note = note.strip() if isinstance(note, str) else note

    # 1. Проверка на существование (по имени)
    try:
        if check_conference_room_exists(db, processed_name):
            return False, const.MSG_CR_ADD_FAIL_EXISTS.format(cr_name=f"'{processed_name}'")
    except Exception as e_check:
        logger.error(f"Ошибка проверки существования комнаты '{processed_name}': {e_check}", exc_info=True)
        # Не можем продолжить без проверки, возвращаем ошибку
        return False, "Ошибка проверки существования комнаты."


    # 2. Добавление новой комнаты
    # --- ИЗМЕНЕНИЕ: Добавляем is_active в запрос и TRUE в параметры ---
    query = """
        INSERT INTO conferenceroom (cr_name, cr_note, is_active)
        VALUES (%s, %s, %s)
        RETURNING id;
    """
    try:
        # Передаем TRUE для is_active по умолчанию
        result = db.execute_query(query, (processed_name, processed_note, True), fetch_results=True, commit=True)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        if result and isinstance(result, list) and len(result) > 0 and 'id' in result[0]:
            new_id = result[0].get('id')
            logger.info(f"Успешно добавлена комната '{processed_name}' с ID {new_id} (is_active=True).")
            success_msg = const.MSG_CR_ADD_SUCCESS.format(cr_name=f"'{processed_name}'")
            return True, success_msg
        else:
            logger.error(f"Не удалось получить ID после добавления комнаты '{processed_name}'. Результат: {result}")
            fail_msg = const.MSG_CR_ADD_FAIL.format(cr_name=f"'{processed_name}'")
            return False, fail_msg + " (ошибка записи в БД)"

    except Exception as e:
        logger.error(f"Ошибка при добавлении комнаты '{processed_name}': {e}", exc_info=True)
        fail_msg = const.MSG_CR_ADD_FAIL.format(cr_name=f"'{processed_name}'")
        # Проверка на ошибку уникальности (на случай гонки потоков)
        if isinstance(e, psycopg2.errors.UniqueViolation) or "unique constraint" in str(e).lower():
            return False, const.MSG_CR_ADD_FAIL_EXISTS.format(cr_name=f"'{processed_name}'")
        # Проверка на NotNullViolation (если вдруг еще какая-то колонка NOT NULL)
        elif isinstance(e, psycopg2.errors.NotNullViolation):
            return False, fail_msg + f" (отсутствует значение для обязательного поля: {e})"
        return False, fail_msg + " (внутренняя ошибка)"


def check_conference_room_usage(db: Database, cr_id: int) -> bool:
    """Проверяет использование комнаты в активных или будущих бронированиях."""
    # --- ИЗМЕНЕНИЕ: Заменяем CURRENT_TIME на NOW() ---
    query = """
        SELECT 1 FROM bookings
        WHERE cr_id = %s
          AND status IN ('pending_confirmation', 'confirmed', 'active')
          AND time_end > NOW() -- Проверяем, что время окончания еще не наступило
        LIMIT 1;
    """
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    try:
        result = db.execute_query(query, (cr_id,), fetch_results=True)
        usage = bool(result)
        logger.info(f"Комната ID {cr_id} {'имеет активные/будущие бронирования' if usage else 'не используется в активных/будущих бронированиях'}")
        return usage
    except Exception as e:
        logger.error(
            f"Ошибка при проверке использования комнаты ID {cr_id}: {e}",
            exc_info=True
        )
        # В случае ошибки лучше считать, что используется, чтобы не удалить случайно
        return True


def delete_conference_room_if_unused(db: Database, cr_id: int) -> Tuple[bool, str]:
    """Удаляет неиспользуемую переговорную комнату.

    Args:
        db: Объект базы данных
        cr_id: ID комнаты

    Returns:
        Tuple[bool, str]: (Успех, Сообщение)
    """
    conn = None
    try:
        # Получаем соединение для управления транзакцией
        conn = db.get_connection()
        conn.autocommit = False # Управляем транзакцией вручную
        logger.debug(f"delete_conference_room_if_unused: Начало транзакции для удаления ID {cr_id}")

        # 1. Проверка использования (через основной объект db)
        logger.debug(f"delete_conference_room_if_unused: Проверка использования ID {cr_id} через check_conference_room_usage(db, ...)")
        if check_conference_room_usage(db, cr_id):
            name = get_conference_room_name_by_id(db, cr_id) or f"ID {cr_id}"
            logger.warning(f"delete_conference_room_if_unused: Попытка удаления используемой комнаты ID {cr_id} ('{name}')")
            # Используем константу для сообщения
            return False, const.MSG_CR_DELETE_FAIL_USED.format(cr_name=f"'{name}'")
        logger.debug(f"delete_conference_room_if_unused: Комната ID {cr_id} не используется в активных/будущих бронированиях.")

        # 2. Получение имени для сообщения об успехе (через основной объект db)
        cr_info = get_conference_room_info_by_id(db, cr_id)
        if not cr_info:
            logger.warning(f"delete_conference_room_if_unused: Комната ID {cr_id} не найдена перед удалением.")
            # Используем константу для сообщения
            return False, const.MSG_CR_DELETE_FAIL_NOT_FOUND
        name = cr_info.get('cr_name', f"ID {cr_id}")
        logger.debug(f"delete_conference_room_if_unused: Получено имя для сообщения: '{name}'")

        # 3. Удаление комнаты (внутри транзакции на соединении conn)
        query_delete = "DELETE FROM conferenceroom WHERE id = %s;"
        logger.debug(f"delete_conference_room_if_unused: Выполнение DELETE для conferenceroom ID {cr_id}...")
        rows_affected = 0
        with conn.cursor() as cursor:
            cursor.execute(query_delete, (cr_id,))
            rows_affected = cursor.rowcount # Получаем количество удаленных строк
            logger.debug(f"delete_conference_room_if_unused: DELETE conferenceroom выполнен. Rows affected: {rows_affected}")

        # 4. Проверка, была ли комната действительно удалена
        if rows_affected == 0:
            logger.warning(f"delete_conference_room_if_unused: DELETE запрос для ID {cr_id} не затронул ни одной строки (возможно, уже удалена). Откат.")
            conn.rollback() # Откатываем, т.к. комната не найдена на этапе удаления
            # Используем константу для сообщения
            return False, const.MSG_CR_DELETE_FAIL_NOT_FOUND

        # 5. Коммит транзакции
        logger.debug(f"delete_conference_room_if_unused: Коммит транзакции для удаления ID {cr_id}")
        conn.commit()
        logger.info(f"delete_conference_room_if_unused: Комната ID {cr_id} ('{name}') успешно удалена.")
        # Используем константу для сообщения об успехе
        success_msg = const.MSG_CR_DELETE_SUCCESS.format(cr_name=f"'{name}'")
        return True, success_msg

    except Exception as e:
        # Откат транзакции в случае любой ошибки
        if conn:
            logger.error(f"delete_conference_room_if_unused: Ошибка в транзакции удаления ID {cr_id}, откат. Ошибка: {e}", exc_info=True)
            try:
                conn.rollback()
                logger.info(f"delete_conference_room_if_unused: Транзакция для ID {cr_id} отменена из-за ошибки.")
            except Exception as e_rollback:
                 logger.error(f"delete_conference_room_if_unused: Ошибка при откате транзакции для ID {cr_id}: {e_rollback}")
        else:
             logger.error(f"delete_conference_room_if_unused: Ошибка до получения соединения для ID {cr_id}: {e}", exc_info=True)
        # Используем общую константу ошибки БД
        return False, const.MSG_CR_DELETE_FAIL_DB
    finally:
        # Гарантированное возвращение соединения в пул
        if conn:
            try:
                # Важно вернуть autocommit в True (или значение по умолчанию для пула)
                conn.autocommit = True
            except Exception as e_autocommit:
                 logger.error(f"delete_conference_room_if_unused: Не удалось включить autocommit для соединения перед возвратом в пул: {e_autocommit}")
            db.release_connection(conn)
            logger.debug(f"delete_conference_room_if_unused: Соединение возвращено в пул после операции с ID {cr_id}")

# --- END OF FILE conference_room_service.py ---