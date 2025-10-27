# main.py
import time
import sys
import logging
import signal
# import config # config больше не нужен для команд

# --- Импорт основных компонентов из bot_app ---
from bot_app import bot, db_connection, scheduler, active_timers, scheduled_jobs_registry
from database import Database
from logger import logger
from typing import List, Tuple, Optional, Dict, Any, Union

# --- Импорт списка команд меню из keyboards ---
from utils.keyboards import USER_BOT_COMMANDS # <-- Импортируем команды меню

# --- Импорт регистраторов хендлеров ---
from handlers import (
    user_commands,
    callback_handlers,
    admin_commands,
    registration
)

# Флаг для корректного завершения
shutdown_flag = False

# --- Обработчик сигналов завершения ---
def handle_shutdown_signal(signum, frame):
    """Обрабатывает сигналы SIGINT и SIGTERM для корректного завершения."""
    global shutdown_flag
    if not shutdown_flag:
        shutdown_flag = True
        logger.info(f"Получен сигнал завершения ({signal.Signals(signum).name}). Завершение работы...")
        if scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Планировщик остановлен.")
            except Exception as e_sch_shut:
                logger.error(f"Ошибка при остановке планировщика: {e_sch_shut}")
        try:
            if bot.worker_pool is not None:
                 bot.stop_polling()
                 logger.info("Polling бота остановлен.")
            else:
                 logger.info("Polling бота уже был остановлен или не был запущен.")
        except Exception as e_poll_stop:
            logger.error(f"Ошибка при остановке polling: {e_poll_stop}")
    else:
        logger.warning("Повторный сигнал завершения получен, игнорируется.")

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


# --- Основная функция запуска ---
def main():
    """Основная функция для инициализации и запуска бота."""
    global shutdown_flag
    exit_code = 0
    try:
        # --- 1. Инициализация пула соединений ---
        logger.info("Инициализация пула соединений базы данных...")
        # Используем значения по умолчанию для min/max conn, т.к. убрали из config
        Database.initialize_pool()
        logger.info("Пул соединений базы данных успешно инициализирован.")

        # --- 2. Проверка соединения ---
        logger.debug("Попытка получить тестовое соединение...")
        conn_test = None
        try:
            conn_test = db_connection.get_connection()
            if conn_test:
                logger.debug(f"Тестовое соединение получено успешно. Статус: {conn_test.status}")
                conn_test.rollback()
            else:
                 raise ConnectionError("Не удалось получить тестовое соединение после инициализации пула!")
        finally:
            if conn_test:
                db_connection.release_connection(conn_test)
                logger.debug("Тестовое соединение возвращено в пул.")

        # --- 3. Регистрация обработчиков ---
        logger.info("Регистрация обработчиков команд пользователя...")
        user_commands.register_user_command_handlers(bot, db_connection) # <-- Убедитесь, что функция называется так

        logger.info("Регистрация обработчиков колбэков...")
        callback_handlers.register_callback_handlers(
            bot, db_connection, scheduler, active_timers, scheduled_jobs_registry
        )

        logger.info("Регистрация обработчиков админ-команд...")
        admin_commands.register_admin_command_handlers(bot, db_connection) # <-- Убедитесь, что функция называется так

        logger.info("Регистрация обработчиков регистрации...")
        registration.register_reg_handlers(bot, db_connection) # <-- Убедитесь, что функция называется так

        logger.info("Все необходимые обработчики успешно зарегистрированы.")

        # --- 4. Установка команд меню ---
        # Используем список команд, импортированный из utils.keyboards
        if USER_BOT_COMMANDS: # Проверяем, что список не пуст
            try:
                bot.delete_my_commands(scope=None, language_code=None)
                bot.set_my_commands(commands=USER_BOT_COMMANDS) # <-- Используем импортированный список
                logger.info("Команды меню бота успешно установлены.")
            except Exception as e_cmd:
                 logger.warning(f"Не удалось установить команды меню бота: {e_cmd}")
        else:
            logger.info("Список USER_BOT_COMMANDS пуст. Команды меню не установлены.")


        # --- 5. Запуск планировщика ---
        if not scheduler.running:
            try:
                scheduler.start()
                logger.info(f"Планировщик APScheduler запущен (состояние: {scheduler.state}).")
            except Exception as e_sch_start:
                 logger.error(f"Не удалось запустить планировщик: {e_sch_start}", exc_info=True)
                 # raise e_sch_start
        else:
            logger.warning("Планировщик уже был запущен.")

        # --- 6. Запуск бота ---
        logger.info("Запуск бота (polling)...")
        bot.infinity_polling(logger_level=logging.INFO, skip_pending=True, timeout=60)

        logger.info("Polling бота штатно завершен.")


    except ConnectionError as ce:
         logger.critical(f"Ошибка подключения к БД при старте: {ce}", exc_info=True)
         exit_code = 1
    except ImportError as ie:
        logger.critical(f"Ошибка импорта при запуске: {ie}", exc_info=True)
        exit_code = 1
    except Exception as e:
        logger.critical(f"Критическая ошибка в главном потоке приложения: {e}", exc_info=True)
        exit_code = 1
    finally:
        # --- 7. Корректное завершение ---
        logger.info("Начало процедуры завершения работы...")
        if scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Планировщик остановлен (в finally).")
            except Exception as e_sch_shut:
                logger.error(f"Ошибка при остановке планировщика (в finally): {e_sch_shut}")
        logger.info("Закрытие пула соединений базы данных...")
        Database.close_pool()
        logger.info("Пул соединений закрыт.")
        logger.info(f"Приложение завершило работу с кодом {exit_code}.")
        sys.exit(exit_code)

# --- Точка входа ---
if __name__ == "__main__":
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    main()