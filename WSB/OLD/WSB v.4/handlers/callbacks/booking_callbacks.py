# --- START OF FILE handlers/callbacks/booking_callbacks.py ---
"""
Обработчики callback-запросов, связанных с управлением бронированиями.

Отвечает за:
- Отмену бронирования пользователем (из /mybookings).
- Завершение бронирования пользователем (из /finish).
- Выбор брони для продления (из команды /extend).
- Выбор времени продления.
"""
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime, date, time, timedelta

from database import Database
from logger import logger
import constants as const
import services.booking_service as bookingService
import services.notification_service as notificationService
import services.equipment_service as equipmentService # Может понадобиться для получения имени
from utils import keyboards
from apscheduler.schedulers.background import BackgroundScheduler

# Импортируем хелпер для редактирования/отправки сообщений из utils
from utils.message_utils import edit_or_send_message

# --- Обработчики ---

def handle_cancel_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    scheduler: Optional[BackgroundScheduler],
    scheduled_jobs_registry: Set[Tuple[str, int]]
    # Убран лишний аргумент active_timers
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
    try:
        booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_CANCEL_SELECT_BOOKING от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception:
            pass
        return

    logger.info(f"User {user_id} инициировал отмену брони {booking_id}")
    try:
        bot.answer_callback_query(call.id, "Отменяем бронирование...")
    except Exception as e_ans_cancel:
        logger.warning(f"Не удалось ответить на callback отмены {booking_id}: {e_ans_cancel}")

    success = False
    msg = const.MSG_ERROR_GENERAL # Сообщение по умолчанию при непредвиденной ошибке
    owner_user_id_unused = None
    try:
        # Сервис должен вернуть (True, MSG_BOOKING_CANCELLED) или (False, "Причина неудачи")
        success, msg, owner_user_id_unused = bookingService.cancel_booking(db, booking_id, user_id=user_id, is_admin_cancel=False)
    except Exception as e_cancel_logic:
        logger.error(f"Ошибка в cancel_booking для booking {booking_id}, user {user_id}: {e_cancel_logic}", exc_info=True)
        success = False
        msg = const.MSG_ERROR_GENERAL # Перезаписываем на общую ошибку при исключении

    if msg is None:
        logger.error(f"cancel_booking не вернул сообщение для брони {booking_id}")
        msg = const.MSG_ERROR_GENERAL

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}
    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    if success:
         if scheduler:
             logger.debug(f"Бронь {booking_id} отменена пользователем, очищаем связанные задачи...")
             try:
                 notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
             except Exception as e_cleanup:
                 logger.error(f"Ошибка очистки задач после отмены брони {booking_id}: {e_cleanup}", exc_info=True)
         else:
             logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")


def handle_finish_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    scheduler: Optional[BackgroundScheduler],
    scheduled_jobs_registry: Set[Tuple[str, int]]
    # Убран лишний аргумент active_timers
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
    try:
        booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в CB_FINISH_SELECT_BOOKING от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception:
            pass
        return

    logger.info(f"User {user_id} инициировал завершение брони {booking_id}")
    try:
        bot.answer_callback_query(call.id, "Завершаю бронирование...")
    except Exception as e_ans_finish:
         logger.warning(f"Не удалось ответить на callback завершения {booking_id}: {e_ans_finish}")

    success = False
    msg = None
    try:
        # Сервис finish_booking должен вернуть (True, MSG_BOOKING_FINISHED) или (False, "Причина ошибки")
        success, msg = bookingService.finish_booking(db, booking_id, user_id)
    except Exception as e_finish_logic:
        logger.error(f"Ошибка в finish_booking для booking {booking_id}, user {user_id}: {e_finish_logic}", exc_info=True)
        success = False
        msg = const.MSG_ERROR_GENERAL

    if msg is None:
        logger.error(f"finish_booking не вернул сообщение для брони {booking_id}")
        msg = const.MSG_ERROR_GENERAL

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}
    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    if success:
         if scheduler:
             logger.debug(f"Бронь {booking_id} завершена пользователем, очищаем связанные задачи...")
             try:
                 notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
             except Exception as e_cleanup_finish:
                  logger.error(f"Ошибка очистки задач после завершения брони {booking_id}: {e_cleanup_finish}", exc_info=True)
             else:
                 logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")


