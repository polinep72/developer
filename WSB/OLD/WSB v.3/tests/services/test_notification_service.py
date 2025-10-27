# tests/services/test_notification_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch, mock_open
from datetime import datetime, timedelta
import pytz
import logging
import json
import datetime as dt_original
from typing import Dict, Any, Set, Tuple, Optional, Callable, List # Добавили для type hinting

# Импортируем тестируемый модуль
try:
    from services import notification_service
    MODULE_EXISTS = True
except ImportError:
    notification_service = None
    MODULE_EXISTS = False

# Пропускаем все тесты, если модуль не найден
pytestmark = pytest.mark.skipif(not MODULE_EXISTS, reason="Модуль services.notification_service не найден")

# Импортируем зависимости
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.date import DateTrigger
# Используем псевдонимы для импорта, чтобы не конфликтовать с mocker
from services import booking_service as booking_service_module
from services import user_service as user_service_module

import constants as const
try:
    from database import Database, QueryResult
except ImportError:
    Database = object
    QueryResult = Optional[List[Dict[str, Any]]] # Fallback

# Импорт для определения типа клавиатуры и API исключений
try:
    import telebot
    from telebot import apihelper
    from telebot.types import InlineKeyboardMarkup
    IS_TELEBOT = True
except ImportError:
    IS_TELEBOT = False
    class BotMock: pass
    class ApiTelegramException(Exception): pass
    InlineKeyboardMarkup = object
    telebot = BotMock()
    apihelper = object()
    apihelper.ApiTelegramException = ApiTelegramException


# Настройка логирования для тестов
log = logging.getLogger("TestNotificationService")

# --- Тестовые данные и константы ---
TEST_BOOKING_ID_1 = 101
TEST_BOOKING_ID_2 = 102
TEST_USER_ID = 13
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
NOW_AWARE = datetime.now(MOSCOW_TZ)
TIME_FUTURE_1 = NOW_AWARE + timedelta(hours=1)
TIME_FUTURE_2 = NOW_AWARE + timedelta(hours=2)
TIME_PAST = NOW_AWARE - timedelta(minutes=10)

JOB_TYPE_START = const.JOB_TYPE_NOTIFY_START
JOB_TYPE_END = const.JOB_TYPE_NOTIFY_END
EQUIP_NAME = "Тестовое Оборудование"
EQUIP_ID = 25

# --- Класс для мокинга datetime ---
class MockDateTime(dt_original.datetime):
    _mock_now = None
    @classmethod
    def set_now(cls, dt_to_set):
        if not isinstance(dt_to_set, dt_original.datetime):
            raise TypeError(f"MockDateTime.set_now ожидает datetime, получил {type(dt_to_set)}")
        cls._mock_now = dt_to_set
        # log.debug(f"MockDateTime.now установлен на: {cls._mock_now}")
    @classmethod
    def now(cls, tz=None):
        dt_now = cls._mock_now if cls._mock_now else dt_original.datetime.now(tz)
        if tz and dt_now.tzinfo is None: # Если запросили aware, а мок naive
             try: dt_now = tz.localize(dt_now)
             except ValueError: dt_now = dt_now.astimezone(tz) # Если уже был localized
        elif not tz and dt_now.tzinfo is not None: # Если запросили naive, а мок aware
             dt_now = dt_now.replace(tzinfo=None)
        # log.debug(f"MockDateTime.now(tz={tz}) вызван, возвращает: {dt_now}")
        return dt_now
    @classmethod
    def reset_now(cls):
        # log.debug(f"MockDateTime.now сброшен (был: {cls._mock_now})")
        cls._mock_now = None

@pytest.fixture(autouse=True)
def auto_mock_datetime_now(mocker):
    """Автоматически патчит datetime.datetime на MockDateTime."""
    mock = mocker.patch('services.notification_service.datetime', MockDateTime)
    yield mock
    MockDateTime.reset_now() # Сбрасываем после теста

