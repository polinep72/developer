# main.py
import time
import sys
import logging
import signal
import requests
from telebot import apihelper

# --- Импорт основных компонентов ---
from config import TELEGRAM_BOT_TOKEN, SCHEDULER_TIMEZONE # <<< Добавлен SCHEDULER_TIMEZONE
from pytz import timezone
from database import Database
from logger import logger
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, Any, Set, Tuple
import telebot

# --- Импорт списка команд меню ---
from utils.keyboards import USER_BOT_COMMANDS

# --- Импорт регистраторов хендлеров ---
from handlers import (
    user_commands,
    callback_handlers,
    admin_commands,
    registration
)

# --- Инициализация глобальных объектов ---
db_connection = Database()
# Создаем pytz timezone объект явно
scheduler_tz = timezone(SCHEDULER_TIMEZONE)
logger.info(f"Создан планировщик с таймзоной: {scheduler_tz} (тип: {type(scheduler_tz)})")
scheduler = BackgroundScheduler(timezone=scheduler_tz) # <<< Используем pytz.timezone
active_timers_main: Dict[int, Any] = {}
scheduled_jobs_registry_main: Set[Tuple[str, int]] = set()
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


# --- Глобальные флаги и константы ---
shutdown_flag = False
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 60
MAX_RETRY_DELAY = 300

# --- Обработчик сигналов завершения ---
def handle_shutdown_signal(signum, frame):
    global shutdown_flag
    if not shutdown_flag:
        shutdown_flag = True
        logger.info(f"Сигнал {signal.Signals(signum).name}. Завершение...")
        if scheduler.running:
            try:
                scheduler.shutdown(wait=False)
                logger.info("Планировщик остановлен.")
            except Exception as e:
                logger.error(f"Ошибка остановки планировщика: {e}")
        try:
            logger.info("Остановка polling...")
            bot.stop_polling()
            logger.info("Сигнал остановки polling отправлен.")
            time.sleep(2)
        except Exception as e:
            logger.error(f"Ошибка остановки polling: {e}")
    else:
        logger.warning("Повторный сигнал, игнорируется.")

signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


