# --- START OF FILE config.py ---

# config.py
import os
from dotenv import load_dotenv
from logger import logger

# --- Загрузка переменных окружения ---

# Определяем путь к файлу .env относительно текущего файла config.py
env_path = os.path.join(os.path.dirname(__file__), '.env')

# Проверяем существование файла .env
if os.path.exists(env_path):
    # Загружаем переменные из .env файла в окружение
    load_dotenv(dotenv_path=env_path)
    # Логируем факт загрузки
    logger.debug(f".env файл найден и загружен из {env_path}")
else:
    # Логируем предупреждение, если файл не найден
    logger.warning(
        f".env файл не найден по пути {env_path}. "
        "Будут использоваться системные переменные окружения (если они заданы)."
    )


# --- Telegram Bot ---
# Получаем токен бота из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Замечание: ADMIN_ID больше не используется напрямую из конфига.
# Проверка прав администратора осуществляется через поле is_admin в таблице users базы данных.

# --- Database ---
# Получаем параметры подключения к базе данных из переменных окружения
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD") # Пароль может отсутствовать (None)
DB_HOST = os.getenv("DB_HOST")
# Получаем порт БД, используем "5432" как значение по умолчанию, если не задано
DB_PORT = os.getenv("DB_PORT", "5432")

# --- Scheduler Timezone ---
# Получаем часовой пояс для планировщика APScheduler
# Используем "Europe/Moscow" как значение по умолчанию
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Europe/Moscow")


# --- Проверка наличия критически важных переменных ---
# Словарь с именами и значениями обязательных переменных
required_env_vars = {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_HOST": DB_HOST,
    # DB_PASSWORD не является строго обязательным (может быть пустым)
    # DB_PORT имеет значение по умолчанию
    # SCHEDULER_TIMEZONE имеет значение по умолчанию
}

# Формируем список имен переменных, которые не были заданы (имеют Falsy значение: None, пустая строка)
missing_vars = [
    name for name, value in required_env_vars.items()
    if not value # Проверка на Falsy значение (None, '', 0, etc.)
]

# Проверяем, есть ли отсутствующие переменные
if missing_vars:
    # Формируем сообщение об ошибке
    message = (
        "Критическая ошибка конфигурации! Отсутствуют следующие "
        f"обязательные переменные окружения: {', '.join(missing_vars)}"
    )
    # Логируем критическую ошибку
    logger.critical(message)
    # Прерываем выполнение приложения, так как без этих переменных работа невозможна
    raise ValueError(message)

# Логируем успешную загрузку базовой конфигурации
logger.info("Базовая конфигурация успешно загружена и проверена.")
# Логируем некоторые загруженные параметры для отладки (уровень DEBUG)
logger.debug(f"Параметры БД: Host={DB_HOST}, Port={DB_PORT}, DBName={DB_NAME}, User={DB_USER}")
logger.debug(f"Часовой пояс планировщика: {SCHEDULER_TIMEZONE}")
# Не логируем токен и пароль БД из соображений безопасности

# --- Параметры, не входящие в этот конфиг ---
# Замечание: Некоторые параметры конфигурации задаются в других модулях:
# - DB_MIN_CONN, DB_MAX_CONN: Задаются с значениями по умолчанию в database.py.
# - USER_BOT_COMMANDS: Определяются в utils/keyboards.py и используются в main.py.
# - ADMIN_COMMANDS_HELP: Определяется в handlers/admin_commands.py.

# --- END OF FILE config.py ---