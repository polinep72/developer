# --- START OF FILE notification_service.py ---

# services/notification_service.py
import threading
import telebot
from datetime import datetime, timedelta, time
from typing import Dict, Any, Set, Tuple, Optional, Callable, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.base import JobLookupError

from database import Database, QueryResult
from logger import logger
import constants as const
from services import booking_service
from utils import keyboards


# --- Функции планирования ---

def schedule_one_notification(
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        job_type: str,
        booking_id: int,
        run_time: datetime,
        func_to_run: Callable,
        args_for_func: list
):
    """
    Планирует одно уведомление в APScheduler, если оно еще не запланировано.
    Удаляет существующую задачу с тем же ID перед добавлением новой.
    """
    job_key = (job_type, booking_id)
    job_id = f"{job_type}_{booking_id}"
    run_time_aware = None

    try:
        now_aware = datetime.now(scheduler.timezone)

        # Приведение run_time к aware datetime
        run_time_tz_info = run_time.tzinfo
        if run_time_tz_info is None:
            run_time_aware = run_time.replace(tzinfo=scheduler.timezone)
        else:
            run_time_aware = run_time.astimezone(scheduler.timezone)

        # Проверка, не прошло ли уже время запуска
        if run_time_aware <= now_aware:
            logger.debug(
                f"Время запуска задачи {job_id} ({run_time_aware}) уже прошло ({now_aware}). Пропуск планирования.")
            # Удаляем из реестра и планировщика, если задача там есть
            if job_key in scheduled_jobs_registry:
                remove_scheduled_job(scheduler, scheduled_jobs_registry, job_type, booking_id)
            return

        # Проверка существующей задачи в планировщике
        existing_job = None
        try:
            existing_job = scheduler.get_job(job_id)
        except Exception as e_get_job:
            logger.warning(f"Ошибка при получении существующей задачи {job_id}: {e_get_job}")

        # Синхронизация реестра и планировщика
        job_in_registry = job_key in scheduled_jobs_registry
        if job_in_registry:
            if existing_job:
                # Задача есть и там, и там. Проверяем время.
                existing_run_time = existing_job.next_run_time
                if existing_run_time == run_time_aware:
                    logger.debug(f"Задача {job_id} уже актуальна в реестре и планировщике. Пропуск.")
                    return
                else:
                    logger.warning(
                        f"Задача {job_id} в реестре, но время в планировщике ({existing_run_time}) отличается от требуемого ({run_time_aware}). Перепланируем.")
                    # Удаляем из реестра, чтобы пересоздать
                    try:
                        scheduled_jobs_registry.discard(job_key)
                    except Exception as e_reg_discard:
                         logger.error(f"Ошибка удаления {job_key} из реестра при перепланировании: {e_reg_discard}")
            else:
                # Задача есть в реестре, но нет в планировщике. Удаляем из реестра.
                logger.warning(f"Задача {job_id} в реестре, но не найдена в планировщике. Удаляем из реестра.")
                try:
                    scheduled_jobs_registry.discard(job_key)
                except Exception as e_reg_discard_orphan:
                    logger.error(f"Ошибка удаления {job_key} (осиротевшей) из реестра: {e_reg_discard_orphan}")

        # Удаляем старую задачу из планировщика, если она там была (даже если время совпадало, но мы дошли сюда)
        if existing_job:
            try:
                scheduler.remove_job(job_id)
                logger.info(f"Удалена предыдущая задача {job_id} из APScheduler перед перепланированием.")
            except JobLookupError:
                # Уже удалена кем-то другим или выполнилась
                pass
            except Exception as e_remove_old:
                logger.error(f"Ошибка при удалении старой задачи {job_id} перед перепланированием: {e_remove_old}")

        # Добавляем новую задачу
        scheduler.add_job(
            func_to_run,
            trigger=DateTrigger(run_date=run_time_aware),
            args=args_for_func,
            id=job_id,
            replace_existing=True # На всякий случай, если remove_job не сработал
        )
        # Добавляем в реестр только после успешного добавления в планировщик
        try:
            scheduled_jobs_registry.add(job_key)
            logger.info(f"Запланирована задача {job_id} на {run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception as e_reg_add:
             logger.error(f"Ошибка добавления {job_key} в реестр после планирования: {e_reg_add}")

    except Exception as e:
        run_time_str = run_time_aware.strftime('%Y-%m-%d %H:%M:%S %Z') if run_time_aware else str(run_time)
        logger.error(f"Ошибка при планировании задачи {job_id} на {run_time_str}: {e}", exc_info=True)


def remove_scheduled_job(
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        job_type: str,
        booking_id: int
):
    """Удаляет запланированную задачу из APScheduler и реестра."""
    job_key = (job_type, booking_id)
    job_id = f"{job_type}_{booking_id}"

    job_removed_from_registry = False
    # Сначала удаляем из реестра
    if job_key in scheduled_jobs_registry:
        try:
            scheduled_jobs_registry.discard(job_key)
            job_removed_from_registry = True
            logger.debug(f"Задача {job_id} удалена из реестра.")
        except Exception as e_reg_remove:
            logger.error(f"Ошибка удаления задачи {job_id} из реестра: {e_reg_remove}")

    # Затем удаляем из планировщика
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Задача {job_id} удалена из APScheduler.")
    except JobLookupError:
        # Если удалили из реестра, но в планировщике нет - это нормально (уже выполнилась/удалена)
        if job_removed_from_registry:
            logger.debug(f"Задача {job_id} не найдена в APScheduler (вероятно, уже выполнена/удалена).")
        # Если не было в реестре и нет в планировщике - тоже ок.
    except Exception as e:
        logger.error(f"Ошибка при удалении задачи {job_id} из APScheduler: {e}", exc_info=True)


# --- START OF MODIFIED FUNCTION schedule_all_notifications ---
def schedule_all_notifications(
        db: Database,
        bot: telebot.TeleBot,
        scheduler: BackgroundScheduler,
        active_timers: Dict[int, Any], # <-- Убедимся, что он здесь есть
        scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """
    Планирует уведомления о начале и конце для всех релевантных бронирований.
    СНАЧАЛА УДАЛЯЕТ ВСЕ СУЩЕСТВУЮЩИЕ ЗАДАЧИ УВЕДОМЛЕНИЙ ИЗ РЕЕСТРА.
    """
    logger.info("=== Начало полного перепланирования уведомлений (/schedule) ===")

    # --- Блок очистки реестра (без изменений) ---
    logger.info("Удаление всех существующих задач уведомлений из реестра и планировщика перед перепланированием...")
    notification_job_prefixes = (
        const.JOB_TYPE_NOTIFY_START,
        const.JOB_TYPE_NOTIFY_END,
        getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', 'final_end_notice')
    )
    keys_to_remove = {
        job_key for job_key in scheduled_jobs_registry
        if any(job_key[0] == prefix for prefix in notification_job_prefixes)
    }
    logger.debug(f"Найдено {len(keys_to_remove)} ключей задач уведомлений в реестре для удаления: {keys_to_remove}")
    removed_count_all = 0
    for job_type, booking_id in list(keys_to_remove):
        try:
             remove_scheduled_job(scheduler, scheduled_jobs_registry, job_type, booking_id)
             removed_count_all += 1
        except Exception as e_remove_reg:
             logger.error(f"Ошибка при вызове remove_scheduled_job для ({job_type}, {booking_id}): {e_remove_reg}")
    logger.info(f"Обработано {removed_count_all} ключей задач уведомлений из реестра для удаления.")
    remaining_keys = {
        job_key for job_key in scheduled_jobs_registry
        if any(job_key[0] == prefix for prefix in notification_job_prefixes)
    }
    if remaining_keys:
        logger.warning(f"В реестре остались ключи уведомлений после очистки: {remaining_keys}")
    # --- Конец блока очистки ---

    # --- Блок получения актуальных бронирований (без изменений) ---
    bookings_to_schedule: List[Tuple] = []
    try:
        bookings_to_schedule = booking_service.get_bookings_for_notification_schedule(db)
    except Exception as e_get_bookings:
        logger.critical(f"Критическая ошибка при получении бронирований для планирования: {e_get_bookings}",
                        exc_info=True)
        logger.info("=== Перепланирование уведомлений прервано из-за ошибки получения броней ===")
        return
    if not bookings_to_schedule:
        logger.info("Нет активных бронирований для планирования уведомлений.")
        logger.info("=== Перепланирование уведомлений завершено (нет активных броней) ===")
        return
    # --- Конец блока получения бронирований ---

    # --- Блок планирования задач ---
    planned_count = 0
    for booking_data in bookings_to_schedule:
        b_id: int
        user_id: int
        equip_id: int
        time_start: datetime
        time_end: datetime
        equip_name: str
        b_id, user_id, equip_id, time_start, time_end, equip_name = booking_data

        try:
            if not isinstance(time_start, datetime):
                 logger.warning(f"Пропуск брони {b_id}: некорректный тип time_start ({type(time_start)}).")
                 continue
            if not isinstance(time_end, datetime):
                 logger.warning(f"Пропуск брони {b_id}: некорректный тип time_end ({type(time_end)}).")
                 continue

            # --- Планирование уведомления о НАЧАЛЕ (без изменений) ---
            notify_start_time = time_start - timedelta(minutes=const.NOTIFICATION_BEFORE_START_MINUTES)
            schedule_one_notification(
                scheduler=scheduler,
                scheduled_jobs_registry=scheduled_jobs_registry,
                job_type=const.JOB_TYPE_NOTIFY_START,
                booking_id=b_id,
                run_time=notify_start_time,
                func_to_run=notify_user_about_booking_start,
                args_for_func=[db, bot, active_timers, scheduler, scheduled_jobs_registry, b_id, user_id, equip_name,
                               time_start]
            )

            # --- Планирование уведомления об ОКОНЧАНИИ ---
            notify_end_time = time_end - timedelta(minutes=const.NOTIFICATION_BEFORE_END_MINUTES)
            # --- ИЗМЕНЕНИЕ: Добавляем active_timers в args_for_func ---
            schedule_one_notification(
                scheduler=scheduler,
                scheduled_jobs_registry=scheduled_jobs_registry,
                job_type=const.JOB_TYPE_NOTIFY_END,
                booking_id=b_id,
                run_time=notify_end_time,
                func_to_run=send_end_booking_notification_wrapper,
                args_for_func=[
                    db,
                    bot,
                    scheduler,
                    scheduled_jobs_registry,
                    active_timers, # <-- ДОБАВЛЕНО ЗДЕСЬ
                    b_id,
                    user_id,
                    equip_id,
                    equip_name,
                    time_end
                ]
            )
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

            # --- Планирование ФИНАЛЬНОГО уведомления (без изменений) ---
            final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
            if final_end_job_type:
                schedule_one_notification(
                    scheduler=scheduler,
                    scheduled_jobs_registry=scheduled_jobs_registry,
                    job_type=final_end_job_type,
                    booking_id=b_id,
                    run_time=time_end,
                    func_to_run=_send_final_end_message,
                    args_for_func=[bot, user_id, equip_name, b_id, None]
                )
            else:
                logger.error(f"Константа JOB_TYPE_FINAL_END_NOTICE не найдена! Финальное уведомление для брони {b_id} не запланировано.")

            planned_count += 1

        except Exception as e_schedule_loop:
            logger.error(f"Ошибка при планировании уведомлений для брони {b_id}: {e_schedule_loop}", exc_info=True)
    # --- Конец блока планирования ---

    # --- Логирование результата (без изменений) ---
    final_registry_size = len(scheduled_jobs_registry)
    logger.info(
        f"=== Перепланирование уведомлений завершено. Запланировано {planned_count} броней ({planned_count*3} задач). Актуальных задач в реестре: {final_registry_size} ===")
# --- END OF MODIFIED FUNCTION schedule_all_notifications ---

def cleanup_completed_jobs(db: Database, scheduler: BackgroundScheduler, scheduled_jobs_registry: Set[Tuple[str, int]]):
    """Удаляет задачи для завершенных или отмененных бронирований."""
    logger.debug("Начало очистки задач для завершенных/отмененных бронирований...")
    query = "SELECT id FROM bookings WHERE cancel = TRUE OR finish IS NOT NULL;"
    completed_bookings_result: Optional[QueryResult] = None
    try:
        completed_bookings_result = db.execute_query(query, fetch_results=True)
    except Exception as e_query:
        logger.error(f"Ошибка при запросе завершенных/отмененных броней: {e_query}", exc_info=True)
        return # Прерываем очистку при ошибке БД

    if not completed_bookings_result:
        logger.debug("Нет завершенных/отмененных бронирований для очистки задач.")
        return

    completed_ids = set()
    try:
        for item in completed_bookings_result:
            item_id = None
            if isinstance(item, dict):
                 item_id = item.get('id')
            elif isinstance(item, (list, tuple)):
                 if len(item) > 0:
                     item_id = item[0]

            if item_id is not None:
                completed_ids.add(item_id)
            else:
                logger.warning(f"Не удалось извлечь ID из элемента: {item}")

    except Exception as e_extract:
        logger.error(f"Ошибка при извлечении ID завершенных броней: {e_extract}", exc_info=True)
        return # Прерываем, если не можем обработать результат

    if not completed_ids:
        logger.debug("Не удалось извлечь ID завершенных/отмененных броней из результата запроса.")
        return

    logger.debug(f"Найдены ID завершенных/отмененных броней: {completed_ids}")

    # Собираем все возможные типы задач, которые нужно удалить
    job_types_to_check = [
        const.JOB_TYPE_NOTIFY_START,
        const.JOB_TYPE_NOTIFY_END,
        const.JOB_TYPE_CONFIRM_TIMEOUT # Таймер автоотмены (хотя он управляется threading.Timer, задача в APScheduler могла остаться)
    ]
    # Добавляем финальное уведомление, если оно есть
    final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
    if final_end_job_type:
        job_types_to_check.append(final_end_job_type)

    # Находим ключи задач в реестре, которые соответствуют завершенным/отмененным броням
    jobs_to_remove_keys = set()
    for job_key in scheduled_jobs_registry:
        job_type = job_key[0]
        booking_id = job_key[1]
        if booking_id in completed_ids:
            if job_type in job_types_to_check:
                jobs_to_remove_keys.add(job_key)

    if not jobs_to_remove_keys:
        logger.debug("Не найдено задач в реестре для завершенных/отмененных бронирований.")
        return

    logger.info(f"Будет удалено {len(jobs_to_remove_keys)} задач для завершенных/отмененных бронирований.")
    # Создаем копию для безопасной итерации и удаления
    keys_to_remove_list = list(jobs_to_remove_keys)
    for job_type, booking_id in keys_to_remove_list:
        remove_scheduled_job(scheduler, scheduled_jobs_registry, job_type, booking_id)

    logger.debug("Очистка завершенных/отмененных задач завершена.")


# --- Функции выполнения уведомлений ---

def send_notification_message(bot: telebot.TeleBot, user_id: int, message_text: str, **kwargs) -> Optional[int]:
    """
    Отправляет текстовое сообщение пользователю с доп. параметрами.
    Возвращает message_id или None.
    """
    sent_message = None
    try:
        logger.debug(f"Попытка отправить уведомление пользователю {user_id}: '{message_text[:50]}...'")
        # Отправляем сообщение
        sent_message = bot.send_message(user_id, message_text, **kwargs)
        # Проверяем результат
        if sent_message:
            logger.info(f"Уведомление успешно отправлено пользователю {user_id} (msg_id: {sent_message.message_id}).")
            return sent_message.message_id
        else:
            # Эта ветка маловероятна для send_message, но на всякий случай
            logger.error(f"send_message для user {user_id} не вернул объект сообщения.")
            return None
    except telebot.apihelper.ApiTelegramException as e:
        # Обработка специфических ошибок API
        error_code = e.error_code
        description = e.description.lower() if e.description else ""

        if error_code == 403:
            # Пользователь заблокировал бота
            logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: бот заблокирован (403).")
            # Пытаемся пометить пользователя как неактивного
            try:
                # Локальный импорт для избежания циклических зависимостей
                from services import user_service
                # Используем новый экземпляр Database для этой операции
                temp_db = Database()
                user_service.handle_user_blocked_bot(temp_db, user_id)
                # Не забываем закрыть соединение, если get_connection/release_connection не используются
                # (зависит от реализации Database и handle_user_blocked_bot)
            except Exception as e_block:
                logger.error(f"Ошибка при вызове handle_user_blocked_bot для {user_id}: {e_block}")
        elif error_code == 400:
             if 'chat not found' in description:
                 logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: чат не найден (400).")
             elif 'user is deactivated' in description:
                 logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: пользователь деактивирован (400).")
             else:
                 logger.error(f"Ошибка Telegram API (400) при отправке уведомления пользователю {user_id}: {e}")
        else:
            # Другие ошибки API
            logger.error(f"Ошибка Telegram API ({error_code}) при отправке уведомления пользователю {user_id}: {e}")
        return None
    except Exception as e:
        # Обработка прочих непредвиденных ошибок
        logger.error(f"Неожиданная ошибка при отправке уведомления пользователю {user_id}: {e}", exc_info=True)
        return None


def notify_user_about_booking_start(
        db: Database,
        bot: telebot.TeleBot,
        active_timers: Dict[int, Any],
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        booking_id: int,
        user_id: int,
        equip_name: str,
        start_time: datetime
):
    """Отправляет уведомление о начале с кнопкой подтверждения и запускает таймер автоотмены."""
    logger.debug(f"Сработала задача уведомления о начале для брони {booking_id}")
    notification_message_id: Optional[int] = None
    booking_info: Optional[Dict[str, Any]] = None

    try:
        # 1. Проверка актуальности бронирования
        try:
            booking_info = booking_service.find_booking_by_id(db, booking_id)
        except Exception as e_find_booking:
            logger.error(f"Ошибка при поиске брони {booking_id} перед уведомлением о начале: {e_find_booking}", exc_info=True)
            # Не можем продолжить без информации о брони
            return

        is_cancelled = False
        is_finished = False
        is_confirmed = False
        if booking_info:
            is_cancelled = booking_info.get('cancel', False)
            is_finished = booking_info.get('finish') is not None
            is_confirmed = booking_info.get('confirm_start') is not None
        else:
            # Если бронь не найдена, считаем ее неактивной
            is_cancelled = True

        if is_cancelled or is_finished or is_confirmed:
            status = "отменена" if is_cancelled else "завершена" if is_finished else "уже подтверждена"
            logger.info(f"Уведомление о начале для booking_id {booking_id} не требуется (бронь {status}).")
            # Удаляем все связанные задачи, если они еще есть
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_START, booking_id)
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_END, booking_id)
            final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
            if final_end_job_type:
                remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id)
            # Удаляем таймер, если он вдруг активен
            timer = active_timers.pop(booking_id, None)
            if timer:
                try:
                    timer.cancel()
                    logger.debug(f"Отменен существующий таймер для неактивной брони {booking_id}.")
                except Exception:
                    pass # Ошибки отмены таймера игнорируем
            return

        # 2. Подготовка и отправка сообщения
        markup = keyboards.generate_start_confirmation_keyboard(booking_id)
        # Приведение времени к aware для отображения
        start_time_aware = start_time
        try:
            if start_time.tzinfo is None:
                start_time_aware = start_time.replace(tzinfo=scheduler.timezone)
            else:
                start_time_aware = start_time.astimezone(scheduler.timezone)
        except Exception as e_tz:
             logger.error(f"Ошибка приведения start_time ({start_time}) к часовому поясу для брони {booking_id}: {e_tz}")
             # Используем время как есть, если не удалось привести
             start_time_aware = start_time


        start_time_str = start_time_aware.strftime('%H:%M')
        minutes_before = const.NOTIFICATION_BEFORE_START_MINUTES
        timeout_minutes = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS // 60
        message_text = (
            f"❗ Ваше бронирование на '{equip_name}' начинается через {minutes_before} мин ({start_time_str}).\n\n"
            f"Пожалуйста, **подтвердите актуальность** в течение {timeout_minutes} минут, иначе бронь будет автоматически отменена."
        )

        # Отправляем сообщение
        notification_message_id = send_notification_message(
            bot, user_id, message_text, reply_markup=markup, parse_mode='Markdown'
        )

        # 3. Запуск таймера автоотмены, если сообщение успешно отправлено
        if notification_message_id:
            logger.info(
                f"Уведомление о начале бронирования {booking_id} (msg_id: {notification_message_id}) отправлено пользователю {user_id}.")

            # Проверяем, нет ли уже активного таймера для этой брони
            if booking_id not in active_timers:
                # Время автоотмены: за 5 минут до начала бронирования
                # (или через const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS после отправки уведомления)
                # Используем фиксированный таймаут от момента отправки уведомления
                delay_seconds = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS

                # Создаем и запускаем таймер
                timer = threading.Timer(
                    delay_seconds,
                    _run_auto_cancel, # Функция, которая будет вызвана по таймеру
                    args=[db, bot, active_timers, scheduler, scheduled_jobs_registry, booking_id, user_id,
                          notification_message_id] # Аргументы для _run_auto_cancel
                )
                # Сохраняем таймер в словаре активных таймеров
                active_timers[booking_id] = timer
                timer.start()
                logger.info(
                    f"Запущен таймер автоотмены (сработает через {delay_seconds:.1f} сек) для бронирования {booking_id}.")
            else:
                # Это не должно происходить при нормальной работе, но логируем на всякий случай
                logger.warning(f"Таймер для бронирования {booking_id} уже существует! Новый таймер не запущен.")
        else:
            # Если не удалось отправить уведомление, таймер не запускаем
            logger.error(
                f"Не удалось отправить уведомление о начале брони {booking_id} пользователю {user_id}. Таймер автоотмены не запущен.")

    except Exception as e_notify_start:
        logger.error(f"Критическая ошибка в notify_user_about_booking_start для брони {booking_id}: {e_notify_start}",
                     exc_info=True)
        # Попытка удалить таймер, если он был создан до ошибки
        timer = active_timers.pop(booking_id, None)
        if timer:
            try:
                timer.cancel()
            except Exception:
                pass

