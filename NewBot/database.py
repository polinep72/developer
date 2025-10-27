import psycopg2
import logging
from typing import Optional, List, Tuple, Any, Dict
from database_config import DB_CONFIG

# Настройка логгера
logger = logging.getLogger('database')
logger.setLevel(logging.INFO)


def execute_query(
        query: str,
        params: Optional[Tuple[Any, ...]] = None,
        fetch: bool = True,
        commit: bool = True
) -> Optional[List[Tuple[Any, ...]]]:
    """
    Универсальная функция выполнения SQL-запросов
    :param query: SQL-запрос
    :param params: Параметры запроса
    :param fetch: Возвращать результат (для SELECT)
    :param commit: Выполнять commit (для INSERT/UPDATE/DELETE)
    :return: Результат запроса или None
    """
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute(query, params)

            if fetch and cursor.description:
                result = cursor.fetchall()
            else:
                result = None

            if commit:
                conn.commit()

            return result

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Ошибка выполнения запроса: {error}\nQuery: {query}\nParams: {params}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


def check_user_exists(user_id: int) -> bool:
    """Проверяет, зарегистрирован ли пользователь"""
    query = "SELECT 1 FROM users WHERE users_id = %s AND is_blocked = FALSE"
    return bool(execute_query(query, (user_id,)))