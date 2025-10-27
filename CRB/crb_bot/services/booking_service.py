# --- START OF FILE services/booking_service.py ---

# services/booking_service.py
from database import Database, QueryResult
from logger import logger
from typing import List, Tuple, Optional, Dict, Any, Union
from datetime import datetime, timedelta, date, time
import constants as const
import os
import telebot

# Ожидаемый тип строки бронирования из БД (теперь с cr_id, cr_name)
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
    cr_name: Optional[str], # <-- Имя комнаты
    date_val: Optional[date],
    time_start: Optional[Union[datetime, time]],
    time_end: Optional[Union[datetime, time]],
    user_name: Optional[str] = None
) -> str:
    """Вспомогательная функция для форматирования информации о бронировании."""
    cr_name_str = cr_name or "???"
    date_str = _format_date(date_val)
    start_str = _format_time(time_start)
    end_str = _format_time(time_end)
    info_lines = [f"Переговорная: *{cr_name_str}*"]
    if user_name: info_lines.append(f"Пользователь: {user_name}")
    info_lines.append(f"Дата: {date_str}")
    info_lines.append(f"Время: {start_str} - {end_str}")
    return "\n".join(info_lines)

# --- Функции получения данных ---

def get_user_active_bookings(db: Database, user_id: int) -> List[BookingRow]:
    """ Получает активные и предстоящие подтвержденные бронирования пользователя (словари). """
    # Используем NOW() для сравнения с time_end
    query = """
        SELECT b.*, cr.cr_name, u.fi as user_fi
        FROM bookings b
        JOIN conferenceroom cr ON b.cr_id = cr.id
        JOIN users u ON b.user_id = u.users_id
        WHERE b.user_id = %s
        AND b.status IN ('pending_confirmation', 'confirmed', 'active')
        AND b.time_end > NOW() -- Исправлено: Сравниваем с текущим полным временем
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, (user_id,), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_user_active_bookings({user_id}): {e}", exc_info=True)
        # Пробрасываем ошибку дальше, чтобы вызывающий код мог ее обработать
        raise e


def get_user_bookings_for_cancel(db: Database, user_id: int) -> List[BookingRow]:
    """ Получает будущие ('confirmed') бронирования пользователя для отмены (словари). """
    now_dt_naive = datetime.now() # Используем datetime для сравнения с timestampz
    query = """
        SELECT b.*, cr.cr_name, u.fi as user_fi
        FROM bookings b
        JOIN conferenceroom cr ON b.cr_id = cr.id
        JOIN users u ON b.user_id = u.users_id
        WHERE b.user_id = %s
        AND b.status IN ('pending_confirmation', 'confirmed') -- Ищем ожидающие И подтвержденные
        AND b.time_start > %s -- Время начала в будущем
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, (user_id, now_dt_naive), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_user_bookings_for_cancel({user_id}): {e}", exc_info=True)
        raise e