# --- START OF MODIFIED FUNCTION send_end_booking_notification_wrapper ---
# --- START OF MODIFIED FUNCTION send_end_booking_notification_wrapper ---
def send_end_booking_notification_wrapper(
        db: Database,
        bot: telebot.TeleBot,
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        active_timers: Dict[int, Any], # <-- ДОБАВЛЕН ПАРАМЕТР
        booking_id: int,
        user_id: int,
        equip_id: int,
        equip_name: str,
        end_time: datetime
):
    """Проверяет возможность продления и отправляет уведомление об окончании (за N минут)."""
    logger.debug(
        f"Сработала задача уведомления о конце (за {const.NOTIFICATION_BEFORE_END_MINUTES} мин) для брони {booking_id}")
    booking_info: Optional[Dict[str, Any]] = None
    notification_message_id: Optional[int] = None # ID сообщения о скором окончании
    end_time_aware = None # Инициализация для finally

    try:
        # 1. Проверка актуальности бронирования (без изменений)
        try:
            booking_info = booking_service.find_booking_by_id(db, booking_id)
        except Exception as e_find_booking:
            logger.error(f"Ошибка при поиске брони {booking_id} перед уведомлением о конце: {e_find_booking}", exc_info=True)
            return
        is_cancelled = False
        is_finished = False
        if booking_info:
            is_cancelled = booking_info.get('cancel', False)
            is_finished = booking_info.get('finish') is not None
        else:
            is_cancelled = True
        if is_cancelled or is_finished:
            status = "отменена" if is_cancelled else "завершена"
            logger.info(f"Уведомление об окончании для booking_id {booking_id} не требуется (бронь {status}).")
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_END, booking_id)
            final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
            if final_end_job_type:
                remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id)
            timer = active_timers.pop(booking_id, None) # Используем переданный active_timers
            if timer:
                try: timer.cancel()
                except Exception: pass
            return
        # --- Конец проверки актуальности ---

        # 2. Приведение времени к aware (без изменений)
        try:
            if end_time.tzinfo is None: end_time_aware = end_time.replace(tzinfo=scheduler.timezone)
            else: end_time_aware = end_time.astimezone(scheduler.timezone)
        except Exception as e_tz:
             logger.error(f"Ошибка приведения end_time ({end_time}) к часовому поясу для брони {booking_id}: {e_tz}")
             end_time_aware = end_time
        # --- Конец приведения времени ---

        # 3. Проверка возможности продления (без изменений)
        can_extend = False
        try:
            check_start_time = end_time_aware
            check_end_time = check_start_time + timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
            conflicts = booking_service.check_booking_conflict(
                db, equip_id,
                check_start_time.replace(tzinfo=None),
                check_end_time.replace(tzinfo=None),
                exclude_booking_id=booking_id
            )
            if not conflicts:
                end_work_dt = datetime.combine(end_time_aware.date(), const.WORKING_HOURS_END, tzinfo=scheduler.timezone)
                if check_start_time < end_work_dt: can_extend = True
                else: logger.debug(f"Продление {booking_id} невозможно (конец раб. дня).")
            else: logger.debug(f"Продление {booking_id} невозможно (конфликт).")
        except Exception as e_check_ext:
            logger.error(f"Ошибка проверки продления для брони {booking_id}: {e_check_ext}", exc_info=True)
        # --- Конец проверки продления ---

        # 4. Формирование и отправка сообщения (без изменений)
        end_time_str = end_time_aware.strftime('%H:%M')
        minutes_left = const.NOTIFICATION_BEFORE_END_MINUTES
        message_text = ""
        markup = None
        if can_extend:
            message_text = (f"🔔 Напоминание: Ваша работа на '{equip_name}' завершится через {minutes_left} мин ({end_time_str}).\nХотите продлить?")
            markup = keyboards.generate_extend_prompt_keyboard(booking_id)
        else:
            message_text = (f"🔔 Напоминание: Ваша работа на '{equip_name}' завершится через {minutes_left} мин ({end_time_str}).\n(Продление невозможно).")
        notification_message_id = send_notification_message(bot, user_id, message_text, reply_markup=markup)
        # --- Конец формирования и отправки ---

        # 5. Запуск таймера для изменения сообщения и отмены финального уведомления
        if notification_message_id:
            if can_extend:
                logger.info(f"Уведомление о завершении с опцией продления отправлено user {user_id} для брони {booking_id} (msg_id: {notification_message_id}).")
                if booking_id not in active_timers: # Используем переданный active_timers
                    delay_seconds = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS
                    # --- ИЗМЕНЕНИЕ: Добавляем active_timers в args ---
                    timer = threading.Timer(
                        delay_seconds,
                        _cancel_extend_option,
                        args=[
                            bot,
                            user_id,
                            notification_message_id,
                            equip_name,
                            booking_id,
                            end_time_aware,
                            scheduler,
                            scheduled_jobs_registry,
                            active_timers # <-- ДОБАВЛЕНО ЗДЕСЬ
                        ]
                    )
                    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                    active_timers[booking_id] = timer # Используем переданный active_timers
                    timer.start()
                    logger.info(f"Запущен таймер изменения сообщения продления (сработает через {delay_seconds:.1f} сек) для бронирования {booking_id}.")
                else:
                     logger.warning(f"Таймер для бронирования {booking_id} уже существует! Новый таймер отмены продления не запущен.")
            else:
                logger.info(f"Уведомление о завершении (без продления) отправлено user {user_id} для брони {booking_id} (msg_id: {notification_message_id}).")

            # 6. Обновление аргументов для финального уведомления (без изменений)
            final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
            if final_end_job_type:
                job_id = f"{final_end_job_type}_{booking_id}"
                try:
                    job = scheduler.get_job(job_id)
                    if job:
                        msg_id_to_pass = notification_message_id if can_extend else None
                        job.modify(args=[bot, user_id, equip_name, booking_id, msg_id_to_pass])
                        logger.debug(f"Обновлены аргументы (message_id={msg_id_to_pass}) для задачи {job_id}.")
                    else: logger.warning(f"Не найдена задача {job_id} для обновления аргументов.")
                except JobLookupError: logger.warning(f"Задача {job_id} не найдена в планировщике при попытке обновить аргументы.")
                except Exception as e_modify_job: logger.error(f"Ошибка при обновлении аргументов задачи {job_id}: {e_modify_job}", exc_info=True)
            # --- Конец обновления аргументов ---
        else:
             logger.error(f"Не удалось отправить уведомление о завершении для брони {booking_id} пользователю {user_id}.")

    except Exception as e_wrapper:
        logger.error(f"Критическая ошибка в send_end_booking_notification_wrapper для брони {booking_id}: {e_wrapper}",
                     exc_info=True)
        # Попытка удалить таймер, если он был создан до ошибки
        timer = active_timers.pop(booking_id, None) # Используем переданный active_timers
        if timer:
            try: timer.cancel()
            except Exception: pass
