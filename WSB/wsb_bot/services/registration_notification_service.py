# --- START OF FILE services/registration_notification_service.py (WSB - адаптированный) ---
"""
Сервис для управления записями об уведомлениях администраторов при регистрации новых пользователей.
Использует global_db_connection.
"""

from typing import List, Dict, Any

# --- Импортируем глобальные объекты из bot_app ---
from bot_app import db_connection as global_db_connection
# --- КОНЕЦ ИМПОРТОВ ГЛОБАЛЬНЫХ ОБЪЕКТОВ ---

from database import QueryResult # DatabaseTypeHint не нужен
from logger import logger


def add_admin_reg_notification(temp_user_id: int, admin_id: int, chat_id: int, message_id: int) -> bool:
    """Добавляет запись об отправленном уведомлении админу в таблицу admin_registration_notifications."""
    query = """
        INSERT INTO admin_registration_notifications
        (temp_user_id, admin_user_id, chat_id, message_id)
        VALUES (%s, %s, %s, %s);
    """
    try:
        global_db_connection.execute_query(query, (temp_user_id, admin_id, chat_id, message_id), commit=True)
        logger.debug(f"Запись уведомления для temp_user={temp_user_id}, admin={admin_id}, msg={message_id} добавлена.")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления записи уведомления админу {admin_id} для {temp_user_id}: {e}", exc_info=True)
        return False

def get_admin_reg_notifications(temp_user_id: int) -> List[Dict[str, Any]]:
    """Получает все записи уведомлений (admin_user_id, chat_id, message_id) для конкретной заявки."""
    query = """
        SELECT admin_user_id, chat_id, message_id
        FROM admin_registration_notifications
        WHERE temp_user_id = %s;
    """
    try:
        result: QueryResult = global_db_connection.execute_query(query, (temp_user_id,), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка получения записей уведомлений для {temp_user_id}: {e}", exc_info=True)
        return []

def delete_admin_reg_notifications(temp_user_id: int) -> bool:
    """Удаляет все записи уведомлений для конкретной заявки из admin_registration_notifications."""
    query = "DELETE FROM admin_registration_notifications WHERE temp_user_id = %s;"
    try:
        rows_affected = global_db_connection.execute_query(query, (temp_user_id,), commit=True, fetch_results=False)
        logger.debug(f"Записи уведомлений для temp_user={temp_user_id} удалены (затронуто строк: {rows_affected}).")
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления записей уведомлений для {temp_user_id}: {e}", exc_info=True)
        return False

# --- END OF FILE services/registration_notification_service.py (WSB - адаптированный) ---