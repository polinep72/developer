# --- START OF FILE utils/message_utils.py (WSB - исправленный) ---
"""
Вспомогательные функции для работы с сообщениями Telegram.
"""

import telebot
from telebot import apihelper # Убрали types, т.к. не используется здесь
from typing import Optional, Dict, Any # Добавили Dict, Any

# Импортируем только user_booking_states из вашего обновленного states.py WSB
from states import user_booking_states
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
    Обновляет message_id в состоянии пользователя (user_booking_states) при необходимости.
    """
    user_id_for_state_update = kwargs.pop('user_id_for_state_update', None)
    # Логика для admin_id_for_state_update и admin_process_states удалена,
    # так как admin_process_states удалены из states.py WSB.
    new_message_id: Optional[int] = None

    try:
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, **kwargs)
            logger.debug(f"Сообщение {message_id} отредактировано в чате {chat_id}")
            new_message_id = message_id
        else:
            logger.warning(f"Нет message_id для редактирования в чате {chat_id}, отправка нового сообщения.")
            sent_message = bot.send_message(chat_id, text, **kwargs)
            if sent_message:
                new_message_id = sent_message.message_id
                logger.info(f"Отправлено новое сообщение {new_message_id} в чат {chat_id}")
            else:
                # Этого не должно происходить с pyTelegramBotAPI, если нет исключения
                logger.error(f"Отправка нового сообщения в {chat_id} не вернула объект сообщения (send_message вернул None).")

    except apihelper.ApiTelegramException as e_api:
        error_text_lower = str(e_api).lower()
        sent_message_fallback = None
        if "message is not modified" in error_text_lower:
            logger.debug(f"Сообщение {message_id} не изменено (API: not modified).")
            new_message_id = message_id # Сообщение осталось прежним
        elif "message to edit not found" in error_text_lower or \
             "message can't be edited" in error_text_lower or \
             "message to be edited not found" in error_text_lower: # Добавлено еще одно условие
            logger.warning(f"Не удалось отредактировать {message_id} в {chat_id} (API: {error_text_lower}). Отправка нового.")
            try:
                sent_message_fallback = bot.send_message(chat_id, text, **kwargs)
                if sent_message_fallback: new_message_id = sent_message_fallback.message_id
            except Exception as e_send_fallback:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (fallback edit error): {e_send_fallback}")
        else:
            # Для других ошибок API, не связанных с "not modified" или "not found/can't be edited"
            logger.error(f"Ошибка API ({e_api.error_code if hasattr(e_api, 'error_code') else 'N/A'}) "
                         f"при редактировании/отправке {message_id} в {chat_id}: {e_api}")
            # Пробуем отправить новое в любом случае
            try:
                sent_message_fallback_other_api_error = bot.send_message(chat_id, text, **kwargs)
                if sent_message_fallback_other_api_error: new_message_id = sent_message_fallback_other_api_error.message_id
            except Exception as e_send_fallback_other_api:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (fallback other API error): {e_send_fallback_other_api}")

    except Exception as e_general: # Ловим другие общие исключения
        logger.error(f"Общая ошибка в edit_or_send_message (chat={chat_id}, msg_id={message_id}): {e_general}", exc_info=True)
        # Пробуем отправить новое сообщение как последний вариант
        sent_message_generic_error_fallback = None
        try:
            sent_message_generic_error_fallback = bot.send_message(chat_id, text, **kwargs)
            if sent_message_generic_error_fallback: new_message_id = sent_message_generic_error_fallback.message_id
        except Exception as e_send_generic_error_fallback:
            logger.error(f"Не удалось отправить новое сообщение в {chat_id} (generic error fallback): {e_send_generic_error_fallback}")

    # Обновляем message_id в состоянии пользователя, если необходимо и ID получен
    if user_id_for_state_update and new_message_id:
        if user_id_for_state_update in user_booking_states:
            current_user_state: Dict[str, Any] = user_booking_states[user_id_for_state_update]
            current_user_msg_id: Optional[int] = current_user_state.get('message_id')

            if current_user_msg_id != new_message_id:
                current_user_state['message_id'] = new_message_id
                logger.debug(f"Обновлен message_id на {new_message_id} для user {user_id_for_state_update}")
        else:
            # Состояние пользователя могло быть очищено, например, если процесс завершился
            logger.debug(f"Состояние для user {user_id_for_state_update} не найдено при попытке обновить message_id (возможно, уже очищено).")

# --- END OF FILE utils/message_utils.py (WSB - исправленный) ---