# --- Фикстуры ---

@pytest.fixture
def mock_scheduler(mocker):
    scheduler = mocker.Mock(spec=BackgroundScheduler)
    scheduler.timezone = MOSCOW_TZ # Устанавливаем таймзону
    scheduler.get_job.return_value = None # По умолчанию задача не найдена
    scheduler.remove_job.side_effect = None # По умолчанию удаление успешно или JobLookupError
    scheduler.add_job.side_effect = None # По умолчанию добавление успешно
    return scheduler

@pytest.fixture
def scheduled_jobs_registry():
    """Фикстура для создания пустого реестра перед каждым тестом."""
    return set()

@pytest.fixture
def mock_db(mocker):
    """Фикстура для создания мока Database."""
    return mocker.Mock(spec=Database)

@pytest.fixture
def mock_bot(mocker):
    """Фикстура для создания мока TeleBot."""
    if IS_TELEBOT:
        bot = mocker.Mock(spec=telebot.TeleBot)
        bot.send_message = MagicMock()
        bot.edit_message_text = MagicMock()
        bot.edit_message_reply_markup = MagicMock()
        # Добавим моки для FSM
        bot.set_state = MagicMock()
        bot.get_state = MagicMock(return_value=None) # По умолчанию нет состояния
        bot.delete_state = MagicMock()
        bot.add_data = MagicMock()
        bot.retrieve_data = MagicMock() # retrieve_data - context manager
        mock_retrieved_data = {}
        bot.retrieve_data.return_value.__enter__.return_value = mock_retrieved_data
        bot.retrieve_data.return_value.__exit__.return_value = None

    else: # Заглушка, если telebot не установлен
        bot = mocker.Mock(spec=BotMock)
        bot.send_message = AsyncMock()
        # Добавить другие AsyncMock, если aiogram
    return bot

# --- Тесты для schedule_one_notification ---
def test_schedule_one_notification_success_new(mocker, mock_scheduler, scheduled_jobs_registry):
    """Тест: Успешное планирование новой задачи."""
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    job_id = f"{JOB_TYPE_START}_{TEST_BOOKING_ID_1}"
    run_time_naive = TIME_FUTURE_1.replace(tzinfo=None) # Передаем naive
    run_time_aware = MOSCOW_TZ.localize(run_time_naive) # Ожидаемое aware время

    # Настраиваем мок remove_job на JobLookupError (задачи нет)
    mock_scheduler.remove_job.side_effect = JobLookupError(job_id)

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, run_time_naive,
        mock_func, ['arg1']
    )

    # Проверяем вызов add_job
    mock_scheduler.add_job.assert_called_once()
    call_args, call_kwargs = mock_scheduler.add_job.call_args
    assert call_args[0] == mock_func
    assert isinstance(call_kwargs['trigger'], DateTrigger)
    # Сравниваем aware datetime объекты
    assert call_kwargs['trigger'].run_date == run_time_aware
    assert call_kwargs['args'] == ['arg1']
    assert call_kwargs['id'] == job_id
    assert call_kwargs['replace_existing'] is True

    # Проверяем реестр
    assert job_key in scheduled_jobs_registry
    # Проверяем, что get_job не вызывался (т.к. ключа не было в реестре)
    mock_scheduler.get_job.assert_not_called()
    # Проверяем, что remove_job был вызван
    mock_scheduler.remove_job.assert_called_once_with(job_id)

def test_schedule_one_notification_skip_past_time(mocker, mock_scheduler, scheduled_jobs_registry):
    """Тест: Пропуск задачи, время которой уже прошло (без удаления из реестра)."""
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    run_time_naive = TIME_PAST.replace(tzinfo=None)

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, run_time_naive,
        mock_func, ['arg1']
    )

    mock_scheduler.add_job.assert_not_called()
    assert job_key not in scheduled_jobs_registry
    # remove_job не должен вызываться, если задачи не было в реестре
    mock_scheduler.remove_job.assert_not_called()


