# services/notification_service.py
import threading
import telebot
from datetime import datetime, timedelta, time, timezone
from typing import Dict, Any, Set, Tuple, Optional, Callable, List # Добавили List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger # Понадобится для сравнения
from apscheduler.jobstores.base import JobLookupError

from database import Database, QueryResult # Импортируем QueryResult
from logger import logger
import constants as const
from services import booking_service # Импортируем модуль целиком
from utils import keyboards


# --- Функции планирования ---

def schedule_one_notification(
        scheduler: BackgroundScheduler,
        # job_type и booking_id теперь должны передаваться отдельно
        job_type: str,
        booking_id: int,
        run_time: datetime,  # Предполагаем, что это naive datetime или datetime с любым tz
        func_to_run,
        args_for_func: tuple,
        scheduled_jobs_registry: set
):
    """
    Планирует одно уведомление в APScheduler.
    - Проверяет, актуальна ли задача в реестре и планировщике.
    - Перепланирует, если время изменилось или задача неактуальна.
    - Пропускает задачи, время которых уже прошло.
    """
    job_key = (job_type, booking_id)
    job_id_aps = f"{job_type}_{booking_id}"  # Уникальный ID для APScheduler
    run_time_aware = None  # Инициализируем

    try:
        # Убедимся, что scheduler.timezone является объектом timezone
        # (APScheduler может хранить его как строку, например, 'Europe/Moscow')
        scheduler_tz = scheduler.timezone
        if isinstance(scheduler_tz, str):
            # Если ваш pytz установлен и используется APScheduler-ом, это сработает.
            # Если нет, вам может потребоваться другая библиотека для работы с tz из строк,
            # или убедиться, что scheduler.timezone инициализирован как объект datetime.timezone
            try:
                import pytz
                scheduler_tz = pytz.timezone(str(scheduler.timezone))
            except ImportError:
                logger.warning("Библиотека pytz не найдена, предполагается UTC для строкового scheduler.timezone. "
                            "Рекомендуется инициализировать scheduler с объектом datetime.timezone.")
                scheduler_tz = timezone.utc # Запасной вариант
            except pytz.UnknownTimeZoneError:
                logger.warning(f"Неизвестный часовой пояс в планировщике: {scheduler.timezone}. Предполагается UTC.")
                scheduler_tz = timezone.utc # Запасной вариант

        # Приводим run_time к aware datetime в часовом поясе планировщика
        if run_time.tzinfo is None:
            run_time_aware = scheduler_tz.localize(run_time) if hasattr(scheduler_tz, 'localize') else run_time.replace(tzinfo=scheduler_tz)
        else:
            run_time_aware = run_time.astimezone(scheduler_tz)

        now_aware = datetime.now(scheduler_tz)

        # Обработка просроченных задач с окном допуска (misfire_grace_time)
        if run_time_aware <= now_aware:
            # Секунды просрочки
            delay_seconds = (now_aware - run_time_aware).total_seconds()
            grace_seconds = getattr(const, 'SCHEDULER_MISFIRE_GRACE_TIME', 300)

            if delay_seconds <= grace_seconds:
                # Планируем немедленное выполнение (через 1 секунду), чтобы не терять уведомление
                adjusted_run_time = now_aware + timedelta(seconds=1)
                logger.info(
                    f"Время задачи {job_id_aps} уже прошло на {int(delay_seconds)} сек, но в пределах grace ({grace_seconds})."
                    f" Переносим на немедленный запуск: {adjusted_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                run_time_aware = adjusted_run_time
            else:
                logger.debug(
                    f"Время запуска задачи {job_id_aps} ({run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}) уже прошло,"
                    f" просрочка {int(delay_seconds)} сек > grace ({grace_seconds}). Пропуск.")
                if job_key in scheduled_jobs_registry:
                    try:
                        scheduler.remove_job(job_id_aps)
                        logger.info(f"Удалена просроченная задача {job_id_aps} из APScheduler.")
                    except JobLookupError:
                        pass
                    scheduled_jobs_registry.discard(job_key)
                    logger.info(f"Просроченная задача {job_key} удалена из реестра.")
                return

        existing_job_in_scheduler = scheduler.get_job(job_id_aps)

        if job_key in scheduled_jobs_registry:
            if existing_job_in_scheduler:
                # --- ИЗМЕНЕНИЕ ДЛЯ APSCHEDULER 4.X ---
                # Предполагаем, что триггер - DateTrigger
                current_job_trigger = existing_job_in_scheduler.trigger
                if isinstance(current_job_trigger, DateTrigger):
                    existing_job_run_time_aware = current_job_trigger.run_date
                    # Сравниваем время с допуском в 1 секунду (для учета микросекунд и небольших расхождений)
                    time_diff = abs((existing_job_run_time_aware - run_time_aware).total_seconds())
                    if time_diff < 1.0:  # Задачи считаются одинаковыми, если разница менее 1 секунды
                        logger.debug(f"Задача {job_id_aps} уже актуальна в реестре и планировщике. Время: {run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}. Пропуск.")
                        return # Задача актуальна, ничего не делаем
                    else:
                        logger.info(
                            f"Задача {job_id_aps} в реестре, но время в планировщике ({existing_job_run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}) "
                            f"отличается от нового ({run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}). Перепланируем.")
                        # Задача будет перепланирована ниже (через remove и add)
                else:
                    logger.warning(
                        f"Задача {job_id_aps} в реестре и планировщике, но имеет неожиданный тип триггера: {type(current_job_trigger)}. Перепланируем.")
                    # Задача будет перепланирована ниже
            else:
                logger.warning(f"Задача {job_key} в реестре, но отсутствует в планировщике. Удаляем из реестра и перепланируем.")
                scheduled_jobs_registry.discard(job_key)
                # Задача будет добавлена/перепланирована ниже
        else: # Задачи нет в реестре
            if existing_job_in_scheduler:
                # Проверяем, не является ли это дубликатом с тем же временем
                current_job_trigger = existing_job_in_scheduler.trigger
                if isinstance(current_job_trigger, DateTrigger):
                    existing_job_run_time_aware = current_job_trigger.run_date
                    time_diff = abs((existing_job_run_time_aware - run_time_aware).total_seconds())
                    if time_diff < 1.0:  # Та же задача с тем же временем - это дубликат
                        logger.warning(f"Обнаружен дубликат задачи {job_id_aps} в планировщике (нет в реестре, но время совпадает). Добавляем в реестр без перепланирования.")
                        scheduled_jobs_registry.add(job_key)
                        return  # Не перепланируем, просто добавляем в реестр
                logger.info(f"Задача {job_id_aps} отсутствует в реестре, но есть в планировщике. Перепланируем (обновим).")
                # Задача будет обновлена через add_job с replace_existing=True ниже
            # else:
                # logger.debug(f"Задачи {job_id_aps} нет ни в реестре, ни в планировщике. Будет создана новая.")


        # На этом этапе мы либо создаем новую задачу, либо обновляем существующую
        # replace_existing=True позаботится об удалении, если задача с таким ID уже есть
        try:
            scheduler.add_job(
                func_to_run,
                trigger=DateTrigger(run_date=run_time_aware), # Явно используем DateTrigger
                args=args_for_func,
                id=job_id_aps,
                name=f"Notification: {job_type} for booking {booking_id}", # Опционально: имя для лучшей читаемости в логах/инструментах
                replace_existing=True,
                misfire_grace_time=300 # Пример: 5 минут (const.SCHEDULER_MISFIRE_GRACE_TIME)
            )
            # Добавляем в реестр ТОЛЬКО после успешного добавления/обновления в планировщике
            scheduled_jobs_registry.add(job_key)
            logger.info(f"Задача {job_id_aps} запланирована/обновлена на {run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        except Exception as e_add:
            # Если add_job не удался, но мы ранее удалили из реестра, это может быть проблемой.
            # Однако, если replace_existing=True, то ручное удаление из планировщика выше может быть избыточным.
            logger.error(f"Критическая ошибка при добавлении/обновлении задачи {job_id_aps} в APScheduler: {e_add}", exc_info=True)
            # Попытаемся удалить из реестра, если она там оказалась по ошибке
            if job_key in scheduled_jobs_registry:
                scheduled_jobs_registry.discard(job_key)
                logger.info(f"Задача {job_key} удалена из реестра после ошибки планирования.")


    except Exception as e:
        run_time_str = run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z') if run_time_aware else str(run_time)
        logger.error(f"Общая ошибка при обработке задачи {job_id_aps} (планируемое время {run_time_str}): {e}", exc_info=True)


def remove_scheduled_job(
    scheduler: BackgroundScheduler,
    scheduled_jobs_registry: Set[Tuple[str, int]],
    job_type: str, # Используем константы const.JOB_TYPE_*
    booking_id: int
):
    """Удаляет запланированную задачу из APScheduler и реестра."""
    job_key = (job_type, booking_id)
    job_id = f"{job_type}_{booking_id}"

    job_removed_from_registry = False
    # Используем discard для безопасного удаления из множества
    if job_key in scheduled_jobs_registry:
        scheduled_jobs_registry.discard(job_key)
        job_removed_from_registry = True
        logger.debug(f"Задача {job_id} удалена из реестра.")

    # Пытаемся удалить из планировщика
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Задача {job_id} удалена из APScheduler.")
    except JobLookupError:
        # Если удалили из реестра, но не нашли в планировщике - это нормально
        if job_removed_from_registry:
            logger.debug(f"Задача {job_id} не найдена в APScheduler (уже выполнена/удалена).")
        pass # Не нашли - значит, и удалять нечего
    except Exception as e:
        # Логируем другие возможные ошибки при удалении
        logger.error(f"Ошибка при удалении задачи {job_id} из APScheduler: {e}", exc_info=True)


def schedule_all_notifications(
    db: Database,
    bot: telebot.TeleBot,
    scheduler: BackgroundScheduler,
    active_timers: Dict[int, Any],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """
    Планирует уведомления о начале и конце для всех релевантных бронирований.
    Очищает устаревшие задачи перед планированием.
    """
    logger.info("=== Начало полного перепланирования уведомлений ===")

    # 1. Очищаем задачи для уже завершенных/отмененных броней
    cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)

    # 2. Получаем актуальные брони для планирования
    # Сервис возвращает список кортежей: (id, user_id, equip_id, time_start, time_end, equipment_name)
    bookings_to_schedule: List[Tuple] = booking_service.get_bookings_for_notification_schedule(db)

    if not bookings_to_schedule:
        logger.info("Нет активных бронирований для планирования уведомлений.")
        # Если активных броней нет, очищаем ВЕСЬ реестр и планировщик от старых задач
        if scheduled_jobs_registry:
            logger.warning(f"Реестр задач не пуст ({len(scheduled_jobs_registry)}), но нет активных броней. Полная очистка...")
            for job_type, booking_id in list(scheduled_jobs_registry): # Копируем для итерации
                remove_scheduled_job(scheduler, scheduled_jobs_registry, job_type, booking_id)
        logger.info("=== Перепланирование уведомлений завершено (нет активных броней) ===")
        return

    # Собираем ID актуальных бронирований
    actual_booking_ids = {b[0] for b in bookings_to_schedule}
    logger.debug(f"Получено {len(bookings_to_schedule)} актуальных бронирований для анализа.")

    # 3. Удаляем из реестра и планировщика задачи для броней, которых больше нет в актуальном списке
    removed_count = 0
    for job_type, booking_id in list(scheduled_jobs_registry): # Копируем для итерации
        if booking_id not in actual_booking_ids:
            remove_scheduled_job(scheduler, scheduled_jobs_registry, job_type, booking_id)
            removed_count += 1
    if removed_count > 0:
        logger.info(f"Удалено {removed_count} задач для бронирований, не найденных в актуальном списке.")

    # 4. Планируем задачи для актуальных броней
    for booking_data in bookings_to_schedule:
        # Распаковываем кортеж
        b_id, user_id, equip_id, time_start, time_end, equip_name = booking_data

        try:
            if not isinstance(time_start, datetime) or not isinstance(time_end, datetime):
                logger.warning(f"Пропуск брони {b_id}: некорректный тип time_start или time_end.")
                continue

            # Уведомление о НАЧАЛЕ
            notify_start_time = time_start - timedelta(minutes=const.NOTIFICATION_BEFORE_START_MINUTES)
            schedule_one_notification(
                scheduler=scheduler,
                job_type=const.JOB_TYPE_NOTIFY_START,  # job_type: str
                booking_id=b_id,  # booking_id: int
                run_time=notify_start_time,  # run_time: datetime
                func_to_run=notify_user_about_booking_start,  # func_to_run: Callable
                args_for_func=tuple([  # args_for_func: tuple
                    db, bot, active_timers, scheduler, scheduled_jobs_registry,
                    b_id, user_id, equip_name, time_start
                ]),
                scheduled_jobs_registry=scheduled_jobs_registry  # scheduled_jobs_registry: set
            )

            # Уведомление о КОНЦЕ
            notify_end_time = time_end - timedelta(minutes=const.NOTIFICATION_BEFORE_END_MINUTES)
            schedule_one_notification(
                scheduler=scheduler,
                job_type=const.JOB_TYPE_NOTIFY_END,  # job_type: str
                booking_id=b_id,  # booking_id: int
                run_time=notify_end_time,  # run_time: datetime
                func_to_run=send_end_booking_notification_wrapper,  # func_to_run: Callable
                args_for_func=tuple([  # args_for_func: tuple
                    db, bot, scheduler, scheduled_jobs_registry,
                    b_id, user_id, equip_id, equip_name, time_end
                ]),
                scheduled_jobs_registry=scheduled_jobs_registry  # scheduled_jobs_registry: set
            )

        except Exception as e_schedule_loop:
            logger.error(f"Ошибка при планировании уведомлений для брони {b_id}: {e_schedule_loop}", exc_info=True)
            # Продолжаем со следующей бронью

    logger.info(f"=== Перепланирование уведомлений завершено. Актуальных задач в реестре: {len(scheduled_jobs_registry)} ===")


def cleanup_completed_jobs(db: Database, scheduler: BackgroundScheduler, scheduled_jobs_registry: Set[Tuple[str, int]]):
    """ Удаляет задачи (из реестра и планировщика) для завершенных или отмененных бронирований. """
    logger.debug("Начало очистки задач для завершенных/отмененных бронирований...")
    # <<< ИСПРАВЛЕНО: Запрос использует finish IS NOT NULL >>>
    query = "SELECT id FROM bookings WHERE cancel = TRUE OR finish IS NOT NULL;"
    try:
        completed_bookings_result: QueryResult = db.execute_query(query, fetch_results=True)
        if not completed_bookings_result:
            logger.debug("Нет завершенных/отмененных бронирований для очистки задач.")
            return

        # Доступ по ключу 'id'
        completed_ids = {item['id'] for item in completed_bookings_result if 'id' in item}
        logger.debug(f"Найдены ID завершенных/отмененных броней: {completed_ids}")

        # Находим задачи в реестре, связанные с этими ID
        jobs_to_remove_keys = {job_key for job_key in scheduled_jobs_registry if job_key[1] in completed_ids}

        if not jobs_to_remove_keys:
            logger.debug("Не найдено задач в реестре для завершенных/отмененных бронирований.")
            return

        logger.info(f"Будет удалено {len(jobs_to_remove_keys)} задач для завершенных/отмененных бронирований.")
        # Удаляем найденные задачи
        for job_type, booking_id in list(jobs_to_remove_keys): # Копируем для итерации
            remove_scheduled_job(scheduler, scheduled_jobs_registry, job_type, booking_id)

        logger.debug("Очистка завершенных/отмененных задач завершена.")

    except Exception as e:
        logger.error(f"Ошибка во время cleanup_completed_jobs: {e}", exc_info=True)


# --- Функции выполнения уведомлений (запускаются планировщиком) ---

def send_notification_message(bot: telebot.TeleBot, user_id: int, message_text: str, **kwargs):
    """Отправляет текстовое сообщение пользователю с доп. параметрами (например, reply_markup)."""
    try:
        logger.debug(f"Попытка отправить уведомление пользователю {user_id}: '{message_text[:50]}...'")
        bot.send_message(user_id, message_text, **kwargs) # Передаем доп. параметры
        logger.info(f"Уведомление успешно отправлено пользователю {user_id}.")
    except telebot.apihelper.ApiTelegramException as e:
        if e.error_code == 403: logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: бот заблокирован.")
        elif e.error_code == 400 and 'chat not found' in e.description.lower(): logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: чат не найден.")
        else: logger.error(f"Ошибка Telegram API при отправке уведомления пользователю {user_id}: {e}")
        # Помечаем пользователя как заблокированного
        try:
            from services import user_service # Локальный импорт во избежание цикла
            from database import Database # Локальный импорт
            # Получаем соединение с БД. Осторожно, если используется пул!
            # Лучше передавать объект db или connection pool
            # В данном контексте (вызов из планировщика) безопаснее создать новый объект DB
            temp_db = Database()
            user_service.handle_user_blocked_bot(temp_db, user_id)
        except Exception as e_block:
            logger.error(f"Ошибка при вызове handle_user_blocked_bot для {user_id}: {e_block}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке уведомления пользователю {user_id}: {e}", exc_info=True)

def send_end_booking_notification_wrapper(
    db: Database,
    bot: telebot.TeleBot,
    scheduler: BackgroundScheduler,
    scheduled_jobs_registry: Set[Tuple[str, int]],
    booking_id: int,
    user_id: int,
    equip_id: int,
    equip_name: str,
    end_time: datetime # Время окончания (ожидается aware)
):
    """ Проверяет возможность продления и отправляет уведомление об окончании. """
    logger.debug(f"Сработала задача уведомления о конце для брони {booking_id}")

    try:
        # 1. Проверяем актуальность брони
        booking_info: Optional[Dict[str, Any]] = booking_service.find_booking_by_id(db, booking_id)

        # --- Проверяем статус брони ---
        is_cancelled = booking_info.get('cancel', False) if booking_info else True
        # <<< ИСПРАВЛЕНО: Проверка finish IS NULL >>>
        is_finished = booking_info.get('finish') is not None if booking_info else True

        if not booking_info or is_cancelled or is_finished:
            logger.info(f"Уведомление об окончании для booking_id {booking_id} не требуется (бронь неактивна).")
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_END, booking_id)
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_START, booking_id)
            return

        current_end_time = booking_info.get('time_end')
        if not isinstance(current_end_time, datetime):
            logger.error(f"Некорректный тип current_end_time при уведомлении об окончании для брони {booking_id}")
            send_notification_message(bot, user_id, f"🔔 Напоминание: Ваша работа на '{equip_name}' скоро завершится (ошибка времени).")
            return

        # Приводим к таймзоне планировщика для сравнений и форматирования
        logger.debug(f"Тип scheduler.timezone: {type(scheduler.timezone)}")
        if current_end_time.tzinfo:
            current_end_time_aware = current_end_time.astimezone(scheduler.timezone)
        else:
            # Проверяем, есть ли метод localize
            if hasattr(scheduler.timezone, 'localize'):
                current_end_time_aware = scheduler.timezone.localize(current_end_time)
            else:
                # Для zoneinfo используем replace()
                current_end_time_aware = current_end_time.replace(tzinfo=scheduler.timezone)

        # 2. Проверяем возможность продления
        can_extend = False
        try:
            check_start_time = current_end_time_aware
            check_end_time = check_start_time + timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
            # Передаем naive время для проверки конфликта
            conflicts = booking_service.check_booking_conflict(
                db, equip_id,
                check_start_time.replace(tzinfo=None),
                check_end_time.replace(tzinfo=None),
                exclude_booking_id=booking_id
            )

            if not conflicts:
                end_work_dt = datetime.combine(
                    current_end_time_aware.date(),
                    const.WORKING_HOURS_END, # Используем time объект из констант
                    tzinfo=scheduler.timezone # Устанавливаем таймзону
                )
                # Сравниваем aware datetimes
                if check_start_time < end_work_dt:
                    can_extend = True
                    logger.debug(f"Продление для брони {booking_id} возможно.")
                else:
                    logger.debug(f"Продление для брони {booking_id} невозможно (конец рабочего дня).")
            else:
                logger.debug(f"Продление для брони {booking_id} невозможно (конфликт).")
        except Exception as e_check_ext:
            logger.error(f"Ошибка при проверке возможности продления для брони {booking_id}: {e_check_ext}", exc_info=True)

        # 3. Отправляем сообщение
        end_time_str = current_end_time_aware.strftime('%H:%M')
        minutes_left = const.NOTIFICATION_BEFORE_END_MINUTES

        if can_extend:
            message_text = (
                f"🔔 Напоминание: Ваша работа на '{equip_name}' завершится через {minutes_left} мин ({end_time_str}).\n"
                f"Хотите продлить?"
            )
            markup = keyboards.generate_extend_prompt_keyboard(booking_id)
            send_notification_message(bot, user_id, message_text, reply_markup=markup)
            logger.info(f"Уведомление о завершении с опцией продления отправлено user {user_id} для брони {booking_id}.")
        else:
            message_text = (
                f"🔔 Напоминание: Ваша работа на '{equip_name}' завершится через {minutes_left} мин ({end_time_str}).\n"
                f"(Продление невозможно)."
            )
            send_notification_message(bot, user_id, message_text)
            logger.info(f"Уведомление о завершении (без продления) отправлено user {user_id} для брони {booking_id}.")

    except Exception as e_wrapper:
        logger.error(f"Ошибка в send_end_booking_notification_wrapper для брони {booking_id}: {e_wrapper}", exc_info=True)