def get_user_active_bookings_text(db: Database, user_id: int) -> str:
    """Форматирует активные и предстоящие бронирования пользователя в текст."""
    try:
        bookings: List[BookingRow] = get_user_active_bookings(db, user_id)
    except Exception: # Ловим ошибку от get_user_active_bookings
        return "Не удалось получить список ваших бронирований."

    if not bookings: return "У вас нет активных или предстоящих бронирований."
    response_lines = ["*Ваши активные и предстоящие бронирования:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(booking.get('cr_name'), booking.get('date'), booking.get('time_start'), booking.get('time_end')))
        response_lines.append("-" * 20)
    if len(response_lines) > 1:
        response_lines.pop()
    return "\n".join(response_lines)


def get_all_active_bookings_for_admin_keyboard(db: Database) -> List[BookingRow]:
    """ Получает все активные и предстоящие подтвержденные бронирования для клавиатуры админа. """
    # Используем NOW() для сравнения с time_end
    query = """
        SELECT b.id, u.fi as user_name, cr.cr_name as conference_room_name, b.date, b.time_start, b.time_end
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        JOIN conferenceroom cr ON b.cr_id = cr.id
        WHERE b.status IN ('pending_confirmation', 'confirmed', 'active')
        AND b.time_end > NOW() -- Исправлено: Сравниваем с текущим полным временем
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_all_active_bookings_for_admin_keyboard: {e}", exc_info=True)
        raise e


def get_all_active_bookings_text(db: Database) -> str:
    """Форматирует все активные и предстоящие бронирования в текст."""
    try:
        bookings: List[BookingRow] = get_all_active_bookings_for_admin_keyboard(db)
    except Exception:
        return "Не удалось получить список всех бронирований."

    if not bookings: return "Нет активных или предстоящих бронирований в системе."
    response_lines = ["*Все активные и предстоящие бронирования:*"]
    for booking in bookings:
        response_lines.append(format_booking_info(booking.get('conference_room_name'), booking.get('date'), booking.get('time_start'), booking.get('time_end'), booking.get('user_name')))
        response_lines.append("-" * 20)
    if len(response_lines) > 1:
        response_lines.pop()
    response = "\n".join(response_lines)
    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (список слишком длинный)"
        logger.warning("Список /allbookings обрезан.")
    return response


def get_bookings_by_date(db: Database, selected_date: date) -> List[BookingRow]:
    """
    Получает бронирования на указанную дату (кроме отмененных).
    Фильтрует по времени окончания для сегодняшнего дня.
    """
    today = date.today()
    is_today = (selected_date == today)
    now_time_naive = datetime.now().time() # Для сравнения времени сегодня

    base_query = """
        SELECT b.*, cr.cr_name, u.fi as user_fi
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        JOIN conferenceroom cr ON b.cr_id = cr.id
        WHERE b.date = %s
        AND b.status != 'cancelled'
    """
    params: List[Any] = [selected_date]

    if is_today:
        logger.debug(f"Запрос бронирований на сегодня ({selected_date}), фильтруем по времени окончания.")
        # Сравниваем только время, т.к. дата уже совпадает
        # Важно: предполагаем, что time_end в БД это TIMESTAMP WITHOUT TIME ZONE
        # Тогда приведение к TIME корректно
        base_query += " AND (CAST(b.time_end AS TIME) > %s OR b.status = 'active')"
        params.append(now_time_naive)
    else:
        logger.debug(f"Запрос бронирований на дату ({selected_date}), показываем все не отмененные.")

    final_query = base_query + " ORDER BY cr.cr_name, b.time_start;"

    try:
        result: QueryResult = db.execute_query(final_query, tuple(params), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_bookings_by_date({selected_date}): {e}", exc_info=True)
        raise e


# def get_bookings_by_date_text(db: Database, selected_date: date) -> str:
#     """Форматирует бронирования на дату в текст."""
#     try:
#         bookings: List[BookingRow] = get_bookings_by_date(db, selected_date)
#     except Exception:
#         return f"Не удалось получить бронирования на {_format_date(selected_date)}."
#
#     date_str = _format_date(selected_date)
#     if not bookings:
#         if selected_date == date.today():
#             return f"Нет предстоящих бронирований на сегодня ({date_str})."
#         else:
#             return f"Нет бронирований на {date_str}."
#
#     response_lines = [f"*Бронирования на {date_str}:*"]
#     for booking in bookings:
#         response_lines.append(format_booking_info(booking.get('cr_name'), booking.get('date'), booking.get('time_start'), booking.get('time_end'), booking.get('user_fi')))
#         status = booking.get('status')
#         if status not in ['pending_confirmation', 'confirmed', 'active']:
#             status_text = status.replace('_', ' ').capitalize()
#             response_lines.append(f"Статус: {status_text}")
#         response_lines.append("-" * 20)
#     if len(response_lines) > 1:
#         response_lines.pop()
#     response = "\n".join(response_lines)
#     if len(response) > const.MAX_MESSAGE_LENGTH:
#         response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (слишком длинный)"
#         logger.warning(f"Список броней {date_str} обрезан.")
#     return response


def get_bookings_by_conference_room(db: Database, cr_id: int) -> List[BookingRow]:
    """ Получает будущие/активные бронирования для переговорной комнаты. """
# Используем NOW() для сравнения с time_end
    query = """
        SELECT b.*, cr.cr_name, u.fi as user_fi
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        JOIN conferenceroom cr ON b.cr_id = cr.id
        WHERE b.cr_id = %s
        AND b.status IN ('pending_confirmation', 'confirmed', 'active')
        AND b.time_end > NOW() -- Исправлено: Сравниваем с текущим полным временем
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, (cr_id, ), fetch_results=True)
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_bookings_by_conference_room({cr_id}): {e}", exc_info=True)
        raise e


def get_bookings_by_conference_room_text(db: Database, cr_id: int, cr_name: str) -> str:
    """Форматирует будущие/активные бронирования для комнаты."""
    try:
        bookings: List[BookingRow] = get_bookings_by_conference_room(db, cr_id)
    except Exception:
        return f"Не удалось получить бронирования для '{cr_name}'."

    if not bookings: return f"Для переговорной '{cr_name}' нет предстоящих бронирований."
    response_lines = [f"*Предстоящие бронирования для '{cr_name}':*"]
    for booking in bookings:
        response_lines.append(format_booking_info(cr_name, booking.get('date'), booking.get('time_start'), booking.get('time_end'), booking.get('user_fi')))
        response_lines.append("-" * 20)
    if len(response_lines) > 1:
        response_lines.pop()
    response = "\n".join(response_lines)
    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (слишком длинный)"
        logger.warning(f"Список броней для комнаты '{cr_name}' обрезан.")
    return response


def find_booking_by_id(db: Database, booking_id: int) -> Optional[BookingRow]:
    """Ищет бронирование по ID."""
    query = """
        SELECT b.*, cr.cr_name, u.fi as user_fi
        FROM bookings b
        LEFT JOIN conferenceroom cr ON b.cr_id = cr.id -- Используем LEFT JOIN на случай, если комната удалена
        LEFT JOIN users u ON b.user_id = u.users_id -- Используем LEFT JOIN на случай, если юзер удален
        WHERE b.id = %s;
    """
    try:
        result: QueryResult = db.execute_query(query, (booking_id,), fetch_results=True)
        if result:
            booking = result[0]
            logger.debug(f"Бронь {booking_id}: date={booking.get('date')}, type={type(booking.get('date'))}, "
                        f"time_end={booking.get('time_end')}, type={type(booking.get('time_end'))}, "
                        f"cr_id={booking.get('cr_id')}, status={booking.get('status')}")
            return booking
        return None
    except Exception as e:
        logger.error(f"Ошибка find_booking_by_id({booking_id}): {e}", exc_info=True)
        raise e


