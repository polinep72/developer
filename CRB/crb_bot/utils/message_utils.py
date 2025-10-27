# --- START OF FILE utils/message_utils.py ---
"""
Вспомогательные функции для работы с сообщениями Telegram.
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional

# --- ИЗМЕНЕНИЕ: Импортируем только user_booking_states ---
from states import user_booking_states
# --- КОНЕЦ ИЗМЕНЕНИЯ ---
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
    Обновляет message_id в состоянии пользователя при необходимости.
    """
    # Получаем user_id для обновления состояния, если он передан
    user_id_for_state_update = kwargs.pop('user_id_for_state_update', None)
    # --- ИЗМЕНЕНИЕ: Удаляем параметр для админа ---
    # admin_id_for_state_update = kwargs.pop('admin_id_for_state_update', None)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    new_message_id = None # ID сообщения, которое в итоге будет актуальным

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
                logger.error(f"Отправка нового сообщения в {chat_id} не вернула объект сообщения.")

    except apihelper.ApiTelegramException as e_api:
        error_text = str(e_api).lower()
        sent_message_fallback = None
        if "message is not modified" in error_text:
            logger.debug(f"Сообщение {message_id} не изменено (API: not modified).")
            new_message_id = message_id # Сообщение осталось прежним
        elif "message to edit not found" in error_text or "message can't be edited" in error_text:
            logger.warning(f"Не удалось отредактировать {message_id} в {chat_id} (API: {error_text}). Отправка нового.")
            try:
                sent_message_fallback = bot.send_message(chat_id, text, **kwargs)
                if sent_message_fallback: new_message_id = sent_message_fallback.message_id
            except Exception as e_send_fallback:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (fallback edit error): {e_send_fallback}")
        else:
            logger.error(f"Ошибка API при редактировании/отправке {message_id} в {chat_id}: {e_api}")
            # Пробуем отправить новое в любом случае при других ошибках API
            try:
                sent_message_fallback = bot.send_message(chat_id, text, **kwargs)
                if sent_message_fallback: new_message_id = sent_message_fallback.message_id
            except Exception as e_send_fallback_api:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (fallback API error): {e_send_fallback_api}")

    except Exception as e:
        logger.error(f"Общая ошибка в edit_or_send_message (chat={chat_id}, msg_id={message_id}): {e}", exc_info=True)
        # Пробуем отправить новое при общей ошибке
        sent_message_generic_fallback = None
        try:
            sent_message_generic_fallback = bot.send_message(chat_id, text, **kwargs)
            if sent_message_generic_fallback: new_message_id = sent_message_generic_fallback.message_id
        except Exception as e_send_generic_fallback:
            logger.error(f"Не удалось отправить новое сообщение в {chat_id} (generic fallback): {e_send_generic_fallback}")


    # Обновляем message_id в состоянии пользователя, если необходимо и ID получен
    if user_id_for_state_update and new_message_id:
        if user_id_for_state_update in user_booking_states:
            current_state = user_booking_states[user_id_for_state_update]
            current_msg_id = current_state.get('message_id')
            # Обновляем, только если ID изменился (или был None)
            if current_msg_id != new_message_id:
                current_state['message_id'] = new_message_id
                logger.debug(f"Обновлен message_id на {new_message_id} для user {user_id_for_state_update}")
        else:
            # Это может произойти, если состояние было очищено до завершения edit_or_send_message
            logger.debug(f"Состояние для user {user_id_for_state_update} не найдено, message_id не обновлен.")

    # --- ИЗМЕНЕНИЕ: Удален блок обновления состояния админа ---
    # if admin_id_for_state_update:
    #    ... (код удален) ...
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

# --- END OF FILE utils/message_utils.py ---