def notify_user_about_booking_start(
        db: Database,
        bot: telebot.TeleBot,  # Убедитесь, что bot передается сюда
        active_timers: Dict[int, Any],
        scheduler: BackgroundScheduler,  # APScheduler все еще нужен для других уведомлений
        scheduled_jobs_registry: Set[Tuple[str, int]],
        booking_id: int,
        user_id: int,  # Это ID пользователя, он же chat_id для личных сообщений
        equip_name: str,
        start_time: datetime
):
    logger.debug(f"Сработала задача уведомления о начале для брони {booking_id}")
    sent_notification_msg = None  # Инициализируем

    try:
        booking_info: Optional[Dict[str, Any]] = booking_service.find_booking_by_id(db, booking_id)
        # ... (проверка актуальности брони как раньше) ...
        is_cancelled = booking_info.get('cancel', False) if booking_info else True
        is_finished = booking_info.get('finish') is not None if booking_info else True

        if not booking_info or is_cancelled or is_finished:
            logger.info(f"Уведомление о начале для booking_id {booking_id} не требуется (бронь неактивна).")
            # ... (удаление задач из APScheduler как раньше) ...
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_START, booking_id)
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_END,
                                booking_id)  # Также и _END, если _START не нужен
            return

        markup = keyboards.generate_start_confirmation_keyboard(booking_id)  # Ваша функция генерации клавиатуры
        # ... (форматирование start_time_str, message_text как раньше) ...
        if start_time.tzinfo is None and hasattr(scheduler, 'timezone'):
            # Универсальная обработка pytz/zoneinfo
            if hasattr(scheduler.timezone, 'localize'):
                start_time_aware = scheduler.timezone.localize(start_time)
            else:
                start_time_aware = start_time.replace(tzinfo=scheduler.timezone)
        elif start_time.tzinfo is not None and hasattr(scheduler, 'timezone'):
            start_time_aware = start_time.astimezone(scheduler.timezone)
        else:  # Если scheduler.timezone не установлен или start_time уже aware и не надо конвертировать
            start_time_aware = start_time
            if start_time_aware.tzinfo is None:  # Если все еще naive, используем UTC как fallback
                logger.warning(
                    "Часовой пояс не определен для start_time и scheduler, используется UTC для форматирования.")
                start_time_aware = start_time.replace(tzinfo=timezone.utc)

        start_time_str = start_time_aware.strftime('%H:%M')
        minutes_before = const.NOTIFICATION_BEFORE_START_MINUTES
        timeout_minutes = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS // 60
        message_text = (
            f"❗ Ваше бронирование на '{equip_name}' начинается через {minutes_before} мин ({start_time_str}).\n\n"
            f"Пожалуйста, **подтвердите актуальность** в течение {timeout_minutes} минут, иначе бронь будет автоматически отменена."
        )

        # --- ОТПРАВКА И ПОЛУЧЕНИЕ MESSAGE_ID ---
        # send_notification_message(bot, user_id, message_text, reply_markup=markup, parse_mode='Markdown') # Старый вызов
        # Вместо этого используем bot.send_message напрямую, чтобы получить объект сообщения
        try:
            sent_notification_msg = bot.send_message(
                chat_id=user_id,  # user_id здесь == chat_id для личного сообщения
                text=message_text,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            logger.info(
                f"Уведомление о начале бронирования {booking_id} (msg_id: {sent_notification_msg.message_id}) отправлено пользователю {user_id}.")
        except Exception as e_send:
            logger.error(f"Ошибка отправки уведомления о начале брони {booking_id} пользователю {user_id}: {e_send}")
            return  # Если не удалось отправить, таймер запускать не нужно

        if booking_id not in active_timers and sent_notification_msg:  # Запускаем таймер только если сообщение отправлено
            timer = threading.Timer(
                const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS,
                _run_auto_cancel,
                # --- ПЕРЕДАЕМ chat_id и message_id ---
                args=[db, bot, active_timers, scheduler, scheduled_jobs_registry, booking_id,
                    sent_notification_msg.chat.id, sent_notification_msg.message_id]
            )
            active_timers[booking_id] = {"timer": timer, "message_id": sent_notification_msg.message_id,
                                        "chat_id": sent_notification_msg.chat.id}
            timer.start()
            logger.info(
                f"Запущен таймер автоотмены ({const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS} сек) для бронирования {booking_id} (msg_id: {sent_notification_msg.message_id}).")
        elif booking_id in active_timers:
            logger.warning(f"Таймер для бронирования {booking_id} уже существует! Новый таймер не запущен.")
        elif not sent_notification_msg:
            logger.error(f"Не удалось запустить таймер для брони {booking_id}: исходное сообщение не было отправлено.")


    except Exception as e_notify_start:
        logger.error(f"Ошибка в notify_user_about_booking_start для брони {booking_id}: {e_notify_start}",
                    exc_info=True)


def _run_auto_cancel(
        db: Database,
        bot: telebot.TeleBot,
        active_timers: Dict[int, Any],
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        booking_id: int,
        # --- НОВЫЕ ПАРАМЕТРЫ ---
        original_chat_id: int,
        original_message_id: int
):
    logger.debug(
        f"Сработал таймер автоотмены для booking_id {booking_id} (исходное сообщение: {original_chat_id}/{original_message_id}).")
    owner_user_id = None  # Инициализируем
    equip_name = "Неизвестное оборудование"  # Значение по умолчанию

    try:
        # Получаем информацию о брони ДО попытки отмены, чтобы иметь данные для редактирования/уведомления
        booking_info_before_cancel = booking_service.find_booking_by_id(db, booking_id)
        if booking_info_before_cancel:
            owner_user_id = booking_info_before_cancel.get('user_id')
            equip_name = booking_info_before_cancel.get('equipment_name', equip_name)

            # Проверяем, не была ли бронь уже подтверждена или отменена
            if booking_info_before_cancel.get('status') == 'confirmed' or \
                    booking_info_before_cancel.get('cancel') is True:
                logger.info(f"Таймер для брони {booking_id}: бронь уже подтверждена или отменена. Удаляем таймер.")
                if booking_id in active_timers:
                    timer_data = active_timers.pop(booking_id, None)
                    if timer_data and isinstance(timer_data.get("timer"), threading.Timer):
                        timer_data["timer"].cancel()  # На всякий случай, если таймер еще не удален
                return  # Ничего больше не делаем

        was_cancelled, _, _ = booking_service.auto_cancel_unconfirmed_booking(db,
                                                                            booking_id)  # owner_user_id и equip_name уже есть

        timer_data = active_timers.pop(booking_id, None)  # Удаляем таймер из словаря
        # Не нужно вызывать timer.cancel() здесь, так как функция уже выполняется этим таймером.

        if was_cancelled:
            logger.info(f"Бронь {booking_id} автоматически отменена из-за отсутствия подтверждения.")

            # --- РЕДАКТИРОВАНИЕ ИСХОДНОГО СООБЩЕНИЯ ---
            try:
                # Сообщение для редактирования исходного уведомления
                edited_text = (
                    f"Бронирование на '{equip_name}' (ID: {booking_id})\n"
                    "Время подтверждения истекло. Бронь была автоматически отменена."
                )
                bot.edit_message_text(
                    chat_id=original_chat_id,
                    message_id=original_message_id,
                    text=edited_text,
                    reply_markup=None  # Убираем кнопки
                )
                logger.info(
                    f"Исходное сообщение {original_message_id} для брони {booking_id} отредактировано (тайм-аут).")
            except telebot.apihelper.ApiTelegramException as e_edit:
                if "message to edit not found" in str(e_edit).lower():
                    logger.warning(
                        f"Не удалось отредактировать сообщение {original_message_id} (тайм-аут брони {booking_id}): сообщение не найдено.")
                else:
                    logger.error(
                        f"Ошибка API при редактировании сообщения {original_message_id} (тайм-аут брони {booking_id}): {e_edit}")
            except Exception as e_edit_generic:
                logger.error(
                    f"Общая ошибка при редактировании сообщения {original_message_id} (тайм-аут брони {booking_id}): {e_edit_generic}",
                    exc_info=True)

            # Отправляем новое сообщение об автоотмене (как и раньше)
            if owner_user_id:  # owner_user_id теперь берется из booking_info_before_cancel
                send_notification_message(
                    bot, owner_user_id,
                    f"🚫 Ваше бронирование на '{equip_name}' (ID: {booking_id}) было автоматически отменено из-за отсутствия подтверждения."
                )

            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_START, booking_id)
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_END, booking_id)
        else:
            logger.debug(
                f"Бронь {booking_id} не была автоматически отменена таймером (возможно, уже подтверждена/отменена).")
            # Если бронь НЕ была отменена (т.е. уже подтверждена), то исходное сообщение с кнопкой
            # должно было быть изменено функцией confirm_booking_callback_logic.
            # Если оно не было изменено, то здесь можно его "почистить", если таймер все же сработал.
            if booking_info_before_cancel and booking_info_before_cancel.get('status') == 'confirmed':
                try:
                    bot.edit_message_text(
                        chat_id=original_chat_id,
                        message_id=original_message_id,
                        text=f"✅ Бронирование на '{equip_name}' (ID: {booking_id}) было подтверждено.",
                        reply_markup=None
                    )
                    logger.info(
                        f"Исходное сообщение {original_message_id} для брони {booking_id} обновлено (было подтверждено).")
                except Exception:
                    pass  # Ошибки редактирования здесь менее критичны

    except Exception as e:
        logger.error(f"Ошибка в _run_auto_cancel для booking_id {booking_id}: {e}", exc_info=True)
        active_timers.pop(booking_id, None)  # Пытаемся удалить таймер в случае любой ошибки


