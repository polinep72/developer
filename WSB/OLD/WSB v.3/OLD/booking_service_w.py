# services/booking_service.py
from database import Database, QueryResult
from logger import logger
# --- ИСПРАВЛЕНО: Добавляем Union ---
from typing import List, Tuple, Optional, Dict, Any, Union
# ----------------------------------
from datetime import datetime, timedelta, date, time
import constants as const

# Ожидаемый тип строки бронирования из БД
BookingRow = Dict[str, Any]

# --- Вспомогательные функции ---

# --- ИСПРАВЛЕНО: Используем Union ---
def _format_time(t: Optional[Union[datetime, time]]) -> str:
    """Безопасно форматирует время или возвращает '??:??'."""
    if isinstance(t, datetime):
        return t.strftime('%H:%M')
    elif isinstance(t, time):
        return t.strftime('%H:%M')
    return '??:??'

# --- ИСПРАВЛЕНО: Используем Union ---
def _format_date(d: Optional[Union[datetime, date]]) -> str:
    """Безопасно форматирует дату или возвращает '??-??-????'."""
    if isinstance(d, (datetime, date)):
        return d.strftime('%d-%m-%Y')
    return '??-??-????'

# --- ИСПРАВЛЕНО: Используем Union ---
def format_booking_info(
    equip_name: Optional[str],
    date_val: Optional[date],
    time_start: Optional[Union[datetime, time]],
    time_end: Optional[Union[datetime, time]],
    user_name: Optional[str] = None
) -> str:
    """Вспомогательная функция для форматирования информации о бронировании."""
    equip_name_str = equip_name or "???"
    date_str = _format_date(date_val)
    start_str = _format_time(time_start)
    end_str = _format_time(time_end)

    info_lines = []
    info_lines.append(f"Оборудование: *{equip_name_str}*")
    if user_name:
        info_lines.append(f"Пользователь: {user_name}")
    info_lines.append(f"Дата: {date_str}")
    info_lines.append(f"Время: {start_str} - {end_str}")

    return "\n".join(info_lines)

# --- Функции получения данных ---

def get_user_active_bookings(db: Database, user_id: int) -> List[BookingRow]:
    """ Получает активные бронирования пользователя (словари). """
    query = """
        SELECT b.*, e.name_equip, u.fi as user_fi
        FROM bookings b
        JOIN equipment e ON b.equip_id = e.id
        JOIN users u ON b.user_id = u.users_id
        WHERE b.user_id = %s
          AND b.cancel = FALSE
          AND b.finish is NULL
          AND b.time_end >= now()
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, (user_id,), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_user_active_bookings для user {user_id}: {e}", exc_info=True)
        return []

def get_user_bookings_for_cancel(db: Database, user_id: int) -> List[BookingRow]:
     """ Получает будущие бронирования пользователя для отмены (словари). """
     now_dt = datetime.now()
     query = """
         SELECT b.*, e.name_equip, u.fi as user_fi
         FROM bookings b
         JOIN equipment e ON b.equip_id = e.id
         JOIN users u ON b.user_id = u.users_id
         WHERE b.user_id = %s
           AND b.cancel = FALSE
           AND b.finish  is NULL
           AND b.time_start > %s -- Строго будущие
         ORDER BY b.date, b.time_start;
     """
     try:
         result: QueryResult = db.execute_query(query, (user_id, now_dt), fetch_results=True)
         return result if result else []
     except Exception as e:
        logger.error(f"Ошибка get_user_bookings_for_cancel для user {user_id}: {e}", exc_info=True)
        return []

def get_user_active_bookings_text(db: Database, user_id: int) -> str:
    """Форматирует активные бронирования пользователя в текст."""
    bookings: List[BookingRow] = get_user_active_bookings(db, user_id)
    if not bookings:
        return "У вас нет активных бронирований."

    response_lines = ["*Ваши активные бронирования:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(
            equip_name=booking.get('name_equip'),
            date_val=booking.get('date'),
            time_start=booking.get('time_start'),
            time_end=booking.get('time_end'),
        ))
        response_lines.append("-" * 20)

    if len(response_lines) > 1: response_lines.pop()
    return "\n".join(response_lines)

def get_all_active_bookings_for_admin_keyboard(db: Database) -> List[BookingRow]:
    """ Получает все активные бронирования для клавиатуры админа (/admin_cancel) (словари). """
    query = """
        SELECT b.id, u.fi as user_name, e.name_equip, b.date, b.time_start, b.time_end
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        JOIN equipment e ON b.equip_id = e.id
        WHERE b.cancel = FALSE
          AND b.finish  is NULL
          AND b.time_end >= now()
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, fetch_results=True)
        return result if result else []
    except Exception as e:
         logger.error(f"Ошибка get_all_active_bookings_for_admin_keyboard: {e}", exc_info=True)
         return []

