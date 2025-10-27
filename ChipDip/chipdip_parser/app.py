# ChipDip/chipdip_parser/app.py
import time
import logging
import sys
import random
import os

config_loader = None
utils = None
database = None
scraper = None
scheduler = None
# Убираем uc и специфичные для Chrome исключения, если они не нужны для Firefox
# import undetected_chromedriver as uc # <-- УБРАТЬ ИЛИ ЗАКОММЕНТИРОВАТЬ
# from selenium.common.exceptions import WebDriverException # Это общее исключение, можно оставить

# Новые импорты для Firefox:
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.common.exceptions import WebDriverException  # Оставляем

try:
    from chipdip_parser import config_loader
except SystemExit as e_conf:
    print(f"CRITICAL: Ошибка загрузки конфигурации: {e_conf}. Парсер не может быть запущен.")
    sys.exit(1)
except ImportError as e_imp:
    print(
        f"CRITICAL: Ошибка импорта модуля конфигурации: {e_imp}. Убедитесь в правильности структуры проекта и PYTHONPATH.")
    sys.exit(1)

try:
    from chipdip_parser import utils

    utils.setup_logging()
except ImportError as e_imp_utils:
    print(f"CRITICAL: Ошибка импорта модуля утилит: {e_imp_utils}.")
    logging.basicConfig(level=logging.ERROR)
    logging.critical(f"Ошибка импорта utils: {e_imp_utils}")
    sys.exit(1)

logger = logging.getLogger(__name__)

try:
    from chipdip_parser import database
    from chipdip_parser import scraper
    from chipdip_parser import scheduler
except ImportError as e_modules:
    logger.critical(f"Критическая ошибка импорта основных модулей: {e_modules}. Проверьте структуру проекта.",
                    exc_info=True)
    sys.exit(1)


