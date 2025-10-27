# --- START OF FILE bot_app.py (с SQLAlchemyJobStore) ---

import telebot
import config # Импортируем наш конфиг
from logger import logger
from database import Database # Пока импортируем только класс

# --- НОВЫЕ ИМПОРТЫ ДЛЯ APSCHEDULER ---
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from pytz import timezone
# --- КОНЕЦ НОВЫХ ИМПОРТОВ ---

from typing import Dict, Any, Set, Tuple # Для типизации хранилищ

logger.info("Инициализация общих компонентов приложения (bot, db_instance, scheduler)...")

# Инициализация бота
try:
    bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN, parse_mode='HTML')
    test_info = bot.get_me()
    logger.info(f"Экземпляр бота создан успешно. ID: {test_info.id}, Имя: {test_info.first_name}, Username: {test_info.username}")
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать экземпляр бота. Проверьте TELEGRAM_BOT_TOKEN. Ошибка: {e}", exc_info=True)
    raise

# Инициализация экземпляра Database (пул будет инициализирован в main.py)
db_connection = Database() # Используется для получения параметров подключения для APScheduler
logger.info("Экземпляр Database создан (пул НЕ инициализирован).")

# Инициализация планировщика с SQLAlchemyJobStore
try:
    tz_name = config.SCHEDULER_TIMEZONE
    try:
        scheduler_timezone = timezone(tz_name)
    except Exception:
        logger.warning(f"Не удалось распознать таймзону '{tz_name}' из config.SCHEDULER_TIMEZONE. Используется UTC.")
        scheduler_timezone = timezone('UTC')

    # --- Настройка SQLAlchemyJobStore ---
    # Формируем URL для подключения SQLAlchemy к вашей БД PostgreSQL
    # config.DB_USER и т.д. должны быть загружены из .env
    if not all([config.DB_USER, config.DB_PASSWORD, config.DB_HOST, config.DB_PORT, config.DB_NAME]):
        err_msg = "КРИТИЧЕСКАЯ ОШИБКА: Не все параметры БД заданы в конфигурации для APScheduler JobStore."
        logger.critical(err_msg)
        raise ValueError(err_msg)

    db_url = f"postgresql+psycopg2://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    logger.info(f"APScheduler JobStore URL: postgresql+psycopg2://{config.DB_USER}:****@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}") # Не логгируем пароль

    jobstores = {
        # 'default' - это имя хранилища, которое будет использоваться по умолчанию
        # tablename='apscheduler_jobs' - имя таблицы, которую создаст APScheduler
        'default': SQLAlchemyJobStore(url=db_url, tablename='apscheduler_jobs')
    }
    # --- КОНЕЦ Настройки SQLAlchemyJobStore ---

    executors = {
        'default': ThreadPoolExecutor(max_workers=50) # Количество потоков для выполнения задач
    }

    scheduler = BackgroundScheduler(
        jobstores=jobstores,             # <--- Передаем настроенные хранилища
        executors=executors,
        timezone=scheduler_timezone,
        misfire_grace_time=300           # Время (в сек), в течение которого пропущенная задача еще может быть выполнена (5 минут)
        # coalesce=True,                 # Если несколько запусков одной задачи пропущены, выполнить только один раз
        # max_instances=3                # Максимальное количество одновременно выполняемых экземпляров одной и той же задачи
    )
    logger.info(f"Планировщик APScheduler инициализирован с SQLAlchemyJobStore. Таймзона: {str(scheduler_timezone)}")
    # Примечание: APScheduler сам создаст таблицу 'apscheduler_jobs' в БД при первом запуске, если она не существует.

except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать APScheduler с SQLAlchemyJobStore: {e}", exc_info=True)
    raise

# Хранилища для управления УВЕДОМЛЕНИЯМИ О ПРОДЛЕНИИ (active_timers все еще нужен для этого)
# и реестр запланированных задач для избежания дублирования
active_timers: Dict[int, Any] = {} # Ключ: booking_id, Значение: timer_object (для _cancel_extend_option)
scheduled_jobs_registry: Set[Tuple[str, int]] = set() # {(job_type, booking_id), ...}
logger.debug("Хранилища active_timers и scheduled_jobs_registry инициализированы.")

logger.info("Общие компоненты приложения инициализированы.")

# --- END OF FILE bot_app.py ---