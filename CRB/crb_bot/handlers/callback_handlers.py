# --- START OF FILE handlers/callback_handlers.py (ПОВТОРНОЕ ИСПРАВЛЕНИЕ) ---
"""
Основной диспетчер для обработки inline callback-запросов.
"""
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple, Callable

from database import Database
from logger import logger
import constants as const
import services.user_service as userService
from states import user_booking_states, clear_user_state  # Управление состоянием процесса бронирования
from apscheduler.schedulers.background import BackgroundScheduler

# Импорт модулей с конкретными обработчиками
from .callbacks import (
    admin_callbacks,
    booking_callbacks,
    common_callbacks,
    notification_callbacks,
    process_callbacks,
    viewing_callbacks
)
from utils.message_utils import edit_or_send_message

# Словарь маршрутизации (убедитесь, что он актуален)
CALLBACK_ROUTES: Dict[str, Callable] = {
    const.CB_BOOK_CONFIRM_START: notification_callbacks.handle_confirm_start,  # <--- Маршрут к правильной функции
    const.CB_NOTIFY_EXTEND_PROMPT: notification_callbacks.handle_notify_extend_prompt,
    const.CB_NOTIFY_DECLINE_EXT: notification_callbacks.handle_notify_decline_extend,
    const.CB_CANCEL_SELECT_BOOKING: booking_callbacks.handle_cancel_select,
    const.CB_FINISH_SELECT_BOOKING: booking_callbacks.handle_finish_select,
    const.CB_EXTEND_SELECT_BOOKING: booking_callbacks.handle_extend_select_booking,
    const.CB_EXTEND_SELECT_TIME: booking_callbacks.handle_extend_select_time,
    const.CB_ADMIN_ADD_CR_CANCEL: admin_callbacks.handle_admin_add_cr_cancel,
    const.CB_REG_CONFIRM_USER: admin_callbacks.handle_registration_confirm,
    const.CB_REG_DECLINE_USER: admin_callbacks.handle_registration_decline,
    const.CB_MANAGE_SELECT_USER: admin_callbacks.handle_manage_user_select,
    const.CB_MANAGE_BLOCK_USER: admin_callbacks.handle_manage_user_action,
    const.CB_MANAGE_UNBLOCK_USER: admin_callbacks.handle_manage_user_action,
    const.CB_ADMIN_CANCEL_SELECT: admin_callbacks.handle_admin_cancel_select,
    const.CB_ADMIN_CANCEL_CONFIRM: admin_callbacks.handle_admin_cancel_confirm,
    const.CB_FILTER_BY_TYPE: admin_callbacks.handle_filter_type_select,
    const.CB_FILTER_SELECT_USER: admin_callbacks.handle_filter_value_select,
    const.CB_FILTER_SELECT_CR: admin_callbacks.handle_filter_value_select,
    const.CB_FILTER_SELECT_DATE: admin_callbacks.handle_filter_value_select,
    const.CB_CR_DELETE_SELECT: admin_callbacks.handle_cr_delete_select,
    const.CB_CR_DELETE_CONFIRM: admin_callbacks.handle_cr_delete_confirm,
    const.CB_DATEB_SELECT_DATE: viewing_callbacks.handle_datebookings_select,
    const.CB_ROOMB_SELECT_CR: viewing_callbacks.handle_roomb_select,
    const.CB_ACTION_CANCEL: common_callbacks.handle_action_cancel,
    const.CB_IGNORE: common_callbacks.handle_ignore,
}


