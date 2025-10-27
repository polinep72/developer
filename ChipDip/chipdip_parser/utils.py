# chipdip_parser/utils.py
import logging
import logging.handlers
# Импортируем get_config напрямую, чтобы избежать циклического импорта, если utils используется в config_loader
# В данном случае config_loader не использует utils, так что можно импортировать как обычно
from chipdip_parser.config_loader import get_config


def setup_logging():
    config = get_config()
    log_level_console_str = config.get('log_level_console', 'INFO')
    log_level_file_str = config.get('log_level_file', 'DEBUG')
    log_file_path = config.get('log_file_path', 'parser_app.log')

    # Используем logging.getLogger() для получения корневого логгера
    # или logging.getLogger(__name__) если хотите специфичный логгер для utils,
    # но для настройки обычно берут корневой или общий для приложения.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    )

    log_level_console = getattr(logging, log_level_console_str.upper(), logging.INFO)
    log_level_file = getattr(logging, log_level_file_str.upper(), logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(log_level_console)
    root_logger.addHandler(console_handler)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(log_level_file)
        root_logger.addHandler(file_handler)
        # Используем logging.info т.к. это еще до того, как logger модуля app.py мог быть создан
        logging.info(
            f"Логирование настроено. Консоль: {logging.getLevelName(log_level_console)}, Файл ('{log_file_path}'): {logging.getLevelName(log_level_file)}")
    except Exception as e:
        logging.error(f"Не удалось настроить файловый логгер для '{log_file_path}': {e}", exc_info=True)
        logging.info("Логирование будет осуществляться только в консоль.")