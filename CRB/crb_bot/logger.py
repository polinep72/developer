import logging
import logging.handlers
import sys
import os
from datetime import datetime

# Настройка директории для логов
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir)
    except OSError as e:
        print(f"Не удалось создать директорию для логов: {e}")
        log_dir = os.path.dirname(__file__)

# Базовые настройки форматирования
log_formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Файловый обработчик с ротацией
file_handler = logging.handlers.TimedRotatingFileHandler(
    filename=os.path.join(log_dir, 'app.log'),
    when='midnight',
    interval=1,
    backupCount=7,
    encoding='utf-8',
    delay=True,
    utc=False
)
file_handler.setFormatter(log_formatter)

# Консольный обработчик
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)

# Основной логгер приложения
logger = logging.getLogger('BookingBot')
logger.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)
logger.addHandler(file_handler)

# Сетевой логгер (отдельный)
network_logger = logging.getLogger('BookingBot.network')
network_logger.setLevel(logging.INFO)
network_file_handler = logging.handlers.TimedRotatingFileHandler(
    filename=os.path.join(log_dir, 'network.log'),
    when='midnight',
    backupCount=3
)
network_file_handler.setFormatter(log_formatter)
network_logger.addHandler(network_file_handler)

# Пример использования
if __name__ == '__main__':
    logger.info("Тест основного логгера")
    network_logger.info("Тест сетевого логгера")