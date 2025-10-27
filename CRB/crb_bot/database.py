# --- START OF FILE database.py ---

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
    # Атрибут класса для хранения пула соединений
    _pool: Optional[psycopg2.pool.SimpleConnectionPool] = None

    @classmethod
    def initialize_pool(cls, min_conn: int = 1, max_conn: int = 5): # <-- Параметры по умолчанию
        """Инициализирует пул соединений PostgreSQL."""
        # Проверяем, не был ли пул уже инициализирован
        if cls._pool is None:
            # --- Валидация параметров пула ---
            # Проверка минимального количества соединений
            if min_conn < 1:
                logger.warning(
                    f"Значение min_conn ({min_conn}) не может быть меньше 1. "
                    "Установлено значение по умолчанию: 1."
                )
                min_conn = 1
            # Проверка максимального количества соединений
            if max_conn < min_conn:
                logger.warning(
                    f"Значение max_conn ({max_conn}) не может быть меньше min_conn ({min_conn}). "
                    f"Установлено значение max_conn = {min_conn}."
                )
                max_conn = min_conn

            # --- Попытка создания пула ---
            try:
                logger.info(
                    f"Инициализация пула соединений с БД PostgreSQL "
                    f"(min={min_conn}, max={max_conn})..."
                )
                # Создаем пул соединений SimpleConnectionPool
                cls._pool = psycopg2.pool.SimpleConnectionPool(
                    minconn=min_conn,           # Минимальное количество соединений
                    maxconn=max_conn,           # Максимальное количество соединений
                    user=config.DB_USER,        # Имя пользователя БД
                    password=config.DB_PASSWORD,# Пароль пользователя БД (может быть None)
                    host=config.DB_HOST,        # Хост БД
                    port=config.DB_PORT,        # Порт БД
                    database=config.DB_NAME,    # Имя базы данных
                    cursor_factory=DictCursor   # Используем DictCursor для удобного доступа к данным
                )
                logger.info("Пул соединений создан. Попытка тестового подключения...")

                # --- Проверка соединения при инициализации ---
                conn = None # Инициализируем переменную перед try
                try:
                    # Получаем тестовое соединение из созданного пула
                    conn = cls.get_connection()
                    # Проверяем, удалось ли получить соединение
                    if conn:
                        logger.info(
                            f"Тестовое соединение успешно получено. "
                            f"Версия PostgreSQL: {conn.server_version}"
                        )
                        # Откатываем любую возможную начальную транзакцию
                        conn.rollback()
                        logger.debug("Тестовая транзакция отменена (rollback).")
                        # Возвращаем тестовое соединение обратно в пул
                        cls.release_connection(conn)
                        logger.info("Пул соединений успешно инициализирован и готов к работе.")
                    else:
                        # Если соединение не получено, генерируем ошибку
                        logger.critical("Не удалось получить тестовое соединение из пула после его создания!")
                        raise ConnectionError("Не удалось получить тестовое соединение из пула.")
                # Обрабатываем возможные ошибки при получении/возврате тестового соединения
                except (Exception, psycopg2.Error, ConnectionError) as test_conn_error:
                    logger.critical(f"Ошибка во время тестового подключения при инициализации пула: {test_conn_error}", exc_info=True)
                    # Если пул был создан, но тестовое соединение не удалось, закрываем пул
                    if cls._pool:
                        cls._pool.closeall()
                        cls._pool = None
                        logger.warning("Пул соединений был закрыт из-за ошибки тестового подключения.")
                    raise test_conn_error # Пробрасываем ошибку дальше

            # Обрабатываем ошибки, возникшие при создании самого пула
            except (Exception, psycopg2.DatabaseError) as pool_init_error:
                logger.critical(f"Критическая ошибка инициализации пула соединений: {pool_init_error}", exc_info=True)
                # Убеждаемся, что пул сброшен в None в случае ошибки
                cls._pool = None
                # Пробрасываем исключение дальше, так как без пула работа невозможна
                raise pool_init_error
        else:
            logger.warning("Попытка повторной инициализации уже существующего пула соединений.")


    @classmethod
    def close_pool(cls):
        """Закрывает все соединения в пуле."""
        # Проверяем, был ли пул инициализирован
        if cls._pool is not None:
            logger.info("Закрытие пула соединений...")
            # Закрываем все соединения в пуле
            cls._pool.closeall()
            # Сбрасываем ссылку на пул
            cls._pool = None
            logger.info("Пул соединений успешно закрыт.")
        else:
            logger.info("Пул соединений не был инициализирован, закрытие не требуется.")

    @classmethod
    def get_connection(cls):
        """Получает соединение из пула."""
        # Проверяем, инициализирован ли пул
        if cls._pool is None:
            logger.error("Критическая ошибка: Попытка получить соединение из неинициализированного пула!")
            # Генерируем исключение, так как работа без пула невозможна
            raise ConnectionError("Пул соединений базы данных не инициализирован.")

        # --- Попытка получения соединения ---
        conn = None # Инициализируем переменную перед try
        try:
            # Получаем соединение из пула
            conn = cls._pool.getconn()
            logger.debug(f"Соединение {id(conn)} получено из пула.")
            # Возвращаем полученное соединение
            return conn
        # Обрабатываем возможные ошибки при получении соединения
        except (Exception, psycopg2.Error) as e:
            logger.error(f"Ошибка при получении соединения из пула: {e}", exc_info=True)
            # Пробрасываем ошибку как ConnectionError для унификации
            raise ConnectionError(f"Не удалось получить соединение из пула: {e}")

    @classmethod
    def release_connection(cls, conn):
        """Возвращает соединение обратно в пул."""
        # Проверяем, что пул существует и переданное соединение не None
        if cls._pool is not None:
            if conn is not None:
                # --- Попытка возврата соединения в пул ---
                try:
                    # Возвращаем соединение в пул
                    cls._pool.putconn(conn)
                    logger.debug(f"Соединение {id(conn)} возвращено в пул.")
                # Обрабатываем ошибки при возврате соединения
                except (Exception, psycopg2.Error) as e:
                    logger.error(f"Ошибка при возврате соединения {id(conn)} в пул: {e}", exc_info=True)
                    # Если вернуть не удалось, пытаемся принудительно закрыть соединение
                    try:
                        conn.close()
                        logger.warning(
                            f"Соединение {id(conn)} было принудительно закрыто "
                            "из-за ошибки возврата в пул."
                        )
                    except Exception as close_err:
                        logger.error(
                            f"Критическая ошибка: Не удалось даже принудительно закрыть "
                            f"соединение {id(conn)} после ошибки возврата в пул: {close_err}"
                        )
            else:
                logger.warning("Попытка вернуть None соединение в пул проигнорирована.")
        else:
            logger.warning("Попытка вернуть соединение в несуществующий пул.")


    # Метод execute_query остается методом экземпляра,
    # так как он обычно вызывается через объект db_connection в других модулях.

    def execute_query(self, query: str, params: Optional[Tuple] = None,
                        fetch_results: bool = False, commit: bool = False) -> Union[QueryResult, Optional[int]]: # <-- Изменен тип возврата
        """
        Выполняет SQL-запрос, используя соединение из пула.

        Args:
            query (str): SQL-запрос с плейсхолдерами %s.
            params (Optional[Tuple]): Кортеж параметров для запроса.
            fetch_results (bool): Указывает, нужно ли возвращать результаты (для SELECT).
            commit (bool): Указывает, нужно ли выполнить COMMIT после запроса (для INSERT/UPDATE/DELETE).

        Returns:
            Union[QueryResult, Optional[int]]:
                - Список словарей (если fetch_results=True и есть результаты).
                - Пустой список (если fetch_results=True и нет результатов).
                - Количество затронутых строк (int) (если fetch_results=False и запрос INSERT/UPDATE/DELETE).
                - None (если fetch_results=False и запрос не INSERT/UPDATE/DELETE, или произошла ошибка выполнения перед получением rowcount).

        Raises:
            psycopg2.Error: В случае ошибок базы данных при выполнении запроса, коммита или роллбэка.
            ConnectionError: Если не удалось получить соединение из пула.
            Exception: Другие непредвиденные ошибки.
        """
        conn = None # Инициализируем соединение как None
        results: QueryResult = None # Инициализируем результат как None
        rows_affected: Optional[int] = None # Для хранения количества строк

        # --- Основной блок выполнения запроса ---
        try:
            # Шаг 1: Получаем соединение из пула
            conn = self.get_connection()

            # Шаг 2: Создаем курсор и выполняем запрос
            # Используем 'with' для автоматического закрытия курсора
            with conn.cursor() as cursor: # cursor_factory=DictCursor задан при инициализации пула
                # Определяем тип запроса для логирования
                query_type = "UNKNOWN" # Значение по умолчанию
                first_word = ""
                if query and isinstance(query, str):
                    stripped_query = query.strip()
                    if stripped_query:
                        first_word = stripped_query.split(maxsplit=1)[0].upper()
                        query_type = first_word

                logger.debug(f"Выполнение запроса [{query_type}] на соед. {id(conn)}: {query.strip()}... Параметры: {params}")
                # Выполняем запрос с параметрами
                cursor.execute(query, params)
                logger.debug(f"Запрос [{query_type}] выполнен на соед. {id(conn)}.")

                # Пытаемся получить rowcount *после* выполнения запроса
                # Это важно для UPDATE/DELETE/INSERT без RETURNING
                try:
                    # cursor.rowcount может быть недоступен или неточен для SELECT
                    # в некоторых реализациях/версиях psycopg2/postgres,
                    # но для INSERT/UPDATE/DELETE он должен работать.
                    rows_affected = cursor.rowcount
                except Exception as e_rowcount:
                    logger.warning(f"Не удалось получить rowcount для запроса типа {query_type}: {e_rowcount}")
                    rows_affected = -1 # Используем -1 как индикатор невозможности получения или нерелевантности

                # Шаг 3: Коммит транзакции, если требуется (после выполнения и получения rowcount)
                if commit:
                    # Внутренний try/except для обработки ошибок коммита
                    try:
                        conn.commit()
                        logger.debug(f"Запрос [{query_type}] успешно закоммичен на соед. {id(conn)}.")
                    except (Exception, psycopg2.Error) as commit_error:
                        logger.error(f"Ошибка при COMMIT после запроса [{query_type}] на соед. {id(conn)}: {commit_error}", exc_info=True)
                        try: conn.rollback()
                        except Exception as rb_error: logger.error(f"Критическая ошибка: Не удалось выполнить rollback на соед. {id(conn)} после ошибки коммита: {rb_error}")
                        raise commit_error # Пробрасываем исходную ошибку коммита

                # Шаг 4: Получение/Возврат результатов
                if fetch_results:
                    # Получаем все строки результата
                    results = cursor.fetchall()
                    if results is not None: logger.debug(f"Запрос [{query_type}] на соед. {id(conn)} вернул {len(results)} строк.")
                    else: logger.debug(f"Запрос [{query_type}] на соед. {id(conn)} не вернул строк (результат None)."); results = []
                    return results # Возвращаем список словарей или пустой список
                else:
                    # Если результаты не запрашивались (fetch_results=False)
                    if query_type in ("INSERT", "UPDATE", "DELETE"):
                        # Для изменяющих запросов возвращаем количество затронутых строк
                        logger.debug(f"Запрос [{query_type}] на соед. {id(conn)} затронул {rows_affected} строк (возвращаем).")
                        return rows_affected
                    else:
                        # Для SELECT и других запросов без fetch_results возвращаем None
                        logger.debug(f"Запрос [{query_type}] без fetch_results, возвращаем None.")
                        return None

        # --- Обработка ошибок выполнения запроса или получения соединения ---
        except (psycopg2.Error, ConnectionError) as db_error:
            logger.error(f"Ошибка базы данных или соединения при выполнении SQL: {query.strip()} Параметры: {params} Ошибка: {db_error}", exc_info=True)
            if conn and not commit: # Если ошибка до коммита (или коммит не требовался)
                try: conn.rollback()
                except Exception as rb_error: logger.error(f"Ошибка при попытке rollback на соед. {id(conn)} после ошибки выполнения: {rb_error}")
            raise db_error # Пробрасываем ошибку БД или соединения дальше

        # --- Обработка прочих непредвиденных ошибок ---
        except Exception as other_error:
            logger.error(f"Непредвиденная ошибка при выполнении SQL: {query.strip()} Параметры: {params} Ошибка: {other_error}", exc_info=True)
            if conn and not commit:
                try: conn.rollback()
                except Exception as rb_error: logger.error(f"Ошибка при попытке rollback на соед. {id(conn)} после непредвиденной ошибки: {rb_error}")
            raise other_error # Пробрасываем ошибку дальше

        # --- Блок finally: Гарантированное возвращение соединения в пул ---
        finally:
            if conn:
                self.release_connection(conn) # Возвращаем соединение обратно в пул

    # --- Методы для явного управления транзакциями ---
    # Эти методы могут быть полезны, если нужно выполнить несколько запросов в одной транзакции,
    # управляя соединением вручную (получить соединение -> выполнить запросы -> commit/rollback -> вернуть соединение).

    def commit_transaction(self, conn):
        """Явно коммитит транзакцию на переданном соединении."""
        # Проверяем, что передано действительное соединение
        if conn:
            # --- Попытка коммита ---
            try:
                # Выполняем коммит
                conn.commit()
                logger.debug(f"Транзакция на соед. {id(conn)} успешно закоммичена (явный вызов).")
            # Обрабатываем ошибки коммита
            except (Exception, psycopg2.Error) as e:
                logger.error(f"Ошибка при явном commit на соед. {id(conn)}: {e}", exc_info=True)
                # Если коммит не удался, пытаемся откатить транзакцию
                try:
                    conn.rollback()
                    logger.warning(f"Транзакция на соед. {id(conn)} отменена (rollback) из-за ошибки явного commit.")
                except Exception as rb_err:
                    logger.error(
                        f"Критическая ошибка: Не удалось выполнить rollback на соед. {id(conn)} "
                        f"после ошибки явного commit: {rb_err}"
                    )
                # Пробрасываем исходную ошибку коммита
                raise e
        else:
            logger.warning("Попытка явного commit для None соединения.")


    def rollback_transaction(self, conn):
        """Явно откатывает транзакцию на переданном соединении."""
        # Проверяем, что передано действительное соединение
        if conn:
            # --- Попытка роллбэка ---
            try:
                # Выполняем роллбэк
                conn.rollback()
                logger.debug(f"Транзакция на соед. {id(conn)} отменена (явный rollback).")
            # Обрабатываем ошибки роллбэка
            except (Exception, psycopg2.Error) as e:
                logger.error(f"Ошибка при явном rollback на соед. {id(conn)}: {e}", exc_info=True)
                # Пробрасываем ошибку дальше (если роллбэк не удался, мало что можно сделать)
                raise e
        else:
            logger.warning("Попытка явного rollback для None соединения.")

# --- END OF FILE database.py ---