def find_next_booking(db: Database, cr_id: int, after_time: datetime) -> Optional[BookingRow]:
    """ Ищет следующее бронирование после времени для комнаты. """
    query = """
        SELECT id, time_start
        FROM bookings
        WHERE cr_id = %s
        AND status IN ('pending_confirmation', 'confirmed', 'active')
        AND time_start > %s
        ORDER BY time_start ASC
        LIMIT 1;
    """
    params = (cr_id, after_time)
    log_msg = f"Поиск след. брони для комнаты {cr_id} после {after_time}. "
    try:
        if after_time.tzinfo is None: logger.warning("find_next_booking вызван с naive after_time")
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
        logger.error(f"Ошибка find_next_booking(cr_id={cr_id}): {e}", exc_info=True)
        raise e


def get_user_current_bookings(db: Database, user_id: int) -> List[BookingRow]:
    """ Находит текущие ('active') бронирования пользователя. """
    query = """
        SELECT b.*, cr.cr_name, u.fi as user_fi
        FROM bookings b
        JOIN conferenceroom cr ON b.cr_id = cr.id
        JOIN users u ON b.user_id = u.users_id
        WHERE b.user_id = %s
        AND b.status = 'active'
        AND NOW() BETWEEN b.time_start AND b.time_end -- Добавлено условие проверки времени
        ORDER BY b.date, b.time_start;
    """
    try:
        result: QueryResult = db.execute_query(query, (user_id, ), fetch_results=True)
        logger.debug(f"Поиск текущих ('active') броней user {user_id}. Найдено: {len(result) if result else 0}")
        return result if result else []
    except Exception as e:
        logger.error(f"Ошибка get_user_current_bookings({user_id}): {e}", exc_info=True)
        raise e


def calculate_available_slots(
    db: Database,
    cr_id: int,
    selected_date: date
) -> List[Tuple[time, time]]:
    """
    Вычисляет доступные временные слоты для бронирования
    на выбранную дату для конкретной комнаты.
    """
    logger.debug(f"Расчет слотов для комнаты cr_id={cr_id} на {selected_date}")
    try:
        all_bookings_on_date = get_bookings_by_date(db, selected_date)
    except Exception as e_get_bookings:
        logger.error(f"Ошибка при получении броней для расчета слотов (cr_id={cr_id}, date={selected_date}): {e_get_bookings}", exc_info=True)
        # Возвращаем пустой список, чтобы показать, что слотов нет
        return []

    room_bookings = [
        b for b in all_bookings_on_date
        if b.get('cr_id') == cr_id
            and isinstance(b.get('time_start'), datetime)
            and isinstance(b.get('time_end'), datetime)
    ]
    sorted_bookings = sorted(room_bookings, key=lambda b: b['time_start'])

    available_slots: List[Tuple[time, time]] = []
    work_start_time = const.WORKING_HOURS_START
    work_end_time = const.WORKING_HOURS_END
    min_step_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    if isinstance(work_start_time, datetime): work_start_time = work_start_time.time()
    if isinstance(work_end_time, datetime): work_end_time = work_end_time.time()

    today = date.today()
    is_today = (selected_date == today)
    now_dt_naive = datetime.now()
    earliest_start_dt_today = now_dt_naive

    if is_today:
        minutes_to_add = 0
        if now_dt_naive.minute % const.BOOKING_TIME_STEP_MINUTES != 0:
            minutes_to_add = const.BOOKING_TIME_STEP_MINUTES - (now_dt_naive.minute % const.BOOKING_TIME_STEP_MINUTES)
        earliest_start_dt_today = (now_dt_naive + timedelta(minutes=minutes_to_add)).replace(second=0, microsecond=0)
        logger.debug(f"Сегодняшний день. Самое раннее начало: {earliest_start_dt_today.time()}")

    effective_start_dt = datetime.combine(selected_date, work_start_time)
    if is_today:
        effective_start_dt = max(effective_start_dt, earliest_start_dt_today)

    current_time_dt = effective_start_dt
    work_end_dt = datetime.combine(selected_date, work_end_time)

    logger.debug(f"Эффективное время начала поиска слотов: {current_time_dt}")
    logger.debug(f"Рабочее время: {work_start_time} - {work_end_time}")
    logger.debug(f"Найденные брони ({len(sorted_bookings)}) для комнаты {cr_id}: {[(b.get('id'), _format_time(b.get('time_start')), _format_time(b.get('time_end'))) for b in sorted_bookings]}")

    for booking in sorted_bookings:
        booking_start_dt = booking['time_start']
        booking_end_dt = booking['time_end']

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

    logger.info(f"Итоговые слоты для комнаты {cr_id} на {selected_date}: {available_slots}")
    return available_slots

# --- Функции изменения данных ---