def test_schedule_one_notification_skip_past_time_remove_from_registry(mocker, mock_scheduler, scheduled_jobs_registry):
    """Тест: Пропуск задачи в прошлом с удалением из реестра и планировщика."""
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    job_id = f"{JOB_TYPE_START}_{TEST_BOOKING_ID_1}"
    scheduled_jobs_registry.add(job_key) # Добавляем в реестр
    run_time_naive = TIME_PAST.replace(tzinfo=None)

    # Настраиваем remove_job на успех
    mock_scheduler.remove_job.side_effect = None

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, run_time_naive,
        mock_func, ['arg1']
    )

    mock_scheduler.add_job.assert_not_called()
    # Проверяем, что ключ удален из реестра
    assert job_key not in scheduled_jobs_registry
    # Проверяем, что remove_job был вызван (через remove_scheduled_job)
    mock_scheduler.remove_job.assert_called_once_with(job_id)

def test_schedule_one_notification_already_scheduled_and_actual(mocker, mock_scheduler, scheduled_jobs_registry):
    """Тест: Пропуск задачи, которая уже актуально запланирована."""
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    job_id = f"{JOB_TYPE_START}_{TEST_BOOKING_ID_1}"
    scheduled_jobs_registry.add(job_key)
    run_time_naive = TIME_FUTURE_1.replace(tzinfo=None)
    run_time_aware = MOSCOW_TZ.localize(run_time_naive)

    # Имитируем существующую актуальную задачу
    mock_existing_job = MagicMock()
    mock_existing_job.next_run_time = run_time_aware
    mock_scheduler.get_job.return_value = mock_existing_job

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, run_time_naive,
        mock_func, ['arg1']
    )

    mock_scheduler.add_job.assert_not_called()
    mock_scheduler.remove_job.assert_not_called() # Удалять не должны
    assert job_key in scheduled_jobs_registry # Ключ остается
    mock_scheduler.get_job.assert_called_once_with(job_id)

def test_schedule_one_notification_reschedule_different_time(mocker, mock_scheduler, scheduled_jobs_registry):
    """Тест: Перепланирование, если время существующей задачи отличается."""
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    job_id = f"{JOB_TYPE_START}_{TEST_BOOKING_ID_1}"
    scheduled_jobs_registry.add(job_key)
    new_run_time_naive = TIME_FUTURE_1.replace(tzinfo=None)
    new_run_time_aware = MOSCOW_TZ.localize(new_run_time_naive)
    old_run_time_aware = TIME_FUTURE_2 # Другое время

    mock_existing_job = MagicMock()
    mock_existing_job.next_run_time = old_run_time_aware
    mock_scheduler.get_job.return_value = mock_existing_job
    mock_scheduler.remove_job.side_effect = None # Удаление успешно

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, new_run_time_naive,
        mock_func, ['arg1']
    )

    mock_scheduler.get_job.assert_called_once_with(job_id)
    mock_scheduler.remove_job.assert_called_once_with(job_id) # Старая удаляется
    mock_scheduler.add_job.assert_called_once() # Новая добавляется
    call_args, call_kwargs = mock_scheduler.add_job.call_args
    assert call_kwargs['trigger'].run_date == new_run_time_aware # Проверяем новое время
    assert call_kwargs['id'] == job_id
    assert job_key in scheduled_jobs_registry # Ключ все еще (или снова) в реестре

def test_schedule_one_notification_reschedule_not_in_scheduler(mocker, mock_scheduler, scheduled_jobs_registry):
    """Тест: Перепланирование, если задача есть в реестре, но не в планировщике."""
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    job_id = f"{JOB_TYPE_START}_{TEST_BOOKING_ID_1}"
    scheduled_jobs_registry.add(job_key)
    run_time_naive = TIME_FUTURE_1.replace(tzinfo=None)
    run_time_aware = MOSCOW_TZ.localize(run_time_naive)

    mock_scheduler.get_job.return_value = None # Не найдено в планировщике
    mock_scheduler.remove_job.side_effect = JobLookupError(job_id) # Ошибка при удалении

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, run_time_naive,
        mock_func, ['arg1']
    )

    mock_scheduler.get_job.assert_called_once_with(job_id)
    mock_scheduler.remove_job.assert_called_once_with(job_id) # Попытка удаления была
    mock_scheduler.add_job.assert_called_once() # Новая задача добавлена
    assert job_key in scheduled_jobs_registry

