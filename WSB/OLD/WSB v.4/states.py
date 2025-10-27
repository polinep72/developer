# --- START OF FILE states.py ---

# states.py
"""
Модуль для хранения и управления состояниями пользователей и админов.
Используется для отслеживания многошаговых процессов (бронирование, добавление оборудования).
"""

from typing import Dict, Any
from logger import logger

# --- Состояния Пользователей ---

# Словарь для хранения состояний процессов бронирования пользователей
# Ключ - user_id, Значение - словарь с состоянием {'step': ..., 'data': {...}, 'message_id': ...}
user_booking_states: Dict[int, Dict[str, Any]] = {}

def clear_user_state(user_id: int):
    """Безопасно удаляет состояние процесса бронирования пользователя."""
    if user_id in user_booking_states:
        try:
            del user_booking_states[user_id]
            logger.debug(f"Состояние пользователя {user_id} очищено.")
        except KeyError:
            # Состояние уже было удалено, например, другим потоком или вызовом
            logger.warning(f"Попытка удалить уже отсутствующее состояние для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при удалении состояния пользователя {user_id}: {e}", exc_info=True)


# --- Состояния Администраторов ---

# Словарь для хранения состояний админских процессов (например, добавления оборудования)
# Ключ - admin_id, Значение - словарь с состоянием {'step': '...', 'data': {...}, 'message_id': ...}
admin_process_states: Dict[int, Dict[str, Any]] = {}

def clear_admin_state(admin_id: int):
    """Безопасно удаляет состояние админского процесса."""
    if admin_id in admin_process_states:
        try:
            del admin_process_states[admin_id]
            logger.debug(f"Состояние админа {admin_id} очищено.")
        except KeyError:
            logger.warning(f"Попытка удалить уже отсутствующее состояние для админа {admin_id}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при удалении состояния админа {admin_id}: {e}", exc_info=True)

# --- END OF FILE states.py ---