# --- START OF MODIFIED FUNCTION handle_extend_select_booking ---
def handle_extend_select_booking(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    # Убираем user_id, chat_id, message_id, booking_id, source из аргументов
):
    """
    Проверяет возможность продления и показывает варианты времени (шаг 1).
    Вызывается из /extend или из notification_callbacks.
    (Префикс: const.CB_EXTEND_SELECT_BOOKING)
    """
    # --- ИЗМЕНЕНИЕ: Извлекаем данные из call ---
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    # Определяем booking_id и source
    booking_id = None
    source = "неизвестно"
    booking_id_str = ""

    if cb_data.startswith(const.CB_EXTEND_SELECT_BOOKING):
        prefix_len = len(const.CB_EXTEND_SELECT_BOOKING)
        booking_id_str = cb_data[prefix_len:]
        source = "из команды /extend"
    # Эта функция больше не вызывается напрямую для CB_NOTIFY_EXTEND_PROMPT,
    # но оставим проверку на всякий случай или для будущего рефакторинга
    elif cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT):
        prefix_len = len(const.CB_NOTIFY_EXTEND_PROMPT)
        booking_id_str = cb_data[prefix_len:]
        source = "из уведомления"

    try:
        booking_id = int(booking_id_str)
    except ValueError:
        logger.error(f"Неверный booking_id '{booking_id_str}' в колбэке продления от user {user_id} (data: {cb_data})")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    try:
        # Отвечаем на коллбэк здесь, а не в вызывающей функции
        bot.answer_callback_query(call.id, "Проверяю возможность продления...")
    except Exception as e_ans_ext_sel:
        logger.warning(f"Не удалось ответить на callback выбора продления {booking_id} ({source}): {e_ans_ext_sel}")

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'user_id_for_state_update': user_id}
    booking_info: Optional[Dict[str, Any]] = None
    owner_id = None
    is_cancelled = True
    is_finished = True
    equip_id = None
    current_end_dt: Optional[datetime] = None

    try:
        booking_info = bookingService.find_booking_by_id(db, booking_id)
        if booking_info:
            owner_id = booking_info.get('user_id')
            is_cancelled = booking_info.get('cancel', False)
            is_finished = booking_info.get('finish') is not None
            equip_id = booking_info.get('equip_id')
            date_val = booking_info.get('date')
            end_time_val = booking_info.get('time_end')

            # --- Логика извлечения даты и времени ---
            date_obj = None
            time_obj = None
            if isinstance(date_val, date): date_obj = date_val
            elif isinstance(date_val, str):
                try: date_obj = datetime.strptime(date_val, '%Y-%m-%d').date()
                except ValueError: logger.error(f"Некорректный формат date (строка) для брони {booking_id} при продлении: {date_val}")
            else: logger.error(f"Неподдерживаемый тип date для брони {booking_id} при продлении: {type(date_val)}")

            if isinstance(end_time_val, datetime): time_obj = end_time_val.time()
            elif isinstance(end_time_val, time): time_obj = end_time_val
            elif isinstance(end_time_val, str):
                try: time_obj = datetime.strptime(end_time_val, '%Y-%m-%d %H:%M:%S').time()
                except ValueError:
                    try: time_obj = datetime.strptime(end_time_val, '%H:%M:%S').time()
                    except ValueError: logger.error(f"Некорректный формат time_end (строка) для брони {booking_id} при продлении: {end_time_val}")
            else: logger.error(f"Неподдерживаемый тип time_end для брони {booking_id} при продлении: {type(end_time_val)}")

            if date_obj and time_obj: current_end_dt = datetime.combine(date_obj, time_obj)
            else: logger.error(f"Не удалось сформировать current_end_dt для брони {booking_id} при продлении: date={date_val}, time_end={end_time_val}")
            # --- Конец логики извлечения ---

    except Exception as e_find_ext:
        logger.error(f"Ошибка поиска брони {booking_id} для продления (user {user_id}, {source}): {e_find_ext}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return

    # Проверки возможности продления
    msg_err = None
    alert_msg = None
    now_naive = datetime.now().replace(tzinfo=None)

    if not booking_info:
        msg_err = const.MSG_EXTEND_FAIL_NOT_FOUND
        alert_msg = "Бронь не найдена."
    elif owner_id != user_id:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_NOT_OWNER', "Это не ваша бронь.")
        alert_msg = "Это не ваша бронь."
    elif is_cancelled:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_CANCELLED', "Бронь отменена.")
        alert_msg = "Бронь отменена."
    elif is_finished:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_FINISHED', "Бронь уже завершена.")
        alert_msg = "Бронь уже завершена."
    elif not current_end_dt or equip_id is None:
        msg_err = const.MSG_ERROR_GENERAL
        alert_msg = "Ошибка данных брони."
        logger.error(f"Отсутствуют current_end_dt={current_end_dt} или equip_id={equip_id} для брони {booking_id} при попытке продления.")
    elif current_end_dt <= now_naive:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_EXPIRED', "Время бронирования истекло.")
        alert_msg = "Время бронирования истекло."
        logger.warning(f"User {user_id} пытается продлить истекшую бронь {booking_id} ({source}). End: {current_end_dt}, Now: {now_naive}")

    if msg_err:
        try:
            # Отвечаем на коллбэк с ошибкой, если он еще не был отвечен
            bot.answer_callback_query(call.id, alert_msg, show_alert=True)
        except apihelper.ApiTelegramException as e_ans_api:
            if "query is too old" not in str(e_ans_api).lower():
                 logger.warning(f"Не удалось ответить на callback с ошибкой продления {booking_id}: {e_ans_api}")
        except Exception as e_ans_err:
            logger.warning(f"Не удалось ответить на callback с ошибкой продления {booking_id}: {e_ans_err}")
        edit_or_send_message(bot, chat_id, message_id, msg_err, reply_markup=None, **kwargs_edit)
        return

    # Расчет доступного времени для продления
    next_booking_start_dt: Optional[datetime] = None
    try:
        next_booking = bookingService.find_next_booking(db, equip_id, current_end_dt)
        if next_booking:
            next_start_time = next_booking.get('time_start')
            # --- Логика извлечения времени следующей брони ---
            if isinstance(next_start_time, datetime):
                next_booking_start_dt = next_start_time
            elif isinstance(next_start_time, time) and isinstance(current_end_dt, datetime):
                next_booking_start_dt = datetime.combine(current_end_dt.date(), next_start_time)
                if next_booking_start_dt <= current_end_dt:
                     next_booking_start_dt += timedelta(days=1)
            else:
                logger.warning(f"Некорректное time_start следующей брони для equip_id={equip_id}: {next_start_time}")
            # --- Конец логики извлечения ---
    except Exception as e_find_next:
        logger.error(f"Ошибка поиска следующей брони для equip {equip_id} после {current_end_dt} (продление {booking_id}): {e_find_next}", exc_info=True)

    # Определяем конец доступного интервала
    end_of_workday_dt = datetime.combine(current_end_dt.date(), const.WORKING_HOURS_END)
    available_until_dt = end_of_workday_dt
    if next_booking_start_dt and next_booking_start_dt < available_until_dt:
        available_until_dt = next_booking_start_dt

    max_duration_available = timedelta(0)
    if available_until_dt > current_end_dt:
        delta = available_until_dt - current_end_dt
        total_minutes = int(delta.total_seconds() // 60)
        allowed_minutes = (total_minutes // const.BOOKING_TIME_STEP_MINUTES) * const.BOOKING_TIME_STEP_MINUTES
        if allowed_minutes > 0:
            max_duration_available = timedelta(minutes=allowed_minutes)

    logger.debug(f"Максимальное доступное время для продления брони {booking_id} ({source}): {max_duration_available}")

    if max_duration_available > timedelta(0):
        markup = keyboards.generate_extend_time_keyboard(booking_id, max_duration=max_duration_available)
        prompt_text = getattr(const, 'MSG_EXTEND_PROMPT_TIME', "Выберите время продления (текущее окончание {end_time}):").format(
            end_time=current_end_dt.strftime('%H:%M')
        )
        edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit)
    else:
        logger.info(f"Нет доступного времени для продления брони {booking_id} ({source}).")
        edit_or_send_message(bot, chat_id, message_id, const.MSG_EXTEND_FAIL_NO_TIME, reply_markup=None, **kwargs_edit)

# --- END OF MODIFIED FUNCTION handle_extend_select_booking ---


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

    # Извлекаем booking_id и extension_str
    data_part = cb_data[len(const.CB_EXTEND_SELECT_TIME):]
    parts = data_part.split('_')
    booking_id = None
    extension_str = None
    if len(parts) == 2:
        try:
            booking_id = int(parts[0])
            extension_str = parts[1] # Формат HH:MM
            if len(extension_str.split(':')) != 2:
                 raise ValueError("Неверный формат времени продления")
        except (ValueError, IndexError) as e_parse_ext:
            logger.error(f"Неверный формат данных '{data_part}' в CB_EXTEND_SELECT_TIME от user {user_id}: {e_parse_ext}")
            try:
                bot.answer_callback_query(call.id, "Ошибка данных для продления.", show_alert=True)
            except Exception: pass
            return # Выход
    else:
        logger.error(f"Неверное количество частей '{len(parts)}' в CB_EXTEND_SELECT_TIME от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка формата колбэка.", show_alert=True)
        except Exception: pass
        return # Выход

    logger.info(f"User {user_id} выбрал продление на {extension_str} для брони {booking_id}")

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    # --- Повторная проверка возможности продления перед выполнением ---
    booking_info_recheck: Optional[Dict[str, Any]] = None
    owner_id_recheck = None
    is_cancelled_recheck = True
    is_finished_recheck = True
    current_end_dt_recheck: Optional[datetime] = None
    try:
        booking_info_recheck = bookingService.find_booking_by_id(db, booking_id)
        if booking_info_recheck:
            owner_id_recheck = booking_info_recheck.get('user_id')
            is_cancelled_recheck = booking_info_recheck.get('cancel', False)
            is_finished_recheck = booking_info_recheck.get('finish') is not None
            date_val_rc = booking_info_recheck.get('date')
            end_time_val_rc = booking_info_recheck.get('time_end')

            # --- Логика извлечения даты и времени (повторно) ---
            date_obj_rc = None
            time_obj_rc = None
            if isinstance(date_val_rc, date): date_obj_rc = date_val_rc
            elif isinstance(date_val_rc, str):
                try: date_obj_rc = datetime.strptime(date_val_rc, '%Y-%m-%d').date()
                except ValueError: logger.error(f"Некорректный формат date (строка) для брони {booking_id} при речеке продления: {date_val_rc}")
            else: logger.error(f"Неподдерживаемый тип date для брони {booking_id} при речеке продления: {type(date_val_rc)}")

            if isinstance(end_time_val_rc, datetime): time_obj_rc = end_time_val_rc.time()
            elif isinstance(end_time_val_rc, time): time_obj_rc = end_time_val_rc
            elif isinstance(end_time_val_rc, str):
                try: time_obj_rc = datetime.strptime(end_time_val_rc, '%Y-%m-%d %H:%M:%S').time()
                except ValueError:
                    try: time_obj_rc = datetime.strptime(end_time_val_rc, '%H:%M:%S').time()
                    except ValueError: logger.error(f"Некорректный формат time_end (строка) для брони {booking_id} при речеке продления: {end_time_val_rc}")
            else: logger.error(f"Неподдерживаемый тип time_end для брони {booking_id} при речеке продления: {type(end_time_val_rc)}")

            if date_obj_rc and time_obj_rc: current_end_dt_recheck = datetime.combine(date_obj_rc, time_obj_rc)
            else: logger.error(f"Не удалось сформировать current_end_dt_recheck для брони {booking_id} при речеке продления: date={date_val_rc}, time_end={end_time_val_rc}")
            # --- Конец логики извлечения ---

    except Exception as e_find_recheck:
         logger.error(f"Ошибка повторной проверки брони {booking_id} перед продлением: {e_find_recheck}", exc_info=True)
         edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)
         return # Выход

    msg_err_recheck = None
    alert_msg_recheck = None
    now_naive_recheck = datetime.now().replace(tzinfo=None)

    if not booking_info_recheck: msg_err_recheck = const.MSG_EXTEND_FAIL_NOT_FOUND; alert_msg_recheck = "Бронь не найдена."
    elif owner_id_recheck != user_id: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_NOT_OWNER', "Это не ваша бронь."); alert_msg_recheck = "Это не ваша бронь."
    elif is_cancelled_recheck: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_CANCELLED', "Бронь отменена."); alert_msg_recheck = "Бронь отменена."
    elif is_finished_recheck: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_FINISHED', "Бронь уже завершена."); alert_msg_recheck = "Бронь уже завершена."
    elif not current_end_dt_recheck: msg_err_recheck = const.MSG_ERROR_GENERAL; alert_msg_recheck = "Ошибка данных брони."
    elif current_end_dt_recheck <= now_naive_recheck: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_EXPIRED', "Время бронирования истекло."); alert_msg_recheck = "Время бронирования истекло."

    if msg_err_recheck:
        logger.warning(f"Повторная проверка перед продлением брони {booking_id} не пройдена: {alert_msg_recheck}")
        try:
            bot.answer_callback_query(call.id, alert_msg_recheck, show_alert=True)
        except Exception as e_ans_recheck_fail:
            logger.warning(f"Не удалось ответить на callback после неудачной повторной проверки {booking_id}: {e_ans_recheck_fail}")
        edit_or_send_message(bot, chat_id, message_id, msg_err_recheck, **kwargs_edit)
        return # Выход
    # --- Конец повторной проверки ---

    try:
        bot.answer_callback_query(call.id, f"Продлеваю бронирование на {extension_str}...")
    except Exception as e_ans_ext_time:
         logger.warning(f"Не удалось ответить на callback выбора времени продления {booking_id} на {extension_str}: {e_ans_ext_time}")

    success = False
    msg = const.MSG_BOOKING_FAIL_GENERAL # Сообщение по умолчанию при ошибке
    try:
        # Вызываем сервис для выполнения продления
        success, msg = bookingService.extend_booking(db, booking_id, user_id, extension_str)
    except ValueError as e_val_extend: # Ловим ошибки валидации времени из сервиса
        logger.warning(f"Ошибка валидации при продлении брони {booking_id} на {extension_str}: {e_val_extend}")
        success = False
        msg = str(e_val_extend) # Показываем пользователю причину ошибки валидации
    except Exception as e_extend_logic:
        logger.error(f"Ошибка при выполнении продления брони {booking_id} на {extension_str}: {e_extend_logic}", exc_info=True)
        success = False
        msg = const.MSG_BOOKING_FAIL_GENERAL

    # Проверяем, что msg не None перед отправкой
    if msg is None:
        logger.error(f"extend_booking не вернул сообщение для брони {booking_id}")
        msg = const.MSG_ERROR_GENERAL # Запасной вариант

    # Редактируем сообщение с результатом
    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    if success:
        # Обновляем уведомления в планировщике
        if scheduler:
            logger.debug(f"Бронь {booking_id} успешно продлена, обновляем уведомления...")
            try:
                # Перепланируем все (проще, чем искать и обновлять конкретные)
                notificationService.schedule_all_notifications(db, bot, scheduler, active_timers, scheduled_jobs_registry)
            except Exception as e_reschedule:
                logger.error(f"Ошибка перепланирования уведомлений после продления брони {booking_id}: {e_reschedule}", exc_info=True)
        else:
            logger.warning("Планировщик (scheduler) не передан, уведомления не обновлены после продления.")


# --- END OF FILE handlers/callbacks/booking_callbacks.py ---