def test_schedule_one_notification_add_job_error(mocker, mock_scheduler, scheduled_jobs_registry, caplog):
    """Тест: Ошибка при вызове scheduler.add_job."""
    caplog.set_level(logging.ERROR)
    mock_func = MagicMock()
    job_key = (JOB_TYPE_START, TEST_BOOKING_ID_1)
    job_id = f"{JOB_TYPE_START}_{TEST_BOOKING_ID_1}"
    run_time_naive = TIME_FUTURE_1.replace(tzinfo=None)

    # Имитируем ошибку добавления
    mock_scheduler.add_job.side_effect = Exception("APScheduler add error")
    mock_scheduler.remove_job.side_effect = JobLookupError(job_id) # remove не находит

    notification_service.schedule_one_notification(
        mock_scheduler, scheduled_jobs_registry,
        JOB_TYPE_START, TEST_BOOKING_ID_1, run_time_naive,
        mock_func, ['arg1']
    )

    mock_scheduler.add_job.assert_called_once()
    assert job_key not in scheduled_jobs_registry # Ключ не должен добавиться в реестр при ошибке
    assert f"Ошибка при планировании задачи {job_id}" in caplog.text


# --- Тесты для remove_scheduled_job ---
def test_remove_scheduled_job_success(mocker, mock_scheduler, scheduled_jobs_registry):
    job_key = (JOB_TYPE_END, TEST_BOOKING_ID_2); job_id = f"{JOB_TYPE_END}_{TEST_BOOKING_ID_2}"
    scheduled_jobs_registry.add(job_key); mock_scheduler.remove_job.side_effect = None
    notification_service.remove_scheduled_job(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_END, TEST_BOOKING_ID_2)
    assert job_key not in scheduled_jobs_registry; mock_scheduler.remove_job.assert_called_once_with(job_id)

def test_remove_scheduled_job_not_in_registry(mocker, mock_scheduler, scheduled_jobs_registry):
    job_id = f"{JOB_TYPE_END}_{TEST_BOOKING_ID_2}"; mock_scheduler.remove_job.side_effect = None
    notification_service.remove_scheduled_job(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_END, TEST_BOOKING_ID_2)
    assert not scheduled_jobs_registry; mock_scheduler.remove_job.assert_called_once_with(job_id)

def test_remove_scheduled_job_not_in_scheduler(mocker, mock_scheduler, scheduled_jobs_registry):
    job_key = (JOB_TYPE_END, TEST_BOOKING_ID_2); job_id = f"{JOB_TYPE_END}_{TEST_BOOKING_ID_2}"
    scheduled_jobs_registry.add(job_key); mock_scheduler.remove_job.side_effect = JobLookupError(job_id)
    notification_service.remove_scheduled_job(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_END, TEST_BOOKING_ID_2)
    assert job_key not in scheduled_jobs_registry; mock_scheduler.remove_job.assert_called_once_with(job_id)

def test_remove_scheduled_job_other_error(mocker, mock_scheduler, scheduled_jobs_registry, caplog):
    caplog.set_level(logging.ERROR)
    job_key = (JOB_TYPE_END, TEST_BOOKING_ID_2); job_id = f"{JOB_TYPE_END}_{TEST_BOOKING_ID_2}"
    scheduled_jobs_registry.add(job_key); mock_scheduler.remove_job.side_effect = Exception("Scheduler internal error")
    notification_service.remove_scheduled_job(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_END, TEST_BOOKING_ID_2)
    assert job_key not in scheduled_jobs_registry; mock_scheduler.remove_job.assert_called_once_with(job_id); assert f"Ошибка при удалении задачи {job_id}" in caplog.text

