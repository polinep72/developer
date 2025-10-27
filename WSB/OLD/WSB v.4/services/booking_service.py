# --- START OF FILE services/booking_service.py ---

# services/booking_service.py
from database import Database, QueryResult
from logger import logger
from typing import List, Tuple, Optional, Dict, Any, Union
from datetime import datetime, timedelta, date, time
import constants as const

# Ожидаемый тип строки бронирования из БД
BookingRow = Dict[str, Any]

# --- Вспомогательные функции ---

def _format_time(t: Optional[Union[datetime, time]]) -> str:
    """Безопасно форматирует время или возвращает '??:??'."""
    if isinstance(t, datetime): return t.strftime('%H:%M')
    elif isinstance(t, time): return t.strftime('%H:%M')
    return '??:??'

def _format_date(d: Optional[Union[datetime, date]]) -> str:
    """Безопасно форматирует дату или возвращает '??-??-????'."""
    if isinstance(d, (datetime, date)): return d.strftime('%d-%m-%Y')
    return '??-??-????'

def format_booking_info(
    equip_name: Optional[str], date_val: Optional[date],
    time_start: Optional[Union[datetime, time]], time_end: Optional[Union[datetime, time]],
    user_name: Optional[str] = None
) -> str:
    """Вспомогательная функция для форматирования информации о бронировании."""
    equip_name_str = equip_name or "???"
    date_str = _format_date(date_val)
    start_str = _format_time(time_start)
    end_str = _format_time(time_end)
    info_lines = [f"Оборудование: *{equip_name_str}*"]
    if user_name: info_lines.append(f"Пользователь: {user_name}")
    info_lines.append(f"Дата: {date_str}")
    info_lines.append(f"Время: {start_str} - {end_str}")
    return "\n".join(info_lines)

# --- Функции получения данных ---