# --- END OF MODIFIED FUNCTION send_end_booking_notification_wrapper ---


# --- START OF MODIFIED FUNCTION _cancel_extend_option ---
def _cancel_extend_option(
        bot: telebot.TeleBot,
        user_id: int,
        message_id: Optional[int],
        equip_name: str,
        booking_id: int,
        end_time: datetime,
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        active_timers: Dict[int, Any] # <-- ДОБАВЛЕН ПАРАМЕТР
):
    """
    Редактирует сообщение, удаляя опцию продления, изменяет текст
    и отменяет финальное уведомление. Вызывается по таймеру.
    """
    logger.debug(f"Сработал таймер изменения сообщения продления для брони {booking_id}")
    # Удаляем таймер из активных (используем переданный active_timers)
    timer = active_timers.pop(booking_id, None)
    if not timer:
         logger.warning(f"Таймер для брони {booking_id} не найден в active_timers при срабатывании _cancel_extend_option.")

    final_notification_cancelled = False # Флаг для предотвращения повторной отмены

    try:
        if message_id:
            # Формируем новый текст сообщения (без изменений)
            end_time_str = "неизвестно"
            try:
                end_time_aware = end_time
                if end_time.tzinfo is None:
                    if scheduler and hasattr(scheduler, 'timezone'): end_time_aware = end_time.replace(tzinfo=scheduler.timezone)
                    else: end_time_aware = end_time.astimezone(); logger.warning(f"Не удалось получить timezone из scheduler для брони {booking_id}, используется локальная timezone.")
                else:
                    if scheduler and hasattr(scheduler, 'timezone'): end_time_aware = end_time.astimezone(scheduler.timezone)
                    else: end_time_aware = end_time; logger.warning(f"Не удалось получить timezone из scheduler для брони {booking_id}, используется исходная timezone времени.")
                end_time_str = end_time_aware.strftime('%H:%M')
            except Exception as e_fmt_time: logger.error(f"Ошибка форматирования end_time ({end_time}) для сообщения брони {booking_id}: {e_fmt_time}")
            new_text = f"Время продления вышло, ваша работа на '{equip_name}' будет завершена в {end_time_str}."
            # --- Конец формирования текста ---

            try:
                # Редактируем сообщение (без изменений)
                bot.edit_message_text(chat_id=user_id, message_id=message_id, text=new_text, reply_markup=None)
                logger.info(f"Сообщение {message_id} отредактировано: время продления вышло для брони {booking_id}.")

                # Отмена финального уведомления (без изменений)
                final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
                if final_end_job_type:
                    logger.debug(f"Попытка отменить финальное уведомление ({final_end_job_type}) для брони {booking_id} после редактирования сообщения.")
                    try:
                        remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id)
                        final_notification_cancelled = True
                    except Exception as e_remove_final: logger.error(f"Ошибка при отмене финального уведомления ({final_end_job_type}) для брони {booking_id}: {e_remove_final}", exc_info=True)
                else: logger.warning(f"Константа JOB_TYPE_FINAL_END_NOTICE не найдена, финальное уведомление для брони {booking_id} не отменяется.")
                # --- Конец отмены ---

            except telebot.apihelper.ApiTelegramException as e_edit:
                # Обработка ошибок редактирования и повторная попытка отмены (без изменений)
                description = str(e_edit).lower()
                if "message to edit not found" in description: logger.warning(f"Не удалось отредактировать сообщение {message_id} (не найдено) для отмены продления брони {booking_id}.")
                elif "message can't be edited" in description: logger.warning(f"Не удалось отредактировать сообщение {message_id} (нельзя редактировать) для отмены продления брони {booking_id}.")
                elif "message is not modified" in description: logger.debug(f"Сообщение {message_id} уже обновлено (не изменено) при отмене продления для брони {booking_id}.")
                else: logger.error(f"Ошибка API при редактировании сообщения {message_id} для отмены продления брони {booking_id}: {e_edit}.")
                # Повторная попытка отмены
                if not final_notification_cancelled:
                    final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
                    if final_end_job_type:
                        logger.debug(f"Попытка отменить финальное уведомление ({final_end_job_type}) для брони {booking_id} (после ошибки/пропуска редактирования)")
                        try: remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id); final_notification_cancelled = True
                        except Exception as e_remove_final_err: logger.error(f"Ошибка при отмене финального уведомления ({final_end_job_type}) для брони {booking_id} (после ошибки/пропуска редактирования): {e_remove_final_err}", exc_info=True)
                    else: logger.warning(f"Константа JOB_TYPE_FINAL_END_NOTICE не найдена, финальное уведомление для брони {booking_id} не отменяется (после ошибки/пропуска редактирования).")
                # --- Конец повторной попытки ---
            except Exception as e_edit_other:
                logger.error(f"Непредвиденная ошибка при редактировании сообщения {message_id} для отмены продления брони {booking_id}: {e_edit_other}", exc_info=True)
                # Попытка отмены финального уведомления при прочих ошибках (без изменений)
                if not final_notification_cancelled:
                    final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
                    if final_end_job_type:
                        logger.debug(f"Попытка отменить финальное уведомление ({final_end_job_type}) для брони {booking_id} (после прочей ошибки редактирования)")
                        try: remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id); final_notification_cancelled = True
                        except Exception as e_remove_final_other: logger.error(f"Ошибка при отмене финального уведомления ({final_end_job_type}) для брони {booking_id} (после прочей ошибки редактирования): {e_remove_final_other}", exc_info=True)
                    else: logger.warning(f"Константа JOB_TYPE_FINAL_END_NOTICE не найдена, финальное уведомление для брони {booking_id} не отменяется (после прочей ошибки редактирования).")
                # --- Конец попытки ---
        else:
            # Если message_id не был передан (без изменений)
            logger.warning(f"Не удалось отредактировать сообщение для отмены продления брони {booking_id}: message_id отсутствует.")
            # Попытка отмены финального уведомления, даже если message_id нет (без изменений)
            if not final_notification_cancelled:
                final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
                if final_end_job_type:
                    logger.debug(f"Попытка отменить финальное уведомление ({final_end_job_type}) для брони {booking_id} (message_id отсутствовал)")
                    try: remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id); final_notification_cancelled = True
                    except Exception as e_remove_final_nomsg: logger.error(f"Ошибка при отмене финального уведомления ({final_end_job_type}) для брони {booking_id} (message_id отсутствовал): {e_remove_final_nomsg}", exc_info=True)
                else: logger.warning(f"Константа JOB_TYPE_FINAL_END_NOTICE не найдена, финальное уведомление для брони {booking_id} не отменяется (message_id отсутствовал).")
            # --- Конец попытки ---

    except Exception as e:
        logger.error(f"Ошибка в _cancel_extend_option для брони {booking_id}: {e}", exc_info=True)
        # Попытка отмены финального уведомления при общей ошибке (без изменений)
        if not final_notification_cancelled:
            final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
            if final_end_job_type:
                logger.debug(f"Попытка отменить финальное уведомление ({final_end_job_type}) для брони {booking_id} (после общей ошибки в _cancel_extend_option)")
                try: remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id)
                except Exception as e_remove_final_fatal: logger.error(f"Ошибка при отмене финального уведомления ({final_end_job_type}) для брони {booking_id} (после общей ошибки в _cancel_extend_option): {e_remove_final_fatal}", exc_info=True)
            else: logger.warning(f"Константа JOB_TYPE_FINAL_END_NOTICE не найдена, финальное уведомление для брони {booking_id} не отменяется (после общей ошибки в _cancel_extend_option).")
        # --- Конец попытки ---
