# --- START OF FILE handlers/callback_handlers.py ---
"""
Основной диспетчер для обработки inline callback-запросов.

Маршрутизирует запросы к соответствующим обработчикам в поддиректории 'callbacks/'.
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple, Callable

from database import Database
from logger import logger
import constants as const
import services.user_service as userService # Для проверки прав доступа
# --- ИЗМЕНЕНИЕ: Удалены импорты admin_process_states, clear_admin_state ---
from states import user_booking_states, clear_user_state # Оставляем только пользовательские состояния
from apscheduler.schedulers.background import BackgroundScheduler

# --- Импорт модулей с обработчиками колбэков ---
from .callbacks import (
    admin_callbacks,
    booking_callbacks,
    common_callbacks,
    notification_callbacks,
    process_callbacks,
    viewing_callbacks
)

# --- Импорт вспомогательной функции ---
from utils.message_utils import edit_or_send_message


# --- Словарь маршрутизации колбэков (БЕЗ ИЗМЕНЕНИЙ) ---
# Записи для CB_ADMIN_ADD_EQUIP_* уже указывают на нужные функции в admin_callbacks.py
CALLBACK_ROUTES: Dict[str, Callable] = {
    # --- Notification Callbacks ---
    const.CB_BOOK_CONFIRM_START: notification_callbacks.handle_confirm_start,
    const.CB_NOTIFY_EXTEND_PROMPT: notification_callbacks.handle_notify_extend_prompt,
    const.CB_NOTIFY_DECLINE_EXT: notification_callbacks.handle_notify_decline_extend,
    # --- Booking Callbacks ---
    const.CB_CANCEL_SELECT_BOOKING: booking_callbacks.handle_cancel_select,
    const.CB_FINISH_SELECT_BOOKING: booking_callbacks.handle_finish_select,
    const.CB_EXTEND_SELECT_BOOKING: booking_callbacks.handle_extend_select_booking, # Обрабатывает и /extend
    const.CB_EXTEND_SELECT_TIME: booking_callbacks.handle_extend_select_time,
    # --- Admin Callbacks ---
    const.CB_ADMIN_ADD_EQUIP_SELECT_CAT_: admin_callbacks.handle_admin_add_equip_select_cat, # <-- Указывает на новую реализацию
    const.CB_ADMIN_ADD_EQUIP_NEW_CAT: admin_callbacks.handle_admin_add_equip_new_cat,       # <-- Указывает на новую реализацию
    const.CB_ADMIN_ADD_EQUIP_CANCEL: admin_callbacks.handle_admin_add_equip_cancel,       # <-- Указывает на новую реализацию
    const.CB_REG_CONFIRM_USER: admin_callbacks.handle_registration_confirm,
    const.CB_REG_DECLINE_USER: admin_callbacks.handle_registration_decline,
    const.CB_MANAGE_SELECT_USER: admin_callbacks.handle_manage_user_select,
    const.CB_MANAGE_BLOCK_USER: admin_callbacks.handle_manage_user_action, # Обрабатывает и блок
    const.CB_MANAGE_UNBLOCK_USER: admin_callbacks.handle_manage_user_action, # и разблок
    const.CB_ADMIN_CANCEL_SELECT: admin_callbacks.handle_admin_cancel_select,
    const.CB_ADMIN_CANCEL_CONFIRM: admin_callbacks.handle_admin_cancel_confirm,
    const.CB_FILTER_BY_TYPE: admin_callbacks.handle_filter_type_select,
    const.CB_FILTER_SELECT_USER: admin_callbacks.handle_filter_value_select, # Обрабатывает все значения
    const.CB_FILTER_SELECT_EQUIPMENT: admin_callbacks.handle_filter_value_select,
    const.CB_FILTER_SELECT_DATE: admin_callbacks.handle_filter_value_select,
    const.CB_EQUIP_DELETE_SELECT: admin_callbacks.handle_equip_delete_select,
    const.CB_EQUIP_DELETE_CONFIRM: admin_callbacks.handle_equip_delete_confirm,
    # --- Viewing Callbacks ---
    const.CB_DATEB_SELECT_DATE: viewing_callbacks.handle_datebookings_select,
    const.CB_WSB_SELECT_CATEGORY: viewing_callbacks.handle_wsb_category_select,
    const.CB_WSB_SELECT_EQUIPMENT: viewing_callbacks.handle_wsb_equipment_select,
    # --- Common Callbacks ---
    const.CB_ACTION_CANCEL: common_callbacks.handle_action_cancel,
    const.CB_IGNORE: common_callbacks.handle_ignore,
}

# --- Главный обработчик (БЕЗ ИЗМЕНЕНИЙ В ЛОГИКЕ МАРШРУТИЗАЦИИ) ---
def handle_callback_query(
    bot: telebot.TeleBot,
    db: Database,
    scheduler: Optional[BackgroundScheduler],
    active_timers: Dict[int, Any],
    scheduled_jobs_registry: Set[Tuple[str, int]],
    call: CallbackQuery
):
    """
    Главный диспетчер callback-запросов.
    Выполняет проверки и маршрутизирует запрос к нужному обработчику.
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data
    logger.debug(f"Callback: user={user_id}, chat={chat_id}, msg={message_id}, data='{cb_data}'")

    # --- НАЧАЛО ОСНОВНОГО БЛОКА TRY ---
    try:
        # --- 1. Обработка подтверждения брони (приходит отдельным сообщением) ---
        if cb_data.startswith(const.CB_BOOK_CONFIRM_START):
            try:
                # Передаем bot, db, call, active_timers (4 аргумента)
                notification_callbacks.handle_confirm_start(bot, db, call, active_timers)
            except Exception as e:
                # Логируем ошибку именно этого обработчика
                logger.critical(f"Критическая ошибка при вызове handle_confirm_start: {e}", exc_info=True)
                try:
                    # Пытаемся ответить пользователю об ошибке
                    bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                except Exception: pass
            return # Завершаем обработку в любом случае для этого колбэка

        # --- 2. Проверка состояния бронирования пользователя ---
        user_state = user_booking_states.get(user_id)
        if user_state:
            current_state_step = user_state.get('step', const.STATE_BOOKING_IDLE)
            if current_state_step != const.STATE_BOOKING_IDLE:
                current_message_id = user_state.get('message_id')
                if current_message_id:
                     if message_id != current_message_id:
                         logger.warning(f"User {user_id} нажал кнопку '{cb_data}' на старом сообщении {message_id} процесса бронирования. Активное сообщение: {current_message_id}. Игнорируем.")
                         try:
                             bot.answer_callback_query(call.id, "Пожалуйста, используйте кнопки на последнем сообщении процесса бронирования.", show_alert=True)
                         except apihelper.ApiTelegramException as e_ans_old:
                              logger.warning(f"Не удалось ответить на callback старого сообщения {message_id} процесса бронирования: {e_ans_old}")
                         return # Прерываем обработку старого сообщения

                # Проверяем, относится ли колбэк к процессу бронирования
                if cb_data.startswith(const.CB_BOOK_ACTION):
                    try:
                        # Передаем все зависимости, т.к. внутри может быть создание брони и планирование
                        process_callbacks.handle_booking_steps(
                            bot, db, call, user_state, scheduler, active_timers, scheduled_jobs_registry
                        )
                    except Exception as e:
                        # Логируем ошибку именно этого обработчика
                        logger.critical(f"Критическая ошибка при вызове handle_booking_steps: {e}", exc_info=True)
                        try:
                            # Пытаемся ответить пользователю об ошибке
                            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                        except Exception: pass
                        # Очищаем состояние при ошибке в обработчике шагов
                        clear_user_state(user_id)
                    return # Завершаем, т.к. обработано handle_booking_steps

        # --- 3. Обработка колбэков вне процесса бронирования пользователя ---
        logger.debug(f"User {user_id} не в процессе бронирования или callback не относится к процессу, обработка callback '{cb_data}'...")

        # --- 3.1 Проверка прав доступа (Админ/Активный пользователь) ---
        is_admin_user = False
        is_active_user = False
        # Блок try/except для проверки прав вынесен наружу основного try,
        # чтобы ошибка проверки прав не маскировалась другими except
        try:
            is_admin_user = userService.is_admin(db, user_id)
            if not is_admin_user:
                is_active_user = userService.is_user_registered_and_active(db, user_id)
        except Exception as e_perm_check:
            logger.error(f"Ошибка проверки прав доступа для user {user_id} при обработке callback '{cb_data}': {e_perm_check}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
            except Exception as e_ans_perm:
                logger.error(f"Не удалось ответить на callback после ошибки проверки прав: {e_ans_perm}")
            return # Прерываем, если не можем проверить права

        # Определяем, является ли действие админским по префиксу/значению
        is_admin_action = any(
            cb_data.startswith(prefix) for prefix in [
                const.CB_REG_CONFIRM_USER, const.CB_REG_DECLINE_USER,
                const.CB_MANAGE_SELECT_USER, const.CB_MANAGE_BLOCK_USER, const.CB_MANAGE_UNBLOCK_USER,
                const.CB_ADMIN_CANCEL_SELECT, const.CB_ADMIN_CANCEL_CONFIRM,
                const.CB_FILTER_BY_TYPE, const.CB_FILTER_SELECT_USER, const.CB_FILTER_SELECT_EQUIPMENT, const.CB_FILTER_SELECT_DATE,
                const.CB_EQUIP_DELETE_SELECT, const.CB_EQUIP_DELETE_CONFIRM,
                const.CB_ADMIN_ADD_EQUIP_SELECT_CAT_ # <-- Включен новый префикс
            ]
        ) or cb_data in [
                const.CB_ADMIN_ADD_EQUIP_NEW_CAT, # <-- Включен новый колбэк
                const.CB_ADMIN_ADD_EQUIP_CANCEL  # <-- Включен новый колбэк
            ]

        # Определяем, нужна ли проверка на активного пользователя
        needs_active_user_check = not (
            is_admin_action or
            cb_data == const.CB_IGNORE or
            cb_data.startswith(const.CB_ACTION_CANCEL) or
            cb_data.startswith(const.CB_BOOK_ACTION) # Процесс бронирования уже обработан выше
        )

        # Проверка прав для админских действий
        if is_admin_action:
            if not is_admin_user:
                 logger.warning(f"Пользователь {user_id} (не админ) попытался выполнить админское действие '{cb_data}'.")
                 try:
                     bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)
                 except Exception as e_ans_no_perm:
                     logger.error(f"Не удалось ответить на callback при отказе в админском доступе: {e_ans_no_perm}")
                 return # Прерываем

        # Проверка статуса для обычных пользовательских действий
        if needs_active_user_check:
            if not is_admin_user: # Админам можно все
                if not is_active_user:
                    logger.warning(f"Неактивный или незарегистрированный пользователь {user_id} попытался выполнить действие '{cb_data}'.")
                    try:
                        bot.answer_callback_query(call.id, const.MSG_ERROR_NOT_REGISTERED, show_alert=True)
                    except Exception as e_ans_not_reg:
                        logger.error(f"Не удалось ответить на callback неактивному пользователю: {e_ans_not_reg}")
                    try:
                        # Пытаемся убрать клавиатуру у старого сообщения
                        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
                    except Exception as e_edit_not_reg:
                        logger.debug(f"Не удалось убрать клавиатуру у неактивного пользователя {user_id}: {e_edit_not_reg}")
                    return # Прерываем

        # --- 3.2 Маршрутизация колбэков через словарь ---
        handler_found = False
        matched_handler: Optional[Callable] = None
        matched_prefix: Optional[str] = None

        # Сначала ищем точное совпадение
        if cb_data in CALLBACK_ROUTES:
            matched_handler = CALLBACK_ROUTES[cb_data]
            matched_prefix = cb_data
            handler_found = True
        else:
            # Затем ищем по префиксу (если ключ заканчивается на '_')
            for prefix, handler in CALLBACK_ROUTES.items():
                if prefix.endswith('_') and cb_data.startswith(prefix):
                    matched_handler = handler
                    matched_prefix = prefix
                    handler_found = True
                    break

        # Если обработчик найден
        if handler_found and matched_handler and matched_prefix:
            logger.debug(f"Маршрутизация callback '{cb_data}' к обработчику для '{matched_prefix}'")
            # Внутренний try/except для ошибки выполнения конкретного обработчика
            try:
                # --- Определение необходимых аргументов для вызова ---
                # (Логика передачи аргументов остается прежней, т.к. новые обработчики
                # CB_ADMIN_ADD_EQUIP_* попадают в блок else)
                if matched_prefix == const.CB_EXTEND_SELECT_TIME:
                     matched_handler(bot, db, call, scheduler, active_timers, scheduled_jobs_registry)
                elif matched_prefix == const.CB_ADMIN_CANCEL_CONFIRM:
                     matched_handler(bot, db, call, scheduler, scheduled_jobs_registry)
                elif matched_prefix in [
                    const.CB_CANCEL_SELECT_BOOKING,
                    const.CB_FINISH_SELECT_BOOKING
                ]:
                     matched_handler(bot, db, call, scheduler, scheduled_jobs_registry)
                elif matched_prefix in [
                    const.CB_NOTIFY_EXTEND_PROMPT
                ]:
                     matched_handler(bot, db, call, active_timers)
                elif matched_prefix == const.CB_NOTIFY_DECLINE_EXT:
                     matched_handler(bot, call, active_timers)
                elif matched_prefix == const.CB_IGNORE:
                     matched_handler(bot, call)
                else:
                     # Все остальные, включая новые CB_ADMIN_ADD_EQUIP_*, вызываются с (bot, db, call)
                     matched_handler(bot, db, call)
            except Exception as e_handler: # Ловим ошибку выполнения конкретного хендлера
                logger.critical(f"Критическая ошибка при вызове обработчика для '{matched_prefix}' (cb='{cb_data}'): {e_handler}", exc_info=True)
                try:
                    # Отвечаем пользователю об ошибке
                    bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                except Exception as e_ans_handler_exc:
                     logger.error(f"Не удалось ответить на callback после ошибки обработчика '{matched_prefix}': {e_ans_handler_exc}")
        else:
            # Если ни один маршрут не подошел
            logger.warning(f"Получен необработанный callback от user {user_id}: '{cb_data}'")
            try:
                bot.answer_callback_query(call.id, "Неизвестное действие.")
            except Exception as e_ans_unknown:
                 logger.warning(f"Не удалось ответить на неизвестный callback '{cb_data}': {e_ans_unknown}")

    # --- БЛОКИ EXCEPT ДЛЯ ОСНОВНОГО TRY (БЕЗ ИЗМЕНЕНИЙ) ---
    except (ValueError, TypeError) as e_parse:
        # Ошибки парсинга данных из callback_data (например, неверный ID)
        logger.error(f"Ошибка парсинга данных callback '{cb_data}' от user {user_id}: {e_parse}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "Ошибка в данных запроса.", show_alert=True)
        except Exception as e_ans_parse:
            logger.error(f"Не удалось ответить на callback после ошибки парсинга: {e_ans_parse}")
    except IndexError as e_index:
        # Ошибки индекса (например, при разделении callback_data)
        logger.error(f"Ошибка индекса при обработке callback '{cb_data}' от user {user_id}: {e_index}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "Ошибка обработки данных.", show_alert=True)
        except Exception as e_ans_index:
            logger.error(f"Не удалось ответить на callback после ошибки индекса: {e_ans_index}")
    except apihelper.ApiTelegramException as e_api:
        # Обработка специфичных ошибок API Telegram
        error_text = str(e_api).lower()
        if "message is not modified" in error_text:
            logger.debug(f"Сообщение {message_id} не было изменено (API).")
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
        elif "message to edit not found" in error_text or "message can't be edited" in error_text:
            logger.warning(f"Сообщение {message_id} не найдено или не может быть отредактировано (API).")
            try:
                bot.answer_callback_query(call.id, "Сообщение устарело или недоступно.", show_alert=True)
            except Exception:
                pass
        elif "message to delete not found" in error_text:
            logger.warning(f"Сообщение {message_id} не найдено для удаления (API).")
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
        elif "bot was blocked by the user" in error_text or "user is deactivated" in error_text:
             logger.warning(f"Бот заблокирован пользователем {user_id} или пользователь деактивирован.")
             try:
                 bot.answer_callback_query(call.id)
             except Exception:
                 pass
             temp_db = None
             try:
                 temp_db = Database()
                 userService.handle_user_blocked_bot(temp_db, user_id)
             except Exception as e_block_handle:
                 logger.error(f"Ошибка обработки блокировки бота пользователем {user_id}: {e_block_handle}")
             finally:
                  if temp_db:
                      # Предполагаем статический пул
                      pass
        else:
            # Другие ошибки API
            logger.error(f"Необработанная ошибка Telegram API при обработке callback '{cb_data}' user {user_id}: {e_api}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "Произошла ошибка при взаимодействии с Telegram.", show_alert=True)
            except Exception as e_ans_api_other:
                 logger.error(f"Не удалось ответить на callback после необработанной ошибки API: {e_ans_api_other}")

    except Exception as e_global:
        # Ловим любые другие непредвиденные ошибки
        logger.critical(f"Критическая непредвиденная ошибка при обработке callback '{cb_data}' от user {user_id}: {e_global}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception as e_ans_crit:
            logger.error(f"Не удалось ответить на callback после критической ошибки: {e_ans_crit}")


# --- Регистрация обработчиков (БЕЗ ИЗМЕНЕНИЙ) ---
def register_callback_handlers(
    bot: telebot.TeleBot,
    db: Database,
    scheduler: Optional[BackgroundScheduler],
    active_timers: Dict[int, Any],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """Регистрирует основной обработчик для всех inline callback-запросов."""

    @bot.callback_query_handler(func=lambda call: True)
    def main_callback_dispatcher(call: CallbackQuery):
        # Вызываем основной диспетчер, передавая все зависимости
        handle_callback_query(bot, db, scheduler, active_timers, scheduled_jobs_registry, call)

    logger.info("Основной обработчик callback-запросов успешно зарегистрирован.")

# --- END OF FILE callback_handlers.py ---