def get_user_active_bookings(db: Database, user_id: int) -> List[BookingRow]:
    """ Получает активные бронирования пользователя (словари). """
    query = """
        SELECT b.*, e.name_equip, u.fi as user_fi FROM bookings b
        JOIN equipment e ON b.equip_id = e.id JOIN users u ON b.user_id = u.users_id
        WHERE b.user_id = %s AND b.cancel = FALSE AND b.finish IS NULL AND b.time_end >= now()
        ORDER BY b.date, b.time_start;"""
    try:
        result: QueryResult = db.execute_query(query, (user_id,), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_user_active_bookings({user_id}): {e}", exc_info=True)
        return []

def get_user_bookings_for_cancel(db: Database, user_id: int) -> List[BookingRow]:
     """ Получает будущие бронирования пользователя для отмены (словари). """
     now_dt = datetime.now()
     query = """
         SELECT b.*, e.name_equip, u.fi as user_fi FROM bookings b
         JOIN equipment e ON b.equip_id = e.id JOIN users u ON b.user_id = u.users_id
         WHERE b.user_id = %s AND b.cancel = FALSE AND b.finish IS NULL AND b.time_start > %s
         ORDER BY b.date, b.time_start;"""
     try:
         result: QueryResult = db.execute_query(query, (user_id, now_dt), fetch_results=True)
         return result if result else []
     except Exception as e:
         logger.error(f"Ошибка get_user_bookings_for_cancel({user_id}): {e}", exc_info=True)
         return []

def get_user_active_bookings_text(db: Database, user_id: int) -> str:
    """Форматирует активные бронирования пользователя в текст."""
    bookings: List[BookingRow] = get_user_active_bookings(db, user_id)
    if not bookings: return "У вас нет активных бронирований."
    response_lines = ["*Ваши активные бронирования:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(booking.get('name_equip'), booking.get('date'), booking.get('time_start'), booking.get('time_end')))
        response_lines.append("-" * 20)
    if len(response_lines) > 1:
        response_lines.pop()
    return "\n".join(response_lines)

def get_all_active_bookings_for_admin_keyboard(db: Database) -> List[BookingRow]:
    """ Получает все активные бронирования для клавиатуры админа (/admin_cancel). """
    query = """
        SELECT b.id, u.fi as user_name, e.name_equip as equipment_name, b.date, b.time_start, b.time_end FROM bookings b
        JOIN users u ON b.user_id = u.users_id JOIN equipment e ON b.equip_id = e.id
        WHERE b.cancel = FALSE AND b.finish IS NULL AND b.time_end >= now()
        ORDER BY b.date, b.time_start;"""
    try:
        result: QueryResult = db.execute_query(query, fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_all_active_bookings_for_admin_keyboard: {e}", exc_info=True)
        return []

def get_all_active_bookings_text(db: Database) -> str:
    """Форматирует все активные бронирования в текст."""
    bookings: List[BookingRow] = get_all_active_bookings_for_admin_keyboard(db)
    if not bookings: return "Нет активных бронирований в системе."
    response_lines = ["*Все активные бронирования:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(booking.get('equipment_name'), booking.get('date'), booking.get('time_start'), booking.get('time_end'), booking.get('user_name')))
        response_lines.append("-" * 20)
    if len(response_lines) > 1:
        response_lines.pop()
    response = "\n".join(response_lines)
    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (список слишком длинный)"
        logger.warning("Список /allbookings обрезан.")
    return response

# --- START OF MODIFIED FUNCTION get_bookings_by_date ---
def get_bookings_by_date(db: Database, selected_date: date) -> List[BookingRow]:
    """
    Получает бронирования на указанную дату.
    Если дата сегодняшняя, возвращает только те, что еще не закончились.
    """
    today = datetime.now().date()
    is_today = (selected_date == today)

    base_query = """
        SELECT b.*, e.name_equip, u.fi as user_fi FROM bookings b
        JOIN users u ON b.user_id = u.users_id JOIN equipment e ON b.equip_id = e.id
        WHERE b.date = %s AND b.cancel = FALSE AND b.finish IS NULL
    """
    params: List[Any] = [selected_date]

    if is_today:
        logger.debug(f"Запрос бронирований на сегодня ({selected_date}), фильтруем по времени окончания.")
        base_query += " AND b.time_end >= %s"
        params.append(datetime.now()) # Добавляем текущее время для сравнения
    else:
        logger.debug(f"Запрос бронирований на будущую/прошлую дату ({selected_date}), показываем все.")

    final_query = base_query + " ORDER BY e.id, b.time_start;"

    try:
        result: QueryResult = db.execute_query(final_query, tuple(params), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_bookings_by_date({selected_date}): {e}", exc_info=True)
        return []
# --- END OF MODIFIED FUNCTION get_bookings_by_date ---

def get_bookings_by_date_text(db: Database, selected_date: date) -> str:
    """Форматирует бронирования на дату в текст."""
    # Эта функция теперь использует обновленную get_bookings_by_date
    bookings: List[BookingRow] = get_bookings_by_date(db, selected_date)
    date_str = _format_date(selected_date)
    if not bookings:
        # Уточняем сообщение для сегодняшнего дня
        if selected_date == datetime.now().date():
             return f"Нет предстоящих бронирований на сегодня ({date_str})."
        else:
             return f"Нет бронирований на {date_str}."

    response_lines = [f"*Бронирования на {date_str}:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(booking.get('name_equip'), booking.get('date'), booking.get('time_start'), booking.get('time_end'), booking.get('user_fi')))
        response_lines.append("-" * 20)
    if len(response_lines) > 1:
        response_lines.pop()
    response = "\n".join(response_lines)
    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (слишком длинный)"
        logger.warning(f"Список броней {date_str} обрезан.")
    return response

def get_bookings_by_workspace(db: Database, equipment_id: int) -> List[BookingRow]:
     """ Получает будущие бронирования для оборудования. """
     now_dt = datetime.now()
     query = """
         SELECT b.*, e.name_equip, u.fi as user_fi FROM bookings b
         JOIN users u ON b.user_id = u.users_id JOIN equipment e ON b.equip_id = e.id
         WHERE b.equip_id = %s AND b.cancel = FALSE AND b.finish IS NULL AND b.time_end > %s
         ORDER BY b.date, b.time_start;"""
     try:
         result: QueryResult = db.execute_query(query, (equipment_id, now_dt), fetch_results=True)
         return result if result else []
     except Exception as e:
         logger.error(f"Ошибка get_bookings_by_workspace({equipment_id}): {e}", exc_info=True)
         return []

def get_bookings_by_workspace_text(db: Database, equipment_id: int, equipment_name: str) -> str:
     """Форматирует будущие бронирования для оборудования."""
     bookings: List[BookingRow] = get_bookings_by_workspace(db, equipment_id)
     if not bookings: return f"Для '{equipment_name}' нет предстоящих броней." # Уточнено
     response_lines = [f"*Предстоящие бронирования для '{equipment_name}':*"] # Уточнено
     for booking in bookings:
         response_lines.append(format_booking_info(equipment_name, booking.get('date'), booking.get('time_start'), booking.get('time_end'), booking.get('user_fi')))
         response_lines.append("-" * 20)
     if len(response_lines) > 1:
         response_lines.pop()
     response = "\n".join(response_lines)
     if len(response) > const.MAX_MESSAGE_LENGTH:
         response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (слишком длинный)"
         logger.warning(f"Список {equipment_name} обрезан.")
     return response

def find_booking_by_id(db: Database, booking_id: int) -> Optional[BookingRow]:
    """Ищет бронирование по ID."""
    query = """
        SELECT b.*, e.name_equip as equipment_name, u.fi as user_fi
        FROM bookings b
        JOIN equipment e ON b.equip_id = e.id
        JOIN users u ON b.user_id = u.users_id
        WHERE b.id = %s;"""
    try:
        result: QueryResult = db.execute_query(query, (booking_id,), fetch_results=True)
        if result:
            booking = result[0]
            logger.debug(f"Бронь {booking_id}: date={booking.get('date')}, type={type(booking.get('date'))}, "
                        f"time_end={booking.get('time_end')}, type={type(booking.get('time_end'))}, "
                        f"equip_id={booking.get('equip_id')}")
            return booking
        return None
    except Exception as e:
        logger.error(f"Ошибка find_booking_by_id({booking_id}): {e}", exc_info=True)
        return None

def find_next_booking(db: Database, equipment_id: int, after_time: datetime) -> Optional[BookingRow]:
    """ Ищет следующее бронирование после времени. """
    query = "SELECT id, time_start FROM bookings WHERE equip_id = %s AND cancel = FALSE AND finish IS NULL AND time_start > %s ORDER BY time_start ASC LIMIT 1;"
    params = (equipment_id, after_time); log_msg = f"Поиск след. брони {equipment_id} после {after_time}. "
    try:
        if after_time.tzinfo is None:
            logger.warning("find_next_booking вызван с naive after_time")
        result: QueryResult = db.execute_query(query, params, fetch_results=True)
        if result:
             next_booking_time = result[0]['time_start']
             log_msg += f"Найдена ID={result[0]['id']} в {next_booking_time}"
             logger.debug(log_msg)
             return result[0]
        else:
             log_msg += "Не найдено."
             logger.debug(log_msg)
             return None
    except Exception as e:
        logger.error(f"Ошибка find_next_booking({equipment_id}): {e}", exc_info=True)
        return None

def get_user_current_bookings(db: Database, user_id: int) -> List[BookingRow]:
     """ Находит текущие бронирования пользователя. """
     now_dt = datetime.now()
     query = """
         SELECT b.*, e.name_equip, u.fi as user_fi FROM bookings b
         JOIN equipment e ON b.equip_id = e.id JOIN users u ON b.user_id = u.users_id
         WHERE b.user_id = %s AND b.cancel = FALSE AND b.finish IS NULL AND b.time_start <= %s AND b.time_end > %s
         ORDER BY b.date, b.time_start;"""
     try:
         result: QueryResult = db.execute_query(query, (user_id, now_dt, now_dt), fetch_results=True)
         logger.debug(f"Поиск тек. броней {user_id}. Найдено: {len(result) if result else 0}")
         return result if result else []
     except Exception as e:
         logger.error(f"Ошибка get_user_current_bookings({user_id}): {e}", exc_info=True)
         return []

def calculate_available_slots(
    db: Database,
    equipment_id: int,
    selected_date: date
) -> List[Tuple[time, time]]:
    """
    Вычисляет доступные временные слоты для бронирования
    на выбранную дату для конкретного оборудования.
    """
    logger.debug(f"Расчет слотов для equip={equipment_id} на {selected_date}")
    # Используем обновленную get_bookings_by_date, которая уже фильтрует по времени для сегодня
    equipment_bookings = get_bookings_by_date(db, selected_date)
    # Фильтруем дополнительно по ID оборудования (на случай если get_bookings_by_date вернула для всех)
    equipment_bookings = [
        b for b in equipment_bookings
        if b.get('equip_id') == equipment_id
           and isinstance(b.get('time_start'), datetime)
           and isinstance(b.get('time_end'), datetime)
    ]
    sorted_bookings = sorted(equipment_bookings, key=lambda b: b['time_start'])

    available_slots: List[Tuple[time, time]] = []
    work_start_time = const.WORKING_HOURS_START
    work_end_time = const.WORKING_HOURS_END
    min_step_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    if isinstance(work_start_time, datetime): work_start_time = work_start_time.time()
    if isinstance(work_end_time, datetime): work_end_time = work_end_time.time()

    today = datetime.now().date()
    is_today = (selected_date == today)
    now_dt = datetime.now()
    earliest_start_dt_today = now_dt

    if is_today:
        minutes_to_add = const.BOOKING_TIME_STEP_MINUTES - (now_dt.minute % const.BOOKING_TIME_STEP_MINUTES) \
                         if now_dt.minute % const.BOOKING_TIME_STEP_MINUTES != 0 else 0
        earliest_start_dt_today = (now_dt + timedelta(minutes=minutes_to_add)).replace(second=0, microsecond=0)
        logger.debug(f"Сегодняшний день. Самое раннее начало: {earliest_start_dt_today.time()}")

    effective_start_dt = datetime.combine(selected_date, work_start_time)
    if is_today:
        effective_start_dt = max(effective_start_dt, earliest_start_dt_today)

    current_time_dt = effective_start_dt
    work_end_dt = datetime.combine(selected_date, work_end_time)

    logger.debug(f"Эффективное время начала поиска слотов: {current_time_dt}")
    logger.debug(f"Рабочее время: {work_start_time} - {work_end_time}")
    logger.debug(f"Найденные брони ({len(sorted_bookings)}): {[(b.get('id'), b.get('time_start'), b.get('time_end')) for b in sorted_bookings]}")

    for booking in sorted_bookings:
        booking_start_dt = booking['time_start'].replace(tzinfo=None)
        booking_end_dt = booking['time_end'].replace(tzinfo=None)
        # Пропускаем брони, которые полностью вне выбранной даты (на всякий случай)
        if booking_end_dt.date() < selected_date or booking_start_dt.date() > selected_date: continue
        # Обрезаем время начала/конца, если бронь пересекает полночь
        if booking_start_dt.date() < selected_date: booking_start_dt = datetime.combine(selected_date, time(0, 0))
        if booking_end_dt.date() > selected_date: booking_end_dt = datetime.combine(selected_date, time(23, 59, 59))

        if booking_start_dt > current_time_dt:
            potential_slot_start_dt = current_time_dt
            potential_slot_end_dt = booking_start_dt

            if potential_slot_end_dt > potential_slot_start_dt and \
               (potential_slot_end_dt - potential_slot_start_dt) >= min_step_delta:
                slot_start_time = max(potential_slot_start_dt.time(), work_start_time)
                slot_end_time = min(potential_slot_end_dt.time(), work_end_time)
                if datetime.combine(selected_date, slot_end_time) > datetime.combine(selected_date, slot_start_time) and \
                   (datetime.combine(selected_date, slot_end_time) - datetime.combine(selected_date, slot_start_time)) >= min_step_delta:
                    available_slots.append((slot_start_time, slot_end_time))
                    logger.debug(f"Добавлен слот перед бронью {booking.get('id')}: {slot_start_time} - {slot_end_time}")
                else:
                    logger.debug(f"Пропуск короткого/невалидного слота перед бронью {booking.get('id')}: {slot_start_time} - {slot_end_time}")

        current_time_dt = max(current_time_dt, booking_end_dt)
        if is_today:
            current_time_dt = max(current_time_dt, earliest_start_dt_today)

    if work_end_dt > current_time_dt:
        potential_slot_start_dt = current_time_dt
        potential_slot_end_dt = work_end_dt
        if potential_slot_end_dt > potential_slot_start_dt and \
           (potential_slot_end_dt - potential_slot_start_dt) >= min_step_delta:
            slot_start_time = max(potential_slot_start_dt.time(), work_start_time)
            slot_end_time = min(potential_slot_end_dt.time(), work_end_time)
            if datetime.combine(selected_date, slot_end_time) > datetime.combine(selected_date, slot_start_time) and \
               (datetime.combine(selected_date, slot_end_time) - datetime.combine(selected_date, slot_start_time)) >= min_step_delta:
                available_slots.append((slot_start_time, slot_end_time))
                logger.debug(f"Добавлен финальный слот: {slot_start_time} - {slot_end_time}")
            else:
                logger.debug(f"Пропуск короткого/невалидного финального слота: {slot_start_time} - {slot_end_time}")

    logger.info(f"Итоговые слоты для {equipment_id} на {selected_date}: {available_slots}")
    return available_slots

# --- Функции изменения данных ---

def check_booking_conflict(db: Database, equipment_id: int, start_dt: datetime, end_dt: datetime, exclude_booking_id: Optional[int] = None) -> List[BookingRow]:
    """ Проверяет пересечение времени. """
    query = """SELECT b.id, b.time_start, b.time_end, u.fi as user_fi FROM bookings b JOIN users u ON b.user_id = u.users_id WHERE b.equip_id = %s AND b.cancel = FALSE AND b.finish IS NULL AND b.time_end > %s AND b.time_start < %s"""
    start_dt_naive = start_dt.replace(tzinfo=None); end_dt_naive = end_dt.replace(tzinfo=None)
    params = [equipment_id, start_dt_naive, end_dt_naive]
    if exclude_booking_id: query += " AND b.id != %s"; params.append(exclude_booking_id)
    query += ";"
    try:
        conflicts: QueryResult = db.execute_query(query, tuple(params), fetch_results=True)
        logger.debug(f"Проверка конфликтов {equipment_id}, {start_dt_naive}-{end_dt_naive}, exclude={exclude_booking_id}. Найдено: {len(conflicts) if conflicts else 0}")
        return conflicts if conflicts else []
    except Exception as e:
        logger.error(f"Ошибка check_booking_conflict: {e}", exc_info=True)
        return [{'id': -1, 'error': 'check_failed'}]

def create_booking(db: Database, user_id: int, equipment_id: int, selected_date_str: str, start_time_str: str, duration_str: str) -> Tuple[bool, str, Optional[int]]:
    """ Создает новое бронирование. """
    try:
        selected_date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
        start_datetime = datetime.combine(selected_date_obj, start_time_obj)
        work_start_dt = datetime.combine(selected_date_obj, const.WORKING_HOURS_START).replace(tzinfo=None)
        work_end_dt = datetime.combine(selected_date_obj, const.WORKING_HOURS_END).replace(tzinfo=None)
        start_datetime = start_datetime.replace(tzinfo=None)
        if start_datetime < work_start_dt:
            logger.warning(f"Бронь {user_id} раньше раб. дня ({start_datetime} < {work_start_dt})")
            return False, const.MSG_BOOKING_FAIL_OUTSIDE_WORK_HOURS.format(start_work=_format_time(const.WORKING_HOURS_START), end_work=_format_time(const.WORKING_HOURS_END)), None
        hours, minutes = map(int, duration_str.split(':'))
        if hours < 0 or minutes < 0 or (hours == 0 and minutes == 0) or (hours * 60 + minutes) % const.BOOKING_TIME_STEP_MINUTES != 0:
             raise ValueError(f"Некорр. длит./не кратна {const.BOOKING_TIME_STEP_MINUTES} мин.")
        duration_timedelta = timedelta(hours=hours, minutes=minutes)
        if duration_timedelta > timedelta(hours=const.MAX_BOOKING_DURATION_HOURS):
             logger.warning(f"{user_id}: превышен лимит ({duration_str})");
             return False, const.MSG_BOOKING_FAIL_LIMIT_EXCEEDED, None
        end_datetime = start_datetime + duration_timedelta
        if end_datetime > work_end_dt:
             logger.warning(f"Бронь {user_id} после раб. дня ({end_datetime} > {work_end_dt})")
             return False, const.MSG_BOOKING_FAIL_ENDS_OUTSIDE_WORK_HOURS.format(end_work=_format_time(const.WORKING_HOURS_END)), None
        if start_datetime < datetime.now().replace(tzinfo=None) - timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES // 2):
             logger.warning(f"{user_id}: бронь в прошлом ({start_datetime})")
             return False, const.MSG_BOOKING_FAIL_TIME_IN_PAST, None
    except ValueError as e:
        logger.warning(f"{user_id}: ошибка парсинга: {e}");
        return False, const.MSG_BOOKING_FAIL_INVALID_TIME, None
    except Exception as e_parse:
        logger.error(f"Неожиданная ошибка парсинга данных брони {user_id}: {e_parse}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL, None

    try:
        conflicts = check_booking_conflict(db, equipment_id, start_datetime, end_datetime)
        if conflicts:
            c = conflicts[0]; c_s = _format_time(c.get('time_start')); c_e = _format_time(c.get('time_end')); c_u = c.get('user_fi', '???')
            msg = const.MSG_BOOKING_FAIL_OVERLAP + f"\n(Занято: {c_u}, {c_s} - {c_e})"
            logger.warning(f"КОНФЛИКТ user {user_id}: equip={equipment_id}, {start_datetime}-{end_datetime}. Занято ID={c.get('id')}")
            return False, msg, None

        time_interval = f"{start_datetime.strftime('%H:%M')}-{end_datetime.strftime('%H:%M')}"
        duration_in_db = duration_timedelta.total_seconds() / 3600.0
        data_booking_ts = datetime.now()
        insert_query = "INSERT INTO bookings (user_id, equip_id, date, time_start, time_end, time_interval, duration, cancel, finish, data_booking) VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, %s) RETURNING id;"
        params = (user_id, equipment_id, selected_date_obj, start_datetime, end_datetime, time_interval, duration_in_db, data_booking_ts)
        result: QueryResult = db.execute_query(insert_query, params, fetch_results=True, commit=True)

        if result and 'id' in result[0]:
            new_id = result[0]['id']
            logger.info(f"Создана бронь ID {new_id} user {user_id}, equip {equipment_id} на {selected_date_str} {time_interval}")
            return True, const.MSG_BOOKING_SUCCESS, new_id
        else:
            logger.error(f"INSERT {user_id} не вернул ID.");
            return False, const.MSG_BOOKING_FAIL_GENERAL, None
    except Exception as e:
        logger.error(f"Ошибка create_booking user {user_id}: {e}", exc_info=True);
        return False, const.MSG_ERROR_GENERAL, None

def cancel_booking(db: Database, booking_id: int, user_id: Optional[int] = None, is_admin_cancel: bool = False) -> Tuple[bool, str, Optional[int]]:
    """ Отменяет бронирование. """
    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_CANCEL_FAIL_NOT_FOUND, None
    b_user_id = booking_info.get('user_id'); b_start = booking_info.get('time_start'); b_cancel = booking_info.get('cancel', False); b_finish_time = booking_info.get('finish')
    if b_cancel: return False, "Бронь уже отменена.", b_user_id
    if b_finish_time is not None: return False, "Бронь уже завершена.", b_user_id

    if not is_admin_cancel:
        if user_id is None: logger.error(f"Отмена {booking_id} без user_id."); return False, const.MSG_ERROR_GENERAL, b_user_id
        if b_user_id != user_id: logger.warning(f"{user_id} пытался отменить чужую {booking_id}."); return False, "Это не ваше бронирование.", b_user_id
        if isinstance(b_start, datetime) and b_start.replace(tzinfo=None) <= datetime.now().replace(tzinfo=None):
             logger.warning(f"{user_id} пытался отменить начавшуюся {booking_id}.")
             return False, const.MSG_CANCEL_FAIL_TOO_LATE, b_user_id

    query = "UPDATE bookings SET cancel = TRUE WHERE id = %s AND cancel = FALSE AND finish IS NULL;"
    try:
        rows_affected = db.execute_query(query, (booking_id,), commit=True, fetch_results=False)
        if rows_affected is None or rows_affected > 0:
            initiator = f"админом {user_id}" if is_admin_cancel and user_id else f"юзером {user_id}" if user_id else "системой"
            logger.info(f"Бронь {booking_id} ({b_user_id}) отменена {initiator}.")
            return True, const.MSG_BOOKING_CANCELLED, b_user_id
        else:
             logger.warning(f"Попытка отмены {booking_id}, но не найдена/неактивна (rows={rows_affected}).")
             current_info = find_booking_by_id(db, booking_id)
             if current_info and current_info.get('cancel'): return False, "Бронь уже отменена.", b_user_id
             if current_info and current_info.get('finish') is not None: return False, "Бронь уже завершена.", b_user_id
             return False, const.MSG_CANCEL_FAIL_NOT_FOUND, b_user_id
    except Exception as e:
        logger.error(f"Ошибка UPDATE отмены {booking_id}: {e}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL, b_user_id

def finish_booking(db: Database, booking_id: int, user_id: int) -> Tuple[bool, str]:
     """ Завершает бронирование. """
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
     if not booking_info: return False, const.MSG_FINISH_FAIL_NOT_ACTIVE
     b_user_id = booking_info.get('user_id'); b_cancel = booking_info.get('cancel', False); b_finish_time = booking_info.get('finish'); equip_name = booking_info.get('equipment_name', '???')
     if b_user_id != user_id: logger.warning(f"{user_id} завершает чужую {booking_id}."); return False, "Это не ваше бронирование."
     if b_cancel: return False, "Бронь отменена."
     if b_finish_time is not None: return False, "Бронь завершена."

     now_dt = datetime.now().replace(tzinfo=None); time_start = booking_info.get('time_start')
     if not isinstance(time_start, datetime): logger.error(f"Некорр. тип time_start ({type(time_start)}) для {booking_id}"); return False, const.MSG_ERROR_GENERAL
     time_start_naive = time_start.replace(tzinfo=None)

     if time_start_naive > now_dt + timedelta(minutes=1): logger.warning(f"Попытка завершить не начавшуюся {booking_id} ({time_start_naive} > {now_dt})."); return False, const.MSG_FINISH_FAIL_NOT_ACTIVE

     finish_time_ts = datetime.now()
     query = "UPDATE bookings SET finish = %s WHERE id = %s AND cancel = FALSE AND finish IS NULL;"
     params = (finish_time_ts, booking_id)
     try:
         rows_affected = db.execute_query(query, params, commit=True, fetch_results=False)
         if rows_affected is None or rows_affected > 0:
             time_str = finish_time_ts.strftime('%H:%M:%S')
             logger.info(f"{user_id} завершил {booking_id} ({equip_name}) в {finish_time_ts:%Y-%m-%d %H:%M}.")
             msg = f"{const.MSG_BOOKING_FINISHED}\nОборудование: *{equip_name}*\nВремя завершения: {time_str}"
             return True, msg
         else:
             logger.warning(f"Попытка завершить {booking_id}, но не найдена/неактивна (rows={rows_affected}).")
             current_info = find_booking_by_id(db, booking_id)
             if current_info and current_info.get('finish') is not None: return False, "Бронь уже завершена."
             if current_info and current_info.get('cancel'): return False, "Бронь была отменена."
             return False, const.MSG_FINISH_FAIL_NOT_ACTIVE
     except Exception as e:
         logger.error(f"Ошибка UPDATE завершения {booking_id}: {e}", exc_info=True)
         return False, const.MSG_ERROR_GENERAL

def extend_booking(db: Database, booking_id: int, user_id: int, extension_str: str) -> Tuple[bool, str]:
    """ Продлевает бронирование. """
    try:
        if not extension_str or ':' not in extension_str: raise ValueError("Некорр. формат HH:MM")
        h, m = map(int, extension_str.split(':'))
        if h < 0 or m < 0 or (h == 0 and m == 0) or (h * 60 + m) % const.BOOKING_TIME_STEP_MINUTES != 0: raise ValueError(f"Некорр. длит./не кратна {const.BOOKING_TIME_STEP_MINUTES} мин.")
        extend_delta = timedelta(hours=h, minutes=m)
    except ValueError as e:
        logger.warning(f"Ошибка парсинга '{extension_str}': {e}")
        return False, f"Некорректный формат времени: {e}"
    except Exception as e_parse:
        logger.error(f"Неожиданная ошибка парсинга продления '{extension_str}': {e_parse}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL

    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_EXTEND_FAIL_NOT_ACTIVE
    b_user_id = booking_info.get('user_id'); equip_id = booking_info.get('equip_id'); cur_end = booking_info.get('time_end')
    time_start = booking_info.get('time_start'); b_cancel = booking_info.get('cancel', False); b_finish_time = booking_info.get('finish')
    equip_name = booking_info.get('equipment_name', '???')

    if b_user_id != user_id: logger.warning(f"{user_id} продляет чужую {booking_id}."); return False, "Это не ваше бронирование."
    if b_cancel: return False, "Бронь отменена."
    if b_finish_time is not None: return False, "Бронь завершена."
    if not isinstance(cur_end, datetime) or not isinstance(time_start, datetime): logger.error(f"{booking_id}: некорр. время."); return False, const.MSG_ERROR_GENERAL
    cur_end_naive = cur_end.replace(tzinfo=None); time_start_naive = time_start.replace(tzinfo=None); now_naive = datetime.now().replace(tzinfo=None)
    if cur_end_naive <= now_naive: logger.warning(f"{user_id} продляет закончившуюся {booking_id}"); return False, "Бронирование уже завершилось."

    new_end_dt = cur_end + extend_delta; new_end_naive = new_end_dt.replace(tzinfo=None)
    current_date = cur_end.date(); work_end_dt = datetime.combine(current_date, const.WORKING_HOURS_END).replace(tzinfo=None)
    if new_end_naive > work_end_dt: logger.warning(f"Продление {booking_id} {user_id} > раб. дня ({new_end_naive} > {work_end_dt})."); return False, const.MSG_BOOKING_FAIL_ENDS_OUTSIDE_WORK_HOURS.format(end_work=_format_time(const.WORKING_HOURS_END))
    total_duration = new_end_dt - time_start
    if total_duration > timedelta(hours=const.MAX_BOOKING_DURATION_HOURS): logger.warning(f"{booking_id}: превышен лимит."); return False, const.MSG_BOOKING_FAIL_LIMIT_EXCEEDED

    try:
        conflicts = check_booking_conflict(db, equip_id, cur_end_naive, new_end_naive, exclude_booking_id=booking_id)
        if conflicts:
            c = conflicts[0]; c_s = _format_time(c.get('time_start')); c_e = _format_time(c.get('time_end')); c_u = c.get('user_fi', '???')
            msg = const.MSG_BOOKING_FAIL_OVERLAP + f"\n(Занято: {c_u}, {c_s} - {c_e})"
            logger.warning(f"Конфликт продления {booking_id} user {user_id}. Занято ID={c.get('id')}")
            return False, msg
    except Exception as e_conflict:
        logger.error(f"{booking_id}: Ошибка проверки конфликта: {e_conflict}", exc_info=True)
        return False, "Ошибка проверки времени."

    new_time_interval = f"{time_start.strftime('%H:%M')}-{new_end_dt.strftime('%H:%M')}"
    new_total_duration_hours = total_duration.total_seconds() / 3600.0
    query = "UPDATE bookings SET time_end = %(new_end)s, time_interval = %(interval)s, duration = %(duration)s, extension = COALESCE(extension, interval '0 hours') + %(ext_delta)s WHERE id = %(b_id)s AND cancel = FALSE AND finish IS NULL;"
    params = {'new_end': new_end_dt, 'interval': new_time_interval, 'duration': new_total_duration_hours, 'ext_delta': extend_delta, 'b_id': booking_id}
    try:
        rows_affected = db.execute_query(query, params, commit=True, fetch_results=False)
        if rows_affected is None or rows_affected > 0:
            new_end_str = _format_time(new_end_dt)
            logger.info(f"{user_id} продлил {booking_id} ({equip_name}) на {extension_str}. New end: {new_end_dt:%Y-%m-%d %H:%M}")
            msg = f"{const.MSG_BOOKING_EXTENDED}\nОборудование: *{equip_name}*\nНовое время окончания: {new_end_str}"
            return True, msg
        else: logger.warning(f"Продление {booking_id}, но неактивна (rows={rows_affected})."); return False, const.MSG_EXTEND_FAIL_NOT_ACTIVE
    except Exception as e:
        logger.error(f"Ошибка UPDATE продления {booking_id}: {e}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL

def confirm_start_booking(db: Database, booking_id: int, user_id: int) -> bool:
     """ "Подтверждает" актуальность брони."""
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
     if booking_info:
          b_user_id = booking_info.get('user_id'); b_cancel = booking_info.get('cancel', False); b_finish_time = booking_info.get('finish')
          if b_user_id == user_id and not b_cancel and b_finish_time is None: logger.info(f"User {user_id} подтвердил {booking_id}."); return True
          else: logger.warning(f"Попытка подтвердить неактив/чужую {booking_id} user {user_id}.")
     else: logger.warning(f"Не найдена {booking_id} для подтверждения user {user_id}.")
     return False

def auto_cancel_unconfirmed_booking(db: Database, booking_id: int) -> Tuple[bool, Optional[int], Optional[str]]:
     """ Автоотмена неподтвержденной брони. """
     logger.debug(f"Автоотмена для {booking_id}...")
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
     if booking_info:
          b_user_id = booking_info.get('user_id'); equip_name = booking_info.get('equipment_name'); b_cancel = booking_info.get('cancel', False); b_finish_time = booking_info.get('finish')
          time_start = booking_info.get('time_start'); can_auto_cancel = False
          if isinstance(time_start, datetime):
                # Автоотмена возможна, если время старта ЕЩЕ НЕ НАСТУПИЛО
                # (или наступило совсем недавно, даем небольшой люфт)
                if time_start.replace(tzinfo=None) > datetime.now().replace(tzinfo=None) - timedelta(minutes=1):
                    can_auto_cancel = True

          if not b_cancel and b_finish_time is None and can_auto_cancel:
               logger.info(f"{booking_id} подлежит автоотмене.")
               success, _, _ = cancel_booking(db, booking_id, user_id=None, is_admin_cancel=True) # Отменяем как админ (система)
               if success: logger.info(f"{booking_id} успешно авто-отменена."); return True, b_user_id, equip_name
               else: logger.error(f"Не удалось авто-отменить {booking_id}."); return False, b_user_id, equip_name
          else:
               reason = f"cancel={b_cancel}, finish_set={b_finish_time is not None}"
               if not can_auto_cancel: reason += ", started_or_past"
               logger.debug(f"Автоотмена {booking_id} не требуется ({reason}).")
               return False, b_user_id, equip_name
     else: logger.warning(f"Не найдена {booking_id} для автоотмены."); return False, None, None

def get_bookings_for_notification_schedule(db: Database) -> List[Tuple[int, int, int, datetime, datetime, str]]:
     """ Получает брони для планировщика уведомлений. """
     threshold_start = datetime.now() - timedelta(days=1); now = datetime.now()
     query = """SELECT b.id, b.user_id, b.equip_id, b.time_start, b.time_end, e.name_equip FROM bookings b JOIN equipment e ON b.equip_id = e.id WHERE b.cancel = FALSE AND b.finish IS NULL AND b.time_start >= %s AND b.time_end >= %s ORDER BY b.id;"""
     try:
         results_dict: QueryResult = db.execute_query(query, (threshold_start, now), fetch_results=True)
         results_tuple: List[Tuple[int, int, int, datetime, datetime, str]] = []
         if results_dict:
             for row in results_dict:
                 if all(k in row for k in ('id', 'user_id', 'equip_id', 'time_start', 'time_end', 'name_equip')) and isinstance(row['time_start'], datetime) and isinstance(row['time_end'], datetime):
                     results_tuple.append((row['id'], row['user_id'], row['equip_id'], row['time_start'], row['time_end'], row['name_equip']))
                 else: logger.warning(f"Неполные/некорр. данные: {row}")
         logger.debug(f"Найдено {len(results_tuple)} броней для уведомлений.")
         return results_tuple
     except Exception as e:
         logger.error(f"Ошибка get_bookings_for_notification_schedule: {e}", exc_info=True)
         return []

# --- END OF FILE services/booking_service.py ---