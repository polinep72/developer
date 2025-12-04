# database.py
import psycopg2
from psycopg2 import pool
from psycopg2.extras import DictCursor # Используем DictCursor для удобства
from logger import logger
import config # Нужен для параметров подключения
from typing import Optional, List, Tuple, Any, Dict, Union

# Определяем тип для возвращаемых строк (список словарей из DictCursor)
QueryResult = Optional[List[Dict[str, Any]]]


class Database:
    _pool: Optional[psycopg2.pool.SimpleConnectionPool] = None

    @classmethod
    def initialize_pool(cls, min_conn: int = 1, max_conn: int = 5): # <-- Параметры по умолчанию
        """Инициализирует пул соединений."""
        if cls._pool is None:
            # Проверка на корректность параметров
            if min_conn < 1:
                logger.warning(f"min_conn ({min_conn}) не может быть меньше 1. Установлено значение 1.")
                min_conn = 1
            if max_conn < min_conn:
                logger.warning(f"max_conn ({max_conn}) не может быть меньше min_conn ({min_conn}). Установлено значение {min_conn}.")
                max_conn = min_conn

            try:
                logger.info(f"Инициализация пула соединений с БД (min={min_conn}, max={max_conn})...")
                cls._pool = psycopg2.pool.SimpleConnectionPool(
                    minconn=min_conn, # <-- Используем параметры
                    maxconn=max_conn, # <-- Используем параметры
                    user=config.DB_USER,
                    password=config.DB_PASSWORD,
                    host=config.DB_HOST,
                    port=config.DB_PORT,
                    database=config.DB_NAME,
                    cursor_factory=DictCursor  # Используем DictCursor по умолчанию
                )
                # Проверка соединения при инициализации
                conn = cls.get_connection()
                if conn:
                    logger.info(f"Пул соединений успешно инициализирован. Версия PostgreSQL: {conn.server_version}")
                    conn.rollback() # Откатываем любую возможную начальную транзакцию
                    cls.release_connection(conn)
                else:
                     raise ConnectionError("Не удалось получить тестовое соединение из пула.") # Используем ConnectionError
            except (Exception, psycopg2.DatabaseError) as error:
                logger.critical(f"Ошибка инициализации пула соединений: {error}", exc_info=True)
                cls._pool = None # Сбрасываем пул в случае ошибки
                raise # Пробрасываем исключение дальше

    @classmethod
    def close_pool(cls):
        """Закрывает все соединения в пуле."""
        if cls._pool is not None:
            logger.info("Закрытие пула соединений...")
            cls._pool.closeall()
            cls._pool = None
            logger.info("Пул соединений закрыт.")

    @classmethod
    def get_connection(cls):
        """Получает соединение из пула."""
        if cls._pool is None:
            logger.error("Пул соединений не инициализирован при попытке получить соединение!")
            raise ConnectionError("Database connection pool is not initialized.") # Используем ConnectionError
        try:
            conn = cls._pool.getconn()
            return conn
        except (Exception, psycopg2.Error) as e:
            logger.error(f"Ошибка при получении соединения из пула: {e}", exc_info=True)
            raise ConnectionError(f"Failed to get connection from pool: {e}") # Пробрасываем как ConnectionError

    @classmethod
    def release_connection(cls, conn):
        """Возвращает соединение в пул."""
        if cls._pool is not None and conn is not None:
            try:
                cls._pool.putconn(conn)
            except (Exception, psycopg2.Error) as e:
                 logger.error(f"Ошибка при возврате соединения в пул: {e}", exc_info=True)
                 try:
                     conn.close()
                     logger.warning("Соединение было принудительно закрыто из-за ошибки возврата в пул.")
                 except Exception as close_err:
                     logger.error(f"Ошибка при принудительном закрытии соединения: {close_err}")

    # Метод execute_query остается методом экземпляра, т.к. он вызывается через db_connection в других модулях
    def execute_query(self, query: str, params: Optional[Tuple] = None,
                      fetch_results: bool = False, commit: bool = False) -> QueryResult:
        """
        Выполняет SQL-запрос, используя соединение из пула.

        Args:
            query (str): SQL-запрос с плейсхолдерами %s.
            params (Optional[Tuple]): Кортеж параметров для запроса.
            fetch_results (bool): Указывает, нужно ли возвращать результаты (для SELECT).
            commit (bool): Указывает, нужно ли выполнить COMMIT после запроса (для INSERT/UPDATE/DELETE).

        Returns:
            QueryResult: Список словарей (DictCursor), если fetch_results=True, иначе None.

        Raises:
            psycopg2.Error: В случае ошибок базы данных или коммита.
            ConnectionError: Если не удалось получить соединение.
            Exception: Другие возможные ошибки.
        """
        conn = None
        results: QueryResult = None
        try:
            conn = self.get_connection() # Получаем соединение
            with conn.cursor() as cursor: # DictCursor по умолчанию
                query_type = query.strip().split(maxsplit=1)[0].upper()
                logger.debug(f"Выполнение запроса [{query_type}]: {query.strip()}... Params: {params}")
                cursor.execute(query, params)

                # Коммит, если требуется
                if commit:
                    try:
                        conn.commit()
                        logger.debug(f"Запрос [{query_type}] успешно закоммичен.")
                    except (Exception, psycopg2.Error) as commit_error:
                        logger.error(f"Ошибка при COMMIT после запроса [{query_type}]: {commit_error}", exc_info=True)
                        try:
                            conn.rollback()
                            logger.warning("Транзакция отменена (rollback) из-за ошибки коммита.")
                        except Exception as rb_error:
                            logger.error(f"Критическая ошибка: Не удалось выполнить rollback после ошибки коммита: {rb_error}")
                        raise commit_error # Пробрасываем ошибку коммита

                # Получение результатов, если требуется
                if fetch_results:
                    results = cursor.fetchall() # DictCursor вернет список словарей
                    logger.debug(f"Запрос [{query_type}] вернул {len(results)} строк.")
                else:
                    # Логируем количество затронутых строк для изменяющих запросов
                    if query_type in ("INSERT", "UPDATE", "DELETE"):
                         logger.debug(f"Запрос [{query_type}] затронул {cursor.rowcount} строк.")
                    results = None # Возвращаем None, если результаты не запрашивались

                return results # Возвращаем список словарей или None

        except (psycopg2.Error, ConnectionError) as db_error: # Ловим ошибки БД и соединения
            # Роллбэк, если коммит не удался или не требовался
            if conn and not commit:
                 try:
                     conn.rollback()
                     logger.warning(f"Транзакция отменена (rollback) из-за ошибки выполнения: {db_error}")
                 except Exception as rb_error:
                     logger.error(f"Ошибка при попытке rollback после ошибки выполнения: {rb_error}")

            logger.error(f"Ошибка выполнения SQL запроса: {query.strip()} Params: {params} Ошибка: {db_error}", exc_info=True)
            raise db_error # Пробрасываем ошибку БД или соединения дальше

        except Exception as other_error: # Ловим прочие непредвиденные ошибки
            if conn and not commit:
                 try: conn.rollback()
                 except Exception: pass
            logger.error(f"Непредвиденная ошибка при выполнении SQL: {other_error}", exc_info=True)
            raise other_error # Пробрасываем дальше

        finally:
            if conn:
                self.release_connection(conn) # Всегда возвращаем соединение в пул

    # Методы commit_transaction и rollback_transaction остаются без изменений
    def commit_transaction(self, conn):
         """Явно коммитит транзакцию на переданном соединении."""
         if conn:
             try:
                 conn.commit()
                 logger.debug("Транзакция успешно закоммичена (явный вызов).")
             except (Exception, psycopg2.Error) as e:
                 logger.error(f"Ошибка при явном commit: {e}", exc_info=True)
                 try:
                    conn.rollback()
                 except Exception as rb_err:
                     logger.error(f"Ошибка rollback после ошибки явного commit: {rb_err}")
                 raise e

    def rollback_transaction(self, conn):
         """Явно откатывает транзакцию на переданном соединении."""
         if conn:
             try:
                 conn.rollback()
                 logger.debug("Транзакция отменена (явный rollback).")
             except (Exception, psycopg2.Error) as e:
                 logger.error(f"Ошибка при явном rollback: {e}", exc_info=True)
                 raise e