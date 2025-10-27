# --- START OF FILE utils/message_utils.py ---
"""
Вспомогательные функции для работы с сообщениями Telegram.
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery # Может понадобиться для других функций в будущем
from typing import Dict, Any, Optional

# Импортируем состояния напрямую, т.к. этот модуль не зависит от хендлеров
from states import user_booking_states, admin_process_states
from logger import logger

def edit_or_send_message(
    bot: telebot.TeleBot,
    chat_id: int,
    message_id: Optional[int],
    text: str,
    **kwargs
):
    """
    Пытается отредактировать сообщение, если message_id есть, иначе отправляет новое.
    Обновляет message_id в состоянии пользователя/админа при необходимости.

    ВАЖНО: Эта функция теперь называется edit_or_send_message (без подчеркивания),
    чтобы избежать путаницы с "приватными" методами.
    """
    user_id_for_state_update = kwargs.pop('user_id_for_state_update', None)
    admin_id_for_state_update = kwargs.pop('admin_id_for_state_update', None)
    new_message_id = None # ID сообщения, которое в итоге будет актуальным

    try:
        if message_id:
            # Пытаемся отредактировать существующее сообщение
            bot.edit_message_text(text, chat_id, message_id, **kwargs)
            logger.debug(f"Сообщение {message_id} отредактировано в чате {chat_id}")
            new_message_id = message_id
        else:
            # Если message_id нет, отправляем новое сообщение
            logger.warning(f"Нет message_id для редактирования в чате {chat_id}, отправка нового сообщения.")
            sent_message = None
            try:
                sent_message = bot.send_message(chat_id, text, **kwargs)
            except Exception as e_send_inner:
                logger.error(f"Не удалось отправить новое сообщение в {chat_id} (внутренняя ошибка): {e_send_inner}")
                raise e_send_inner # Пробрасываем ошибку выше

            if sent_message: # Проверяем, что сообщение было успешно отправлено
                new_message_id = sent_message.message_id
            else:
                logger.error(f"Отправка нового сообщения в {chat_id} не вернула объект сообщения.")

    except apihelper.ApiTelegramException as e_api:
        error_text = str(e_api).lower()
        if "message is not modified" in error_text:
            logger.debug(f"Сообщение {message_id} не изменено (API: not modified).")
            new_message_id = message_id
        elif "message to edit not found" in error_text or "message can't be edited" in error_text:
            logger.warning(f"Не удалось отредактировать {message_id} в {chat_id} (API: {error_text}). Отправка нового.")
            sent_message_fallback = None
            try:
                sent_message_fallback = bot.send_message(chat_id, text, **kwargs)
            except Exception as e_send_fallback:
                logger.error(f"Не удалось отправить новое сообщение в {chat_id} (fallback): {e_send_fallback}")

            if sent_message_fallback:
                new_message_id = sent_message_fallback.message_id
        else:
            logger.error(f"Ошибка API при редактировании/отправке {message_id} в {chat_id}: {e_api}")
            sent_message_final = None
            try:
                sent_message_final = bot.send_message(chat_id, text, **kwargs)
            except Exception as e_send_final:
                logger.error(f"Не удалось отправить новое сообщение в {chat_id} (final fallback): {e_send_final}")

            if sent_message_final:
                new_message_id = sent_message_final.message_id
    except Exception as e:
        logger.error(f"Общая ошибка в edit_or_send_message (chat={chat_id}, msg_id={message_id}): {e}", exc_info=True)
        sent_message_generic_fallback = None
        try:
            sent_message_generic_fallback = bot.send_message(chat_id, text, **kwargs)
        except Exception as e_send_generic_fallback:
            logger.error(f"Не удалось отправить новое сообщение в {chat_id} (generic fallback): {e_send_generic_fallback}")

        if sent_message_generic_fallback:
            new_message_id = sent_message_generic_fallback.message_id

    # Обновляем message_id в состоянии пользователя, если необходимо
    if user_id_for_state_update:
        if new_message_id:
            if user_id_for_state_update in user_booking_states:
                current_state = user_booking_states[user_id_for_state_update]
                current_msg_id = current_state.get('message_id')
                if current_msg_id != new_message_id:
                    current_state['message_id'] = new_message_id
                    logger.debug(f"Обновлен message_id на {new_message_id} для user {user_id_for_state_update}")
            else:
                logger.debug(f"Состояние для user {user_id_for_state_update} не найдено, message_id не обновлен.")

    # Обновляем message_id в состоянии админа, если необходимо
    if admin_id_for_state_update:
        if new_message_id:
            if admin_id_for_state_update in admin_process_states:
                current_admin_state = admin_process_states[admin_id_for_state_update]
                current_admin_msg_id = current_admin_state.get('message_id')
                if current_admin_msg_id != new_message_id:
                    current_admin_state['message_id'] = new_message_id
                    logger.debug(f"Обновлен message_id на {new_message_id} для admin {admin_id_for_state_update}")
            else:
                logger.debug(f"Состояние для admin {admin_id_for_state_update} не найдено, message_id не обновлен.")

# --- END OF FILE utils/message_utils.py ---