# --- END OF MODIFIED FUNCTION _cancel_extend_option ---

# --- ИЗМЕНЕННАЯ ФУНКЦИЯ ---
def _run_auto_cancel(
        db: Database,
        bot: telebot.TeleBot,
        active_timers: Dict[int, Any],
        scheduler: BackgroundScheduler,
        scheduled_jobs_registry: Set[Tuple[str, int]],
        booking_id: int,
        chat_id: int, # ID чата, где было отправлено сообщение
        message_id: Optional[int] # ID сообщения с кнопкой подтверждения
):
    """Выполняет автоотмену неподтвержденной брони и РЕДАКТИРУЕТ сообщение."""
    logger.debug(f"Сработал таймер автоотмены для booking_id {booking_id}. Исходное сообщение: {message_id}")

    # Удаляем таймер из активных, чтобы предотвратить повторный запуск
    timer = active_timers.pop(booking_id, None)
    if not timer:
         logger.warning(f"Таймер для booking_id {booking_id} не найден в active_timers при срабатывании _run_auto_cancel.")
    # else: # Если нужно убедиться, что таймер действительно был удален
    #     logger.debug(f"Таймер для booking_id {booking_id} удален из active_timers.")

    try:
        # Выполняем отмену бронирования в базе данных
        was_cancelled: bool = False
        owner_user_id: Optional[int] = None
        equip_name: Optional[str] = None

        try:
            # Эта функция должна возвращать флаг отмены, ID пользователя и имя оборудования
            was_cancelled, owner_user_id, equip_name = booking_service.auto_cancel_unconfirmed_booking(db, booking_id)
        except Exception as e_cancel_db:
             logger.error(f"Ошибка при вызове auto_cancel_unconfirmed_booking для брони {booking_id}: {e_cancel_db}", exc_info=True)
             # Не можем продолжить без результата отмены
             return

        if was_cancelled:
            logger.info(f"Бронь {booking_id} автоматически отменена из-за отсутствия подтверждения.")

            # Формируем текст сообщения об отмене
            message_text = "Время подтверждения вышло, ваша бронь отменена." # Используем явный текст
            if equip_name:
                 # Можно использовать константу, если она есть и подходит
                 # message_text = const.MSG_BOOKING_CONFIRM_TIMEOUT.format(equipment_name=equip_name)
                 message_text = f"Время подтверждения для брони на '{equip_name}' вышло, ваша бронь отменена."


            # Пытаемся отредактировать исходное сообщение
            if owner_user_id and message_id:
                try:
                    bot.edit_message_text(
                        chat_id=owner_user_id, # Используем ID пользователя из результата отмены
                        message_id=message_id,
                        text=message_text,
                        reply_markup=None # <<< Убираем клавиатуру
                    )
                    logger.info(f"Сообщение {message_id} отредактировано: время подтверждения вышло для брони {booking_id}.")
                except telebot.apihelper.ApiTelegramException as e_edit:
                    # Обработка ошибок редактирования
                    description = str(e_edit).lower()
                    if "message to edit not found" in description:
                        logger.warning(f"Не удалось отредактировать сообщение {message_id} (не найдено) для автоотмены брони {booking_id}. Отправка нового.")
                        send_notification_message(bot, owner_user_id, message_text)
                    elif "message can't be edited" in description:
                        logger.warning(f"Не удалось отредактировать сообщение {message_id} (нельзя редактировать) для автоотмены брони {booking_id}. Отправка нового.")
                        send_notification_message(bot, owner_user_id, message_text)
                    elif "message is not modified" in description:
                        # Сообщение уже было отредактировано (маловероятно, но возможно)
                        logger.debug(f"Сообщение {message_id} уже обновлено (не изменено) при автоотмене брони {booking_id}.")
                    else:
                        logger.error(f"Ошибка API при редактировании сообщения {message_id} для автоотмены брони {booking_id}: {e_edit}. Отправка нового.")
                        send_notification_message(bot, owner_user_id, message_text)
                except Exception as e_edit_other:
                    logger.error(
                        f"Непредвиденная ошибка при редактировании сообщения {message_id} для автоотмены брони {booking_id}: {e_edit_other}",
                        exc_info=True)
                    # Отправляем новое сообщение как fallback
                    send_notification_message(bot, owner_user_id, message_text)
            else:
                # Если нет message_id или owner_user_id, просто отправляем новое сообщение
                logger.warning(
                    f"Не удалось отредактировать сообщение для автоотмены брони {booking_id} (отсутствует message_id={message_id} или owner_user_id={owner_user_id}). Отправка нового.")
                if owner_user_id: # Проверяем, что ID пользователя есть
                     send_notification_message(bot, owner_user_id, message_text)
                else:
                     logger.error(f"Не удалось отправить уведомление об автоотмене брони {booking_id}: отсутствует owner_user_id.")


            # Удаляем связанные запланированные задачи (уведомление о конце и финальное)
            remove_scheduled_job(scheduler, scheduled_jobs_registry, const.JOB_TYPE_NOTIFY_END, booking_id)
            final_end_job_type = getattr(const, 'JOB_TYPE_FINAL_END_NOTICE', None)
            if final_end_job_type:
                remove_scheduled_job(scheduler, scheduled_jobs_registry, final_end_job_type, booking_id)
            # Задачу JOB_TYPE_NOTIFY_START удалять не нужно, т.к. она уже выполнилась
            # Задачу JOB_TYPE_CONFIRM_TIMEOUT тоже, т.к. она связана с этим таймером

        else:
            # Если auto_cancel_unconfirmed_booking вернула False
            logger.debug(
                f"Бронь {booking_id} не была автоматически отменена (возможно, уже подтверждена или отменена ранее).")
            # Таймер уже удален из active_timers в начале функции.
            # Никаких сообщений пользователю отправлять не нужно.

    except Exception as e:
        logger.error(f"Критическая ошибка в _run_auto_cancel для booking_id {booking_id}: {e}", exc_info=True)


