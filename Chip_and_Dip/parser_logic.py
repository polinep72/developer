# parser_logic.py
import datetime
import os
import random
import time
import warnings
import logging
import logging.handlers

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# openpyxl больше не нужен для основной логики парсинга
import pytz
from decouple import config, UndefinedValueError

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)
APP_CONFIG = {}


def setup_logging(log_level_console=logging.INFO, log_level_file=logging.DEBUG):
    global logger
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(log_level_console)
    logger.addHandler(console_handler)
    log_file_path = "app.log"
    try:
        file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(log_level_file)
        logger.addHandler(file_handler)
        logger.info(
            f"Логирование настроено. Консоль: {logging.getLevelName(log_level_console)}, Файл ('{log_file_path}'): {logging.getLevelName(log_level_file)}")
    except Exception as e:
        logger.error(f"Не удалось настроить файловый логгер для '{log_file_path}': {e}", exc_info=False)
        logger.info("Логирование будет осуществляться только в консоль.")


def get_stock_from_page(driver, url, xpath_selector, wait_timeout_sec=20, delay_after_load_sec=5):
    logger.debug(f"Загрузка URL в существующем драйвере: {url}")
    result_code = "error_webdriver"
    stock_value = None

    try:
        driver.get(url)
        logger.debug(f"URL '{url}' загружен. Ожидание {delay_after_load_sec} сек...")
        time.sleep(delay_after_load_sec)

        logger.debug(f"Ожидание элемента (до {wait_timeout_sec} сек) по XPath: {xpath_selector}")
        element = WebDriverWait(driver, wait_timeout_sec).until(
            EC.presence_of_element_located((By.XPATH, xpath_selector))
        )
        logger.debug(f"Элемент по XPath '{xpath_selector}' найден. Текст: '{element.text}'")

        raw_text = element.text
        cleaned_text = ''.join(filter(str.isdigit, raw_text))
        if cleaned_text:
            stock_value = int(cleaned_text)
            result_code = "ok"
        else:
            logger.warning(f"Текст элемента '{raw_text}' не содержит цифр после очистки для URL: {url}")
            result_code = "no_digits"
        logger.info(f"Для URL '{url}' получен результат: {result_code}, значение: {stock_value}")

    except TimeoutException:
        logger.warning(f"Элемент по XPath '{xpath_selector}' не найден (TimeoutException) для URL: {url}")
        result_code = "not_found"
    except WebDriverException as e:
        logger.error(f"WebDriverException при обработке URL '{url}': {type(e).__name__} - {str(e)[:100]}...")
        if "CAPTCHA" in str(e).upper() or "CHALLENGE" in str(e).upper() or "VERIFY" in str(e).upper():
            logger.warning(f"Обнаружена возможная CAPTCHA или проверка на URL: {url}")
            result_code = "captcha"
        else:
            result_code = "error_webdriver"
    except Exception as e:
        logger.error(f"Непредвиденная ошибка в get_stock_from_page для URL '{url}': {e}", exc_info=True)
        result_code = "error_unknown"

    return result_code, stock_value


