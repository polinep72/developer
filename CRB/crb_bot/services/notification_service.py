# --- START OF FULL services/notification_service.py (с APScheduler для таймаута и глобальными экземплярами) ---

import threading
import telebot  # Для аннотации типов
from datetime import datetime, timedelta, time
from typing import Dict, Any, Set, Tuple, Optional, Callable, List

# --- Импортируем глобальные объекты из bot_app ---
from bot_app import bot as global_bot_instance
from bot_app import db_connection as global_db_connection  # Это экземпляр класса Database
from bot_app import scheduler as global_scheduler
from bot_app import active_timers as global_active_timers  # Для UI-таймера продления
from bot_app import scheduled_jobs_registry as global_scheduled_jobs_registry
# --- КОНЕЦ ИМПОРТОВ ГЛОБАЛЬНЫХ ОБЪЕКТОВ ---

from database import Database as DatabaseTypeHint, QueryResult  # Database как тип для аннотаций
from logger import logger
import constants as const
from services import booking_service  # booking_service использует global_db_connection внутри себя
from utils import keyboards
import pytz
from apscheduler.schedulers.background import BackgroundScheduler  # Для аннотации типов
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.base import JobLookupError


# --- Функции планирования ---
def schedule_one_notification(
        job_type: str,
        booking_id: int,
        run_time: datetime,  # Ожидается naive datetime, будет локализован
        func_to_run: Callable,
        args_for_func: list  # Только пиклюемые аргументы
):
    job_key = (job_type, booking_id)
    job_id = f"{job_type}_{booking_id}"
    run_time_aware: Optional[datetime] = None

    try:
        target_timezone = global_scheduler.timezone
        now_aware = datetime.now(target_timezone)

        if run_time.tzinfo is None or run_time.tzinfo.utcoffset(run_time) is None:
            try:
                run_time_aware = target_timezone.localize(run_time)
            except pytz.exceptions.AmbiguousTimeError:  # Обработка перехода на зимнее время
                run_time_aware = target_timezone.localize(run_time,
                                                          is_dst=False)  # или is_dst=True, в зависимости от политики
                logger.warning(
                    f"Неоднозначное время {run_time} для {job_id} при локализации (переход времени), выбрано is_dst=False.")
            except pytz.exceptions.NonExistentTimeError:  # Обработка перехода на летнее время
                # Сдвигаем на час вперед, если время попало на "несуществующий" час
                run_time_shifted = run_time + timedelta(hours=1)
                run_time_aware = target_timezone.localize(run_time_shifted)
                logger.warning(
                    f"Несуществующее время {run_time} для {job_id} при локализации (переход времени), сдвинуто на {run_time_shifted}.")
            except Exception as e_tz_localize:
                logger.error(
                    f"Ошибка локализации наивного времени {run_time} в {target_timezone.zone} для задачи {job_id}: {e_tz_localize}",
                    exc_info=True)
                return
        elif run_time.tzinfo != target_timezone:
            run_time_aware = run_time.astimezone(target_timezone)
        else:
            run_time_aware = run_time

        if run_time_aware <= now_aware:
            logger.debug(
                f"Время запуска задачи {job_id} ({run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z%z')}) уже прошло. Пропуск.")
            if job_key in global_scheduled_jobs_registry:
                remove_scheduled_job(job_type, booking_id)
            return

        existing_job = global_scheduler.get_job(job_id, jobstore='default')
        if job_key in global_scheduled_jobs_registry and existing_job and getattr(existing_job, 'next_run_time',
                                                                                  None) == run_time_aware:
            logger.debug(f"Задача {job_id} уже актуальна в реестре и планировщике. Пропуск.")
            return

        if job_key in global_scheduled_jobs_registry:  # Если была в реестре, но требует обновления/удаления из планировщика
            global_scheduled_jobs_registry.discard(job_key)
            logger.debug(f"Ключ {job_key} удален из реестра перед (пере)планированием.")

        logger.info(
            f"ПЛАНИРОВАНИЕ: Job ID={job_id}, Run Time (Aware)={run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")
        global_scheduler.add_job(
            func_to_run,
            trigger=DateTrigger(run_date=run_time_aware),
            args=args_for_func,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300
        )
        global_scheduled_jobs_registry.add(job_key)
        logger.info(f"Запланирована/обновлена задача {job_id} на {run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")

    except Exception as e:
        logger.error(f"Ошибка при планировании задачи {job_id} на {run_time}: {e}", exc_info=True)