def confirm_booking_callback_logic(
        db: Database,
        active_timers: Dict[int, Any],
        booking_id: int,
        user_id: int
) -> bool:
    """
    Логика обработки нажатия кнопки подтверждения бронирования.
    Останавливает таймер автоотмены и подтверждает бронь в БД.
    Возвращает True при успехе, False при неудаче или если таймер уже сработал.
    """
    logger.debug(f"Попытка подтверждения брони {booking_id} пользователем {user_id}")

    # 1. Попытка остановить таймер автоотмены
    timer = active_timers.pop(booking_id, None)
    if timer:
        try:
            timer.cancel()
            logger.info(f"Таймер автоотмены для бронирования {booking_id} успешно остановлен пользователем.")
        except Exception as e_cancel:
            # Ошибка отмены таймера не критична, но логируем
            logger.error(f"Ошибка при отмене таймера для брони {booking_id}: {e_cancel}")
            # Продолжаем выполнение, т.к. таймер уже удален из active_timers
    else:
        # Если таймера нет в active_timers, значит он либо уже сработал, либо не был запущен
        logger.warning(
            f"Активный таймер для бронирования {booking_id} не найден при подтверждении. Проверяем статус брони...")
        # Проверяем, не была ли бронь уже отменена (вероятно, таймером)
        try:
            booking_info = booking_service.find_booking_by_id(db, booking_id)
            # Проверяем флаг cancel и confirm_start
            is_cancelled = booking_info.get('cancel', False) if booking_info else True
            is_confirmed = booking_info.get('confirm_start') is not None if booking_info else False

            if is_cancelled:
                 logger.warning(f"Попытка подтвердить бронь {booking_id}, которая уже ОТМЕНЕНА (вероятно, таймером). Отказ.")
                 return False # Не позволяем подтвердить уже отмененную бронь
            if is_confirmed:
                 logger.warning(f"Попытка подтвердить бронь {booking_id}, которая уже ПОДТВЕРЖДЕНА. Игнорируем.")
                 # Возвращаем True, т.к. цель (подтверждение) достигнута, хоть и ранее
                 return True
            # Если не отменена и не подтверждена, но таймера нет - это странная ситуация, но пробуем подтвердить
            logger.warning(f"Бронь {booking_id} не отменена и не подтверждена, но таймер не найден. Продолжаем попытку подтверждения.")

        except Exception as e_check_cancel:
            logger.error(f"Ошибка проверки статуса брони {booking_id} перед подтверждением (после отсутствия таймера): {e_check_cancel}")
            # В случае ошибки проверки, не рискуем подтверждать
            return False

    # 2. Подтверждение бронирования в базе данных
    try:
        # Эта функция должна возвращать True при успехе
        success = booking_service.confirm_start_booking(db, booking_id, user_id)
        if success:
             logger.info(f"Бронь {booking_id} успешно подтверждена пользователем {user_id}.")
             return True
        else:
             logger.warning(f"Функция confirm_start_booking для брони {booking_id} вернула False.")
             # Возможно, проверка внутри confirm_start_booking выявила проблему
             return False
    except Exception as e_confirm:
        logger.error(f"Ошибка при вызове booking_service.confirm_start_booking для {booking_id}: {e_confirm}",
                     exc_info=True)
        return False


