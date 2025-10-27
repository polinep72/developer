# chipdip_parser/config_loader.py
import logging
from decouple import config as env_config, UndefinedValueError

logger = logging.getLogger(__name__)

APP_CONFIG = {}


def load_app_config():
    global APP_CONFIG
    logger.info("Загрузка конфигурации приложения...")
    try:
        APP_CONFIG['geckodriver_path'] = env_config('GECKODRIVER_PATH', default='geckodriver')
        APP_CONFIG['user_agent'] = env_config('USER_AGENT',
                                              default='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:100.0) Gecko/20100101 Firefox/100.0')

        # --- PostgreSQL ---
        APP_CONFIG['db_name'] = env_config('DB_NAME')
        APP_CONFIG['db_user'] = env_config('DB_USER')
        APP_CONFIG['db_password'] = env_config('DB_PASSWORD')
        APP_CONFIG['db_host'] = env_config('DB_HOST')
        APP_CONFIG['db_port'] = env_config('DB_PORT', cast=int)

        # --- Selenium / Chrome ---
        APP_CONFIG['headless_bool'] = env_config('HEADLESS', default='1', cast=bool)
        APP_CONFIG['chrome_executable_path'] = env_config('CHROME_EXECUTABLE_PATH', default=None)
        APP_CONFIG['selenium_wait_timeout'] = env_config('SELENIUM_WAIT_TIMEOUT', default=25, cast=int)
        APP_CONFIG['selenium_page_load_timeout_sec'] = env_config('SELENIUM_PAGE_LOAD_TIMEOUT_SEC', default=60,
                                                                  cast=int)

        # --- Логирование ---
        APP_CONFIG['log_level_console'] = env_config('LOG_LEVEL_CONSOLE', default='INFO')
        APP_CONFIG['log_level_file'] = env_config('LOG_LEVEL_FILE', default='DEBUG')
        APP_CONFIG['log_file_path'] = env_config('LOG_FILE_PATH', default='parser_app.log')

        # --- Логика парсера ---
        APP_CONFIG['max_requests_per_hour'] = env_config('MAX_REQUESTS_PER_HOUR', default=25, cast=int)
        APP_CONFIG['min_request_delay_sec'] = env_config('MIN_REQUEST_DELAY_SEC', default=70, cast=int)
        APP_CONFIG['max_request_delay_sec'] = env_config('MAX_REQUEST_DELAY_SEC', default=200, cast=int)
        APP_CONFIG['sleep_non_work_time_min'] = env_config('SLEEP_NON_WORK_TIME_MIN', default=30, cast=int)
        APP_CONFIG['sleep_no_products_min'] = env_config('SLEEP_NO_PRODUCTS_MIN', default=15, cast=int)
        APP_CONFIG['work_start_hour'] = env_config('WORK_START_HOUR', default=8, cast=int)
        APP_CONFIG['work_end_hour'] = env_config('WORK_END_HOUR', default=17, cast=int)
        APP_CONFIG['holidays_country_code'] = env_config('HOLIDAYS_COUNTRY_CODE', default='RU')
        APP_CONFIG['timezone'] = env_config('TIMEZONE', default='Europe/Moscow')

        # --- Статусы парсера (пример) ---
        APP_CONFIG['status_product_not_found'] = env_config('STATUS_PRODUCT_NOT_FOUND',
                                                            default='product_not_found_on_site')
        # --- XPath селекторы ---
        APP_CONFIG['xpath_stock'] = env_config('XPATH_STOCK')
        APP_CONFIG['xpath_product_name'] = env_config('XPATH_PRODUCT_NAME')
        APP_CONFIG['xpath_product_description'] = env_config('XPATH_PRODUCT_DESCRIPTION',
                                                             default=None)  # Может отсутствовать
        APP_CONFIG['xpath_price'] = env_config('XPATH_PRICE', default=None)  # Может отсутствовать
        # APP_CONFIG['xpath_artikul_page'] = env_config('XPATH_ARTIKUL_PAGE', default=None) # Опционально

        logger.info("Конфигурация успешно загружена.")
        logger.debug(f"Загруженная конфигурация (частично): "
                     f"DB Host: {APP_CONFIG.get('db_host')}, "
                     f"Headless: {APP_CONFIG.get('headless_bool')}, "
                     f"XPath Stock: {APP_CONFIG.get('xpath_stock')}")  # Логируем только часть для краткости
        return APP_CONFIG

    except UndefinedValueError as e:
        logger.critical(f"Критическая ошибка: не найдена обязательная переменная конфигурации в .env: {e}",
                        exc_info=True)
        raise SystemExit(f"Ошибка конфигурации: {e}. Проверьте .env файл.")
    except Exception as e:
        logger.critical(f"Критическая ошибка при загрузке конфигурации: {e}", exc_info=True)
        raise SystemExit("Не удалось загрузить конфигурацию.")


def get_config():
    if not APP_CONFIG:  # Загружаем только если еще не загружено
        load_app_config()
    return APP_CONFIG