def remove_scheduled_job(job_type: str, booking_id: int):
    job_key = (job_type, booking_id)
    job_id = f"{job_type}_{booking_id}"
    removed_from_registry = False
    if job_key in global_scheduled_jobs_registry:
        try:
            global_scheduled_jobs_registry.discard(job_key); removed_from_registry = True; logger.debug(
                f"Задача {job_id} удалена из реестра.")
        except Exception as e_reg:
            logger.error(f"Ошибка удаления {job_id} из реестра: {e_reg}")
    try:
        global_scheduler.remove_job(job_id)
        logger.info(f"Задача {job_id} удалена из APScheduler.")
    except JobLookupError:
        if removed_from_registry: logger.debug(f"Задача {job_id} не найдена в APScheduler (уже выполнена/удалена).")
    except Exception as e:
        logger.error(f"Ошибка удаления {job_id} из APScheduler: {e}", exc_info=True)


def schedule_all_notifications():
    logger.info("=== Начало полного перепланирования уведомлений ===")
    notification_job_prefixes = (
    const.JOB_TYPE_NOTIFY_START, const.JOB_TYPE_NOTIFY_END, const.JOB_TYPE_FINAL_END_NOTICE,
    const.JOB_TYPE_CONFIRM_TIMEOUT)
    keys_to_remove = {jk for jk in list(global_scheduled_jobs_registry) if
                      any(jk[0] == prefix for prefix in notification_job_prefixes)}
    logger.debug(f"Найдено {len(keys_to_remove)} ключей для удаления: {keys_to_remove}")
    for job_type, booking_id in keys_to_remove:
        remove_scheduled_job(job_type, booking_id)

    bookings_to_schedule: List[Tuple] = []
    try:
        bookings_to_schedule = booking_service.get_bookings_for_notification_schedule(global_db_connection)
    except Exception as e_get_bookings:
        logger.critical(f"Критическая ошибка получения броней для планирования: {e_get_bookings}", exc_info=True);
        return
    if not bookings_to_schedule: logger.info("Нет броней для планирования уведомлений."); return

    planned_count = 0
    for booking_data in bookings_to_schedule:
        b_id, user_id, cr_id, time_start, time_end, cr_name = booking_data
        try:
            if not all(isinstance(t, datetime) for t in [time_start, time_end]):
                logger.warning(f"Пропуск {b_id}: некорр. типы времени.");
                continue

            notify_start_time = time_start - timedelta(minutes=const.NOTIFICATION_BEFORE_START_MINUTES)
            schedule_one_notification(
                const.JOB_TYPE_NOTIFY_START, b_id, notify_start_time,
                notify_user_about_booking_start,
                [b_id, user_id, cr_name, time_start]  # Только пиклюемые аргументы
            )

            notify_end_time = time_end - timedelta(minutes=const.NOTIFICATION_BEFORE_END_MINUTES)
            schedule_one_notification(
                const.JOB_TYPE_NOTIFY_END, b_id, notify_end_time,
                send_end_booking_notification_wrapper,
                [b_id, user_id, cr_id, cr_name, time_end]
            )

            schedule_one_notification(
                const.JOB_TYPE_FINAL_END_NOTICE, b_id, time_end,
                _send_final_end_message,
                [user_id, cr_name, b_id, None]
            )
            planned_count += 1
        except Exception as e_loop:
            logger.error(f"Ошибка планирования для брони {b_id}: {e_loop}", exc_info=True)
    logger.info(
        f"=== Перепланирование завершено. Обработано {planned_count} броней. Задач в реестре: {len(global_scheduled_jobs_registry)} ===")


