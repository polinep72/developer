# --- START OF FILE main.py ---

import logging
import signal
import sys
import time
from services import notification_service
import requests
from apscheduler.schedulers.background import \
    BackgroundScheduler  # <-- Этот импорт тоже может быть не нужен, если scheduler импортируется из bot_app
from telebot import apihelper  # <-- Убрал 'import telebot'

from bot_app import bot, db_connection, scheduler, active_timers, scheduled_jobs_registry
from constants import APP_VERSION
# --- Импорт основных компонентов ---
from database import Database
# --- Импорт регистраторов хендлеров ---
from handlers import (
    user_commands,
    callback_handlers,
    admin_commands,
    registration
)
from logger import logger
# --- Импорт списка команд меню ---
from utils.keyboards import USER_BOT_COMMANDS

# --- Инициализация глобальных объектов ---
# Объекты bot, db_connection, scheduler, active_timers, scheduled_jobs_registry импортируются из bot_app.py
# Удалены закомментированные строки:
# # db_connection = Database()
# # scheduler = BackgroundScheduler(timezone=SCHEDULER_TIMEZONE)
# # active_timers_main: Dict[int, Any] = {}
# # scheduled_jobs_registry_main: Set[Tuple[str, int]] = set()
# # bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


# --- Глобальные флаги и константы ---
shutdown_flag = False
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 60
MAX_RETRY_DELAY = 300

# --- Обработчик сигналов завершения ---
def handle_shutdown_signal(signum, frame):
    global shutdown_flag
    # Проверяем, не был ли флаг уже установлен
    if not shutdown_flag:
        # Устанавливаем флаг, чтобы предотвратить повторный вход
        shutdown_flag = True
        logger.info(f"Сигнал {signal.Signals(signum).name}. Завершение...")
        # Проверяем, запущен ли планировщик
        if scheduler.running:
            try:
                # Пытаемся остановить планировщик без ожидания завершения задач
                scheduler.shutdown(wait=False)
                logger.info("Планировщик остановлен.")
            except Exception as e:
                # Логируем ошибку, если остановка не удалась
                logger.error(f"Ошибка остановки планировщика: {e}")
        # Обертываем остановку polling в try/except
        try:
            # Логируем начало остановки polling
            logger.info("Остановка polling...")
            # Отправляем команду боту на остановку polling
            bot.stop_polling()
            logger.info("Сигнал остановки polling отправлен.")
            # Даем небольшую паузу для обработки остановки
            time.sleep(2)
        except Exception as e:
            # Логируем ошибку, если остановка polling не удалась
            logger.error(f"Ошибка остановки polling: {e}")
    else:
        # Если флаг уже был установлен, логируем предупреждение
        logger.warning("Повторный сигнал завершения, игнорируется.")

# Регистрируем обработчик для сигналов SIGINT (Ctrl+C) и SIGTERM
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)


