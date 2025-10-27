# --- START OF FILE handlers/callbacks/notification_callbacks.py (ИСПРАВЛЕННЫЙ ВЫЗОВ confirm_booking_callback_logic) ---
"""
Обработчики callback-запросов, связанных с уведомлениями бота.
"""
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple

from apscheduler.schedulers.background import BackgroundScheduler # Для аннотации

from database import Database # Для аннотации
from logger import logger
import constants as const
import services.notification_service as notificationService # Сервис, где находится confirm_booking_callback_logic
from utils.message_utils import edit_or_send_message
from .booking_callbacks import handle_extend_select_booking

# --- Обработчики ---

def handle_confirm_start(
    bot: telebot.TeleBot,
    db: Database, # db формально передается, но notificationService.confirm_booking_callback_logic его не использует
    call: CallbackQuery,
    scheduler: BackgroundScheduler, # scheduler формально передается, но notificationService.confirm_booking_callback_logic его не использует
    scheduled_jobs_registry: Set[Tuple[str, int]] # registry формально передается, но notificationService.confirm_booking_callback_logic его не использует
):
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
        try: bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return

    logger.info(f"User {user_id} подтверждает бронь {booking_id} из уведомления.")
    success = False
    try:
        # --- ИЗМЕНЕНО: Вызываем confirm_booking_callback_logic только с booking_id и user_id ---
        success = notificationService.confirm_booking_callback_logic(
            booking_id, user_id
        )
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    except Exception as e_confirm_logic:
        logger.error(f"Ошибка в confirm_booking_callback_logic для booking {booking_id}, user {user_id}: {e_confirm_logic}", exc_info=True)
        success = False

    if success:
        try:
            bot.answer_callback_query(call.id, const.MSG_BOOKING_CONFIRMED)
        except Exception as e_ans_ok:
            logger.warning(f"Не удалось ответить на callback после успешного подтверждения {booking_id}: {e_ans_ok}")
        try:
            edit_or_send_message(
                bot, chat_id, message_id,
                text=f"✅ {const.MSG_BOOKING_CONFIRMED}",
                reply_markup=None
            )
        except Exception as e_edit:
            logger.warning(f"Не удалось отредактировать сообщение {message_id} после подтверждения {booking_id}: {e_edit}")
    else:
        alert_msg = "Не удалось подтвердить. Возможно, время вышло или бронь отменена/уже активна."
        try:
            bot.answer_callback_query(call.id, alert_msg, show_alert=True)
        except Exception as e_ans_fail:
            logger.warning(f"Не удалось ответить на callback после неудачного подтверждения {booking_id}: {e_ans_fail}")


def handle_notify_extend_prompt(
    bot: telebot.TeleBot,
    db: Database, # db передается, но booking_callbacks.handle_extend_select_booking может использовать глобальный
    call: CallbackQuery,
    active_timers: Dict[int, Any] # Это global_active_timers, переданный из callback_handlers
):
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
        return
    logger.info(f"User {user_id} выбрал бронь {booking_id} для продления (из уведомления)")
    timer = active_timers.pop(booking_id, None)
    if timer:
        try:
            timer.cancel()
            logger.info(f"UI-таймер отмены продления для {booking_id} отменен (нажал 'Продлить').")
        except Exception as e_cancel:
            logger.error(f"Ошибка отмены UI-таймера продления {booking_id}: {e_cancel}")
    else:
        logger.warning(f"UI-таймер отмены продления для {booking_id} не найден при нажатии 'Продлить'.")
    try:
        handle_extend_select_booking(bot, db, call)
    except Exception as e_call_helper:
         logger.error(f"Ошибка вызова handle_extend_select_booking из handle_notify_extend_prompt для {booking_id}: {e_call_helper}", exc_info=True)
         try:
             bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
         except Exception:
             pass
         try:
             edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)
         except Exception:
             pass


def handle_notify_decline_extend(
    bot: telebot.TeleBot,
    call: CallbackQuery,
    active_timers: Dict[int, Any] # Это global_active_timers, переданный из callback_handlers
):
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
        return
    logger.info(f"User {user_id} отказался продлевать бронь {booking_id} из уведомления.")
    timer = active_timers.pop(booking_id, None)
    if timer:
        try:
            timer.cancel()
            logger.info(f"UI-таймер отмены продления для {booking_id} отменен (нажал 'Отмена').")
        except Exception as e_cancel:
            logger.error(f"Ошибка отмены UI-таймера продления {booking_id}: {e_cancel}")
    else:
        logger.warning(f"UI-таймер отмены продления для {booking_id} не найден при нажатии 'Отмена'.")
    try:
        bot.answer_callback_query(call.id, "Хорошо, бронирование завершится по расписанию.")
    except Exception:
        pass
    try:
        original_text = call.message.text
        if original_text and const.MSG_EXTEND_DECLINED not in original_text and "Время продления вышло" not in original_text:
            edit_or_send_message(bot, chat_id, message_id, text=f"{original_text}\n\n{const.MSG_EXTEND_DECLINED}", reply_markup=None)
        else:
            logger.debug(f"Сообщение {message_id} для {booking_id} уже содержит текст отказа/таймаута или текст пуст.")
    except Exception as e_edit:
        logger.warning(f"Не удалось отредактировать сообщение {message_id} после отказа от продления {booking_id}: {e_edit}")

# --- END OF FILE handlers/callbacks/notification_callbacks.py (ИСПРАВЛЕННЫЙ ВЫЗОВ confirm_booking_callback_logic) ---