def cleanup_completed_jobs():
    logger.debug("Начало очистки задач для завершенных/отмененных бронирований...")
    query = "SELECT id FROM bookings WHERE status IN ('finished', 'cancelled');"
    try:
        completed_bookings: QueryResult = global_db_connection.execute_query(query, fetch_results=True)
    except Exception as e_query:
        logger.error(f"Ошибка запроса завершенных броней: {e_query}", exc_info=True); return
    if not completed_bookings: logger.debug("Нет завершенных/отмененных броней для очистки."); return
    completed_ids = {item.get('id') for item in completed_bookings if
                     isinstance(item, dict) and item.get('id') is not None}
    if not completed_ids: logger.debug("Не удалось извлечь ID завершенных броней."); return

    job_types = [const.JOB_TYPE_NOTIFY_START, const.JOB_TYPE_NOTIFY_END, const.JOB_TYPE_CONFIRM_TIMEOUT,
                 const.JOB_TYPE_FINAL_END_NOTICE]
    jobs_to_remove = {jk for jk in list(global_scheduled_jobs_registry) if
                      jk[1] in completed_ids and jk[0] in job_types}
    if not jobs_to_remove: logger.debug("Не найдено задач в реестре для удаления."); return
    logger.info(f"Будет удалено {len(jobs_to_remove)} задач для завершенных/отмененных бронирований.")
    for job_type, booking_id in jobs_to_remove: remove_scheduled_job(job_type, booking_id)
    logger.debug("Очистка завершенных/отмененных задач завершена.")


# --- Функции выполнения уведомлений ---

def send_notification_message(user_id: int, message_text: str, **kwargs) -> Optional[int]:
    try:
        logger.debug(f"Отправка уведомления user {user_id}: '{message_text[:50]}...'")
        sent_message = global_bot_instance.send_message(user_id, message_text, **kwargs)
        if sent_message: logger.info(
            f"Уведомление user {user_id} (msg_id: {sent_message.message_id}) отправлено."); return sent_message.message_id
        return None
    except telebot.apihelper.ApiTelegramException as e:
        err_code = getattr(e, 'error_code', None);
        desc = str(e).lower()
        if err_code == 403 or "blocked" in desc or "forbidden" in desc:
            logger.warning(f"Уведомление user {user_id} не отправлено: бот заблокирован ({err_code}).")
            try:
                from services import user_service; user_service.handle_user_blocked_bot(global_db_connection, user_id)
            except Exception as e_block:
                logger.error(f"Ошибка handle_user_blocked_bot для {user_id}: {e_block}")
        elif err_code == 400 and ('chat not found' in desc or 'user is deactivated' in desc):
            logger.warning(f"Уведомление {user_id} не отправлено: чат не найден/юзер деактивирован (400).")
        else:
            logger.error(f"Ошибка API ({err_code}) при отправке user {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления user {user_id}: {e}", exc_info=True); return None