def confirm_booking_callback_logic(
        db: Database,
        bot: telebot.TeleBot,  # <--- Добавляем bot
        active_timers: Dict[int, Any],
        call: telebot.types.CallbackQuery,  # <--- Передаем весь объект call
        booking_id: int,
        user_id: int
) -> bool:
    logger.debug(f"Попытка подтверждения брони {booking_id} пользователем {user_id} через callback.")

    timer_data = active_timers.pop(booking_id, None)
    if timer_data and isinstance(timer_data.get("timer"), threading.Timer):
        try:
            timer_data["timer"].cancel()
            logger.info(f"Таймер автоотмены для бронирования {booking_id} остановлен пользователем.")
        except Exception as e_cancel:
            logger.error(f"Ошибка при отмене таймера для брони {booking_id}: {e_cancel}")
    else:
        logger.debug(
            f"Активный таймер для бронирования {booking_id} не найден при подтверждении (возможно, уже сработал или был отменен).")

    try:
        success = booking_service.confirm_start_booking(db, booking_id, user_id)

        # --- РЕДАКТИРОВАНИЕ СООБЩЕНИЯ ПОСЛЕ ПОДТВЕРЖДЕНИЯ ---
        if call.message:  # Убедимся, что у callback'а есть сообщение
            original_chat_id = call.message.chat.id
            original_message_id = call.message.message_id

            if success:
                booking_info = booking_service.find_booking_by_id(db, booking_id)
                equip_name = booking_info.get('equipment_name', 'оборудование') if booking_info else 'оборудование'
                edited_text = f"✅ Бронирование на '{equip_name}' (ID: {booking_id}) успешно подтверждено!"
                try:
                    bot.edit_message_text(
                        chat_id=original_chat_id,
                        message_id=original_message_id,
                        text=edited_text,
                        reply_markup=None  # Убираем кнопки
                    )
                    logger.info(
                        f"Сообщение {original_message_id} для брони {booking_id} отредактировано (успешное подтверждение).")
                except Exception as e_edit:
                    logger.error(
                        f"Ошибка редактирования сообщения {original_message_id} при подтверждении брони {booking_id}: {e_edit}")
            else:
                # Если подтверждение не удалось (например, бронь уже отменена кем-то еще)
                edited_text = f"⚠️ Не удалось подтвердить бронь ID {booking_id}. Возможно, она уже была отменена или произошла ошибка."
                try:
                    bot.edit_message_text(
                        chat_id=original_chat_id,
                        message_id=original_message_id,
                        text=edited_text,
                        reply_markup=None
                    )
                except Exception as e_edit_fail:
                    logger.error(
                        f"Ошибка редактирования сообщения {original_message_id} при неудачном подтверждении брони {booking_id}: {e_edit_fail}")
        return success

    except Exception as e_confirm:
        logger.error(f"Ошибка при подтверждении брони {booking_id}: {e_confirm}", exc_info=True)
        return False