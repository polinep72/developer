"""
Rate limiting для защиты от DDoS и брутфорса
"""
import os
from typing import Optional
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

# Пытаемся импортировать redis для проверки доступности
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Настройки rate limiting из переменных окружения
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
RATE_LIMIT_AUTH_PER_MINUTE = int(os.getenv("RATE_LIMIT_AUTH_PER_MINUTE", "5"))

# Определяем storage для rate limiting
# Если Redis доступен, используем его, иначе память
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# Пытаемся использовать Redis, если доступен
storage_uri = "memory://"  # По умолчанию память
if REDIS_AVAILABLE and redis:  # type: ignore
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD, socket_connect_timeout=2)
        r.ping()
        # Redis доступен, используем его
        if REDIS_PASSWORD:
            storage_uri = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        else:
            storage_uri = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        logger.info(f"Rate limiting использует Redis: {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.info(f"Rate limiting использует память (Redis недоступен: {e})")
else:
    logger.info("Rate limiting использует память (redis не установлен)")

# Создаем лимитер
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{RATE_LIMIT_PER_MINUTE}/minute"] if RATE_LIMIT_ENABLED else [],
    storage_uri=storage_uri,
    headers_enabled=True,
)

# Обработчик ошибок rate limiting будет добавлен в main.py


def get_rate_limit_decorator(limit: str):
    """Получить декоратор rate limiting"""
    if not RATE_LIMIT_ENABLED:
        # Если rate limiting отключен, возвращаем пустой декоратор
        def noop_decorator(func):
            return func
        return noop_decorator
    
    return limiter.limit(limit)


# Предустановленные лимиты для разных типов эндпоинтов
def auth_rate_limit():
    """Лимит для эндпоинтов аутентификации (более строгий)"""
    return get_rate_limit_decorator(f"{RATE_LIMIT_AUTH_PER_MINUTE}/minute")


def api_rate_limit():
    """Лимит для обычных API эндпоинтов"""
    return get_rate_limit_decorator(f"{RATE_LIMIT_PER_MINUTE}/minute")


def public_rate_limit():
    """Лимит для публичных эндпоинтов"""
    return get_rate_limit_decorator(f"{RATE_LIMIT_PER_MINUTE}/minute")