# --- Основная функция запуска ---
def main():
    global shutdown_flag
    exit_code = 0
    polling_attempts = 0
    api_409_retries = 0
    current_409_delay = INITIAL_RETRY_DELAY

    try:
        # --- 1. Инициализация пула соединений ---
        logger.info("Инициализация пула БД...")
        Database.initialize_pool()
        logger.info("Пул БД инициализирован.")

        # --- 2. Проверка соединения ---
        logger.debug("Проверка соединения...")
        conn_test = None
        try:
            conn_test = db_connection.get_connection()
            if conn_test:
                logger.debug(f"Соединение ОК. Статус: {conn_test.status}")
                conn_test.rollback()
            else:
                raise ConnectionError("Не удалось получить соед. после инициализации!")
        finally:
            if conn_test:
                db_connection.release_connection(conn_test)
                logger.debug("Тестовое соед. возвращено.")

        # --- 3. Регистрация обработчиков ---
        logger.info("Регистрация обработчиков...")
        user_commands.register_user_command_handlers(bot, db_connection)
        callback_handlers.register_callback_handlers(
            bot, db_connection, scheduler, active_timers_main, scheduled_jobs_registry_main
        )
        admin_commands.register_admin_command_handlers(bot, db_connection)
        registration.register_reg_handlers(bot, db_connection)
        logger.info("Обработчики зарегистрированы.")

        # --- 4. Установка команд меню ---
        if USER_BOT_COMMANDS:
            try:
                bot.set_my_commands(commands=USER_BOT_COMMANDS)
                logger.info("Команды меню установлены.")
            except Exception as e_cmd:
                logger.warning(f"Не удалось установить команды: {e_cmd}")
        else:
            logger.info("USER_BOT_COMMANDS пуст. Команды не установлены.")


        # --- 5. Запуск планировщика ---
        if not scheduler.running:
            try:
                scheduler.start()
                logger.info(f"Планировщик запущен (состояние: {scheduler.state}).")
                logger.info("Первоначальное планирование...")
                from services import notification_service  # Локальный импорт

                if hasattr(notification_service, "schedule_all_notifications"):
                    notification_service.schedule_all_notifications(
                        db_connection,
                        bot,
                        scheduler,
                        active_timers_main,
                        scheduled_jobs_registry_main,
                    )
                    logger.info("Планирование завершено.")
                else:
                    logger.warning(
                        "В services.notification_service отсутствует schedule_all_notifications; "
                        "планирование уведомлений пропущено в тестовом боте WSB_core."
                    )
            except Exception as e_sch_start:
                logger.error(f"Ошибка запуска планировщика: {e_sch_start}", exc_info=True)
                # В тестовой копии WSB_core не падаем, если планировщик не смог стартовать полностью
                # shutdown_flag оставляем False, чтобы бот продолжил работу.
        else:
            logger.warning("Планировщик уже был запущен.")

        # --- 6. Основной цикл запуска бота ---
        logger.info("Запуск polling...");
        while not shutdown_flag:
            polling_attempts += 1
            logger.info(f"Polling #{polling_attempts}...")
            try:
                current_skip_pending = (polling_attempts == 1)
                logger.info(f"skip_pending = {current_skip_pending}")
                bot.infinity_polling(
                    logger_level=logging.INFO,
                    skip_pending=current_skip_pending,
                    timeout=30,
                    long_polling_timeout=90
                )
                if shutdown_flag:
                    logger.info("Polling остановлен сигналом.")
                    break
                else:
                    logger.warning("infinity_polling завершился без сигнала. Перезапуск...")
                    time.sleep(5)
            except requests.exceptions.ReadTimeout:
                logger.warning("Таймаут чтения. Перезапуск...")
                try:
                    bot.stop_polling() # <<< ЯВНО ОСТАНОВИТЬ
                    logger.info("Polling штатно остановлен перед перезапуском из-за таймаута.")
                except Exception as e_stop:
                    logger.error(f"Ошибка при попытке остановить polling: {e_stop}")
                logger.warning("Таймаут чтения. Перезапуск через 30 сек...")
                api_409_retries = 0
                time.sleep(30)
            except requests.exceptions.ConnectionError as ce:
                logger.error(f"Ошибка подключения: {ce}. Перезапуск...")
                try:
                    bot.stop_polling() # <<< ЯВНО ОСТАНОВИТЬ
                    logger.info("Polling штатно остановлен перед перезапуском из-за ошибки подключения.")
                except Exception as e_stop:
                    logger.error(f"Ошибка при попытке остановить polling: {e_stop}")
                logger.error(f"Ошибка подключения: {ce}. Перезапуск через 90 сек...")
                api_409_retries = 0
                time.sleep(90)
            except apihelper.ApiTelegramException as ate:
                logger.error(f"Ошибка API: {ate}")
                if ate.error_code == 409:
                    api_409_retries += 1
                    logger.critical(
                        f"Конфликт (409)! Попытка {api_409_retries}/{MAX_RETRIES}. "
                        f"Ожидание {current_409_delay} сек..."
                    )
                    if api_409_retries >= MAX_RETRIES:
                        logger.critical(f"Ошибка 409 x{MAX_RETRIES}. Завершение.")
                        shutdown_flag = True
                        exit_code = 1
                        break
                    time.sleep(current_409_delay)
                    current_409_delay = min(current_409_delay * 2, MAX_RETRY_DELAY)
                elif ate.error_code == 401:
                    logger.critical(f"Ошибка авторизации (401)! Неверный токен. Завершение.")
                    shutdown_flag = True
                    exit_code = 1
                    break
                else:
                    logger.error(f"Другая ошибка API ({ate.error_code}). Перезапуск...")
                    api_409_retries = 0
                    time.sleep(60)
            except Exception as e_poll:
                logger.critical(f"Ошибка polling: {e_poll}", exc_info=True)
                logger.info("Перезапуск polling...")
                api_409_retries = 0
                time.sleep(60)

            if shutdown_flag:
                logger.info("shutdown_flag после исключения. Выход.")
                break
    except ConnectionError as ce:
        logger.critical(f"Крит. ошибка БД старта: {ce}", exc_info=True)
        exit_code = 1
    except ImportError as ie:
        logger.critical(f"Крит. ошибка импорта: {ie}", exc_info=True)
        exit_code = 1
    except Exception as e_main:
        logger.critical(f"Крит. ошибка main: {e_main}", exc_info=True)
        exit_code = 1
    finally:
        # --- 7. Корректное завершение ---
        logger.info("Завершение (finally)...")
        if scheduler.running:
            try:
                scheduler.shutdown(wait=True)
                logger.info("Планировщик остановлен (finally).")
            except Exception as e:
                logger.error(f"Ошибка остановки планировщика (finally): {e}")
        logger.info("Закрытие пула БД...");
        Database.close_pool()
        logger.info("Пул закрыт.")
        logger.info(f"Приложение завершено с кодом {exit_code}.")
        sys.exit(exit_code)

if __name__ == "__main__":
    logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
    logging.getLogger('apscheduler.scheduler').setLevel(logging.WARNING)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    main()