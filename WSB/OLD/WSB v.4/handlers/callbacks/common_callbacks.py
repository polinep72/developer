# --- START OF FILE handlers/callbacks/common_callbacks.py ---
"""
Обработчики общих callback-запросов, не связанных с конкретным процессом.

Отвечает за:
- Обработку общей кнопки "Отмена" (CB_ACTION_CANCEL).
- Обработку кнопки "Игнорировать" (CB_IGNORE).
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple

from database import Database
from logger import logger
import constants as const

# Импортируем хелперы и специфичные обработчики отмены из других модулей
# TODO: Пересмотреть зависимости после завершения рефакторинга основного файла
try:
    from utils.message_utils import edit_or_send_message
    # Импортируем функции-обработчики отмены из admin_callbacks
    from .admin_callbacks import (
        handle_cancel_delete_equip,
        handle_cancel_admin_cancel,
        handle_cancel_manage_user
    )
except ImportError as e:
    logger.error(f"Не удалось импортировать зависимости для common_callbacks: {e}")
    # Заглушки на случай ошибок импорта
    def edit_or_send_message(bot, chat_id, message_id, text, **kwargs): pass
    def handle_cancel_delete_equip(bot, db, call): pass
    def handle_cancel_admin_cancel(bot, db, call): pass
    def handle_cancel_manage_user(bot, db, call): pass


# --- Обработчики ---

def handle_action_cancel(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    # user_id, chat_id, message_id извлекаются из call
):
    """
    Обрабатывает нажатие общей кнопки отмены действия.
    Определяет контекст и вызывает соответствующий обработчик
    для возврата к предыдущему шагу или просто редактирует сообщение.
    (Префикс: const.CB_ACTION_CANCEL)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    context = cb_data[len(const.CB_ACTION_CANCEL):]
    logger.debug(f"User {user_id} нажал кнопку отмены для контекста '{context}'. Сообщение: {message_id}")

    try:
        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
    except Exception as e_ans_cancel:
        logger.warning(f"Не удалось ответить на callback отмены '{context}': {e_ans_cancel}")

    # Определяем, нужно ли передавать admin_id в kwargs_edit
    # (Предполагаем, что все контекстные отмены - админские, кроме отмены продления)
    is_admin_context = context in ["delete_equip", "admin_cancel_confirm", "manage_user_list"]
    admin_id_param = user_id if is_admin_context else None
    kwargs_edit = {'user_id_for_state_update': user_id, 'admin_id_for_state_update': admin_id_param}

    try:
        # Вызов специфичных обработчиков отмены для возврата к предыдущему шагу
        if context == "delete_equip":
            handle_cancel_delete_equip(bot, db, call) # Передаем call
        elif context == "admin_cancel_confirm":
            handle_cancel_admin_cancel(bot, db, call) # Передаем call
        elif context == "manage_user_list":
            handle_cancel_manage_user(bot, db, call) # Передаем call
        # Отмена выбора времени продления - просто удаляем сообщение с кнопками
        elif context == const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1).rstrip('_'):
            logger.debug(f"Отмена выбора времени продления (контекст '{context}'), удаляем сообщение {message_id}")
            try:
                bot.delete_message(chat_id, message_id)
            except Exception as e_del_cancel_ext:
                logger.warning(f"Не удалось удалить сообщение {message_id} при отмене продления: {e_del_cancel_ext}")
        # Общая отмена - просто редактируем сообщение
        else:
            logger.debug(f"Общая отмена для контекста '{context}', редактируем сообщение {message_id}")
            edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None, **kwargs_edit)
    except Exception as e_cancel_action:
        logger.error(f"Ошибка при обработке отмены для контекста '{context}', сообщение {message_id}: {e_cancel_action}", exc_info=True)
        # Пытаемся хотя бы отредактировать сообщение в случае ошибки
        try:
            edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None, **kwargs_edit)
        except Exception as e_edit_fallback_cancel:
            logger.error(f"Не удалось даже отредактировать сообщение {message_id} после ошибки отмены '{context}': {e_edit_fallback_cancel}")


def handle_ignore(
    bot: telebot.TeleBot,
    call: CallbackQuery,
    # user_id извлекается из call
):
    """
    Обрабатывает нажатие кнопки "Игнорировать".
    Просто отвечает на колбэк, ничего не делая.
    (Префикс: const.CB_IGNORE)
    """
    user_id = call.from_user.id
    logger.debug(f"User {user_id} нажал кнопку 'Игнорировать'. Callback: {call.data}")
    try:
        bot.answer_callback_query(call.id)
    except Exception as e_ans_ignore:
        logger.warning(f"Не удалось ответить на callback CB_IGNORE: {e_ans_ignore}")


# --- END OF FILE handlers/callbacks/common_callbacks.py ---