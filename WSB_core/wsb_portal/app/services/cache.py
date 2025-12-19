"""
Сервис для работы с Redis кэшем
"""
import json
import logging
import os
from typing import Any, Optional, Dict
from datetime import timedelta
from dotenv import load_dotenv
import os

logger = logging.getLogger(__name__)

# Загружаем .env только если переменные окружения не заданы
# Это позволяет использовать env_file из docker-compose с приоритетом
if not os.getenv("REDIS_HOST") and not os.getenv("REDIS_ENABLED"):
    load_dotenv(override=False)

# Настройки Redis из переменных окружения
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"

# TTL для разных типов данных (в секундах)
TTL_HEATMAP = int(os.getenv("CACHE_TTL_HEATMAP", "300"))  # 5 минут
TTL_DASHBOARD = int(os.getenv("CACHE_TTL_DASHBOARD", "600"))  # 10 минут
TTL_EQUIPMENT = int(os.getenv("CACHE_TTL_EQUIPMENT", "1800"))  # 30 минут
TTL_CATEGORIES = int(os.getenv("CACHE_TTL_CATEGORIES", "1800"))  # 30 минут
TTL_SI_MODULE = int(os.getenv("CACHE_TTL_SI_MODULE", "900"))  # 15 минут
TTL_USERS = int(os.getenv("CACHE_TTL_USERS", "1800"))  # 30 минут

# Префиксы для ключей кэша
PREFIX_HEATMAP = "heatmap"
PREFIX_DASHBOARD = "dashboard"
PREFIX_EQUIPMENT = "equipment"
PREFIX_CATEGORIES = "categories"
PREFIX_SI_MODULE = "si_module"
PREFIX_USERS = "users"

_redis_client: Optional[Any] = None


def _get_redis_client():
    """Получить клиент Redis (ленивая инициализация с переподключением)"""
    global _redis_client
    
    if not REDIS_ENABLED:
        return None
    
    # Проверяем существующее подключение
    if _redis_client is not None:
        try:
            # Проверяем, что подключение еще активно
            _redis_client.ping()
            return _redis_client
        except Exception:
            # Подключение разорвано, сбрасываем клиент
            _redis_client = None
    
    # Пытаемся создать новое подключение
    try:
        import redis
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,  # Автоматически декодировать строки
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Проверка подключения
        _redis_client.ping()
        logger.info(f"Redis подключен: {REDIS_HOST}:{REDIS_PORT}")
        return _redis_client
    except ImportError:
        logger.warning("Redis не установлен. Установите: pip install redis")
        return None
    except Exception as exc:
        logger.warning(f"Не удалось подключиться к Redis: {exc}. Кэширование отключено.")
        _redis_client = None
        return None


def get(key: str) -> Optional[Any]:
    """Получить значение из кэша"""
    if not REDIS_ENABLED:
        return None
    
    client = _get_redis_client()
    if not client:
        return None
    
    try:
        value = client.get(key)
        if value:
            return json.loads(value)
        return None
    except Exception as exc:
        # При ошибке соединения сбрасываем клиент для переподключения
        if "Connection" in str(type(exc).__name__) or "10061" in str(exc):
            global _redis_client
            _redis_client = None
        logger.error(f"Ошибка при получении из кэша {key}: {exc}")
        return None