def notify_user_about_booking_start(
        booking_id: int,
        user_id: int,
        cr_name: str,
        start_time: datetime  # naive datetime из БД/планировщика
):
    target_timezone = global_scheduler.timezone
    actual_run_time = datetime.now(target_timezone)
    logger.info(
        f"ЗАПУСК notify_start для брони {booking_id}. Реальное время: {actual_run_time:%Y-%m-%d %H:%M:%S.%f %Z%z}.")
    notification_message_id: Optional[int] = None
    try:
        booking_info = booking_service.find_booking_by_id(global_db_connection, booking_id)
        current_status = booking_info.get('status') if booking_info else None
        if current_status != 'pending_confirmation':
            logger.info(f"notify_start для {booking_id} не требуется (статус={current_status}).");
            remove_scheduled_job(const.JOB_TYPE_NOTIFY_START, booking_id)
            remove_scheduled_job(const.JOB_TYPE_CONFIRM_TIMEOUT, booking_id)
            return

        markup = keyboards.generate_start_confirmation_keyboard(booking_id)
        display_start_time = target_timezone.localize(
            start_time) if start_time.tzinfo is None else start_time.astimezone(target_timezone)
        start_time_str = display_start_time.strftime('%H:%M')
        minutes_before = const.NOTIFICATION_BEFORE_START_MINUTES
        timeout_minutes = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS // 60
        message_text = (
            f"❗ Ваше бронирование '{cr_name}' начинается через {minutes_before} мин ({start_time_str}).\n\n"
            f"**Подтвердите актуальность** в течение {timeout_minutes} минут, иначе бронь будет отменена."
        )
        notification_message_id = send_notification_message(user_id, message_text, reply_markup=markup,
                                                            parse_mode='Markdown')

        if notification_message_id:
            logger.info(
                f"Уведомление о начале {booking_id} (msg_id: {notification_message_id}) user {user_id} отправлено.")
            confirm_timeout_job_type = const.JOB_TYPE_CONFIRM_TIMEOUT
            timeout_run_time_aware = datetime.now(target_timezone) + timedelta(
                seconds=const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS)
            schedule_one_notification(
                confirm_timeout_job_type, booking_id, timeout_run_time_aware.replace(tzinfo=None),  # Передаем naive
                _run_auto_cancel,
                [booking_id, user_id, notification_message_id]  # Только пиклюемые
            )
        else:
            logger.error(f"Не удалось отправить уведомление о начале {booking_id}. Задача автоотмены не запланирована.")
    except Exception as e:
        logger.error(f"Критическая ошибка в notify_user_about_booking_start для {booking_id}: {e}", exc_info=True)


def _run_auto_cancel(
        booking_id: int,
        user_id: int,
        message_id: Optional[int]
):
    logger.debug(
        f"Сработала задача APScheduler ({const.JOB_TYPE_CONFIRM_TIMEOUT}) автоотмены для booking_id {booking_id}.")
    try:
        was_cancelled, owner_user_id, cr_name = booking_service.auto_cancel_unconfirmed_booking(global_db_connection,
                                                                                                booking_id)
        if was_cancelled:
            logger.info(f"Бронь {booking_id} автоматически отменена (APScheduler).")
            message_text = const.MSG_BOOKING_CONFIRM_TIMEOUT
            if cr_name: message_text += f" (Переговорная: '{cr_name}')"
            if owner_user_id and message_id:
                try:
                    global_bot_instance.edit_message_text(chat_id=owner_user_id, message_id=message_id,
                                                          text=message_text, reply_markup=None)
                except Exception as e_edit:
                    logger.warning(
                        f"Не удалось отредактировать {message_id} автоотмены {booking_id}: {e_edit}. Отправка нового."); send_notification_message(
                        owner_user_id, message_text)
            elif owner_user_id:
                send_notification_message(owner_user_id, message_text)

            remove_scheduled_job(const.JOB_TYPE_NOTIFY_END, booking_id)
            remove_scheduled_job(const.JOB_TYPE_FINAL_END_NOTICE, booking_id)
        else:
            logger.debug(f"Бронь {booking_id} не была автоотменена (APScheduler).")
    except Exception as e:
        logger.error(f"Критическая ошибка в _run_auto_cancel (APScheduler) для {booking_id}: {e}", exc_info=True)


