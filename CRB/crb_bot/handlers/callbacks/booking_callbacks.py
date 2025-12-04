# --- START OF FILE handlers/callbacks/booking_callbacks.py ---
"""
Обработчики callback-запросов, связанных с управлением бронированиями.

Отвечает за:
- Отмену бронирования пользователем.
- Завершение бронирования пользователем.
- Выбор брони для продления.
- Выбор времени продления.
"""
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime, date, time, timedelta

from database import Database
from logger import logger
import constants as const # Используем обновленные константы
import services.booking_service as bookingService # Уже адаптирован
import services.notification_service as notificationService # Уже адаптирован
# --- ИЗМЕНЕНО: Импорт сервиса комнат (для handle_extend_select_booking, если понадобится имя) ---
import services.conference_room_service as room_service
# --- КОНЕЦ ИЗМЕНЕНИЯ ---
from utils import keyboards # Уже адаптирован
from apscheduler.schedulers.background import BackgroundScheduler

from utils.message_utils import edit_or_send_message

# --- Обработчики ---

def handle_cancel_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    scheduler: Optional[BackgroundScheduler],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """
    Обрабатывает нажатие кнопки отмены бронирования пользователем.
    (Префикс: const.CB_CANCEL_SELECT_BOOKING)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    booking_id_str = cb_data[len(const.CB_CANCEL_SELECT_BOOKING):]
    booking_id = None
    try: booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_CANCEL_SELECT_BOOKING от user {user_id}")
        try: bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return

    logger.info(f"User {user_id} инициировал отмену брони {booking_id}")
    try: bot.answer_callback_query(call.id, "Отменяем бронирование...")
    except Exception: pass

    success = False
    msg = const.MSG_ERROR_GENERAL
    owner_user_id_unused = None
    try:
        # Вызываем адаптированный сервис
        success, msg, owner_user_id_unused = bookingService.cancel_booking(db, booking_id, user_id=user_id, is_admin_cancel=False)
    except Exception as e_cancel_logic:
        logger.error(f"Ошибка в cancel_booking для booking {booking_id}, user {user_id}: {e_cancel_logic}", exc_info=True)
        success = False; msg = const.MSG_ERROR_GENERAL

    if msg is None: logger.error(f"cancel_booking не вернул сообщение для брони {booking_id}"); msg = const.MSG_ERROR_GENERAL

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown"}
    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    if success and scheduler:
        logger.debug(f"Бронь {booking_id} отменена пользователем, очищаем связанные задачи...")
        try: notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
        except Exception as e_cleanup: logger.error(f"Ошибка очистки задач после отмены брони {booking_id}: {e_cleanup}", exc_info=True)
    elif success and not scheduler: logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")


def handle_finish_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    scheduler: Optional[BackgroundScheduler],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """
    Обрабатывает нажатие кнопки завершения бронирования пользователем.
    (Префикс: const.CB_FINISH_SELECT_BOOKING)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    booking_id_str = cb_data[len(const.CB_FINISH_SELECT_BOOKING):]
    booking_id = None
    try: booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_FINISH_SELECT_BOOKING от user {user_id}")
        try: bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return

    logger.info(f"User {user_id} инициировал завершение брони {booking_id}")
    try: bot.answer_callback_query(call.id, "Завершаю бронирование...")
    except Exception: pass

    success = False
    msg = None
    try:
        # Вызываем адаптированный сервис
        success, msg = bookingService.finish_booking(db, booking_id, user_id)
    except Exception as e_finish_logic:
        logger.error(f"Ошибка в finish_booking для booking {booking_id}, user {user_id}: {e_finish_logic}", exc_info=True)
        success = False; msg = const.MSG_ERROR_GENERAL

    if msg is None: logger.error(f"finish_booking не вернул сообщение для брони {booking_id}"); msg = const.MSG_ERROR_GENERAL

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown"}
    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    if success and scheduler:
         logger.debug(f"Бронь {booking_id} завершена пользователем, очищаем связанные задачи...")
         try: notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
         except Exception as e_cleanup_finish: logger.error(f"Ошибка очистки задач после завершения брони {booking_id}: {e_cleanup_finish}", exc_info=True)
    elif success and not scheduler: logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")


