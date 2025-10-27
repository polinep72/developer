# bot_app.py
import telebot
import config # Импортируем наш конфиг
from config import SCHEDULER_TIMEZONE # Убедитесь, что импорт есть
from logger import logger
from database import Database # Пока импортируем только класс
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone # Для указания таймзоны планировщику
from typing import Dict, Any, Set, Tuple # Для типизации хранилищ
from apscheduler.executors.pool import ThreadPoolExecutor # <-- ДОБАВИТЬ ЭТОТ ИМПОРТ

logger.info("Инициализация общих компонентов приложения (bot, db_instance, scheduler)...")

# Инициализация бота
try:
    # Используем переменную из config.py
    bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN, parse_mode='HTML')
    # Проверка токена
    test_info = bot.get_me()
    logger.info(f"Экземпляр бота создан успешно. ID: {test_info.id}, Имя: {test_info.first_name}, Username: {test_info.username}")
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать экземпляр бота. Проверьте TELEGRAM_BOT_TOKEN. Ошибка: {e}", exc_info=True)
    raise

# Инициализация экземпляра Database (пул будет инициализирован в main.py)
db_connection = Database()
logger.info("Экземпляр Database создан (пул НЕ инициализирован).")

# Инициализация планировщика
try:
    # Используем таймзону из config.py
    tz_name = config.SCHEDULER_TIMEZONE
    try:
        scheduler_timezone = timezone(tz_name)
    except Exception:
        logger.warning(f"Не удалось распознать таймзону '{tz_name}' из config.SCHEDULER_TIMEZONE. Используется UTC.")
        scheduler_timezone = timezone('UTC') # Запасной вариант
    # --- ДОБАВИТЬ КОНФИГУРАЦИЮ ИСПОЛНИТЕЛЯ ---
    executors = {
            'default': ThreadPoolExecutor(max_workers=50) # <-- Установите желаемое количество потоков (например, 50)
    }
# --- КОНЕЦ ДОБАВЛЕНИЯ ---

    scheduler = BackgroundScheduler(executors=executors, timezone=scheduler_timezone, misfire_grace_time=60)  # Добавлено misfire_grace_time
    logger.info(f"Планировщик APScheduler инициализирован. Таймзона: {str(scheduler_timezone)}")
except Exception as e:
    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать APScheduler: {e}", exc_info=True)
    raise

# Хранилища для управления уведомлениями и задачами
active_timers: Dict[int, Any] = {} # Ключ: booking_id, Значение: timer_object
scheduled_jobs_registry: Set[Tuple[str, int]] = set() # {(job_type, booking_id), ...}
logger.debug("Хранилища active_timers и scheduled_jobs_registry инициализированы.")

logger.info("Общие компоненты приложения инициализированы.")