# --- Основная функция запуска ---
def main():
    logger.info(f"--- Запуск приложения {APP_VERSION} ---")
    global shutdown_flag
    exit_code = 0
    polling_attempts = 0
    api_409_retries = 0
    current_409_delay = INITIAL_RETRY_DELAY

    # Основной блок try для отлова критических ошибок на старте
    try:
        # --- 1. Инициализация пула соединений ---
        logger.info("Инициализация пула БД...")
        # Вызываем статический метод для инициализации пула
        Database.initialize_pool()
        logger.info("Пул БД инициализирован.")

        # --- 2. Проверка соединения ---
        logger.debug("Проверка соединения...")
        conn_test = None
        # Внутренний try/finally для гарантии возврата соединения
        try:
            # Получаем тестовое соединение из пула
            conn_test = db_connection.get_connection()
            # Проверяем, что соединение получено
            if conn_test:
                # Логируем статус соединения
                logger.debug(f"Соединение ОК. Статус: {conn_test.status}")
                # Откатываем возможные незавершенные транзакции (на всякий случай)
                conn_test.rollback()
            else:
                # Если соединение не получено, генерируем ошибку
                raise ConnectionError("Не удалось получить соединение после инициализации!")
        finally:
            # В блоке finally гарантированно возвращаем соединение в пул, если оно было получено
            if conn_test:
                db_connection.release_connection(conn_test)
                logger.debug("Тестовое соединение возвращено в пул.")

        # --- 3. Регистрация обработчиков ---
        logger.info("Регистрация обработчиков...")
        # Регистрируем обработчики пользовательских команд
        user_commands.register_user_command_handlers(bot, db_connection)
        # Регистрируем обработчики колбэков (нажатий на кнопки)
        callback_handlers.register_callback_handlers(
            bot, db_connection, scheduler, active_timers, scheduled_jobs_registry
        )
        # Регистрируем обработчики админских команд
        admin_commands.register_admin_command_handlers(bot, db_connection)
        # Регистрируем обработчики, связанные с регистрацией пользователей
        registration.register_reg_handlers(bot, db_connection)
        logger.info("Обработчики зарегистрированы.")

        # --- 4. Установка команд меню ---
        # Проверяем, есть ли команды для установки
        if USER_BOT_COMMANDS:
            # Внутренний try/except для обработки ошибок установки команд
            try:
                # Устанавливаем команды меню для бота
                bot.set_my_commands(commands=USER_BOT_COMMANDS)
                logger.info("Команды меню установлены.")
            except Exception as e_cmd:
                # Логируем предупреждение, если установка команд не удалась
                logger.warning(f"Не удалось установить команды меню: {e_cmd}")
        else:
            # Логируем, если список команд пуст
            logger.info("Список USER_BOT_COMMANDS пуст. Команды меню не установлены.")


        # --- 5. Запуск планировщика ---
        # Проверяем, не запущен ли планировщик уже
        if not scheduler.running:
            # Внутренний try/except для обработки ошибок запуска планировщика
            try:
                # Запускаем планировщик
                scheduler.start()
                logger.info(f"Планировщик запущен (состояние: {scheduler.state}).")
                logger.info(f"Планировщик использует timezone: {scheduler.timezone}")
                logger.info("Первоначальное планирование уведомлений...")
                # Импортируем сервис уведомлений локально, чтобы избежать циклических зависимостей
                
                # Вызываем функцию для планирования всех необходимых уведомлений при старте
                notification_service.schedule_all_notifications(
                    db_connection, bot, scheduler, active_timers, scheduled_jobs_registry
                )
                logger.info("Первоначальное планирование завершено.")
            except Exception as e_sch_start:
                # Логируем критическую ошибку, если запуск планировщика не удался
                logger.error(f"Ошибка запуска планировщика: {e_sch_start}", exc_info=True)
                # Пробрасываем исключение дальше, так как без планировщика работа невозможна
                raise e_sch_start
        else:
            # Логируем предупреждение, если планировщик уже был запущен кем-то другим
            logger.warning("Планировщик уже был запущен.")

        # --- 6. Основной цикл запуска бота ---
        logger.info("Запуск polling...")
        # Цикл работает, пока не установлен флаг завершения
        while not shutdown_flag:
            # Увеличиваем счетчик попыток polling
            polling_attempts += 1
            logger.info(f"Запуск polling #{polling_attempts}...")

            # Определяем, нужно ли пропускать ожидающие обновления (только при первой попытке)
            # Вынесено из try, т.к. не вызывает исключений
            current_skip_pending = (polling_attempts == 1)

            # Внутренний try/except для обработки ошибок во время polling
            try:
                logger.info(f"Параметр skip_pending = {current_skip_pending}")
                # Запускаем бесконечный polling с указанными параметрами
                bot.infinity_polling(
                    logger_level=logging.INFO,      # Уровень логирования для polling
                    skip_pending=current_skip_pending, # Пропускать ли старые сообщения
                    timeout=30,                     # Таймаут запроса к Telegram API
                    long_polling_timeout=90         # Таймаут long polling
                )
                # Если polling завершился и флаг установлен, значит это штатное завершение
                if shutdown_flag:
                    logger.info("Polling штатно остановлен сигналом.")
                    # Выходим из цикла while
                    break
                else:
                    # Если polling завершился сам по себе (неожиданно)
                    logger.warning("infinity_polling завершился без сигнала. Перезапуск через 5 секунд...")
                    # Делаем небольшую паузу перед перезапуском
                    time.sleep(5)
            except requests.exceptions.ReadTimeout:
                logger.warning("Таймаут чтения от Telegram API. Попытка остановить polling...")
                try:
                    bot.stop_polling()
                    logger.info("Polling штатно остановлен из-за таймаута чтения.")
                except Exception as e_stop:
                    logger.error(f"Ошибка при попытке остановить polling (ReadTimeout): {e_stop}")
                logger.warning("Перезапуск polling через 30 секунд...")
                api_409_retries = 0
                current_409_delay = INITIAL_RETRY_DELAY
                time.sleep(30)
            except requests.exceptions.ConnectionError as ce:
                logger.error(f"Ошибка сетевого подключения: {ce}. Попытка остановить polling...")
                try:
                    bot.stop_polling()
                    logger.info("Polling штатно остановлен из-за ошибки подключения.")
                except Exception as e_stop:
                    logger.error(f"Ошибка при попытке остановить polling (ConnectionError): {e_stop}")
                logger.error(f"Перезапуск polling через 90 секунд...")
                api_409_retries = 0
                current_409_delay = INITIAL_RETRY_DELAY
                time.sleep(90)
            except apihelper.ApiTelegramException as ate:
                # Обработка ошибок API Telegram
                logger.error(f"Ошибка Telegram API: {ate}")
                # Проверяем код ошибки
                if ate.error_code == 409:
                    # Ошибка "Conflict": другой экземпляр бота уже запущен
                    api_409_retries += 1
                    logger.critical(
                        f"Конфликт (409)! Обнаружен другой запущенный экземпляр бота. "
                        f"Попытка {api_409_retries}/{MAX_RETRIES}. "
                        f"Ожидание {current_409_delay} секунд..."
                    )
                    # Проверяем, не превышено ли максимальное количество попыток
                    if api_409_retries >= MAX_RETRIES:
                        logger.critical(f"Превышено максимальное количество ({MAX_RETRIES}) попыток при ошибке 409. Завершение работы.")
                        # Устанавливаем флаг завершения
                        shutdown_flag = True
                        # Устанавливаем код выхода, сигнализирующий об ошибке
                        exit_code = 1
                        # Выходим из цикла while
                        break
                    # Ждем перед следующей попыткой
                    time.sleep(current_409_delay)
                    # Увеличиваем задержку для следующей попытки (экспоненциально), но не более MAX_RETRY_DELAY
                    current_409_delay = min(current_409_delay * 2, MAX_RETRY_DELAY)
                elif ate.error_code == 401:
                    # Ошибка "Unauthorized": неверный токен бота
                    logger.critical(f"Ошибка авторизации (401)! Вероятно, указан неверный токен бота. Завершение работы.")
                    # Устанавливаем флаг завершения
                    shutdown_flag = True
                    # Устанавливаем код выхода, сигнализирующий об ошибке
                    exit_code = 1
                    # Выходим из цикла while
                    break
                else:
                    # Другие ошибки API Telegram
                    logger.error(f"Необработанная ошибка Telegram API (код: {ate.error_code}). Перезапуск polling через 60 секунд...")
                    # Сбрасываем счетчик ошибок 409
                    api_409_retries = 0
                    # Сбрасываем задержку для 409
                    current_409_delay = INITIAL_RETRY_DELAY
                    # Ждем перед следующей попыткой
                    time.sleep(60)
            except Exception as e_poll:
                # Обработка любых других непредвиденных исключений во время polling
                logger.critical(f"Критическая ошибка в цикле polling: {e_poll}", exc_info=True)
                logger.info("Перезапуск polling через 60 секунд...")
                # Сбрасываем счетчик ошибок 409
                api_409_retries = 0
                # Сбрасываем задержку для 409
                current_409_delay = INITIAL_RETRY_DELAY
                # Ждем перед следующей попыткой
                time.sleep(60)

            # Дополнительная проверка флага завершения после блока try...except
            # На случай, если сигнал был получен во время обработки исключения или паузы time.sleep()
            if shutdown_flag:
                logger.info("Обнаружен флаг shutdown_flag после обработки исключения или паузы. Выход из цикла polling.")
                break
    # Обработка исключений верхнего уровня, возникших до или вне основного цикла polling
    except ConnectionError as ce:
        # Обработка ошибки подключения к БД на этапе инициализации
        logger.critical(f"Критическая ошибка подключения к БД при старте: {ce}", exc_info=True)
        exit_code = 1
    except ImportError as ie:
        # Обработка ошибки импорта модуля
        logger.critical(f"Критическая ошибка импорта модуля: {ie}", exc_info=True)
        exit_code = 1
    except Exception as e_main:
        # Обработка любых других критических ошибок на верхнем уровне функции main
        logger.critical(f"Критическая ошибка в функции main: {e_main}", exc_info=True)
        exit_code = 1
    # Блок finally гарантирует выполнение действий по завершению работы
    finally:
        # --- 7. Корректное завершение ---
        logger.info("Блок finally: начало процедур завершения...")
        # Проверяем, запущен ли планировщик
        if scheduler.running:
            # Внутренний try/except для остановки планировщика
            try:
                # Останавливаем планировщик, ожидая завершения текущих задач
                scheduler.shutdown(wait=True)
                logger.info("Планировщик штатно остановлен (finally).")
            except Exception as e:
                # Логируем ошибку, если остановка не удалась
                logger.error(f"Ошибка остановки планировщика в блоке finally: {e}")
        # Логируем закрытие пула БД
        logger.info("Закрытие пула соединений БД...")
        # Вызываем статический метод для закрытия пула
        Database.close_pool()
        logger.info("Пул соединений БД закрыт.")
        # Логируем завершение приложения с кодом выхода
        logger.info(f"Приложение завершено с кодом выхода {exit_code}.")
        # Завершаем процесс с указанным кодом
        sys.exit(exit_code)

# --- Точка входа в приложение ---
if __name__ == "__main__":
    # Понижаем уровень логирования для библиотек, чтобы избежать лишнего "шума" в логах
    # Удалены закомментированные строки:
    # # logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
    # # logging.getLogger('apscheduler.scheduler').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.DEBUG)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    # Запускаем основную функцию приложения
    main()

# --- END OF FILE main.py ---