def main_parser_loop():
    logger.info("Запуск основного цикла парсера.")
    db_conn = None
    driver = None
    task_scheduler = scheduler.TaskScheduler()
    config = config_loader.get_config()

    try:
        # --- Инициализация WebDriver для Firefox ---
        logger.info("Инициализация Selenium WebDriver (Firefox)...")
        options = FirefoxOptions()

        if config.get('headless_bool', True):
            options.add_argument("--headless")
            logger.info("WebDriver (Firefox) будет запущен в headless режиме.")
        else:
            logger.info("WebDriver (Firefox) будет запущен в обычном (не headless) режиме.")

        # User-Agent для Firefox (можно также брать из конфига)
        options.set_preference("general.useragent.override",
                               config.get('user_agent',
                                          'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0'))

        # Другие полезные опции Firefox для стабильности/маскировки
        options.set_preference("dom.webdriver.enabled", False)  # Попытка скрыть, что это WebDriver
        options.set_preference('useAutomationExtension', False)
        # options.add_argument("--width=1920") # Можно задать размер окна
        # options.add_argument("--height=1080")

        geckodriver_path = config.get('geckodriver_path', 'geckodriver')  # 'geckodriver' если он в PATH

        try:
            # Если geckodriver_path указывает на исполняемый файл, Selenium его найдет.
            # В Dockerfile мы установим geckodriver в /usr/local/bin, который обычно в PATH.
            service = FirefoxService(
                executable_path=geckodriver_path if os.path.exists(geckodriver_path) else 'geckodriver')

            # Проверяем, существует ли путь к geckodriver, если он задан явно и не является просто 'geckodriver'
            if geckodriver_path != 'geckodriver' and not os.path.exists(geckodriver_path):
                logger.warning(
                    f"Указанный путь к geckodriver '{geckodriver_path}' не существует. Попытка использовать geckodriver из PATH.")
                # В этом случае Selenium попытается найти geckodriver в системном PATH
                driver = webdriver.Firefox(options=options)
            elif geckodriver_path == 'geckodriver':  # Явно используем из PATH
                driver = webdriver.Firefox(options=options)
            else:  # Используем указанный путь
                driver = webdriver.Firefox(service=service, options=options)

            driver.set_page_load_timeout(config.get('selenium_page_load_timeout_sec', 60))
            logger.info("Selenium WebDriver (Firefox) успешно инициализирован.")
        except WebDriverException as e_wd_init:
            logger.critical(f"Критическая ошибка инициализации WebDriver (Firefox): {e_wd_init}", exc_info=True)
            logger.critical(
                "Парсер не может продолжить работу без WebDriver. Проверьте установку Firefox/Geckodriver и пути.")
            raise SystemExit("Ошибка инициализации WebDriver (Firefox)")
        # --- Конец инициализации WebDriver ---

        db_conn = database.get_db_connection()

        # ... (Остальная часть цикла while True остается такой же, как была) ...
        # Она должна быть совместима с любым Selenium WebDriver (Chrome или Firefox)
        # Убедитесь, что scraper.py использует только общие методы Selenium

        while True:
            if not task_scheduler.wait_if_needed():
                continue

            # Проверяем соединение с БД и переподключаемся при необходимости
            if db_conn.closed:
                logger.info("Соединение с БД закрыто, переподключаемся...")
                db_conn = database.get_db_connection()

            product_to_parse = database.get_product_to_parse(db_conn)

            if not product_to_parse:
                cfg_sleep_no_prod = config.get('sleep_no_products_min', 15) * 60
                logger.info(f"Нет товаров для парсинга. Пауза на {cfg_sleep_no_prod / 60:.1f} минут.")
                time.sleep(cfg_sleep_no_prod + random.uniform(0, 10))
                continue

            product_id = product_to_parse['id']
            product_url = product_to_parse['url']
            current_db_name = product_to_parse.get('name')
            current_db_sku = product_to_parse.get('internal_sku')
            current_db_price = product_to_parse.get('current_price')

            logger.info(
                f"Начало обработки товара ID: {product_id}, URL: {product_url}, Текущая цена в БД: {current_db_price}")

            parsed_data = scraper.get_product_details_from_site(product_url, driver, config)

            page_not_found_flag = parsed_data.get("page_not_found", False)
            status_product_not_found = config.get('status_product_not_found', 'product_not_found_on_site')

            if page_not_found_flag:
                logger.warning(
                    f"Страница для товара ID: {product_id}, URL: {product_url} не найдена или товар отсутствует.")
                database.deactivate_product(db_conn, product_id)
                stock = 0
                parsed_price = None
                status_msg = status_product_not_found
                raw_text_stock = parsed_data.get("raw_stock_text", "Product page not found by scraper")
                error_message_text = raw_text_stock
                database.save_stock_history(db_conn, product_id, stock, raw_text_stock, status_msg, error_message_text,
                                            price=parsed_price)
            else:
                parsed_name = parsed_data.get("name")
                parsed_notes = parsed_data.get("notes")
                stock = parsed_data.get("stock_level", -1)
                raw_text_stock = parsed_data.get("raw_stock_text")
                err_flag = parsed_data.get("error_flag", False)
                parsed_price = parsed_data.get("price")

                name_to_update = None
                if parsed_name and (
                        not current_db_name or current_db_name == current_db_sku or current_db_name != parsed_name):
                    name_to_update = parsed_name

                notes_to_update = None
                if parsed_notes is not None:
                    notes_to_update = parsed_notes

                database.update_product_details_in_db(db_conn, product_id,
                                                      new_name=name_to_update,
                                                      new_notes=notes_to_update,
                                                      new_price=parsed_price,
                                                      current_db_price=current_db_price)

                status_msg = 'success'
                error_message_text = None

                if err_flag:
                    status_msg = parsed_data.get("status_override", 'error_parsing')
                    error_message_text = raw_text_stock if raw_text_stock else "Scraper flagged an error"
                elif stock == -1 and "Invalid URL" in str(raw_text_stock):
                    status_msg = 'error_invalid_url'
                    error_message_text = raw_text_stock
                elif stock == -1 and "XPath not configured" in str(raw_text_stock):
                    status_msg = 'config_error_xpath'
                    error_message_text = raw_text_stock
                elif stock == 0 and raw_text_stock and (
                        "not found" in raw_text_stock.lower() or "timeout" in raw_text_stock.lower()):
                    status_msg = 'not_found_on_site'
                    error_message_text = raw_text_stock
                elif stock == -1 and not err_flag:
                    status_msg = 'error_processing_stock'
                    error_message_text = f"Failed to parse stock from: {raw_text_stock}"

                database.save_stock_history(db_conn, product_id, stock, raw_text_stock, status_msg, error_message_text,
                                            price=parsed_price)
                database.update_product_check_time(db_conn, product_id)

            task_scheduler.record_request_processed()
            logger.info(f"Завершение обработки товара ID: {product_id}")

            delay = task_scheduler.get_random_delay()
            logger.debug(f"Пауза перед следующим запросом: {delay:.2f} сек.")
            time.sleep(delay)

    except ConnectionError as e:
        logger.critical(f"Критическая ошибка соединения с БД: {e}. Завершение работы.", exc_info=True)
    except SystemExit as e:
        logger.info(f"Завершение работы из-за SystemExit: {e}")
    except KeyboardInterrupt:
        logger.info("Парсер остановлен вручную (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Непредвиденная критическая ошибка в основном цикле парсера: {e}", exc_info=True)
    finally:
        if driver:
            logger.info("Закрытие Selenium WebDriver (Firefox)...")
            try:
                driver.quit()
                logger.info("Selenium WebDriver (Firefox) успешно закрыт.")
                time.sleep(1)  # Небольшая пауза после quit
            except Exception as e_quit:
                logger.error(f"Ошибка при закрытии Selenium WebDriver (Firefox): {e_quit}", exc_info=True)

        if db_conn and not getattr(db_conn, 'closed', True):
            try:
                db_conn.close()
                logger.info("Соединение с PostgreSQL закрыто.")
            except Exception as e_close:
                logger.error(f"Ошибка при закрытии соединения с БД: {e_close}", exc_info=True)
        logger.info("Основной цикл парсера штатно или аварийно завершен.")


if __name__ == '__main__':
    logger.info("Запуск приложения парсера ChipDip (main_parser_loop).")
    main_parser_loop()