# --- Тесты для cleanup_completed_jobs ---
def test_cleanup_completed_jobs_no_completed(mocker, mock_db, mock_scheduler, scheduled_jobs_registry):
    """Тест: нет завершенных броней, ничего не удаляется."""
    mock_db.execute_query.return_value = [] # БД не вернула завершенных
    mock_remove = mocker.patch.object(notification_service, 'remove_scheduled_job')
    notification_service.cleanup_completed_jobs(mock_db, mock_scheduler, scheduled_jobs_registry)
    query_expected_start = "SELECT id FROM bookings WHERE cancel = TRUE OR finish IS NOT NULL"; mock_db.execute_query.assert_called_once(); assert mock_db.execute_query.call_args[0][0].strip().startswith(query_expected_start); assert mock_db.execute_query.call_args[1].get('fetch_results') is True
    mock_remove.assert_not_called()

def test_cleanup_completed_jobs_no_jobs_in_registry(mocker, mock_db, mock_scheduler, scheduled_jobs_registry):
    """Тест: есть завершенные брони, но нет задач в реестре."""
    completed_id = 50; mock_db.execute_query.return_value = [{'id': completed_id}]
    mock_remove = mocker.patch.object(notification_service, 'remove_scheduled_job')
    notification_service.cleanup_completed_jobs(mock_db, mock_scheduler, scheduled_jobs_registry)
    mock_db.execute_query.assert_called_once(); mock_remove.assert_not_called()

def test_cleanup_completed_jobs_success_removes_jobs(mocker, mock_db, mock_scheduler, scheduled_jobs_registry):
    """Тест: успешное удаление задач для завершенных броней."""
    completed_id_1 = 50; completed_id_2 = 51; active_booking_id = 52
    job_key_start_1 = (JOB_TYPE_START, completed_id_1); job_key_end_1 = (JOB_TYPE_END, completed_id_1)
    job_key_start_2 = (JOB_TYPE_START, completed_id_2); job_key_active = (JOB_TYPE_START, active_booking_id)
    # Имитируем реестр
    scheduled_jobs_registry.update([job_key_start_1, job_key_end_1, job_key_start_2, job_key_active])
    # БД возвращает завершенные ID
    mock_db.execute_query.return_value = [{'id': completed_id_1}, {'id': completed_id_2}]
    # Мокируем функцию удаления
    mock_remove = mocker.patch.object(notification_service, 'remove_scheduled_job')

    # Вызов
    notification_service.cleanup_completed_jobs(mock_db, mock_scheduler, scheduled_jobs_registry)

    # Проверки
    mock_db.execute_query.assert_called_once()
    expected_calls = [
        call(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_START, completed_id_1),
        call(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_END, completed_id_1),
        call(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_START, completed_id_2)
    ]
    mock_remove.assert_has_calls(expected_calls, any_order=True)
    assert mock_remove.call_count == 3
    # Проверяем, что вызов для активной брони НЕ был сделан
    assert call(mock_scheduler, scheduled_jobs_registry, JOB_TYPE_START, active_booking_id) not in mock_remove.call_args_list

def test_cleanup_completed_jobs_db_error(mocker, mock_db, mock_scheduler, scheduled_jobs_registry, caplog):
    """Тест: ошибка при запросе завершенных броней."""
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Query Error")
    mock_remove = mocker.patch.object(notification_service, 'remove_scheduled_job')

    # Вызов
    notification_service.cleanup_completed_jobs(mock_db, mock_scheduler, scheduled_jobs_registry)

    # Проверки
    mock_db.execute_query.assert_called_once()
    mock_remove.assert_not_called() # Удаление не должно вызываться
    assert "Ошибка во время cleanup_completed_jobs" in caplog.text