def set(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Сохранить значение в кэш"""
    if not REDIS_ENABLED:
        return False
    
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        value_json = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            client.setex(key, ttl, value_json)
        else:
            client.set(key, value_json)
        return True
    except Exception as exc:
        # При ошибке соединения сбрасываем клиент для переподключения
        if "Connection" in str(type(exc).__name__) or "10061" in str(exc):
            global _redis_client
            _redis_client = None
        logger.error(f"Ошибка при сохранении в кэш {key}: {exc}")
        return False


def delete(key: str) -> bool:
    """Удалить ключ из кэша"""
    if not REDIS_ENABLED:
        return False
    
    client = _get_redis_client()
    if not client:
        return False
    
    try:
        client.delete(key)
        return True
    except Exception as exc:
        logger.error(f"Ошибка при удалении из кэша {key}: {exc}")
        return False


def delete_pattern(pattern: str) -> int:
    """Удалить все ключи по паттерну"""
    if not REDIS_ENABLED:
        return 0
    
    client = _get_redis_client()
    if not client:
        return 0
    
    try:
        keys = client.keys(pattern)
        if keys:
            return client.delete(*keys)
        return 0
    except Exception as exc:
        logger.error(f"Ошибка при удалении по паттерну {pattern}: {exc}")
        return 0


# Функции для работы с конкретными типами данных

def get_heatmap(date_str: str) -> Optional[Dict[str, Any]]:
    """Получить тепловую карту из кэша"""
    key = f"{PREFIX_HEATMAP}:{date_str}"
    return get(key)


def set_heatmap(date_str: str, data: Dict[str, Any]) -> bool:
    """Сохранить тепловую карту в кэш"""
    key = f"{PREFIX_HEATMAP}:{date_str}"
    return set(key, data, TTL_HEATMAP)


def invalidate_heatmap(date_str: Optional[str] = None) -> int:
    """Инвалидировать кэш тепловой карты"""
    if date_str:
        key = f"{PREFIX_HEATMAP}:{date_str}"
        return 1 if delete(key) else 0
    else:
        pattern = f"{PREFIX_HEATMAP}:*"
        return delete_pattern(pattern)


def get_dashboard(date_from: str, date_to: str) -> Optional[Dict[str, Any]]:
    """Получить дашборд из кэша"""
    key = f"{PREFIX_DASHBOARD}:{date_from}:{date_to}"
    return get(key)


def set_dashboard(date_from: str, date_to: str, data: Dict[str, Any]) -> bool:
    """Сохранить дашборд в кэш"""
    key = f"{PREFIX_DASHBOARD}:{date_from}:{date_to}"
    return set(key, data, TTL_DASHBOARD)


def invalidate_dashboard() -> int:
    """Инвалидировать кэш дашборда"""
    pattern = f"{PREFIX_DASHBOARD}:*"
    return delete_pattern(pattern)


def get_equipment_list(category_id: Optional[int] = None) -> Optional[Any]:
    """Получить список оборудования из кэша"""
    if category_id:
        key = f"{PREFIX_EQUIPMENT}:category:{category_id}"
    else:
        key = f"{PREFIX_EQUIPMENT}:all"
    return get(key)


def set_equipment_list(category_id: Optional[int], data: Any) -> bool:
    """Сохранить список оборудования в кэш"""
    if category_id:
        key = f"{PREFIX_EQUIPMENT}:category:{category_id}"
    else:
        key = f"{PREFIX_EQUIPMENT}:all"
    return set(key, data, TTL_EQUIPMENT)


def invalidate_equipment() -> int:
    """Инвалидировать кэш оборудования"""
    pattern = f"{PREFIX_EQUIPMENT}:*"
    return delete_pattern(pattern)


def get_categories() -> Optional[Any]:
    """Получить список категорий из кэша"""
    key = f"{PREFIX_CATEGORIES}:all"
    return get(key)


def set_categories(data: Any) -> bool:
    """Сохранить список категорий в кэш"""
    key = f"{PREFIX_CATEGORIES}:all"
    return set(key, data, TTL_CATEGORIES)


def invalidate_categories() -> int:
    """Инвалидировать кэш категорий"""
    pattern = f"{PREFIX_CATEGORIES}:*"
    return delete_pattern(pattern)


def get_si_module(module_type: str) -> Optional[Any]:
    """Получить данные модуля СИ из кэша"""
    key = f"{PREFIX_SI_MODULE}:{module_type}"
    return get(key)


def set_si_module(module_type: str, data: Any) -> bool:
    """Сохранить данные модуля СИ в кэш"""
    key = f"{PREFIX_SI_MODULE}:{module_type}"
    return set(key, data, TTL_SI_MODULE)


def invalidate_si_module(module_type: Optional[str] = None) -> int:
    """Инвалидировать кэш модуля СИ"""
    if module_type:
        key = f"{PREFIX_SI_MODULE}:{module_type}"
        return 1 if delete(key) else 0
    else:
        pattern = f"{PREFIX_SI_MODULE}:*"
        return delete_pattern(pattern)


def get_users() -> Optional[Any]:
    """Получить список пользователей из кэша"""
    key = f"{PREFIX_USERS}:all"
    return get(key)


def set_users(data: Any) -> bool:
    """Сохранить список пользователей в кэш"""
    key = f"{PREFIX_USERS}:all"
    return set(key, data, TTL_USERS)


def invalidate_users() -> int:
    """Инвалидировать кэш пользователей"""
    pattern = f"{PREFIX_USERS}:*"
    return delete_pattern(pattern)