def check_booking_conflict(db: Database, cr_id: int, start_dt: datetime, end_dt: datetime, exclude_booking_id: Optional[int] = None) -> List[BookingRow]:
    """ Проверяет пересечение времени для комнаты. """
    # Сравниваем только с 'confirmed' и 'active'
    query = """
        SELECT b.id, b.time_start, b.time_end, u.fi as user_fi
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        WHERE b.cr_id = %s
        AND b.status IN ('pending_confirmation', 'confirmed', 'active')
        AND b.time_end > %s -- Новое бронирование начинается до конца старого
        AND b.time_start < %s -- Новое бронирование заканчивается после начала старого
    """
    params = [cr_id, start_dt, end_dt]
    if exclude_booking_id:
        query += " AND b.id != %s"
        params.append(exclude_booking_id)
    query += ";"
    try:
        conflicts: QueryResult = db.execute_query(query, tuple(params), fetch_results=True)
        logger.debug(f"Проверка конфликтов комнаты {cr_id}, {start_dt}-{end_dt}, exclude={exclude_booking_id}. Найдено: {len(conflicts) if conflicts else 0}")
        return conflicts if conflicts else []
    except Exception as e:
        logger.error(f"Ошибка check_booking_conflict(cr_id={cr_id}): {e}", exc_info=True)
        return [{'id': -1, 'error': 'check_failed', 'details': str(e)}]