def get_all_active_bookings_text(db: Database) -> str:
    """Форматирует все активные бронирования в текст."""
    bookings: List[BookingRow] = get_all_active_bookings_for_admin_keyboard(db)
    if not bookings:
        return "Нет активных бронирований в системе."

    response_lines = ["*Все активные бронирования:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(
            equip_name=booking.get('name_equip'),
            date_val=booking.get('date'),
            time_start=booking.get('time_start'),
            time_end=booking.get('time_end'),
            user_name=booking.get('user_name')
        ))
        response_lines.append("-" * 20)

    if len(response_lines) > 1: response_lines.pop()
    response = "\n".join(response_lines)

    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (список слишком длинный)"
        logger.warning("Список /allbookings обрезан из-за превышения лимита длины.")
    return response

def get_bookings_by_date(db: Database, selected_date: date) -> List[BookingRow]:
    """ Получает бронирования на указанную дату (словари). """
    query = """
        SELECT b.*, e.name_equip, u.fi as user_fi
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        JOIN equipment e ON b.equip_id = e.id
        WHERE b.date = %s
          AND b.cancel = FALSE
          AND b.finish  is NULL
        ORDER BY e.name_equip, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, (selected_date,), fetch_results=True)
        return result if result else []
    except Exception as e:
         logger.error(f"Ошибка get_bookings_by_date для {selected_date}: {e}", exc_info=True)
         return []

def get_bookings_by_date_text(db: Database, selected_date: date) -> str:
    """Форматирует бронирования на дату в текст."""
    bookings: List[BookingRow] = get_bookings_by_date(db, selected_date)
    date_str = _format_date(selected_date)
    if not bookings:
        return f"Нет бронирований на {date_str}."

    response_lines = [f"*Бронирования на {date_str}:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(
             equip_name=booking.get('name_equip'),
             date_val=booking.get('date'),
             time_start=booking.get('time_start'),
             time_end=booking.get('time_end'),
             user_name=booking.get('user_fi')
        ))
        response_lines.append("-" * 20)

    if len(response_lines) > 1: response_lines.pop()
    response = "\n".join(response_lines)

    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (список слишком длинный)"
        logger.warning(f"Список броней на дату {date_str} обрезан.")
    return response

def get_bookings_by_workspace(db: Database, equipment_id: int) -> List[BookingRow]:
     """ Получает будущие бронирования для оборудования (словари). """
     now_dt = datetime.now()
     query = """
         SELECT b.*, e.name_equip, u.fi as user_fi
         FROM bookings b
         JOIN users u ON b.user_id = u.users_id
         JOIN equipment e ON b.equip_id = e.id
         WHERE b.equip_id = %s
           AND b.cancel = FALSE
           AND b.finish  is NULL
           AND b.time_end > %s -- Будущие или текущие
         ORDER BY b.date, b.time_start;
     """
     try:
         result: QueryResult = db.execute_query(query, (equipment_id, now_dt), fetch_results=True)
         return result if result else []
     except Exception as e:
          logger.error(f"Ошибка get_bookings_by_workspace для equip_id {equipment_id}: {e}", exc_info=True)
          return []

def get_bookings_by_workspace_text(db: Database, equipment_id: int, equipment_name: str) -> str:
     """Форматирует будущие бронирования для оборудования в текст."""
     bookings: List[BookingRow] = get_bookings_by_workspace(db, equipment_id)
     if not bookings:
         return f"Для оборудования '{equipment_name}' нет активных или будущих бронирований."

     response_lines = [f"*Бронирования для '{equipment_name}':*"]
     for booking in bookings:
         response_lines.append(format_booking_info(
             equip_name=equipment_name,
             date_val=booking.get('date'),
             time_start=booking.get('time_start'),
             time_end=booking.get('time_end'),
             user_name=booking.get('user_fi')
         ))
         response_lines.append("-" * 20)

     if len(response_lines) > 1: response_lines.pop()
     response = "\n".join(response_lines)

     if len(response) > const.MAX_MESSAGE_LENGTH:
         response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (список слишком длинный)"
         logger.warning(f"Список броней для оборудования {equipment_name} обрезан.")
     return response

def find_booking_by_id(db: Database, booking_id: int) -> Optional[BookingRow]:
     """ Ищет бронирование по ID. Возвращает словарь или None. """
     query = """
         SELECT b.*, e.name_equip as equipment_name, u.fi as user_fi
         FROM bookings b
         JOIN equipment e ON b.equip_id = e.id
         JOIN users u ON b.user_id = u.users_id
         WHERE b.id = %s;
     """
     try:
         result: QueryResult = db.execute_query(query, (booking_id,), fetch_results=True)
         return result[0] if result else None
     except Exception as e:
          logger.error(f"Ошибка find_booking_by_id для ID {booking_id}: {e}", exc_info=True)
          return None

def find_next_booking(db: Database, equipment_id: int, after_time: datetime) -> Optional[BookingRow]:
    """ Ищет следующее бронирование для оборудования после времени (словарь). """
    query = """
        SELECT id, time_start
        FROM bookings
        WHERE equip_id = %s
          AND cancel = FALSE
          AND finish  is NULL
          AND time_start > %s
        ORDER BY time_start ASC
        LIMIT 1;
    """
    params = (equipment_id, after_time)
    log_msg = f"Поиск следующей брони для equip={equipment_id} после {after_time}. "
    try:
        result: QueryResult = db.execute_query(query, params, fetch_results=True)
        if result:
             log_msg += f"Найдена бронь ID={result[0]['id']} в {result[0]['time_start']}"
             logger.debug(log_msg)
             return result[0]
        else:
             log_msg += "Не найдено."
             logger.debug(log_msg)
             return None
    except Exception as e:
         logger.error(f"Ошибка find_next_booking для equip_id {equipment_id}: {e}", exc_info=True)
         return None

def get_user_current_bookings(db: Database, user_id: int) -> List[BookingRow]:
     """ Находит текущие бронирования пользователя (словари). """
     now_dt = datetime.now()
     query = """
         SELECT b.*, e.name_equip, u.fi as user_fi
         FROM bookings b
         JOIN equipment e ON b.equip_id = e.id
         JOIN users u ON b.user_id = u.users_id
         WHERE b.user_id = %s
           AND b.cancel = FALSE
           AND b.finish  is NULL
           AND b.time_start <= %s
           AND b.time_end > %s
         ORDER BY b.date, b.time_start;
     """
     try:
         result: QueryResult = db.execute_query(query, (user_id, now_dt, now_dt), fetch_results=True)
         logger.debug(f"Поиск текущих броней для user {user_id}. Найдено: {len(result) if result else 0}")
         return result if result else []
     except Exception as e:
          logger.error(f"Ошибка get_user_current_bookings для user {user_id}: {e}", exc_info=True)
          return []


# --- Функции изменения данных ---

def check_booking_conflict(db: Database, equipment_id: int, start_dt: datetime, end_dt: datetime, exclude_booking_id: Optional[int] = None) -> List[BookingRow]:
    """ Проверяет пересечение времени. Возвращает список конфликтующих броней (словари). """
    query = """
        SELECT b.id, b.time_start, b.time_end, u.fi as user_fi
        FROM bookings b JOIN users u ON b.user_id = u.users_id
        WHERE b.equip_id = %s AND b.cancel = FALSE AND b.finish  is NULL
          AND b.time_end > %s AND b.time_start < %s
    """
    params = [equipment_id, start_dt, end_dt]
    if exclude_booking_id:
        query += " AND b.id != %s"
        params.append(exclude_booking_id)
    query += ";"
    try:
        conflicts: QueryResult = db.execute_query(query, tuple(params), fetch_results=True)
        logger.debug(f"Проверка конфликтов для equip={equipment_id}, {start_dt}-{end_dt}, exclude={exclude_booking_id}. Найдено: {len(conflicts) if conflicts else 0}")
        return conflicts if conflicts else []
    except Exception as e:
         logger.error(f"Ошибка check_booking_conflict: {e}", exc_info=True)
         return [{'id': -1, 'error': 'check_failed'}]

def create_booking(db: Database, user_id: int, equipment_id: int, selected_date_str: str, start_time_str: str, duration_str: str) -> Tuple[bool, str, Optional[int]]:
    """ Создает новое бронирование. Возвращает (Успех, Сообщение-константа, ID брони или None). """
    try:
        selected_date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
        start_datetime = datetime.combine(selected_date_obj, start_time_obj)

        hours, minutes = map(int, duration_str.split(':'))
        if hours < 0 or minutes < 0 or (hours == 0 and minutes == 0) or (hours * 60 + minutes) % const.BOOKING_TIME_STEP_MINUTES != 0:
             raise ValueError(f"Некорректная длительность или не кратна шагу {const.BOOKING_TIME_STEP_MINUTES} мин.")
        duration_timedelta = timedelta(hours=hours, minutes=minutes)

        if duration_timedelta > timedelta(hours=const.MAX_BOOKING_DURATION_HOURS):
            logger.warning(f"Попытка бронирования user {user_id} превысила макс. длительность ({duration_str})")
            return False, const.MSG_BOOKING_FAIL_LIMIT_EXCEEDED, None

        end_datetime = start_datetime + duration_timedelta

        if start_datetime < datetime.now() - timedelta(minutes=1):
             logger.warning(f"Попытка бронирования user {user_id} в прошлом ({start_datetime})")
             return False, const.MSG_BOOKING_FAIL_TIME_IN_PAST, None

    except ValueError as e:
        logger.warning(f"Ошибка парсинга данных бронирования user {user_id}: {e}")
        return False, const.MSG_BOOKING_FAIL_INVALID_TIME, None

    try:
        conflicts = check_booking_conflict(db, equipment_id, start_datetime, end_datetime)
        if conflicts:
            conflict_booking = conflicts[0]
            c_start = _format_time(conflict_booking.get('time_start'))
            c_end = _format_time(conflict_booking.get('time_end'))
            c_user = conflict_booking.get('user_fi', 'Другой пользователь')
            msg = const.MSG_BOOKING_FAIL_OVERLAP + f"\n(Занято: {c_user}, {c_start} - {c_end})"
            logger.warning(f"Конфликт при бронировании user {user_id}: equip={equipment_id}, время={start_datetime}-{end_datetime}. Занято ID={conflict_booking.get('id')}")
            return False, msg, None

        time_interval = f"{start_datetime.strftime('%H:%M')}-{end_datetime.strftime('%H:%M')}"
        duration_in_db = duration_timedelta.total_seconds() / 3600.0
        data_booking_ts = datetime.now()

        insert_query = """
            INSERT INTO bookings
            (user_id, equip_id, date, time_start, time_end, time_interval, duration, cancel, finish, data_booking)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, %s)
            RETURNING id;
            """
        params = (user_id, equipment_id, selected_date_obj, start_datetime, end_datetime, time_interval, duration_in_db, data_booking_ts)

        result: QueryResult = db.execute_query(insert_query, params, fetch_results=True, commit=True)

        if result and 'id' in result[0]:
            new_id = result[0]['id']
            logger.info(f"Создана бронь ID {new_id} пользователем {user_id} для equip {equipment_id} на {selected_date_str} {time_interval}")
            return True, const.MSG_BOOKING_SUCCESS, new_id
        else:
            logger.error(f"INSERT бронирования для user {user_id} не вернул ID.")
            return False, const.MSG_BOOKING_FAIL_GENERAL, None

    except Exception as e:
        logger.error(f"Ошибка при создании бронирования user {user_id}: {e}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL, None


def cancel_booking(db: Database, booking_id: int, user_id: Optional[int] = None, is_admin_cancel: bool = False) -> Tuple[bool, str, Optional[int]]:
    """ Отменяет бронирование. Возвращает (Успех, Сообщение-константа, User ID владельца). """
    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info:
        return False, const.MSG_CANCEL_FAIL_NOT_FOUND, None

    b_user_id = booking_info.get('user_id')
    b_start = booking_info.get('time_start')
    b_cancel = booking_info.get('cancel', False)
    b_finish = booking_info.get('finish', False)

    if b_cancel: return False, "Бронирование уже отменено.", b_user_id
    if b_finish: return False, "Бронирование уже завершено.", b_user_id

    if not is_admin_cancel:
        if user_id is None:
            logger.error(f"Попытка отмены брони {booking_id} без user_id.")
            return False, const.MSG_ERROR_GENERAL, b_user_id
        if b_user_id != user_id:
            logger.warning(f"Пользователь {user_id} пытался отменить чужую бронь {booking_id} (владелец {b_user_id}).")
            return False, "Это не ваше бронирование.", b_user_id
        now = datetime.now()
        if isinstance(b_start, datetime) and b_start <= now:
            logger.warning(f"Пользователь {user_id} пытался отменить уже начавшуюся бронь {booking_id}.")
            return False, const.MSG_CANCEL_FAIL_TOO_LATE, b_user_id

    query = "UPDATE bookings SET cancel = TRUE WHERE id = %s AND cancel = FALSE AND finish  is NULL;"
    try:
        db.execute_query(query, (booking_id,), commit=True)
        initiator = f"администратором {user_id}" if is_admin_cancel and user_id else f"пользователем {user_id}" if user_id else "системой"
        logger.info(f"Бронь {booking_id} (пользователь {b_user_id}) отменена {initiator}.")
        return True, const.MSG_BOOKING_CANCELLED, b_user_id
    except Exception as e:
        logger.error(f"Ошибка при отмене бронирования {booking_id}: {e}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL, b_user_id


def finish_booking(db: Database, booking_id: int, user_id: int) -> Tuple[bool, str]:
    """ Завершает бронирование. Возвращает (Успех, Сообщение). """
    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_FINISH_FAIL_NOT_ACTIVE

    b_user_id = booking_info.get('user_id');
    b_cancel = booking_info.get('cancel', False);
    b_finish = booking_info.get('finish');
    equip_name = booking_info.get('equipment_name', '???')

    if b_user_id != user_id: logger.warning(
        f"{user_id} пытался finish чужую {booking_id}."); return False, "Это не ваше бронирование."
    if b_cancel: return False, "Бронирование было отменено."
    if b_finish is not None: return False, "Бронирование уже завершено."

    now_dt = datetime.now();
    time_start = booking_info.get('time_start')
    if not (isinstance(time_start, datetime) and time_start <= now_dt): logger.warning(
        f"Попытка завершить {booking_id} (еще не началась?)"); return False, const.MSG_FINISH_FAIL_NOT_ACTIVE

    finish_time = datetime.now()  # Получаем текущее время для записи

    # --- ИСПРАВЛЕНО: Устанавливаем finish = finish_time ---
    query = "UPDATE bookings SET finish = %s, time_end = %s WHERE id = %s AND cancel = FALSE AND finish IS NULL;"
    params = (finish_time, finish_time, booking_id)  # Передаем finish_time в оба поля
    # ----------------------------------------------------
    try:
        db.execute_query(query, params, commit=True)
        time_str = finish_time.strftime('%H:%M:%S')
        logger.info(f"{user_id} завершил {booking_id} ({equip_name}) в {finish_time.strftime('%Y-%m-%d %H:%M')}.")
        msg = f"{const.MSG_BOOKING_FINISHED}\nОборудование: *{equip_name}*\nВремя завершения: {time_str}"
        return True, msg
    except Exception as e:
        logger.error(f"Ошибка при завершении бронирования {booking_id}: {e}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL


def extend_booking(db: Database, booking_id: int, user_id: int, extension_str: str) -> Tuple[bool, str]:
    """ Продлевает бронирование. Возвращает (Успех, Сообщение). """
    try:
        if not extension_str or ':' not in extension_str: raise ValueError("Некорректный формат времени продления HH:MM")
        h, m = map(int, extension_str.split(':'))
        if h < 0 or m < 0 or (h == 0 and m == 0) or (h * 60 + m) % const.BOOKING_TIME_STEP_MINUTES != 0:
            raise ValueError(f"Некорректная длительность продления или не кратна шагу {const.BOOKING_TIME_STEP_MINUTES} мин.")
        extend_delta = timedelta(hours=h, minutes=m)
    except ValueError as e:
        logger.warning(f"Ошибка парсинга времени продления '{extension_str}': {e}")
        return False, f"Некорректный формат времени: {e}"

    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_EXTEND_FAIL_NOT_ACTIVE

    b_user_id = booking_info.get('user_id'); equip_id = booking_info.get('equip_id'); cur_end = booking_info.get('time_end')
    time_start = booking_info.get('time_start'); b_cancel = booking_info.get('cancel', False); b_finish = booking_info.get('finish', False)
    equip_name = booking_info.get('equipment_name', '???')

    if b_user_id != user_id: logger.warning(f"{user_id} пытался продлить чужую {booking_id}."); return False, "Это не ваше бронирование."
    if b_cancel: return False, "Бронирование отменено."
    if b_finish: return False, "Бронирование завершено."
    if not isinstance(cur_end, datetime) or not isinstance(time_start, datetime): logger.error(f"{booking_id}: некорр. время."); return False, const.MSG_ERROR_GENERAL
    if cur_end <= datetime.now(): logger.warning(f"{user_id} продляет закончившуюся {booking_id}"); return False, "Бронирование уже завершилось."

    new_end_dt = cur_end + extend_delta
    total_duration = new_end_dt - time_start
    if total_duration > timedelta(hours=const.MAX_BOOKING_DURATION_HOURS): logger.warning(f"{booking_id}: превышение лимита при продлении."); return False, const.MSG_BOOKING_FAIL_LIMIT_EXCEEDED

    try:
        conflicts = check_booking_conflict(db, equip_id, cur_end, new_end_dt, exclude_booking_id=booking_id)
        if conflicts:
            conflict = conflicts[0]; c_s = _format_time(conflict.get('time_start')); c_e = _format_time(conflict.get('time_end')); c_u = conflict.get('user_fi', '???')
            msg = const.MSG_BOOKING_FAIL_OVERLAP + f"\n(Занято: {c_u}, {c_s} - {c_e})"
            logger.warning(f"Конфликт продления {booking_id} user {user_id}. Занято ID={conflict.get('id')}")
            return False, msg
    except Exception as e_conflict: logger.error(f"{booking_id}: Ошибка проверки конфликта: {e_conflict}"); return False, "Ошибка проверки времени."

    new_time_interval = f"{time_start.strftime('%H:%M')}-{new_end_dt.strftime('%H:%M')}"
    new_total_duration_hours = total_duration.total_seconds() / 3600.0

    query = """
        UPDATE bookings SET time_end = %(new_end)s, time_interval = %(interval)s,
               duration = %(duration)s, extension = COALESCE(extension, interval '0 hours') + %(ext_delta)s
        WHERE id = %(b_id)s AND cancel = FALSE AND finish  is NULL;
    """
    params = {'new_end': new_end_dt, 'interval': new_time_interval, 'duration': new_total_duration_hours, 'ext_delta': extend_delta, 'b_id': booking_id}

    try:
        db.execute_query(query, params, commit=True)
        new_end_str = _format_time(new_end_dt)
        logger.info(f"{user_id} продлил {booking_id} ({equip_name}) на {extension_str}. New end: {new_end_dt.strftime('%Y-%m-%d %H:%M')}")
        msg = f"{const.MSG_BOOKING_EXTENDED}\nОборудование: *{equip_name}*\nНовое время окончания: {new_end_str}"
        return True, msg
    except Exception as e: logger.error(f"Ошибка UPDATE продления {booking_id}: {e}", exc_info=True); return False, const.MSG_ERROR_GENERAL


def confirm_start_booking(db: Database, booking_id: int, user_id: int) -> bool:
     """ "Подтверждает" актуальность брони. Возвращает True, если бронь активна и принадлежит пользователю. """
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
     if booking_info:
          b_user_id = booking_info.get('user_id'); b_cancel = booking_info.get('cancel', False); b_finish = booking_info.get('finish', False)
          if b_user_id == user_id and not b_cancel and not b_finish:
               # Можно добавить UPDATE bookings SET confirmed = TRUE, если нужно
               logger.info(f"User {user_id} подтвердил актуальность брони {booking_id}.")
               return True
          else: logger.warning(f"Попытка подтвердить неактивную/чужую {booking_id} user {user_id}.")
     else: logger.warning(f"Не найдена бронь {booking_id} для подтверждения user {user_id}.")
     return False

def auto_cancel_unconfirmed_booking(db: Database, booking_id: int) -> Tuple[bool, Optional[int], Optional[str]]:
     """ Автоотмена неподтвержденной брони. Возвращает (Была ли отменена, User ID, Equip Name). """
     logger.debug(f"Запуск автоотмены для брони {booking_id}...")
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
     if booking_info:
          b_user_id = booking_info.get('user_id'); equip_name = booking_info.get('equipment_name'); b_cancel = booking_info.get('cancel', False); b_finish = booking_info.get('finish', False)
          # confirmed = booking_info.get('confirmed', False) # Если будет поле confirmed

          if not b_cancel and not b_finish: # and not confirmed:
               success, _, _ = cancel_booking(db, booking_id, user_id=None, is_admin_cancel=True)
               if success: logger.info(f"Бронь {booking_id} успешно автоматически отменена."); return True, b_user_id, equip_name
               else: logger.error(f"Не удалось автоматически отменить бронь {booking_id}."); return False, b_user_id, equip_name
          else: logger.debug(f"Автоотмена для брони {booking_id} не требуется (статус: cancel={b_cancel}, finish={b_finish})."); return False, b_user_id, equip_name
     else: logger.warning(f"Не найдена бронь {booking_id} для выполнения автоотмены."); return False, None, None

def get_bookings_for_notification_schedule(db: Database) -> List[Tuple[int, int, int, datetime, datetime, str]]:
     """ Получает брони для планировщика уведомлений. Возвращает список кортежей. """
     threshold_start = datetime.now() - timedelta(days=1); now = datetime.now()
     query = """SELECT b.id, b.user_id, b.equip_id, b.time_start, b.time_end, e.name_equip FROM bookings b JOIN equipment e ON b.equip_id = e.id WHERE b.cancel = FALSE AND b.finish is NULL AND b.time_start >= %s AND b.time_end >= %s ORDER BY b.id;"""
     try:
         results_dict: QueryResult = db.execute_query(query, (threshold_start, now), fetch_results=True)
         results_tuple: List[Tuple[int, int, int, datetime, datetime, str]] = []
         if results_dict:
             for row in results_dict:
                 # Проверяем наличие ключей перед добавлением в кортеж
                 if all(k in row for k in ('id', 'user_id', 'equip_id', 'time_start', 'time_end', 'name_equip')):
                     results_tuple.append((
                         row['id'], row['user_id'], row['equip_id'],
                         row['time_start'], row['time_end'], row['name_equip']
                     ))
                 else:
                      logger.warning(f"Неполные данные в строке при получении броней для уведомлений: {row}")
         logger.debug(f"Найдено {len(results_tuple)} броней для планирования уведомлений.")
         return results_tuple
     except Exception as e:
          logger.error(f"Ошибка get_bookings_for_notification_schedule: {e}", exc_info=True)
          return []