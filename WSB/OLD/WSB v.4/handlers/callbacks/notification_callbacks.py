# --- START OF FILE handlers/callbacks/notification_callbacks.py ---
"""
Обработчики callback-запросов, связанных с уведомлениями бота.

Отвечает за:
- Подтверждение начала бронирования (кнопка в уведомлении о начале).
- Обработку нажатия кнопки "Продлить" в уведомлении о скором окончании.
- Обработку нажатия кнопки "Отмена" в уведомлении о скором окончании.
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple

from database import Database
from logger import logger
import constants as const
import services.notification_service as notificationService
# Импортируем хелпер для редактирования/отправки сообщений из utils
from utils.message_utils import edit_or_send_message
# Импортируем обработчик выбора брони для продления из booking_callbacks
from .booking_callbacks import handle_extend_select_booking

# --- Обработчики ---

def handle_confirm_start(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    active_timers: Dict[int, Any]
):
    """
    Обрабатывает нажатие кнопки подтверждения начала бронирования.
    (Префикс: const.CB_BOOK_CONFIRM_START)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    booking_id_str = cb_data[len(const.CB_BOOK_CONFIRM_START):]
    booking_id = None
    try:
        booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_BOOK_CONFIRM_START от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception:
            pass
        return # Выход

    logger.info(f"User {user_id} подтверждает бронь {booking_id} из уведомления.")
    success = False
    try:
        # Логика подтверждения (включая отмену таймера) находится в notification_service
        success = notificationService.confirm_booking_callback_logic(db, active_timers, booking_id, user_id)
    except Exception as e_confirm_logic:
        logger.error(f"Ошибка в confirm_booking_callback_logic для booking {booking_id}, user {user_id}: {e_confirm_logic}", exc_info=True)
        success = False # Считаем неуспешным при любой ошибке

    if success:
        try:
            bot.answer_callback_query(call.id, const.MSG_BOOKING_CONFIRMED)
        except Exception as e_ans_confirm_ok:
             logger.warning(f"Не удалось ответить на callback после успешного подтверждения {booking_id}: {e_ans_confirm_ok}")
        try:
            # Редактируем сообщение, убираем кнопки
            edit_or_send_message( # Используем исправленное имя функции
                bot, chat_id, message_id,
                text=f"✅ {const.MSG_BOOKING_CONFIRMED}",
                reply_markup=None,
                user_id_for_state_update=user_id # На всякий случай
            )
        except Exception as e_edit_confirm:
            logger.warning(f"Не удалось отредактировать сообщение {message_id} после подтверждения брони {booking_id}: {e_edit_confirm}")
    else:
        # Если confirm_booking_callback_logic вернул False
        alert_msg = "Не удалось подтвердить. Возможно, время вышло или бронь отменена."
        try:
            bot.answer_callback_query(call.id, alert_msg, show_alert=True)
        except Exception as e_ans_confirm_fail:
             logger.warning(f"Не удалось ответить на callback после неудачного подтверждения {booking_id}: {e_ans_confirm_fail}")


def handle_notify_extend_prompt(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    active_timers: Dict[int, Any]
):
    """
    Обрабатывает нажатие кнопки "Продлить" в уведомлении о скором окончании.
    Останавливает таймер изменения сообщения и инициирует процесс продления.
    (Префикс: const.CB_NOTIFY_EXTEND_PROMPT)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    booking_id_str = cb_data[len(const.CB_NOTIFY_EXTEND_PROMPT):]
    booking_id = None
    try:
        booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_NOTIFY_EXTEND_PROMPT от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception:
            pass
        return # Выход

    source = "из уведомления"
    logger.info(f"User {user_id} выбрал бронь {booking_id} для продления ({source})")

    # --- Отмена таймера изменения сообщения ---
    timer = active_timers.pop(booking_id, None)
    if timer:
        try:
            timer.cancel()
            logger.info(f"Таймер изменения сообщения продления для брони {booking_id} отменен пользователем (нажал 'Продлить').")
        except Exception as e_cancel_timer:
            logger.error(f"Ошибка при отмене таймера продления {booking_id} (нажал 'Продлить'): {e_cancel_timer}")
    else:
        logger.warning(f"Таймер изменения сообщения продления для брони {booking_id} не найден при нажатии 'Продлить'.")

    # Вызываем хелпер для показа вариантов времени продления из booking_callbacks
    try:
        # --- ИСПРАВЛЕННЫЙ ВЫЗОВ: Передаем только bot, db, call ---
        handle_extend_select_booking(bot, db, call)
        # --- КОНЕЦ ИСПРАВЛЕННОГО ВЫЗОВА ---
    except Exception as e_call_helper:
         logger.error(f"Ошибка при вызове handle_extend_select_booking из handle_notify_extend_prompt для брони {booking_id}: {e_call_helper}", exc_info=True)
         try:
             bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
         except Exception: pass
         try:
             edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, user_id_for_state_update=user_id)
         except Exception: pass


def handle_notify_decline_extend(
    bot: telebot.TeleBot,
    call: CallbackQuery,
    active_timers: Dict[int, Any]
):
    """
    Обрабатывает нажатие кнопки "Отмена" в уведомлении о скором окончании.
    Останавливает таймер и редактирует сообщение.
    (Префикс: const.CB_NOTIFY_DECLINE_EXT)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    booking_id_str = cb_data[len(const.CB_NOTIFY_DECLINE_EXT):]
    booking_id = None
    try:
        booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_NOTIFY_DECLINE_EXT от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception:
            pass
        return # Выход

    logger.info(f"User {user_id} отказался продлевать бронь {booking_id} из уведомления.")

    # --- Отмена таймера ---
    timer = active_timers.pop(booking_id, None)
    if timer:
        try:
            timer.cancel()
            logger.info(f"Таймер изменения сообщения продления для брони {booking_id} отменен пользователем (нажал 'Отмена').")
        except Exception as e_cancel_timer_decline:
            logger.error(f"Ошибка при отмене таймера продления {booking_id} (нажал 'Отмена'): {e_cancel_timer_decline}")
    else:
        logger.warning(f"Таймер изменения сообщения продления для брони {booking_id} не найден при нажатии 'Отмена'.")

    try:
        bot.answer_callback_query(call.id, "Хорошо, бронирование завершится по расписанию.")
    except Exception as e_ans_decline:
         logger.warning(f"Не удалось ответить на callback отказа от продления {booking_id}: {e_ans_decline}")

    try:
        original_text = call.message.text
        if original_text and const.MSG_EXTEND_DECLINED not in original_text:
            # Редактируем сообщение, добавляем информацию об отказе и убираем кнопки
            edit_or_send_message(
                bot, chat_id, message_id,
                text=f"{original_text}\n\n{const.MSG_EXTEND_DECLINED}",
                reply_markup=None,
                user_id_for_state_update=user_id
            )
        else:
            logger.debug(f"Сообщение {message_id} уже содержит текст отказа от продления для брони {booking_id} или текст пуст.")
    except Exception as e_edit_decline:
        logger.warning(f"Не удалось отредактировать сообщение {message_id} после отказа от продления {booking_id}: {e_edit_decline}")

# --- END OF FILE handlers/callbacks/notification_callbacks.py ---