def run_parsing_process(items_to_parse, app_config_values, progress_callback, db_update_callback=None):
    global APP_CONFIG
    APP_CONFIG = app_config_values

    logger.info(f"Начало обработки {len(items_to_parse)} элементов из БД.")
    progress_callback(0, len(items_to_parse), "Инициализация парсера...", None, None)

    if not items_to_parse:
        logger.info("Нет элементов для парсинга.")
        progress_callback(0, 0, "Нет данных для обработки.", None, None)
        return []

    driver = None
    options = uc.ChromeOptions()

    is_docker = APP_CONFIG.get('running_in_docker', 'false').lower() == 'true'
    default_headless_str = "1" if is_docker else "0"
    try:
        # Используем .get с ключом в нижнем регистре, как он сохраняется в APP_CONFIG
        headless_setting_str = APP_CONFIG.get('headless', default_headless_str)
        options.headless = bool(int(headless_setting_str))
    except ValueError:
        options.headless = bool(int(default_headless_str))
    logger.info(f"Режим Headless для сессии парсинга: {options.headless}")

    if options.headless:
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920,1080")

    chrome_executable_path_val = APP_CONFIG.get('chrome_executable_path', '')  # Используем ключ в нижнем регистре
    # Убираем кавычки и комментарии, если они случайно попали из .env
    if isinstance(chrome_executable_path_val, str):
        chrome_executable_path_val = chrome_executable_path_val.split('#')[0].strip().strip('"')

    if chrome_executable_path_val and os.path.exists(chrome_executable_path_val):
        options.binary_location = chrome_executable_path_val
        logger.info(f"Используется Chrome из (binary_location): {chrome_executable_path_val}")
    elif chrome_executable_path_val:  # Если путь указан, но не существует
        logger.warning(
            f"Указанный путь к Chrome '{chrome_executable_path_val}' не существует. undetected_chromedriver попытается найти Chrome автоматически.")
    else:  # Если путь не указан
        logger.info("Путь к Chrome не указан. undetected_chromedriver попытается найти Chrome автоматически.")

    try:
        logger.info("Инициализация основного драйвера Chrome для сессии...")
        driver = uc.Chrome(options=options)
        logger.info("Основной драйвер Chrome успешно инициализирован.")
        initial_load_delay = float(APP_CONFIG.get('initial_load_delay_sec', 2.0))
        if initial_load_delay > 0:
            logger.info(f"Первоначальная задержка после запуска драйвера: {initial_load_delay} сек.")
            time.sleep(initial_load_delay)
    except Exception as e:
        logger.critical(f"Не удалось инициализировать основной драйвер Chrome: {e}", exc_info=True)
        progress_callback(len(items_to_parse), len(items_to_parse), "Ошибка инициализации браузера", None, str(e))
        return [{'id': item.get('id'), 'url': item.get('url'), 'result_code': 'error_driver_init', 'stock_value': None}
                for item in items_to_parse]

    xpath_selector = "//span[contains(@class, 'item__avail') and contains(@class, 'item__avail_delivery')]/b"
    delay_between_urls_min = float(APP_CONFIG.get('delay_between_urls_min_sec', 3.0))
    delay_between_urls_max = float(APP_CONFIG.get('delay_between_urls_max_sec', 7.0))
    wait_element_timeout = int(APP_CONFIG.get('wait_element_timeout_sec', 25))
    delay_after_page_load = int(APP_CONFIG.get('delay_after_page_load_sec', 7))

    processed_items = []

    for i, item_data in enumerate(items_to_parse):
        item_id = item_data.get('id')
        url_to_process = item_data.get('url')
        current_step = i + 1

        progress_callback(
            current_step,
            len(items_to_parse),
            f"Обработка ID {item_id} ({current_step}/{len(items_to_parse)})...",
            None,
            None
        )

        if not url_to_process or not url_to_process.lower().startswith(('http://', 'https://')):
            logger.warning(f"ID {item_id}: некорректный URL '{url_to_process}'. Пропускаем.")
            result_code = "invalid_url"
            stock_value = None
        else:
            logger.info(f"ID {item_id}: Обработка URL: {url_to_process}")
            result_code, stock_value = get_stock_from_page(driver, url_to_process, xpath_selector,
                                                           wait_timeout_sec=wait_element_timeout,
                                                           delay_after_load_sec=delay_after_page_load)

        current_item_result = item_data.copy()  # Копируем, чтобы не изменять исходный список напрямую, если он используется где-то еще
        current_item_result['result_code'] = result_code
        current_item_result['stock_value'] = stock_value
        processed_items.append(current_item_result)

        if db_update_callback:
            try:
                db_update_callback(item_id, result_code, stock_value)
                logger.info(f"ID {item_id}: Данные обновлены в БД (код: {result_code}, сток: {stock_value}).")
            except Exception as e:
                logger.error(f"ID {item_id}: Ошибка при вызове db_update_callback: {e}", exc_info=True)

        if APP_CONFIG.get('console_log_active', False):
            logger.info(f"(Процесс) ID: {item_id}, URL: {url_to_process}, Код: {result_code}, Сток: {stock_value}")

        if i < len(items_to_parse) - 1:
            current_delay = random.uniform(delay_between_urls_min, delay_between_urls_max)
            logger.debug(f"Задержка перед следующим URL: {current_delay:.2f} сек.")
            progress_callback(current_step, len(items_to_parse),
                              f"Обработан ID {item_id}. Задержка {current_delay:.1f}с...", None, None)
            time.sleep(current_delay)

    if driver:
        logger.info("Все URL обработаны. Закрытие основного драйвера Chrome...")
        try:
            driver.quit()
            logger.info("Основной драйвер Chrome успешно закрыт.")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии основного драйвера Chrome: {e}")

    logger.info("Парсинг завершен.")
    progress_callback(len(items_to_parse), len(items_to_parse), "Обработка завершена!", None, None)
    return processed_items


