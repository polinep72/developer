"""Общие модели домена WSB.

Здесь собраны базовые сущности, которые должны быть едиными
для Telegram‑бота и веб‑портала:
- User
- Equipment
- Booking
- TimeSlot

Файл не привязан к конкретной ORM, это «контракт» ядра.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum
from typing import Optional, Dict, Any


class BookingStatus(str, Enum):
    """Базовые статусы брони.

    Фактические статусы в БД бота и портала могут отличаться,
    но ядро будет приводить их к этому набору.
    """

    ACTIVE = "active"           # Активное бронирование (cancel=FALSE, finish=NULL, time_end >= now)
    CANCELLED = "cancelled"     # Отменено (cancel=TRUE)
    FINISHED = "finished"       # Завершено (finish IS NOT NULL или time_end < now)
    PLANNED = "planned"         # Запланировано (time_start > now, но еще не началось)


@dataclass
class User:
    """Унифицированное представление пользователя."""
    id: int
    tg_id: Optional[int] = None
    fio: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False
    is_blocked: bool = False
    is_active: bool = True


@dataclass
class Equipment:
    """Унифицированное представление оборудования."""
    id: int
    name: str
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    note: Optional[str] = None


@dataclass
class Booking:
    """Унифицированное представление брони.
    
    Соответствует структуре таблицы bookings в БД:
    - id, user_id, equip_id (equipment_id), date, time_start, time_end
    - cancel (boolean), finish (datetime или NULL)
    - time_interval, duration, data_booking
    """

    id: int
    user_id: int
    equipment_id: int
    date: date
    time_start: datetime
    time_end: datetime
    status: BookingStatus
    
    # Дополнительные поля из БД
    cancel: bool = False
    finish: Optional[datetime] = None
    time_interval: Optional[str] = None
    duration: Optional[float] = None  # в часах
    data_booking: Optional[datetime] = None
    
    # Дополнительные поля из JOIN
    user_fio: Optional[str] = None
    equipment_name: Optional[str] = None


def determine_booking_status(
    cancel: bool,
    finish: Optional[datetime],
    time_start: datetime,
    time_end: datetime,
    now: Optional[datetime] = None
) -> BookingStatus:
    """
    Определяет статус брони на основе полей из БД.
    
    Args:
        cancel: Флаг отмены брони
        finish: Время завершения брони (если есть)
        time_start: Время начала брони
        time_end: Время окончания брони
        now: Текущее время (если None, используется datetime.now())
    
    Returns:
        BookingStatus: Статус брони
    """
    if now is None:
        now = datetime.now()
    
    if cancel:
        return BookingStatus.CANCELLED
    if finish is not None:
        return BookingStatus.FINISHED
    if now >= time_end:
        return BookingStatus.FINISHED
    if now < time_start:
        return BookingStatus.PLANNED
    return BookingStatus.ACTIVE


def booking_from_db_row(row: Dict[str, Any], now: Optional[datetime] = None) -> Booking:
    """
    Создает объект Booking из строки БД.
    
    Поддерживает разные варианты именования полей:
    - equip_id (бот) или equipment_id (портал)
    - user_fi или fio для имени пользователя
    - name_equip или equipment_name для названия оборудования
    
    Args:
        row: Словарь с данными из БД
        now: Текущее время (если None, используется datetime.now())
    
    Returns:
        Booking: Объект брони
    """
    equipment_id = row.get('equip_id') or row.get('equipment_id')
    if equipment_id is None:
        raise ValueError("Не найдено поле equipment_id/equip_id в строке БД")
    
    time_start = row.get('time_start')
    time_end = row.get('time_end')
    if not isinstance(time_start, datetime) or not isinstance(time_end, datetime):
        raise ValueError("time_start и time_end должны быть datetime")
    
    cancel = bool(row.get('cancel', False))
    finish = row.get('finish')
    if finish is not None and not isinstance(finish, datetime):
        finish = None
    
    status = determine_booking_status(cancel, finish, time_start, time_end, now)
    
    return Booking(
        id=row['id'],
        user_id=row['user_id'],
        equipment_id=equipment_id,
        date=row.get('date') or time_start.date(),
        time_start=time_start,
        time_end=time_end,
        status=status,
        cancel=cancel,
        finish=finish,
        time_interval=row.get('time_interval'),
        duration=row.get('duration'),
        data_booking=row.get('data_booking'),
        user_fio=row.get('user_fi') or row.get('fio'),
        equipment_name=row.get('name_equip') or row.get('equipment_name'),
    )


class TimeSlotStatus(str, Enum):
    """Статусы временного слота в ядровой таблице слотов."""

    FREE = "free"          # свободен
    BOOKED = "booked"      # занят подтверждённой бронью
    BLOCKED = "blocked"    # зарезервирован системой/админом


@dataclass
class TimeSlot:
    """Слот времени для конкретного оборудования.

    Предполагаем, что в БД будет таблица вида wsb_time_slots
    с полями вида (equipment_id, slot_start, slot_end, status, booking_id).
    """

    id: int
    equipment_id: int
    slot_start: datetime
    slot_end: datetime
    status: TimeSlotStatus
    booking_id: Optional[int] = None