def confirm_booking_callback_logic(
        booking_id: int,
        user_id: int
) -> bool:
    logger.debug(f"Попытка подтверждения брони {booking_id} user {user_id}")
    task_removed = False
    try:
        remove_scheduled_job(const.JOB_TYPE_CONFIRM_TIMEOUT, booking_id)
        logger.info(
            f"Задача автоотмены '{const.JOB_TYPE_CONFIRM_TIMEOUT}_{booking_id}' удалена (пользователь подтвердил).")
        task_removed = True
    except JobLookupError:
        logger.warning(f"Задача '{const.JOB_TYPE_CONFIRM_TIMEOUT}_{booking_id}' не найдена. Возможно, уже сработала.")
    except Exception as e_rem:
        logger.error(f"Ошибка удаления задачи '{const.JOB_TYPE_CONFIRM_TIMEOUT}_{booking_id}': {e_rem}")

    if not task_removed:
        try:
            booking_info = booking_service.find_booking_by_id(global_db_connection, booking_id)
            status = booking_info.get('status') if booking_info else 'not_found'
            if status == 'cancelled': logger.warning(f"{booking_id} уже ОТМЕНЕНА. Отказ."); return False
            if status == 'active': logger.warning(f"{booking_id} уже АКТИВНА. Игнор (успех)."); return True
        except Exception as e_chk:
            logger.error(f"Ошибка проверки статуса {booking_id}: {e_chk}"); return False

    try:
        success = booking_service.confirm_start_booking(global_db_connection, booking_id, user_id)
        if success: logger.info(f"Бронь {booking_id} успешно подтверждена user {user_id}."); return True
        return False
    except Exception as e_cnf:
        logger.error(f"Ошибка confirm_start_booking для {booking_id}: {e_cnf}", exc_info=True); return False


def send_end_booking_notification_wrapper(
        booking_id: int, user_id: int, cr_id: int, cr_name: str, end_time: datetime
):
    target_timezone = global_scheduler.timezone
    actual_run_time = datetime.now(target_timezone)
    logger.info(
        f"ЗАПУСК notify_end для брони {booking_id}. Реальное время: {actual_run_time:%Y-%m-%d %H:%M:%S.%f %Z%z}.")
    notification_message_id: Optional[int] = None
    end_time_aware: datetime

    try:
        booking_info = booking_service.find_booking_by_id(global_db_connection, booking_id)
        current_status = booking_info.get('status') if booking_info else None
        if current_status != 'active': logger.info(
            f"notify_end для {booking_id} не требуется (статус={current_status})."); return

        if end_time.tzinfo is None:
            end_time_aware = target_timezone.localize(end_time)
        else:
            end_time_aware = end_time.astimezone(target_timezone)

        can_extend = False
        try:
            check_start_time = end_time_aware
            check_end_time = check_start_time + timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
            conflicts = booking_service.check_booking_conflict(global_db_connection, cr_id, check_start_time,
                                                               check_end_time, exclude_booking_id=booking_id)
            if conflicts and conflicts[0].get('error') == 'check_failed': conflicts = []
            if not conflicts:
                end_work_dt = target_timezone.localize(datetime.combine(end_time_aware.date(), const.WORKING_HOURS_END))
                if check_start_time < end_work_dt: can_extend = True
        except Exception as e_chk_ext:
            logger.error(f"Ошибка проверки продления для {booking_id}: {e_chk_ext}", exc_info=True)

        end_time_str = end_time_aware.strftime('%H:%M');
        minutes_left = const.NOTIFICATION_BEFORE_END_MINUTES
        message_text = (
            f"🔔 '{cr_name}' завершится через {minutes_left} мин ({end_time_str}).\nПродлить?") if can_extend else (
            f"🔔 '{cr_name}' завершится через {minutes_left} мин ({end_time_str}).")
        markup = keyboards.generate_extend_prompt_keyboard(booking_id) if can_extend else None
        notification_message_id = send_notification_message(user_id, message_text, reply_markup=markup)

        if notification_message_id and can_extend:
            logger.info(
                f"Уведомление о завершении (с продлением) для {booking_id} (msg_id:{notification_message_id}) user {user_id} отправлено.")
            if booking_id not in global_active_timers:
                delay_seconds = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS
                # _cancel_extend_option все еще использует threading.Timer для UI, его args остаются полными
                timer_args = [global_bot_instance, user_id, notification_message_id, cr_name, booking_id,
                              end_time_aware, global_scheduler, global_scheduled_jobs_registry, global_active_timers]
                timer = threading.Timer(delay_seconds, _cancel_extend_option, timer_args)
                global_active_timers[booking_id] = timer;
                timer.start()
                logger.info(f"Запущен UI-таймер отмены продления ({delay_seconds:.1f} сек) для {booking_id}.")

        final_end_job_id = f"{const.JOB_TYPE_FINAL_END_NOTICE}_{booking_id}"
        try:
            job = global_scheduler.get_job(final_end_job_id)
            if job: job.modify(args=[user_id, cr_name, booking_id,
                                     notification_message_id])  # _send_final_end_message ожидает эти args
        except Exception as e_mod_job:
            logger.error(f"Ошибка обновления аргументов задачи {final_end_job_id}: {e_mod_job}", exc_info=True)
    except Exception as e_wrap:
        logger.error(f"Критическая ошибка в send_end_booking_notification_wrapper для {booking_id}: {e_wrap}",
                     exc_info=True)


