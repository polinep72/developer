# config.py
import os
from dotenv import load_dotenv
from logger import logger

# Загружаем переменные из .env файла в окружение
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
    logger.debug(f".env файл найден и загружен из {env_path}")
else:
    logger.warning(f".env файл не найден по пути {env_path}. Используются системные переменные окружения.")


# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# ADMIN_ID больше не используется, проверка прав через БД (users.is_admin)

# --- Database ---
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD") # Может быть None
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432") # Порт по умолчанию

# --- Scheduler Timezone ---
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Europe/Moscow")


# --- Проверка наличия критически важных переменных ---
required_env_vars = {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_HOST": DB_HOST,
}

missing_vars = [name for name, value in required_env_vars.items()
                if not value] # Проверка на Falsy значения

if missing_vars:
    message = f"Отсутствуют критически важные переменные окружения: {', '.join(missing_vars)}"
    logger.critical(message)
    raise ValueError(message) # Прерываем выполнение

HEATMAP_BASE_URL = os.getenv("HEATMAP_BASE_URL")

logger.info("Базовая конфигурация успешно загружена.")
# Минимальное логирование загруженных параметров
logger.debug(f"DB Host: {DB_HOST}:{DB_PORT}, DB Name: {DB_NAME}")
logger.debug(f"Scheduler Timezone: {SCHEDULER_TIMEZONE}")

# --- Параметры, не входящие в этот конфиг ---
# DB_MIN_CONN, DB_MAX_CONN - будут заданы по умолчанию в database.py
# BOT_COMMANDS - будут заданы в main.py или user_commands.py
# ADMIN_COMMANDS_HELP - будет задан в admin_commands.py