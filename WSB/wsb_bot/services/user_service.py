# services/user_service.py
from database import Database, QueryResult
from logger import logger
from typing import List, Tuple, Optional, Dict, Any # Добавили Dict
from datetime import datetime

# --- Функции проверки статуса ---

def is_user_registered_and_active(db: Database, user_id: int) -> bool:
    """Проверяет, зарегистрирован ли пользователь в основной таблице и не заблокирован ли он."""
    query = "SELECT EXISTS (SELECT 1 FROM users WHERE users_id = %s AND is_blocked = FALSE);"
    try:
        result: QueryResult = db.execute_query(query, (user_id,), fetch_results=True)
        # Ожидаем [{'exists': True/False}]
        return result[0]['exists'] if result else False
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса пользователя {user_id}: {e}", exc_info=True)
        return False # В случае ошибки считаем неактивным

def is_admin(db: Database, user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором (активным)."""
    # Запрашиваем только нужные поля
    query = "SELECT is_admin FROM users WHERE users_id = %s AND is_blocked = FALSE;"
    try:
        result: QueryResult = db.execute_query(query, (user_id,), fetch_results=True)
        # Ожидаем [{'is_admin': True/False}]
        return result[0]['is_admin'] if result else False
    except Exception as e:
        logger.error(f"Ошибка при проверке прав админа для {user_id}: {e}", exc_info=True)
        return False

# --- Функции получения информации ---

def get_user_info(db: Database, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает полную информацию о пользователе из таблицы users.
    Возвращает словарь с данными пользователя или None, если пользователь не найден.
    """
    query = "SELECT users_id, first_name, last_name, date, fi, is_admin, is_blocked FROM users WHERE users_id = %s"
    params = (user_id,)

    try:
        # Используем db.execute_query с fetch_results=True
        results: Optional[List[Dict[str, Any]]] = db.execute_query(query, params, fetch_results=True)

        if results and len(results) > 0:
            # Так как users_id уникален, ожидаем одну строку. Берем первый элемент.
            user_data: Dict[str, Any] = results[0]
            logger.debug(f"Получены данные для user_id {user_id}: {user_data}")
            return user_data
        else:
            # Пользователь не найден или результат пустой
            logger.warning(f"Пользователь с ID {user_id} не найден или запрос не вернул данных.")
            return None
    except Exception as e:
        # Логируем ошибку, если db.execute_query вызвал исключение
        logger.error(f"Ошибка при выполнении запроса для получения информации о пользователе {user_id}: {e}", exc_info=True)
        return None

def get_all_users(db: Database, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """
    Возвращает список пользователей в виде словарей.
    По умолчанию только активные (не заблокированные).
    Если include_inactive=True, возвращает всех.
    """
    try:
        if include_inactive:
            # Запрос для получения ВСЕХ пользователей
            query = "SELECT users_id, first_name, last_name, fi, is_blocked, is_admin, date FROM users ORDER BY fi;"
        else:
            # Запрос для получения только АКТИВНЫХ (НЕ ЗАБЛОКИРОВАННЫХ)
            # --- ИСПРАВЛЕНО: используем is_blocked ---
            query = "SELECT users_id, first_name, last_name, fi, is_blocked, is_admin, date FROM users WHERE is_blocked = FALSE ORDER BY fi;"
            # ---------------------------------------
        results: QueryResult = db.execute_query(query, fetch_results=True)
        return results if results else [] # Возвращаем список словарей
    except Exception as e:
        logger.error(f"Ошибка получения списка пользователей (include_inactive={include_inactive}): {e}", exc_info=True)
        return []


def get_user_details_for_management(db: Database, user_id: int) -> Optional[Tuple[str, bool, bool]]:
    """
    Получает ФИ, статус блокировки и статус администратора пользователя для управления.
    Возвращает кортеж (fi, is_blocked, is_admin) или None, если пользователь не найден.
    """
    user_info = get_user_info(db, user_id)  # Эта функция теперь исправлена

    if user_info:
        fi = user_info.get('fi')
        if not fi:
            first = user_info.get('first_name', '')
            last = user_info.get('last_name', '')
            fi = f"{first} {last}".strip() or f"User ID {user_id}"

        is_blocked = user_info.get('is_blocked', False)
        is_admin = user_info.get('is_admin', False)

        logger.debug(
            f"Для управления пользователем {user_id} получены данные: FI='{fi}', Blocked={is_blocked}, Admin={is_admin}")
        return fi, is_blocked, is_admin
    else:
        logger.warning(f"Не найдена информация для пользователя {user_id} в get_user_details_for_management.")
        return None

# --- ДОБАВЛЕНО: Получение ID админов ---
def get_admin_ids(db: Database) -> List[int]:
    """Возвращает список ID всех активных администраторов."""
    query = "SELECT users_id FROM users WHERE is_admin = TRUE AND is_blocked = FALSE;"
    try:
        result: QueryResult = db.execute_query(query, fetch_results=True)
        # Ожидаем список словарей [{'users_id': id1}, {'users_id': id2}, ...]
        admin_ids = [row['users_id'] for row in result] if result else []
        logger.debug(f"Найдены администраторы: {admin_ids}")
        return admin_ids
    except Exception as e:
        logger.error(f"Ошибка при получении ID администраторов: {e}", exc_info=True)
        return []

# --- Функции регистрации ---

# --- ДОБАВЛЕНО: Поиск во временной таблице ---
def find_temp_user(db: Database, user_id: int) -> Optional[Dict[str, Any]]:
     """Ищет пользователя во временной таблице users_temp."""
     query = "SELECT users_id, first_name, last_name, fi, date FROM users_temp WHERE users_id = %s;"
     try:
         result: QueryResult = db.execute_query(query, (user_id,), fetch_results=True)
         return result[0] if result else None
     except Exception as e:
         logger.error(f"Ошибка при поиске временного пользователя {user_id}: {e}", exc_info=True)
         return None

# --- ИЗМЕНЕНО: Принимает full_name (fi) ---
def register_temporary_user(db: Database, user_id: int, first_name: str, last_name: str, full_name: str) -> bool:
    """Сохраняет данные нового пользователя во временную таблицу."""
    date_registered = datetime.now()
    insert_query = """
        INSERT INTO users_temp (users_id, first_name, last_name, date, fi)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (users_id) DO UPDATE SET
          first_name = EXCLUDED.first_name,
          last_name = EXCLUDED.last_name,
          date = EXCLUDED.date,
          fi = EXCLUDED.fi;
    """
    try:
        # --- ИЗМЕНЕНО: Добавлен commit=True ---
        db.execute_query(insert_query, (user_id, first_name, last_name, date_registered, full_name), commit=True)
        logger.info(f"Временная запись для пользователя {user_id} ({full_name}) создана/обновлена.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при временной регистрации пользователя {user_id}: {e}", exc_info=True)
        return False

# --- ИЗМЕНЕНО: Работает со словарями и возвращает данные пользователя ---
def confirm_registration(db: Database, temp_user_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Переносит пользователя из временной таблицы в основную.
    Возвращает (Успех, Словарь с данными пользователя или None).
    """
    # 1. Получить данные из временной таблицы
    temp_user_data = find_temp_user(db, temp_user_id)

    if not temp_user_data:
        logger.warning(f"Не найден временный пользователь с ID {temp_user_id} для подтверждения.")
        return False, None

    # Данные пользователя из временной таблицы (словарь)
    user_id = temp_user_data['users_id']
    first_name = temp_user_data['first_name']
    last_name = temp_user_data['last_name']
    date_registered = temp_user_data['date']
    full_name = temp_user_data['fi']

    # 2. Вставить или обновить данные в основной таблице users
    insert_query = """
        INSERT INTO users (users_id, first_name, last_name, date, fi, is_blocked, is_admin)
        VALUES (%s, %s, %s, %s, %s, FALSE, FALSE)
        ON CONFLICT (users_id) DO UPDATE SET
          first_name = EXCLUDED.first_name,
          last_name = EXCLUDED.last_name,
          date = EXCLUDED.date,
          fi = EXCLUDED.fi,
          is_blocked = FALSE; -- Снимаем блок при подтверждении/обновлении
    """
    conn = None # Для управления транзакцией
    try:
        # Выполняем в рамках одной транзакции
        conn = db.get_connection()

        # Вставляем/Обновляем в users
        with conn.cursor() as cursor:
            cursor.execute(insert_query, (user_id, first_name, last_name, date_registered, full_name))
            logger.info(f"Пользователь {user_id} ({full_name}) записан/обновлен в таблице users.")

        # Удаляем из users_temp
        delete_query = "DELETE FROM users_temp WHERE users_id = %s;"
        with conn.cursor() as cursor:
            cursor.execute(delete_query, (user_id,))
            logger.debug(f"Временная запись для {user_id} удалена.")

        # Коммитим транзакцию
        conn.commit()
        logger.info(f"Регистрация пользователя {user_id} успешно подтверждена.")
        # Возвращаем словарь с данными подтвержденного пользователя
        confirmed_user_data = {
            'users_id': user_id,
            'first_name': first_name,
            'last_name': last_name,
            'fi': full_name,
            'date': date_registered,
            'is_blocked': False,
            'is_admin': False # Новый пользователь не админ по умолчанию
        }
        return True, confirmed_user_data

    except Exception as e:
        logger.error(f"Ошибка при подтверждении регистрации пользователя {temp_user_id}: {e}", exc_info=True)
        if conn:
            try: conn.rollback() # Откатываем транзакцию при ошибке
            except Exception as rb_err: logger.error(f"Ошибка rollback при ошибке подтверждения: {rb_err}")
        return False, None
    finally:
        if conn:
            db.release_connection(conn) # Возвращаем соединение


def decline_registration(db: Database, temp_user_id: int) -> bool:
    """Удаляет пользователя из временной таблицы."""
    delete_query = "DELETE FROM users_temp WHERE users_id = %s;"
    try:
        # --- ИЗМЕНЕНО: Добавлен commit=True ---
        # execute_query теперь может возвращать rowcount, но мы его не используем
        db.execute_query(delete_query, (temp_user_id,), commit=True)
        logger.info(f"Регистрация пользователя {temp_user_id} отклонена, временная запись удалена.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при отклонении регистрации пользователя {temp_user_id}: {e}", exc_info=True)
        return False


# --- ДОБАВЛЕНО: Основная функция регистрации/поиска для /start ---
def find_or_register_user(db: Database, user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Проверяет статус пользователя и инициирует регистрацию при необходимости.
    Возвращает: (is_pending, user_info_dict or None)
    is_pending=True, user_info=None: Пользователя нет, инициирована временная регистрация (или уже ждет).
    is_pending=False, user_info={...}: Пользователь найден в основной таблице users.
    is_pending=False, user_info=None: Произошла ошибка.
    """
    try:
        # 1. Проверяем основную таблицу users
        user_info = get_user_info(db, user_id)
        if user_info:
            logger.debug(f"Пользователь {user_id} найден в основной таблице.")
            return False, user_info # Найден в users

        # 2. Проверяем временную таблицу users_temp
        temp_user_info = find_temp_user(db, user_id)
        if temp_user_info:
            logger.debug(f"Пользователь {user_id} найден во временной таблице (ожидает подтверждения).")
            # Можно переотправить уведомление админам, если нужно
            # notify_admins_for_confirmation(...)
            return True, None # Ожидает подтверждения

        # 3. Пользователя нигде нет - нужно запросить имя (возвращаем is_pending=True)
        # Сам запрос имени и сохранение в temp делается в обработчике команды
        logger.debug(f"Пользователь {user_id} не найден, требуется регистрация.")
        return True, None # Требуется регистрация

    except Exception as e:
        logger.error(f"Ошибка в find_or_register_user для {user_id}: {e}", exc_info=True)
        return False, None # Ошибка

# --- Функции управления пользователями ---

def update_user_block_status(db: Database, user_id: int, block: bool) -> bool:
     """ Обновляет статус блокировки пользователя. """
     query = "UPDATE users SET is_blocked = %s WHERE users_id = %s;"
     try:
         # --- ИЗМЕНЕНО: Добавлен commit=True ---
         db.execute_query(query, (block, user_id), commit=True)
         status = "заблокирован" if block else "разблокирован"
         logger.info(f"Пользователь {user_id} успешно {status}.")
         return True
     except Exception as e:
         logger.error(f"Ошибка при обновлении статуса блокировки для user_id={user_id}: {e}", exc_info=True)
         return False

# НОВАЯ ФУНКЦИЯ:
def update_user_admin_status(db: Database, user_id: int, make_admin: bool) -> bool:
    """
    Обновляет статус администратора пользователя.
    Returns: True в случае успеха, False в случае ошибки.
    """
    query = "UPDATE users SET is_admin = %s WHERE users_id = %s;"
    params = (make_admin, user_id)
    try:
        # Аналогично update_user_block_status
        db.execute_query(query, params, commit=True)
        status_text = "назначен администратором" if make_admin else "лишен прав администратора"
        logger.info(f"Пользователь {user_id} успешно {status_text}.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса администратора для пользователя {user_id} на {make_admin}: {e}", exc_info=True)
        return False


# --- ДОБАВЛЕНО: Обработка блокировки бота пользователем ---
def handle_user_blocked_bot(db: Database, user_id: int):
    """ Помечает пользователя как заблокированного при ошибке 'bot was blocked'. """
    logger.warning(f"Пользователь {user_id} заблокировал бота или деактивирован. Обновляем статус is_blocked=TRUE.")
    # Просто вызываем функцию блокировки
    update_user_block_status(db, user_id, block=True)

# НОВАЯ ФУНКЦИЯ (или если она была, но называлась по-другому)
def is_user_admin(db: Database, user_id: int) -> bool:
    """
    Проверяет, является ли пользователь с указанным user_id администратором.
    Возвращает True, если пользователь админ, иначе False.
    """
    user_data = get_user_info(db, user_id) # Используем существующую get_user_info
    if user_data:
        is_admin_flag = user_data.get('is_admin', False)
        logger.debug(f"Проверка админских прав для user_id {user_id}: {is_admin_flag}")
        return is_admin_flag
    else:
        # Пользователь не найден, значит не админ
        logger.warning(f"Пользователь {user_id} не найден при проверке админских прав.")
        return False