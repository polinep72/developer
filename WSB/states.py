# --- START OF FILE states.py ---

# states.py
"""
Модуль для хранения и управления состоянием процесса бронирования пользователя.
"""

from typing import Dict, Any
from logger import logger

# --- Состояние процесса бронирования пользователя ---

# Словарь для хранения состояний процессов бронирования пользователей
# Ключ - user_id, Значение - словарь с состоянием:
# {'step': <текущий_шаг_из_constants>, 'data': {<данные_брони>}, 'message_id': <id_сообщения_с_кнопками>, 'chat_id': <id_чата>}
user_booking_states: Dict[int, Dict[str, Any]] = {}

def clear_user_state(user_id: int):
    """Безопасно удаляет состояние процесса бронирования пользователя."""
    if user_id in user_booking_states:
        try:
            # Получаем состояние перед удалением для лога
            state_before_clear = user_booking_states.get(user_id)
            del user_booking_states[user_id]
            logger.debug(f"Состояние пользователя {user_id} очищено. Предыдущее состояние: {state_before_clear}")
        except KeyError:
            # Состояние уже было удалено
            logger.warning(f"Попытка удалить уже отсутствующее состояние для пользователя {user_id}")
        except Exception as e:
            logger.error(f"Неожиданная ошибка при удалении состояния пользователя {user_id}: {e}", exc_info=True)
    else:
        # Логируем, только если состояние действительно пытались очистить, а его не было
        # logger.debug(f"Состояние пользователя {user_id} для очистки не найдено (возможно, уже было очищено).")
        pass


# --- Состояния Администраторов (Больше не используются) ---
# Словарь admin_process_states и функция clear_admin_state удалены,
# так как админские процессы (например, добавление комнаты)
# теперь управляются через register_next_step_handler.

# --- END OF FILE states.py ---