# --- Тесты для schedule_all_notifications ---
@pytest.fixture
def mock_schedule_all_dependencies(mocker):
    """Мокает зависимости для schedule_all_notifications."""
    # Мокаем только внешние зависимости, не сам schedule_one_notification
    mocks = {
        'cleanup': mocker.patch.object(notification_service, 'cleanup_completed_jobs'),
        'get_bookings': mocker.patch.object(booking_service_module, 'get_bookings_for_notification_schedule'),
        # Не мокаем schedule_one_notification и remove_scheduled_job
    }
    return mocks

def test_schedule_all_notifications_no_bookings(mocker, mock_db, mock_bot, mock_scheduler, scheduled_jobs_registry, mock_schedule_all_dependencies):
    """Тест: нет броней для планирования, реестр очищается."""
    mock_schedule_all_dependencies['get_bookings'].return_value = []
    # Имитируем старую задачу в реестре
    old_job_key = (JOB_TYPE_START, 999)
    old_job_id = f"{old_job_key[0]}_{old_job_key[1]}"
    scheduled_jobs_registry.add(old_job_key)

    # remove_job планировщика должен быть вызван
    mock_scheduler.remove_job.side_effect = None

    # Вызов
    notification_service.schedule_all_notifications(
        mock_db, mock_bot, mock_scheduler, {}, scheduled_jobs_registry # Передаем {} вместо active_timers
    )

    # Проверки
    mock_schedule_all_dependencies['cleanup'].assert_called_once()
    mock_schedule_all_dependencies['get_bookings'].assert_called_once()
    mock_scheduler.add_job.assert_not_called() # Новые задачи не добавляются
    # Старая задача должна быть удалена
    mock_scheduler.remove_job.assert_called_once_with(old_job_id)
    assert not scheduled_jobs_registry # Реестр должен быть пуст

def test_schedule_all_notifications_schedules_correctly(mocker, mock_db, mock_bot, mock_scheduler, scheduled_jobs_registry, mock_schedule_all_dependencies):
    """Тест: удаление устаревших и планирование актуальных задач."""
    booking_id_actual_1 = 10; booking_id_actual_2 = 11; booking_id_outdated = 12
    equip_name_1 = "Место 1"; equip_name_2 = "Место 2"
    job_key_start_actual_1 = (JOB_TYPE_START, booking_id_actual_1) # Уже в реестре
    job_key_end_outdated = (JOB_TYPE_END, booking_id_outdated) # Устаревшая
    job_id_outdated = f"{job_key_end_outdated[0]}_{job_key_end_outdated[1]}"

    scheduled_jobs_registry.add(job_key_start_actual_1)
    scheduled_jobs_registry.add(job_key_end_outdated)

    # Время для актуальных броней
    start_time_1 = NOW_AWARE + timedelta(hours=2); end_time_1 = NOW_AWARE + timedelta(hours=3)
    start_time_2 = NOW_AWARE + timedelta(hours=4); end_time_2 = NOW_AWARE + timedelta(hours=5)
    # Сервис возвращает кортежи
    mock_schedule_all_dependencies['get_bookings'].return_value = [
        (booking_id_actual_1, 201, 1, start_time_1, end_time_1, equip_name_1),
        (booking_id_actual_2, 202, 2, start_time_2, end_time_2, equip_name_2),
    ]

    # Настраиваем моки remove_job и get_job
    existing_job_mock = MagicMock()
    existing_job_mock.next_run_time = start_time_1 - timedelta(minutes=const.NOTIFICATION_BEFORE_START_MINUTES) # Актуальное время
    def get_job_side_effect(job_id):
        if job_id == f"{JOB_TYPE_START}_{booking_id_actual_1}":
            return existing_job_mock # Эта задача уже есть и актуальна
        return None # Других нет
    def remove_job_side_effect(job_id):
        if job_id == job_id_outdated: return # Успешное удаление устаревшей
        else: raise JobLookupError(job_id) # Новых и актуальной не должно быть
    mock_scheduler.get_job.side_effect = get_job_side_effect
    mock_scheduler.remove_job.side_effect = remove_job_side_effect

    # Вызов
    notification_service.schedule_all_notifications(
        mock_db, mock_bot, mock_scheduler, {}, scheduled_jobs_registry
    )

    # Проверки
    mock_schedule_all_dependencies['cleanup'].assert_called_once()
    mock_schedule_all_dependencies['get_bookings'].assert_called_once()

    # Проверка удаления устаревшей задачи
    mock_scheduler.remove_job.assert_any_call(job_id_outdated)

    # Проверка добавления новых задач
    # Должны быть добавлены: end1, start2, end2 (т.к. start1 уже актуальна)
    assert mock_scheduler.add_job.call_count == 3

    # Проверка итогового реестра
    assert len(scheduled_jobs_registry) == 4
    assert (JOB_TYPE_START, booking_id_actual_1) in scheduled_jobs_registry
    assert (JOB_TYPE_END, booking_id_actual_1) in scheduled_jobs_registry
    assert (JOB_TYPE_START, booking_id_actual_2) in scheduled_jobs_registry
    assert (JOB_TYPE_END, booking_id_actual_2) in scheduled_jobs_registry
    assert job_key_end_outdated not in scheduled_jobs_registry