def _send_final_end_message(
        bot: telebot.TeleBot,
        user_id: int,
        equip_name: str,
        booking_id: int,
        message_id: Optional[int] = None # ID сообщения о скором окончании (если было)
):
    """Редактирует или отправляет сообщение о фактическом завершении работы."""
    logger.debug(f"Сработала задача финального уведомления для брони {booking_id}.")
    try:
        # Текст финального сообщения
        message_text = f"🏁 Ваша работа на оборудовании '{equip_name}' окончена."

        if message_id:
            # Если есть ID предыдущего сообщения (о скором окончании), пытаемся его отредактировать
            try:
                bot.edit_message_text(
                    chat_id=user_id,
                    message_id=message_id,
                    text=message_text,
                    reply_markup=None # Убираем клавиатуру, если она там была
                )
                logger.info(f"Сообщение {message_id} отредактировано на финальное для брони {booking_id}.")
            except telebot.apihelper.ApiTelegramException as e_edit:
                # Обработка ошибок редактирования
                description = str(e_edit).lower()
                if "message to edit not found" in description:
                    logger.warning(
                        f"Не удалось отредактировать сообщение {message_id} (не найдено) на финальное для брони {booking_id}. Отправляем новое.")
                    send_notification_message(bot, user_id, message_text)
                elif "message can't be edited" in description:
                     logger.warning(
                        f"Не удалось отредактировать сообщение {message_id} (нельзя редактировать) на финальное для брони {booking_id}. Отправляем новое.")
                     send_notification_message(bot, user_id, message_text)
                elif "message is not modified" in description:
                    # Сообщение уже имеет финальный текст (например, если _cancel_extend_option его уже изменил)
                    logger.debug(f"Сообщение {message_id} уже имеет финальный текст (не изменено) для брони {booking_id}.")
                else:
                    logger.error(
                        f"Ошибка API при редактировании сообщения {message_id} на финальное для брони {booking_id}: {e_edit}. Отправляем новое.")
                    send_notification_message(bot, user_id, message_text)
            except Exception as e_edit_other:
                logger.error(
                    f"Непредвиденная ошибка при редактировании сообщения {message_id} на финальное для брони {booking_id}: {e_edit_other}",
                    exc_info=True)
                # Отправляем новое сообщение как fallback
                send_notification_message(bot, user_id, message_text)
        else:
            # Если ID предыдущего сообщения не было передано, просто отправляем новое
            logger.info(f"Финальное сообщение отправлено для брони {booking_id} (message_id не был предоставлен).")
            send_notification_message(bot, user_id, message_text)

    except Exception as e:
        logger.error(f"Ошибка в _send_final_end_message для брони {booking_id}, user {user_id}: {e}", exc_info=True)

# --- END OF FILE notification_service.py ---