def create_booking(db: Database, user_id: int, cr_id: int, selected_date_str: str, start_time_str: str, duration_str: str) -> Tuple[bool, str, Optional[int]]:
    """ Создает новое бронирование комнаты со статусом 'pending_confirmation'. """
    try:
        selected_date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
        start_datetime = datetime.combine(selected_date_obj, start_time_obj)

        work_start_dt = datetime.combine(selected_date_obj, const.WORKING_HOURS_START)
        work_end_dt = datetime.combine(selected_date_obj, const.WORKING_HOURS_END)
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

        if start_datetime < datetime.now() - timedelta(minutes=1):
            logger.warning(f"{user_id}: попытка брони в прошлом ({start_datetime})")
            return False, const.MSG_BOOKING_FAIL_TIME_IN_PAST, None

    except ValueError as e:
        logger.warning(f"Ошибка парсинга данных бронирования user {user_id}: {e}");
        return False, const.MSG_BOOKING_FAIL_INVALID_TIME, None
    except Exception as e_parse:
        logger.error(f"Неожиданная ошибка парсинга данных брони {user_id}: {e_parse}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL, None

    try:
        conflicts = check_booking_conflict(db, cr_id, start_datetime, end_datetime)
        if conflicts:
            if conflicts[0].get('error') == 'check_failed':
                logger.error(f"Не удалось проверить конфликты для cr_id={cr_id}. Отмена создания брони.")
                return False, "Ошибка проверки конфликтов. Попробуйте позже.", None
            c = conflicts[0]; c_s = _format_time(c.get('time_start')); c_e = _format_time(c.get('time_end')); c_u = c.get('user_fi', '???')
            msg = const.MSG_BOOKING_FAIL_OVERLAP + f"\n(Занято: {c_u}, {c_s} - {c_e})"
            logger.warning(f"КОНФЛИКТ user {user_id}: cr_id={cr_id}, {start_datetime}-{end_datetime}. Занято ID={c.get('id')}")
            return False, msg, None

        time_interval = f"{start_datetime.strftime('%H:%M')}-{end_datetime.strftime('%H:%M')}"
        duration_in_db = duration_timedelta.total_seconds() / 3600.0
        data_booking_ts = datetime.now()
        status = 'pending_confirmation'

        insert_query = """
            INSERT INTO bookings
            (user_id, cr_id, date, time_start, time_end, time_interval, duration, status, data_booking, cancel, finish)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, False,  NULL) RETURNING id;
        """
        params = (user_id, cr_id, selected_date_obj, start_datetime, end_datetime, time_interval, duration_in_db, status, data_booking_ts)
        result: QueryResult = db.execute_query(insert_query, params, fetch_results=True, commit=True)

        if result and 'id' in result[0]:
            new_id = result[0]['id']
            logger.info(f"Создана бронь ID {new_id} (status={status}) user {user_id}, комната {cr_id} на {selected_date_str} {time_interval}")
            # Возвращаем успех и ID, но сообщение об успехе будет после подтверждения
            return True, const.MSG_BOOKING_SUCCESS, new_id
        else:
            logger.error(f"INSERT для user {user_id} не вернул ID.");
            return False, const.MSG_BOOKING_FAIL_GENERAL, None
    except Exception as e:
        logger.error(f"Ошибка create_booking user {user_id}, cr_id {cr_id}: {e}", exc_info=True);
        raise e # Пробрасываем ошибку для обработки в вызывающем коде


def cancel_booking(db: Database, booking_id: int, user_id: Optional[int] = None, is_admin_cancel: bool = False) -> Tuple[bool, str, Optional[int]]:
    """ Отменяет бронирование (устанавливает статус 'cancelled'). """
    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_CANCEL_FAIL_NOT_FOUND, None

    b_user_id = booking_info.get('user_id')
    b_status = booking_info.get('status')
    b_start = booking_info.get('time_start')

    if b_status == 'cancelled': return False, "Бронь уже отменена.", b_user_id
    if b_status == 'finished': return False, "Бронь уже завершена.", b_user_id

    if not is_admin_cancel:
        if user_id is None:
            logger.error(f"Попытка отмены {booking_id} без user_id и не админом.")
            return False, const.MSG_ERROR_GENERAL, b_user_id
        if b_user_id != user_id:
            logger.warning(f"Пользователь {user_id} попытался отменить чужую бронь {booking_id}.")
            return False, "Это не ваше бронирование.", b_user_id
        if b_status not in ['pending_confirmation', 'confirmed']:
            logger.warning(f"Пользователь {user_id} пытался отменить бронь {booking_id} со статусом '{b_status}'.")
            return False, const.MSG_CANCEL_FAIL_TOO_LATE, b_user_id
        if isinstance(b_start, datetime) and b_start <= datetime.now():
            logger.warning(f"Пользователь {user_id} пытался отменить начавшуюся/прошедшую бронь {booking_id}.")
            return False, const.MSG_CANCEL_FAIL_TOO_LATE, b_user_id

    query = "UPDATE bookings SET status = 'cancelled' WHERE id = %s AND status != 'cancelled';"
    try:
        rows_affected = db.execute_query(query, (booking_id,), commit=True, fetch_results=False)
        if rows_affected is not None and rows_affected > 0:
            initiator = f"админом {user_id}" if is_admin_cancel and user_id else f"пользователем {user_id}" if user_id else "системой"
            logger.info(f"Бронь {booking_id} (пользователь {b_user_id}) отменена {initiator}.")
            return True, const.MSG_BOOKING_CANCELLED, b_user_id
        elif rows_affected == 0:
            logger.warning(f"Попытка отмены {booking_id}, но не найдена или уже отменена (rows={rows_affected}).")
            current_info = find_booking_by_id(db, booking_id)
            if current_info and current_info.get('status') == 'cancelled': return False, "Бронь уже отменена.", b_user_id
            return False, const.MSG_CANCEL_FAIL_NOT_FOUND, b_user_id
        else:
            return False, const.MSG_ERROR_GENERAL, b_user_id
    except Exception as e:
        logger.error(f"Ошибка UPDATE при отмене брони {booking_id}: {e}", exc_info=True)
        raise e


def finish_booking(db: Database, booking_id: int, user_id: int) -> Tuple[bool, str]:
    """ Завершает бронирование (устанавливает статус 'finished' и время в столбец 'finish'). """  # <-- Обновлен docstring
    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_FINISH_FAIL_NOT_ACTIVE

    b_user_id = booking_info.get('user_id')
    b_status = booking_info.get('status')
    cr_name = booking_info.get('cr_name', '???')

    if b_user_id != user_id:
        logger.warning(f"Пользователь {user_id} попытался завершить чужую бронь {booking_id}.")
        return False, "Это не ваше бронирование."

    if b_status != 'active':
        if b_status == 'finished': return False, "Бронь уже завершена."
        if b_status == 'cancelled': return False, "Бронь была отменена."
        logger.warning(f"Попытка завершить бронь {booking_id} с некорректным статусом '{b_status}'.")
        return False, const.MSG_FINISH_FAIL_NOT_ACTIVE

    finish_time_ts = datetime.now()
    # --- ИЗМЕНЕНИЕ: Обновляем столбец 'finish', а не 'finish_actual' ---
    query = "UPDATE bookings SET status = 'finished', finish = %s WHERE id = %s AND status = 'active';"
    params = (finish_time_ts, booking_id)
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    try:
        rows_affected = db.execute_query(query, params, commit=True, fetch_results=False)
        # Проверяем rows_affected, так как execute_query теперь его возвращает
        if rows_affected is not None and rows_affected > 0:
            time_str = finish_time_ts.strftime('%H:%M:%S')
            logger.info(
                f"Пользователь {user_id} завершил бронь {booking_id} ({cr_name}) в {finish_time_ts:%Y-%m-%d %H:%M}.")
            msg = f"{const.MSG_BOOKING_FINISHED}\nПереговорная: *{cr_name}*\nВремя завершения: {time_str}"
            return True, msg
        elif rows_affected == 0:
            logger.warning(f"Попытка завершить {booking_id}, но статус уже не 'active' (rows={rows_affected}).")
            current_info = find_booking_by_id(db, booking_id)
            if current_info and current_info.get('status') == 'finished': return False, "Бронь уже завершена."
            return False, const.MSG_FINISH_FAIL_NOT_ACTIVE
        else:  # rows_affected is None (ошибка)
            # Возвращаем общую ошибку, т.к. не знаем, что пошло не так
            return False, const.MSG_ERROR_GENERAL
    except Exception as e:
        logger.error(f"Ошибка UPDATE при завершении брони {booking_id}: {e}", exc_info=True)
        # Пробрасываем ошибку, чтобы она была видна в логах верхнего уровня
        raise e


def extend_booking(db: Database, booking_id: int, user_id: int, extension_str: str) -> Tuple[bool, str]:
    """ Продлевает бронирование. """
    try:
        if not extension_str or ':' not in extension_str: raise ValueError("Некорр. формат HH:MM")
        h, m = map(int, extension_str.split(':'))
        if h < 0 or m < 0 or (h == 0 and m == 0) or (h * 60 + m) % const.BOOKING_TIME_STEP_MINUTES != 0: raise ValueError(f"Некорр. длит./не кратна {const.BOOKING_TIME_STEP_MINUTES} мин.")
        extend_delta = timedelta(hours=h, minutes=m)
    except ValueError as e:
        logger.warning(f"Ошибка парсинга времени продления '{extension_str}' для user {user_id}: {e}")
        return False, f"Некорректный формат времени: {e}"
    except Exception as e_parse:
        logger.error(f"Неожиданная ошибка парсинга продления '{extension_str}': {e_parse}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL

    booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
    if not booking_info: return False, const.MSG_EXTEND_FAIL_NOT_ACTIVE

    b_user_id = booking_info.get('user_id')
    cr_id = booking_info.get('cr_id')
    cr_name = booking_info.get('cr_name', '???')
    b_status = booking_info.get('status')
    cur_end = booking_info.get('time_end')
    time_start = booking_info.get('time_start')

    if b_user_id != user_id:
        logger.warning(f"Пользователь {user_id} попытался продлить чужую бронь {booking_id}.")
        return False, "Это не ваше бронирование."
    if b_status != 'active':
        logger.warning(f"Пользователь {user_id} попытался продлить бронь {booking_id} с неактивным статусом '{b_status}'.")
        return False, const.MSG_EXTEND_FAIL_NOT_ACTIVE

    if not isinstance(cur_end, datetime) or not isinstance(time_start, datetime):
        logger.error(f"Некорректные типы времени для брони {booking_id} при продлении.")
        return False, const.MSG_ERROR_GENERAL
    if cur_end <= datetime.now():
        logger.warning(f"Пользователь {user_id} попытался продлить уже закончившуюся бронь {booking_id}.")
        return False, "Бронирование уже завершилось."

    new_end_dt = cur_end + extend_delta
    current_date = cur_end.date()
    work_end_dt = datetime.combine(current_date, const.WORKING_HOURS_END).replace(tzinfo=cur_end.tzinfo) # Use original tzinfo
    if new_end_dt > work_end_dt:
        logger.warning(f"Продление брони {booking_id} (user {user_id}) выходит за рамки рабочего дня ({new_end_dt} > {work_end_dt}).")
        return False, const.MSG_BOOKING_FAIL_ENDS_OUTSIDE_WORK_HOURS.format(end_work=_format_time(const.WORKING_HOURS_END))

    total_duration = new_end_dt - time_start
    if total_duration > timedelta(hours=const.MAX_BOOKING_DURATION_HOURS):
        logger.warning(f"Продление брони {booking_id} (user {user_id}) превышает максимальную длительность.")
        return False, const.MSG_BOOKING_FAIL_LIMIT_EXCEEDED

    try:
        conflicts = check_booking_conflict(db, cr_id, cur_end, new_end_dt, exclude_booking_id=booking_id)
        if conflicts:
            if conflicts[0].get('error') == 'check_failed':
                logger.error(f"Не удалось проверить конфликты продления для cr_id={cr_id}.")
                return False, "Ошибка проверки конфликтов. Попробуйте позже."
            c = conflicts[0]; c_s = _format_time(c.get('time_start')); c_e = _format_time(c.get('time_end')); c_u = c.get('user_fi', '???')
            msg = const.MSG_BOOKING_FAIL_OVERLAP + f"\n(Занято: {c_u}, {c_s} - {c_e})"
            logger.warning(f"Конфликт продления брони {booking_id} (user {user_id}). Занято ID={c.get('id')}")
            return False, msg
    except Exception as e_conflict:
        logger.error(f"Ошибка проверки конфликта при продлении брони {booking_id}: {e_conflict}", exc_info=True)
        raise e_conflict # Пробрасываем ошибку

    new_time_interval = f"{time_start.strftime('%H:%M')}-{new_end_dt.strftime('%H:%M')}"
    new_total_duration_hours = total_duration.total_seconds() / 3600.0
    query = """
        UPDATE bookings
        SET time_end = %(new_end)s,
            time_interval = %(interval)s,
            duration = %(duration)s,
            extension = COALESCE(extension, interval '0 hours') + %(ext_delta)s
        WHERE id = %(b_id)s AND status = 'active';
    """
    params = {'new_end': new_end_dt, 'interval': new_time_interval, 'duration': new_total_duration_hours, 'ext_delta': extend_delta, 'b_id': booking_id}
    try:
        rows_affected = db.execute_query(query, params, commit=True, fetch_results=False)
        if rows_affected is not None and rows_affected > 0:
            new_end_str = _format_time(new_end_dt)
            logger.info(f"Пользователь {user_id} продлил бронь {booking_id} ({cr_name}) на {extension_str}. Новое время окончания: {new_end_dt:%Y-%m-%d %H:%M}")
            msg = f"{const.MSG_BOOKING_EXTENDED}\nПереговорная: *{cr_name}*\nНовое время окончания: {new_end_str}"
            return True, msg
        elif rows_affected == 0:
            logger.warning(f"Попытка продления {booking_id}, но статус уже не 'active' (rows={rows_affected}).")
            return False, const.MSG_EXTEND_FAIL_NOT_ACTIVE
        else:
            logger.error(f"Ошибка выполнения UPDATE при продлении брони {booking_id} (rows_affected is None).")
            return False, const.MSG_ERROR_GENERAL
    except Exception as e:
        logger.error(f"Ошибка UPDATE при продлении брони {booking_id}: {e}", exc_info=True)
        return False, const.MSG_ERROR_GENERAL # <-- Неудача (НЕ пробрасываем)


def confirm_start_booking(db: Database, booking_id: int, user_id: int) -> bool:
     """ Подтверждает начало брони (устанавливает статус 'active'). """
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)
     if not booking_info:
         logger.warning(f"Не найдена бронь {booking_id} для подтверждения user {user_id}.")
         return False

     b_user_id = booking_info.get('user_id')
     b_status = booking_info.get('status')

     if b_user_id != user_id:
          logger.warning(f"Попытка подтвердить чужую бронь {booking_id} user {user_id}.")
          return False

     if b_status != 'pending_confirmation':
          if b_status == 'active': logger.info(f"Бронь {booking_id} уже активна (user {user_id})."); return True
          logger.warning(f"Попытка подтвердить бронь {booking_id} с неверным статусом '{b_status}' user {user_id}.")
          return False

     query = "UPDATE bookings SET status = 'active' WHERE id = %s AND status = 'pending_confirmation';"
     try:
         db.execute_query(query, (booking_id,), commit=True)
         updated_booking_info = find_booking_by_id(db, booking_id)
         if updated_booking_info and updated_booking_info.get('status') == 'active':
             logger.info(f"User {user_id} подтвердил бронь {booking_id}. Статус успешно изменен на 'active'.")
             return True
         else:
             logger.error(f"Не удалось подтвердить бронь {booking_id} (user {user_id}): статус не стал 'active' после UPDATE.")
             return False
     except Exception as e:
         logger.error(f"Ошибка UPDATE при подтверждении брони {booking_id} user {user_id}: {e}", exc_info=True)
         return False


def auto_cancel_unconfirmed_booking(db: Database, booking_id: int) -> Tuple[bool, Optional[int], Optional[str]]:
     """ Автоотмена неподтвержденной брони (статус 'pending_confirmation'). """
     logger.debug(f"Проверка автоотмены для booking_id {booking_id}...")
     booking_info: Optional[BookingRow] = find_booking_by_id(db, booking_id)

     if booking_info:
          b_user_id = booking_info.get('user_id')
          cr_name = booking_info.get('cr_name')
          b_status = booking_info.get('status')

          if b_status == 'pending_confirmation':
               logger.info(f"Бронь {booking_id} (user {b_user_id}) подлежит автоотмене (status='pending_confirmation').")
               try:
                   success, _, _ = cancel_booking(db, booking_id, user_id=None, is_admin_cancel=True)
                   if success:
                       logger.info(f"Бронь {booking_id} успешно автоматически отменена.")
                       return True, b_user_id, cr_name
                   else:
                       logger.error(f"Не удалось автоматически отменить бронь {booking_id}.")
                       return False, b_user_id, cr_name
               except Exception as e_cancel:
                    logger.error(f"Ошибка при вызове cancel_booking в auto_cancel для {booking_id}: {e_cancel}", exc_info=True)
                    return False, b_user_id, cr_name
          else:
               logger.debug(f"Автоотмена для брони {booking_id} не требуется (status='{b_status}').")
               return False, b_user_id, cr_name
     else:
         logger.warning(f"Не найдена бронь {booking_id} для проверки автоотмены.")
         return False, None, None


def get_bookings_for_notification_schedule(db: Database) -> List[Tuple[int, int, int, datetime, datetime, str]]:
    """ Получает подтвержденные и активные брони для планировщика уведомлений. """
    now_naive = datetime.now()
    query = """
        SELECT b.id, b.user_id, b.cr_id, b.time_start, b.time_end, cr.cr_name
        FROM bookings b
        JOIN conferenceroom cr ON b.cr_id = cr.id
        WHERE b.status IN ('pending_confirmation', 'confirmed', 'active')
        AND b.time_end > %s
        ORDER BY b.id;
    """
    try:
        results_dict: QueryResult = db.execute_query(query, (now_naive,), fetch_results=True)
        results_tuple: List[Tuple[int, int, int, datetime, datetime, str]] = []
        if results_dict:
            for row in results_dict:
                if all(k in row for k in ('id', 'user_id', 'cr_id', 'time_start', 'time_end', 'cr_name')) \
                    and isinstance(row['time_start'], datetime) \
                    and isinstance(row['time_end'], datetime):
                    results_tuple.append((
                        row['id'], row['user_id'], row['cr_id'],
                        row['time_start'], row['time_end'], row['cr_name']
                    ))
                else:
                    logger.warning(f"Неполные/некорректные данные для уведомлений: {row}")
        logger.debug(f"Найдено {len(results_tuple)} броней для планирования уведомлений.")
        return results_tuple
    except Exception as e:
        logger.error(f"Ошибка get_bookings_for_notification_schedule: {e}", exc_info=True)
        raise e

# --- START OF NEW FUNCTION in services/booking_service.py ---

def auto_finish_booking(db: Database, booking_id: int) -> bool:
    """
    Автоматически завершает бронирование, меняя статус с 'active' на 'finished'.
    Вызывается по расписанию при наступлении времени окончания.
    """
    logger.debug(f"Попытка автоматического завершения брони {booking_id}...")
    # Сначала проверим текущий статус
    booking_info = find_booking_by_id(db, booking_id)
    current_status = booking_info.get('status') if booking_info else None

    if current_status == 'active':
        finish_time_ts = datetime.now() # Фактическое время завершения
        query = "UPDATE bookings SET status = 'finished', finish = %s WHERE id = %s AND status = 'active';"
        params = (finish_time_ts, booking_id)
        try:
            rows_affected = db.execute_query(query, params, commit=True, fetch_results=False)
            if rows_affected is not None and rows_affected > 0:
                logger.info(f"Бронь {booking_id} автоматически завершена (статус 'finished'). Время: {finish_time_ts}")
                return True
            elif rows_affected == 0:
                # Статус мог измениться между проверкой и обновлением
                logger.warning(f"Не удалось автоматически завершить бронь {booking_id} (status уже не 'active'?)")
                return False
            else: # Ошибка execute_query
                logger.error(f"Ошибка execute_query при автоматическом завершении брони {booking_id}.")
                return False
        except Exception as e:
            logger.error(f"Ошибка UPDATE при автоматическом завершении брони {booking_id}: {e}", exc_info=True)
            return False
    elif current_status == 'finished':
        logger.debug(f"Бронь {booking_id} уже была завершена ранее.")
        return True # Считаем успехом, т.к. цель достигнута
    else:
        logger.warning(f"Автоматическое завершение для брони {booking_id} не требуется (статус '{current_status}').")
        return False # Не было статуса 'active'
# --- END OF auto_finish_booking FUNCTION ---
def get_bookings_by_date_text(db: Database, selected_date: date) -> str:
    """Форматирует бронирования на дату в текст С УЧАСТНИКАМИ и ссылкой на график."""
    try:
        bookings: List[BookingRow] = get_bookings_by_date(db, selected_date)
    except Exception:
        return f"Не удалось получить бронирования на {_format_date(selected_date)}."

    date_str_title = _format_date(selected_date)
    date_str_link = selected_date.strftime('%Y-%m-%d') # Формат для URL

    # --- ДОБАВЛЕНО: Ссылка на тепловую карту ---
    # !!! ЗАМЕНИТЕ URL на актуальный адрес вашего Dash приложения !!!
    # Можно вынести в .env или config.py: HEATMAP_BASE_URL = os.getenv("HEATMAP_BASE_URL", "http://localhost:8081")
    heatmap_base_url = os.getenv("HEATMAP_BASE_URL", "http://192.168.1.139:8081") # Пример
    # Формируем ссылку с параметром даты (Dash сам обработает)
    # Хотя в текущей реализации Dash дата выбирается на странице,
    # даем прямую ссылку на базовый URL визуализации.
    # heatmap_url = f"{heatmap_base_url}?date={date_str_link}" # Если бы Dash принимал дату из URL
    heatmap_url = heatmap_base_url
    link_text = f"📊 <a href='{heatmap_url}'>График занятости на {date_str_title}</a>\n"
    # --- КОНЕЦ ДОБАВЛЕНИЯ ---

    if not bookings:
        # Не добавляем ссылку, если броней нет
        if selected_date == date.today(): return f"Нет предстоящих бронирований на сегодня ({date_str_title})."
        else: return f"Нет бронирований на {date_str_title}."

    # Используем HTML для форматирования всего сообщения
    response_lines = [f"<b>Бронирования на {date_str_title}:</b>"]
    response_lines.append(link_text) # Добавляем ссылку после заголовка

    for booking in bookings:
        # --- ИЗМЕНЕНО: Вызываем format_booking_info_html ---
        response_lines.append(format_booking_info_html( # Вызываем HTML-версию форматтера
            cr_name=booking.get('cr_name'),
            date_val=booking.get('date'),
            time_start=booking.get('time_start'),
            time_end=booking.get('time_end'),
            user_name=booking.get('user_fi'),
            participant_names=booking.get('participant_names')
        ))
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        status = booking.get('status')
        if status not in ['pending_confirmation', 'confirmed', 'active']:
            status_text = status.replace('_', ' ').capitalize() if status else 'Unknown'
            response_lines.append(f"<i>Статус: {status_text}</i>") # Используем курсив
        response_lines.append("<pre>--------------------</pre>") # Используем pre для разделителя

    if len(response_lines) > 2: response_lines.pop() # Удаляем последний разделитель

    response = "\n".join(response_lines)

    # Обрезка сообщения, если слишком длинное (без изменений)
    if len(response) > const.MAX_MESSAGE_LENGTH:
        response = response[:const.MAX_MESSAGE_LENGTH - 30] + "\n... (список слишком длинный)"
        logger.warning(f"Список броней {date_str_title} обрезан.")

    return response

# --- ДОБАВЛЕНО: HTML версия форматтера ---
def format_booking_info_html(
    cr_name: Optional[str],
    date_val: Optional[date],
    time_start: Optional[Union[datetime, time]],
    time_end: Optional[Union[datetime, time]],
    user_name: Optional[str] = None, # Организатор
    participant_names: Optional[List[str]] = None # Список имен участников
) -> str:
    """Вспомогательная функция для форматирования информации о бронировании в HTML."""
    cr_name_str = telebot.formatting.escape_html(cr_name or "???")
    date_str = _format_date(date_val)
    start_str = _format_time(time_start)
    end_str = _format_time(time_end)

    info_lines = [f"🚪 <b>{cr_name_str}</b>"] # Используем <b> для комнаты
    if user_name: info_lines.append(f"👤 Организатор: {telebot.formatting.escape_html(user_name)}")
    info_lines.append(f"🗓️ Дата: {date_str}")
    info_lines.append(f"⏰ Время: {start_str} - {end_str}")

    if participant_names:
        info_lines.append("👥 Участники:")
        for name in participant_names:
            info_lines.append(f"  - {telebot.formatting.escape_html(name)}")

    return "\n".join(info_lines)
# --- КОНЕЦ ДОБАВЛЕНИЯ ---
# --- END OF FILE services/booking_service.py ---