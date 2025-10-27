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
import constants as const # Используем обновленные константы
from utils import keyboards # Относительный импорт из handlers/callbacks/ в utils/
# Импортируем хелперы и специфичные обработчики отмены из других модулей
try:
    from utils.message_utils import edit_or_send_message
    # --- ИЗМЕНЕНИЕ: Импортируем правильные функции отмены ---
    from .admin_callbacks import (
        handle_cancel_delete_cr, # <-- Отмена удаления комнаты
        handle_cancel_admin_cancel,
        handle_cancel_manage_user
    )
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
except ImportError as e:
    logger.error(f"Не удалось импортировать зависимости для common_callbacks: {e}")
    # Заглушки
    def edit_or_send_message(bot, chat_id, message_id, text, **kwargs): pass
    def handle_cancel_delete_cr(bot, db, call): pass # <-- Заглушка для комнаты
    def handle_cancel_admin_cancel(bot, db, call): pass
    def handle_cancel_manage_user(bot, db, call): pass


# --- Обработчики ---

def handle_action_cancel(
    bot: telebot.TeleBot,
    db: Database, # db может быть нужен для функций отмены
    call: CallbackQuery,
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
    except Exception: pass # Игнорируем ошибку ответа

    # kwargs_edit больше не содержит admin_id_for_state_update
    kwargs_edit: Dict[str, Any] = {}

    try:
        # --- ИЗМЕНЕНИЕ: Используем контекст и функцию для комнат ---
        if context == "delete_cr": # <-- Контекст отмены удаления комнаты
            handle_cancel_delete_cr(bot, db, call) # <-- Вызов функции для комнат
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        elif context == "admin_cancel_confirm": # Контекст для админской отмены брони
            handle_cancel_admin_cancel(bot, db, call)
        elif context == "manage_user_list": # Контекст для управления пользователями
            handle_cancel_manage_user(bot, db, call)
        # Контекст для отмены выбора времени продления
        elif context == const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1).replace('_s_book_', '', 1):
            # Контекст извлекается из префикса CB_EXTEND_SELECT_BOOKING (например, 'extend')
            logger.debug(f"Отмена выбора времени продления (контекст '{context}'), удаляем сообщение {message_id}")
            try:
                bot.delete_message(chat_id, message_id)
            except Exception as e_del_cancel_ext:
                # Если сообщение не удалилось, пытаемся его отредактировать
                logger.warning(f"Не удалось удалить сообщение {message_id} при отмене продления, пробуем редактировать: {e_del_cancel_ext}")
                try:
                    edit_or_send_message(bot, chat_id, message_id, "Выбор времени продления отменен.", reply_markup=None, **kwargs_edit)
                except Exception as e_edit_cancel_ext:
                    logger.error(f"Не удалось и отредактировать сообщение {message_id} при отмене продления: {e_edit_cancel_ext}")
        # --- ИЗМЕНЕНИЕ: Контекст для отмены выбора фильтра /all ---
        elif context == "filter_type":
            logger.debug(f"Отмена выбора значения фильтра /all (контекст '{context}'), возврат к выбору типа фильтра. Msg: {message_id}")
            markup_filter_options = keyboards.generate_filter_options_keyboard()
            edit_or_send_message(bot, chat_id, message_id, "Отмена. Выберите критерий для фильтрации:", reply_markup=markup_filter_options, **kwargs_edit)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
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