def _cancel_extend_option(  # Эта функция вызывается из threading.Timer, поэтому ее аргументы могут быть сложными
        bot: telebot.TeleBot, user_id: int, message_id: Optional[int], cr_name: str, booking_id: int,
        end_time: datetime, scheduler: BackgroundScheduler, scheduled_jobs_registry: Set[Tuple[str, int]],
        active_timers: Dict[int, Any]  # Принимает active_timers, чтобы удалить себя
):
    logger.debug(f"Сработал UI-таймер отмены продления для брони {booking_id}")
    timer = active_timers.pop(booking_id, None)  # Использует переданный active_timers
    if not timer: logger.warning(f"UI-таймер для {booking_id} не найден в active_timers.")
    try:
        if message_id:
            end_time_str = end_time.strftime('%H:%M')
            new_text = f"Время продления вышло, '{cr_name}' завершится в {end_time_str}."
            try:
                bot.edit_message_text(chat_id=user_id, message_id=message_id, text=new_text, reply_markup=None)
            except Exception as e_edit:
                logger.warning(f"Ошибка API при редактировании {message_id} отмены продления {booking_id}: {e_edit}.")
    except Exception as e:
        logger.error(f"Ошибка в _cancel_extend_option для {booking_id}: {e}", exc_info=True)


def _send_final_end_message(
        user_id: int, cr_name: str,
        booking_id: int, message_id: Optional[int] = None
):
    logger.debug(f"Сработала задача финального уведомления/завершения для брони {booking_id}.")
    message_sent_or_edited = False
    try:
        message_text = const.MSG_BOOKING_ENDED_NO_ACTION.format(cr_name=f"'{cr_name}'")
        if message_id:
            try:
                global_bot_instance.edit_message_text(chat_id=user_id, message_id=message_id, text=message_text,
                                                      reply_markup=None); message_sent_or_edited = True
            except Exception as e_edit:
                logger.warning(
                    f"Не удалось отредактировать {message_id} на финальное для {booking_id}: {e_edit}. Отправляем новое.");
            if not message_sent_or_edited:
                if send_notification_message(user_id, message_text): message_sent_or_edited = True
        else:
            if send_notification_message(user_id, message_text): message_sent_or_edited = True

        if message_sent_or_edited:
            try:
                if not booking_service.auto_finish_booking(global_db_connection, booking_id): logger.warning(
                    f"auto_finish_booking для {booking_id} вернула False.")
            except Exception as e_auto_fin:
                logger.error(f"Ошибка auto_finish_booking для {booking_id}: {e_auto_fin}", exc_info=True)
    except Exception as e:
        logger.error(f"Ошибка в _send_final_end_message для {booking_id}: {e}", exc_info=True)

# --- END OF FULL services/notification_service.py ---