def handle_extend_select_booking(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    """
    Проверяет возможность продления и показывает варианты времени (шаг 1).
    (Префикс: const.CB_EXTEND_SELECT_BOOKING)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    booking_id = None
    booking_id_str = ""
    source = "из команды /extend или уведомления" # Источник больше не важен здесь

    # Извлекаем booking_id
    if cb_data.startswith(const.CB_EXTEND_SELECT_BOOKING):
        prefix_len = len(const.CB_EXTEND_SELECT_BOOKING)
        booking_id_str = cb_data[prefix_len:]
    elif cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT): # Обрабатываем и нажатие "Продлить" из уведомления
        prefix_len = len(const.CB_NOTIFY_EXTEND_PROMPT)
        booking_id_str = cb_data[prefix_len:]
    else: # Добавим обработку непредвиденного случая
        logger.error(f"Неизвестный префикс '{cb_data}' в handle_extend_select_booking от user {user_id}")
        try: bot.answer_callback_query(call.id, "Неизвестное действие.", show_alert=True)
        except Exception: pass
        return

    try: booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в колбэке продления от user {user_id} (data: {cb_data})")
        try: bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return

    try: bot.answer_callback_query(call.id, "Проверяю возможность продления...")
    except Exception: pass

    kwargs_edit = {}
    booking_info: Optional[Dict[str, Any]] = None
    owner_id = None
    b_status = None
    cr_id = None # <-- ID комнаты
    current_end_dt: Optional[datetime] = None

    try:
        booking_info = bookingService.find_booking_by_id(db, booking_id)
        if booking_info:
            owner_id = booking_info.get('user_id')
            b_status = booking_info.get('status')
            cr_id = booking_info.get('cr_id') # <-- Получаем ID комнаты
            current_end_dt = booking_info.get('time_end') # Должен быть datetime

            # Проверка типа current_end_dt
            if not isinstance(current_end_dt, datetime):
                 logger.error(f"Некорректный тип time_end ({type(current_end_dt)}) для брони {booking_id} при продлении.")
                 current_end_dt = None # Сбрасываем, чтобы вызвать ошибку ниже

    except Exception as e_find_ext:
        logger.error(f"Ошибка поиска брони {booking_id} для продления (user {user_id}): {e_find_ext}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return

    # Проверки возможности продления
    msg_err = None
    alert_msg = None
    now_dt = datetime.now() # Время с таймзоной, если настроено

    if not booking_info: msg_err = const.MSG_EXTEND_FAIL_NOT_FOUND; alert_msg = "Бронь не найдена."
    elif owner_id != user_id: msg_err = "Это не ваше бронирование."; alert_msg = "Это не ваше бронь."
    elif b_status != 'active': msg_err = const.MSG_EXTEND_FAIL_NOT_ACTIVE; alert_msg = "Бронь не активна."
    elif not current_end_dt or cr_id is None: # <-- Проверяем cr_id
        msg_err = const.MSG_ERROR_GENERAL; alert_msg = "Ошибка данных брони."
        logger.error(f"Отсутствуют current_end_dt={current_end_dt} или cr_id={cr_id} для брони {booking_id} при попытке продления.")
    elif current_end_dt <= now_dt: # Сравниваем aware datetime
        msg_err = "Время бронирования истекло."; alert_msg = "Время бронирования истекло."
        logger.warning(f"User {user_id} пытается продлить истекшую бронь {booking_id}. End: {current_end_dt}, Now: {now_dt}")

    if msg_err:
        try: bot.answer_callback_query(call.id, alert_msg, show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, msg_err, reply_markup=None, **kwargs_edit)
        return

    # Расчет доступного времени для продления
    next_booking_start_dt: Optional[datetime] = None
    try:
        # Ищем следующую бронь для комнаты cr_id
        next_booking = bookingService.find_next_booking(db, cr_id, current_end_dt)
        if next_booking:
            next_start_time = next_booking.get('time_start')
            if isinstance(next_start_time, datetime):
                next_booking_start_dt = next_start_time
            else:
                 logger.warning(f"Некорректное time_start следующей брони для cr_id={cr_id}: {next_start_time}")
    except Exception as e_find_next:
        logger.error(f"Ошибка поиска следующей брони для комнаты {cr_id} после {current_end_dt} (продление {booking_id}): {e_find_next}", exc_info=True)

    # Определяем конец доступного интервала
    end_of_workday_dt = datetime.combine(current_end_dt.date(), const.WORKING_HOURS_END).replace(tzinfo=current_end_dt.tzinfo) # Сохраняем tzinfo
    available_until_dt = end_of_workday_dt
    if next_booking_start_dt and next_booking_start_dt < available_until_dt:
        available_until_dt = next_booking_start_dt

    # Расчет максимальной длительности
    max_duration_available = timedelta(0)
    if available_until_dt > current_end_dt:
        delta = available_until_dt - current_end_dt
        total_minutes = int(delta.total_seconds() // 60)
        # Округляем вниз до ближайшего шага
        allowed_minutes = (total_minutes // const.BOOKING_TIME_STEP_MINUTES) * const.BOOKING_TIME_STEP_MINUTES
        if allowed_minutes > 0:
            max_duration_available = timedelta(minutes=allowed_minutes)

    logger.debug(f"Максимальное доступное время для продления брони {booking_id}: {max_duration_available}")

    if max_duration_available > timedelta(0):
        markup = keyboards.generate_extend_time_keyboard(booking_id, max_duration=max_duration_available)
        # Формируем текст запроса
        prompt_text = "Выберите время продления (текущее окончание {end_time}):".format(
            end_time=current_end_dt.strftime('%H:%M')
        )
        edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit)
    else:
        logger.info(f"Нет доступного времени для продления брони {booking_id}.")
        edit_or_send_message(bot, chat_id, message_id, const.MSG_EXTEND_FAIL_NO_TIME, reply_markup=None, **kwargs_edit)


def handle_extend_select_time(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    scheduler: Optional[BackgroundScheduler],
    active_timers: Dict[int, Any],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """
    Выполняет продление брони на выбранное время (шаг 2).
    (Префикс: const.CB_EXTEND_SELECT_TIME)
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    # Извлекаем booking_id и extension_str (логика остается)
    data_part = cb_data[len(const.CB_EXTEND_SELECT_TIME):]
    parts = data_part.split('_')
    booking_id = None
    extension_str = None
    if len(parts) == 2:
        try:
            booking_id = int(parts[0])
            extension_str = parts[1]
            if len(extension_str.split(':')) != 2: raise ValueError("Неверный формат времени")
        except (ValueError, IndexError) as e_parse_ext:
            logger.error(f"Неверный формат данных '{data_part}' в CB_EXTEND_SELECT_TIME от user {user_id}: {e_parse_ext}")
            try: bot.answer_callback_query(call.id, "Ошибка данных для продления.", show_alert=True)
            except Exception: pass
            return
    else:
        logger.error(f"Неверное количество частей '{len(parts)}' в CB_EXTEND_SELECT_TIME от user {user_id}")
        try: bot.answer_callback_query(call.id, "Ошибка формата колбэка.", show_alert=True)
        except Exception: pass
        return

    logger.info(f"User {user_id} выбрал продление на {extension_str} для брони {booking_id}")

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown"}

    # Повторная проверка перед выполнением (остается полезной)
    booking_info_recheck: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)
    msg_err_recheck = None
    alert_msg_recheck = None
    if not booking_info_recheck: msg_err_recheck = const.MSG_EXTEND_FAIL_NOT_FOUND; alert_msg_recheck = "Бронь не найдена."
    elif booking_info_recheck.get('user_id') != user_id: msg_err_recheck = "Это не ваше бронирование."; alert_msg_recheck = "Это не ваша бронь."
    elif booking_info_recheck.get('status') != 'active': msg_err_recheck = const.MSG_EXTEND_FAIL_NOT_ACTIVE; alert_msg_recheck = "Бронь не активна."
    elif not isinstance(booking_info_recheck.get('time_end'), datetime) or booking_info_recheck.get('time_end') <= datetime.now(): msg_err_recheck = "Время бронирования истекло."; alert_msg_recheck = "Время бронирования истекло."

    if msg_err_recheck:
        logger.warning(f"Повторная проверка перед продлением брони {booking_id} не пройдена: {alert_msg_recheck}")
        try: bot.answer_callback_query(call.id, alert_msg_recheck, show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, msg_err_recheck, **kwargs_edit)
        return

    try: bot.answer_callback_query(call.id, f"Продлеваю бронирование на {extension_str}...")
    except Exception: pass

    success = False
    msg = const.MSG_BOOKING_FAIL_GENERAL
    try:
        # Вызываем адаптированный сервис
        success, msg = bookingService.extend_booking(db, booking_id, user_id, extension_str)
    except ValueError as e_val_extend:
        logger.warning(f"Ошибка валидации при продлении брони {booking_id} на {extension_str}: {e_val_extend}")
        success = False
        msg = str(e_val_extend)
    except Exception as e_extend_logic:
        logger.error(f"Ошибка при выполнении продления брони {booking_id} на {extension_str}: {e_extend_logic}", exc_info=True)
        success = False
        msg = const.MSG_BOOKING_FAIL_GENERAL

    if msg is None: logger.error(f"extend_booking не вернул сообщение для брони {booking_id}"); msg = const.MSG_ERROR_GENERAL

    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    # --- ДОБАВИТЬ ЛОГИРОВАНИЕ ---
    logger.debug(
        f"Проверка перед перепланировкой для брони {booking_id}: success={success}, scheduler is None={scheduler is None}")
    # --- КОНЕЦ ДОБАВЛЕНИЯ ---

    if success and scheduler:
        logger.debug(f"Бронь {booking_id} успешно продлена, обновляем уведомления (ВЫЗЫВАЕМ schedule_all_notifications)...")
        try:
            # Вызываем перепланировку уведомлений (используются глобальные зависимости внутри сервиса)
            notificationService.schedule_all_notifications()
        except Exception as e_reschedule:
            logger.error(f"Ошибка перепланирования уведомлений после продления брони {booking_id}: {e_reschedule}", exc_info=True)
    elif success and not scheduler: logger.warning("Планировщик (scheduler) не передан, уведомления не обновлены после продления.")


# --- END OF FILE handlers/callbacks/booking_callbacks.py ---