# --- Тесты для send_notification_message ---
# (Тесты send_notification_message остаются без изменений)
@pytest.mark.skipif(not IS_TELEBOT, reason="Тест для синхронного send_message (telebot)")
def test_send_notification_message_success_sync(mocker, mock_bot):
    user_id = TEST_USER_ID; text = "Test notification"; reply_markup = MagicMock()
    notification_service.send_notification_message(mock_bot, user_id, text, reply_markup=reply_markup)
    mock_bot.send_message.assert_called_once_with(user_id, text, reply_markup=reply_markup)

@pytest.mark.skipif(not IS_TELEBOT, reason="Тест для синхронного send_message (telebot)")
def test_send_notification_message_forbidden_sync(mocker, mock_bot, mock_db, caplog): # Добавляем mock_db
    caplog.set_level(logging.WARNING); user_id = TEST_USER_ID; text = "Test notification"
    mock_handle_block = mocker.patch.object(user_service_module, 'handle_user_blocked_bot')
    mocker.patch('services.notification_service.Database', return_value=mock_db) # Мокаем создание Database
    error_json_str = '{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}'; error_json_dict = json.loads(error_json_str)
    mock_bot.send_message.side_effect = apihelper.ApiTelegramException('sendMessage', error_json_str, error_json_dict)
    notification_service.send_notification_message(mock_bot, user_id, text)
    mock_bot.send_message.assert_called_once()
    # Проверяем вызов обработчика с моком БД
    mock_handle_block.assert_called_once_with(mock_db, user_id)
    assert f"Ошибка отправки {user_id}: бот заблокирован" in caplog.text

@pytest.mark.skipif(not IS_TELEBOT, reason="Тест для синхронного send_message (telebot)")
def test_send_notification_message_api_error_sync(mocker, mock_bot, mock_db, caplog):
    caplog.set_level(logging.WARNING); user_id = TEST_USER_ID; text = "Test notification"
    mock_handle_block = mocker.patch.object(user_service_module, 'handle_user_blocked_bot')
    error_json_str = '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'; error_json_dict = json.loads(error_json_str)
    mock_bot.send_message.side_effect = apihelper.ApiTelegramException('sendMessage', error_json_str, error_json_dict)
    notification_service.send_notification_message(mock_bot, user_id, text)
    mock_bot.send_message.assert_called_once(); mock_handle_block.assert_not_called()
    assert f"Не удалось отправить уведомление пользователю {user_id}: чат не найден" in caplog.text