def load_parser_config():
    global APP_CONFIG  # Эта глобальная переменная будет заполнена ключами в нижнем регистре
    logger.info("Загрузка конфигурации парсера...")

    # Словарь для чтения из .env (ключи как в .env, обычно UPPER_CASE)
    raw_config = {}
    # Словарь для APP_CONFIG и возврата (ключи в lower_case)
    processed_config = {}

    try:
        # Определяем переменные и их типы/значения по умолчанию
        # Имена здесь - это то, что мы ожидаем в .env или переменных окружения
        config_vars_specs = {
            'HEADLESS_MODE': {'default': '0', 'cast': str},  # Будет bool(int()) позже
            'TIME_FORMAT': {'default': '%Y-%m-%d %H:%M:%S', 'cast': str},
            'CONSOLE_LOG_ACTIVE': {'default': '1', 'cast': bool},
            'CHROME_EXECUTABLE_PATH': {'default': '', 'cast': str},
            'RUNNING_IN_DOCKER': {'default': 'false', 'cast': str},  # Будет .lower() позже

            'INITIAL_LOAD_DELAY_SEC': {'default': '2.0', 'cast': float},
            'DELAY_BETWEEN_URLS_MIN_SEC': {'default': '3.0', 'cast': float},
            'DELAY_BETWEEN_URLS_MAX_SEC': {'default': '7.0', 'cast': float},
            'WAIT_ELEMENT_TIMEOUT_SEC': {'default': '25', 'cast': int},
            'DELAY_AFTER_PAGE_LOAD_SEC': {'default': '7', 'cast': int},
            'XLSX_FILE': {'default': None, 'cast': str}  # Необязательная переменная
        }

        for var_name, spec in config_vars_specs.items():
            raw_config[var_name] = config(var_name, default=spec['default'], cast=spec['cast'])

        # Преобразуем ключи в нижний регистр и специфические обработки
        processed_config['headless'] = raw_config[
            'HEADLESS_MODE']  # оставим строкой, bool(int()) будет при использовании
        processed_config['time_format'] = raw_config['TIME_FORMAT']
        processed_config['console_log_active'] = raw_config['CONSOLE_LOG_ACTIVE']  # уже bool

        # Очистка пути к Chrome
        chrome_path_raw = raw_config['CHROME_EXECUTABLE_PATH']
        if isinstance(chrome_path_raw, str):
            processed_config['chrome_executable_path'] = chrome_path_raw.split('#')[0].strip().strip('"')
        else:  # На случай если cast вернул не строку (хотя для str это не должно быть)
            processed_config['chrome_executable_path'] = ''

        processed_config['running_in_docker'] = raw_config['RUNNING_IN_DOCKER'].lower()

        processed_config['initial_load_delay_sec'] = raw_config['INITIAL_LOAD_DELAY_SEC']
        processed_config['delay_between_urls_min_sec'] = raw_config['DELAY_BETWEEN_URLS_MIN_SEC']
        processed_config['delay_between_urls_max_sec'] = raw_config['DELAY_BETWEEN_URLS_MAX_SEC']
        processed_config['wait_element_timeout_sec'] = raw_config['WAIT_ELEMENT_TIMEOUT_SEC']
        processed_config['delay_after_page_load_sec'] = raw_config['DELAY_AFTER_PAGE_LOAD_SEC']

        # Обработка необязательного XLSX_FILE
        xlsx_file_from_env = raw_config['XLSX_FILE']
        if xlsx_file_from_env:  # Если None, то ключ не добавляем или добавляем как None
            processed_config['xlsx_file_path_legacy'] = xlsx_file_from_env
            logger.info(
                f"Обнаружена переменная XLSX_FILE: {xlsx_file_from_env} (может использоваться для других целей).")
            # Если бы actual_xlsx_file_path все еще был нужен:
            # if processed_config['running_in_docker'] == 'true':
            #     processed_config['actual_xlsx_file_path'] = os.path.join("/app", xlsx_file_from_env)
            # else:
            #     script_dir = os.path.dirname(os.path.abspath(__file__))
            #     if os.path.isabs(xlsx_file_from_env):
            #          processed_config['actual_xlsx_file_path'] = xlsx_file_from_env
            #     else:
            #          processed_config['actual_xlsx_file_path'] = os.path.join(script_dir, xlsx_file_from_env)
        else:
            processed_config['xlsx_file_path_legacy'] = None

        logger.info(f"Конфигурация парсера загружена (обработанная): {processed_config}")
        APP_CONFIG = processed_config  # Обновляем глобальную APP_CONFIG
        return processed_config

    except UndefinedValueError as e:
        logger.critical(f"Критическая ошибка: не найдена обязательная переменная конфигурации: {e}")
        raise
    except Exception as e:
        logger.critical(f"Критическая ошибка при загрузке конфигурации: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    setup_logging(log_level_console=logging.DEBUG, log_level_file=logging.DEBUG)
    logger.info("Запуск parser_logic.py в автономном режиме для отладки...")
    try:
        cfg = load_parser_config()

        sample_items = [
            {'id': 1, 'url': 'https://www.chipdip.ru/product/gr-1206s-100k-f-0.125w-1'},
            {'id': 2, 'url': 'https://www.chipdip.ru/product0/8003073404'},
        ]

        if not sample_items:
            logger.info("Нет примеров данных для автономного теста.")
        else:
            def console_db_update(item_id, result_code, stock_value):
                logger.info(f"[DB Update Mock] ID: {item_id}, Result: {result_code}, Stock: {stock_value}")


            def console_progress_callback(current, total, message, file_path=None, error_msg=None):
                progress_percent = (current / total) * 100 if total > 0 else 0
                log_message = f"Прогресс: {current}/{total} ({progress_percent:.2f}%) - {message}"
                if error_msg: log_message += f" | Ошибка UI: {error_msg}"
                logger.info(log_message)


            logger.info(f"Тестирование парсера с {len(sample_items)} элементами.")
            processed_results = run_parsing_process(sample_items, cfg, console_progress_callback, console_db_update)

            logger.info("Результаты автономного запуска:")
            for res_item in processed_results:
                logger.info(
                    f"  ID: {res_item.get('id')}, URL: {res_item.get('url')}, Код: {res_item.get('result_code')}, Сток: {res_item.get('stock_value')}")
            logger.info("Автономный запуск завершен.")
    except Exception as e:
        logger.critical(f"Ошибка во время автономного запуска parser_logic.py: {e}", exc_info=True)
    logger.info("Автономный режим parser_logic.py завершен.")