def handle_callback_query(
        bot: telebot.TeleBot,
        db: Database,
        scheduler: Optional[BackgroundScheduler],
        active_timers: Dict[int, Any],  # active_timers для UI-таймеров (например, _cancel_extend_option)
        scheduled_jobs_registry: Set[Tuple[str, int]],
        call: CallbackQuery
):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data
    logger.debug(f"Callback: user={user_id}, chat={chat_id}, msg={message_id}, data='{cb_data}'")

    try:
        # --- 1. Обработка подтверждения брони (CB_BOOK_CONFIRM_START) ---
        if cb_data.startswith(const.CB_BOOK_CONFIRM_START):
            try:
                logger.debug(f"Вызов notification_callbacks.handle_confirm_start для {cb_data} с scheduler и registry")
                # Передаем bot, db, call, scheduler, scheduled_jobs_registry
                # НЕ ПЕРЕДАЕМ active_timers сюда, т.к. handle_confirm_start его не ждет
                notification_callbacks.handle_confirm_start(
                    bot, db, call, scheduler, scheduled_jobs_registry
                )
            except Exception as e:
                logger.critical(f"Критическая ошибка при вызове handle_confirm_start: {e}", exc_info=True)
                try:
                    bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                except Exception:
                    pass
            return  # Завершаем обработку для этого специфичного колбэка

        # --- 2. Проверка состояния бронирования пользователя (CB_BOOK_ACTION) ---
        user_state = user_booking_states.get(user_id)
        if user_state:
            current_message_id = user_state.get('message_id')
            if current_message_id and message_id != current_message_id:
                logger.warning(
                    f"User {user_id} нажал кнопку '{cb_data}' на старом сообщении {message_id}. Активное: {current_message_id}. Игнор.")
                try:
                    bot.answer_callback_query(call.id,
                                              "Пожалуйста, используйте кнопки на последнем сообщении процесса.",
                                              show_alert=True)
                except Exception:
                    pass
                return
            if cb_data.startswith(const.CB_BOOK_ACTION):
                logger.debug(
                    f"Callback '{cb_data}' относится к процессу бронирования user {user_id}. Вызов handle_booking_steps.")
                try:
                    process_callbacks.handle_booking_steps(
                        bot, db, call, user_state, scheduler, active_timers, scheduled_jobs_registry
                    )
                except Exception as e:
                    logger.critical(f"Критическая ошибка при вызове handle_booking_steps для user {user_id}: {e}",
                                    exc_info=True)
                    try:
                        bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                    except Exception:
                        pass
                    clear_user_state(user_id)
                return
            else:
                logger.debug(
                    f"User {user_id} в состоянии {user_state.get('step')}, но cb '{cb_data}' не для процесса. Общая обработка.")

        # --- 3. Обработка колбэков вне процесса бронирования пользователя ---
        # (Проверки прав и маршрутизация)
        logger.debug(f"Обработка cb '{cb_data}' вне процесса бронирования user {user_id}...")
        is_admin_user = userService.is_admin(db, user_id)
        is_active_user = False
        if not is_admin_user: is_active_user = userService.is_user_registered_and_active(db, user_id)

        is_admin_action = any(cb_data.startswith(p) for p in [
            const.CB_REG_CONFIRM_USER, const.CB_REG_DECLINE_USER, const.CB_MANAGE_SELECT_USER,
            const.CB_MANAGE_BLOCK_USER, const.CB_MANAGE_UNBLOCK_USER, const.CB_ADMIN_CANCEL_SELECT,
            const.CB_ADMIN_CANCEL_CONFIRM, const.CB_FILTER_BY_TYPE, const.CB_FILTER_SELECT_USER,
            const.CB_FILTER_SELECT_CR, const.CB_FILTER_SELECT_DATE, const.CB_CR_DELETE_SELECT,
            const.CB_CR_DELETE_CONFIRM, const.CB_ADMIN_ADD_CR_CANCEL
        ])
        needs_active_user_check = not (is_admin_action or cb_data == const.CB_IGNORE or cb_data.startswith(
            const.CB_ACTION_CANCEL) or cb_data.startswith(const.CB_BOOK_CONFIRM_START))

        if is_admin_action and not is_admin_user:
            logger.warning(f"User {user_id} (не админ) попытался выполнить админское действие '{cb_data}'.")
            try:
                bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)
            except Exception:
                pass
            return
        if needs_active_user_check and not is_admin_user and not is_active_user:
            logger.warning(f"Неактивный user {user_id} попытался выполнить '{cb_data}'.")
            try:
                bot.answer_callback_query(call.id, const.MSG_ERROR_NOT_REGISTERED, show_alert=True)
            except Exception:
                pass
            try:
                bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
            except Exception:
                pass
            return

        # Маршрутизация
        handler_found = False;
        matched_handler: Optional[Callable] = None;
        matched_prefix: Optional[str] = None
        if cb_data in CALLBACK_ROUTES:
            matched_handler = CALLBACK_ROUTES[cb_data];
            matched_prefix = cb_data;
            handler_found = True
        else:
            for prefix, handler in CALLBACK_ROUTES.items():
                if prefix.endswith('_') and cb_data.startswith(prefix):
                    matched_handler = handler;
                    matched_prefix = prefix;
                    handler_found = True;
                    break

        if handler_found and matched_handler and matched_prefix:
            logger.debug(f"Маршрутизация cb '{cb_data}' к {matched_handler.__name__} для префикса '{matched_prefix}'")
            try:
                if matched_prefix == const.CB_EXTEND_SELECT_TIME:
                    matched_handler(bot, db, call, scheduler, active_timers, scheduled_jobs_registry)
                elif matched_prefix in [const.CB_ADMIN_CANCEL_CONFIRM, const.CB_CANCEL_SELECT_BOOKING,
                                        const.CB_FINISH_SELECT_BOOKING]:
                    matched_handler(bot, db, call, scheduler, scheduled_jobs_registry)
                elif matched_prefix == const.CB_NOTIFY_EXTEND_PROMPT:
                    matched_handler(bot, db, call, active_timers)  # active_timers для UI-таймера
                elif matched_prefix == const.CB_NOTIFY_DECLINE_EXT:
                    matched_handler(bot, call, active_timers)  # active_timers для UI-таймера
                elif matched_prefix == const.CB_IGNORE:
                    matched_handler(bot, call)
                # const.CB_BOOK_CONFIRM_START уже обработан выше и ожидает (bot, db, call, scheduler, scheduled_jobs_registry)
                # Эта ветка больше не нужна здесь, т.к. CB_BOOK_CONFIRM_START обрабатывается отдельно в начале
                # elif matched_prefix == const.CB_BOOK_CONFIRM_START:
                #    matched_handler(bot, db, call, scheduler, scheduled_jobs_registry)
                else:  # Общий случай для большинства остальных
                    matched_handler(bot, db, call)
            except Exception as e_handler:
                logger.critical(
                    f"Критическая ошибка вызова обработчика для '{matched_prefix}' (cb='{cb_data}'): {e_handler}",
                    exc_info=True)
                try:
                    bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                except Exception:
                    pass
        else:
            logger.warning(f"Получен необработанный callback от user {user_id}: '{cb_data}'")
            try:
                bot.answer_callback_query(call.id, "Неизвестное действие.")
            except Exception:
                pass

    except Exception as e_global:  # Общая обработка ошибок
        logger.critical(f"Критическая непредвиденная ошибка cb '{cb_data}' user {user_id}: {e_global}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception:
            pass


def register_callback_handlers(
        bot: telebot.TeleBot,
        db: Database,
        scheduler: Optional[BackgroundScheduler],
        active_timers: Dict[int, Any],
        scheduled_jobs_registry: Set[Tuple[str, int]]
):
    @bot.callback_query_handler(func=lambda call: True)
    def main_callback_dispatcher(call: CallbackQuery):
        handle_callback_query(bot, db, scheduler, active_timers, scheduled_jobs_registry, call)

    logger.info("Основной обработчик callback-запросов успешно зарегистрирован.")

# --- END OF FILE handlers/callback_handlers.py (ПОВТОРНОЕ ИСПРАВЛЕНИЕ) ---