@pytest.mark.skipif(not IS_TELEBOT, reason="Тест для синхронного send_message (telebot)")
def test_send_notification_message_unexpected_error_sync(mocker, mock_bot, mock_db, caplog):
    caplog.set_level(logging.ERROR); user_id = TEST_USER_ID; text = "Test notification"
    mock_handle_block = mocker.patch.object(user_service_module, 'handle_user_blocked_bot')
    error_message = "Network issue"; mock_bot.send_message.side_effect = Exception(error_message)
    notification_service.send_notification_message(mock_bot, user_id, text)
    mock_bot.send_message.assert_called_once(); mock_handle_block.assert_not_called()
    assert f"Неожиданная ошибка при отправке уведомления {user_id}" in caplog.text; assert error_message in caplog.text

# --- Тесты для send_end_booking_notification_wrapper ---
# (Требуется добавить тесты)
@pytest.mark.skip("Тесты для send_end_booking_notification_wrapper еще не реализованы")
def test_send_end_booking_notification_wrapper_can_extend(): pass

@pytest.mark.skip("Тесты для send_end_booking_notification_wrapper еще не реализованы")
def test_send_end_booking_notification_wrapper_cannot_extend_conflict(): pass

@pytest.mark.skip("Тесты для send_end_booking_notification_wrapper еще не реализованы")
def test_send_end_booking_notification_wrapper_cannot_extend_work_hours(): pass

@pytest.mark.skip("Тесты для send_end_booking_notification_wrapper еще не реализованы")
def test_send_end_booking_notification_wrapper_booking_inactive(): pass

@pytest.mark.skip("Тесты для send_end_booking_notification_wrapper еще не реализованы")
def test_send_end_booking_notification_wrapper_send_error(): pass


# --- Тесты для notify_user_about_booking_start (FSM) ---
# (Требуется добавить тесты)
@pytest.mark.skip("Тесты для FSM notify_user_about_booking_start еще не реализованы")
def test_notify_user_about_booking_start_fsm_success(): pass

@pytest.mark.skip("Тесты для FSM notify_user_about_booking_start еще не реализованы")
def test_notify_user_about_booking_start_fsm_booking_inactive(): pass

@pytest.mark.skip("Тесты для FSM notify_user_about_booking_start еще не реализованы")
def test_notify_user_about_booking_start_fsm_send_error(): pass

@pytest.mark.skip("Тесты для FSM notify_user_about_booking_start еще не реализованы")
def test_notify_user_about_booking_start_fsm_schedule_timeout_error(): pass


# --- Тесты для handle_confirmation_timeout (FSM) ---
# (Требуется добавить тесты)
@pytest.mark.skip("Тесты для FSM handle_confirmation_timeout еще не реализованы")
def test_handle_confirmation_timeout_cancels_booking(): pass

@pytest.mark.skip("Тесты для FSM handle_confirmation_timeout еще не реализованы")
def test_handle_confirmation_timeout_wrong_state(): pass

@pytest.mark.skip("Тесты для FSM handle_confirmation_timeout еще не реализованы")
def test_handle_confirmation_timeout_booking_already_cancelled(): pass

@pytest.mark.skip("Тесты для FSM handle_confirmation_timeout еще не реализованы")
def test_handle_confirmation_timeout_edit_message_error(): pass


# --- Тесты для confirm_booking_callback_logic (FSM) ---
# (Требуется добавить тесты)
@pytest.mark.skip("Тесты для FSM confirm_booking_callback_logic еще не реализованы")
def test_confirm_booking_callback_logic_fsm_success(): pass

@pytest.mark.skip("Тесты для FSM confirm_booking_callback_logic еще не реализованы")
def test_confirm_booking_callback_logic_fsm_wrong_state(): pass

@pytest.mark.skip("Тесты для FSM confirm_booking_callback_logic еще не реализованы")
def test_confirm_booking_callback_logic_fsm_service_fails(): pass

@pytest.mark.skip("Тесты для FSM confirm_booking_callback_logic еще не реализованы")
def test_confirm_booking_callback_logic_fsm_removes_timeout_job(): pass