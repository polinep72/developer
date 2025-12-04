"""Общая логика работы со слотами WSB.

Единое ядро для генерации и управления слотами бронирования.
Используется в боте и портале.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta, time
from typing import List, Iterable, Tuple, Optional, Any, Dict

from .constants import WORKING_HOURS_START, WORKING_HOURS_END, BOOKING_TIME_STEP_MINUTES


@dataclass
class SlotSpec:
    """Описание слота без привязки к БД (для внутренних расчётов ядра)."""

    equipment_id: int
    slot_start: datetime
    slot_end: datetime


def generate_daily_slots(target_date: date, now: datetime | None = None) -> List[datetime]:
    """Сгенерировать список datetime-слотов для указанной даты.

    Временной диапазон и шаг берём из общих констант ядра.
    Если передан `now`, он пока не используется (фильтрация делается выше).
    """

    start_dt = datetime.combine(target_date, WORKING_HOURS_START)
    end_dt = datetime.combine(target_date, WORKING_HOURS_END)
    step = timedelta(minutes=BOOKING_TIME_STEP_MINUTES)

    slots: List[datetime] = []
    current = start_dt
    while current < end_dt:
        slots.append(current)
        current += step
    return slots


DDL_CREATE_TIME_SLOTS_TABLE = """
-- Черновое определение таблицы слотов ядра WSB.

CREATE TABLE IF NOT EXISTS wsb_time_slots (
    id           SERIAL PRIMARY KEY,
    equipment_id INTEGER      NOT NULL,
    slot_start   TIMESTAMP    NOT NULL,
    slot_end     TIMESTAMP    NOT NULL,
    status       TEXT         NOT NULL DEFAULT 'free', -- free/booked/blocked
    booking_id   INTEGER      NULL,
    CONSTRAINT wsb_time_slots_uniq UNIQUE (equipment_id, slot_start, slot_end)
);
""".strip()


def build_slots_specs_for_day(equipment_id: int, target_date: date) -> List[SlotSpec]:
    """Построить список SlotSpec для указанного оборудования и даты.

    Это чистый расчёт, без доступа к БД. Используется для первоначального
    наполнения таблицы слотов или пересчёта при изменении настроек времени.
    """

    slots_start = generate_daily_slots(target_date)
    step = timedelta(minutes=BOOKING_TIME_STEP_MINUTES)

    specs: List[SlotSpec] = []
    for start_dt in slots_start:
        specs.append(
            SlotSpec(
                equipment_id=equipment_id,
                slot_start=start_dt,
                slot_end=start_dt + step,
            )
        )
    return specs


def describe_slots_for_debug(slots: Iterable[SlotSpec]) -> str:
    """Вспомогательная функция: текстовое представление списка слотов.

    Полезно для логов и отладки на стороне ядра.
    """

    return ", ".join(f"{s.equipment_id}@{s.slot_start:%Y-%m-%d %H:%M}-{s.slot_end:%H:%M}" for s in slots)


def cleanup_old_slots_sql() -> str:
    """SQL для очистки слотов старых дат.

    Удаляет все записи, у которых slot_start < текущей даты.
    История при этом остаётся в таблице bookings, слоты — только для будущего.
    """

    return (
        "DELETE FROM wsb_time_slots "
        "WHERE slot_start::date < CURRENT_DATE;"
    )


def calculate_available_slots_from_bookings(
    bookings: List[Dict[str, Any]],
    equipment_id: int,
    selected_date: date,
    now_dt: Optional[datetime] = None
) -> List[Tuple[time, time]]:
    """
    Вычисляет доступные временные слоты на основе списка бронирований.
    
    Унифицированная логика для бота и портала.
    Учитывает рабочие часы, текущее время (для сегодня) и минимальный шаг.
    
    Args:
        bookings: Список бронирований (словари с ключами 'time_start', 'time_end', 'equip_id')
        equipment_id: ID оборудования
        selected_date: Дата для расчета слотов
        now_dt: Текущее время (если None, используется datetime.now())
    
    Returns:
        Список кортежей (start_time, end_time) доступных слотов
    """
    if now_dt is None:
        now_dt = datetime.now()
    
    # Фильтруем бронирования для данного оборудования
    equipment_bookings = [
        b for b in bookings
        if b.get('equip_id') == equipment_id
           and isinstance(b.get('time_start'), datetime)
           and isinstance(b.get('time_end'), datetime)
    ]
    sorted_bookings = sorted(equipment_bookings, key=lambda b: b['time_start'])

    available_slots: List[Tuple[time, time]] = []
    work_start_time = WORKING_HOURS_START
    work_end_time = WORKING_HOURS_END
    min_step_delta = timedelta(minutes=BOOKING_TIME_STEP_MINUTES)
    
    if isinstance(work_start_time, datetime):
        work_start_time = work_start_time.time()
    if isinstance(work_end_time, datetime):
        work_end_time = work_end_time.time()

    # Определяем самое раннее время начала для сегодня
    today = now_dt.date()
    is_today = (selected_date == today)
    earliest_start_dt_today = now_dt

    if is_today:
        # Округляем текущее время ВВЕРХ до ближайшего шага
        minutes_to_add = BOOKING_TIME_STEP_MINUTES - (now_dt.minute % BOOKING_TIME_STEP_MINUTES) \
                        if now_dt.minute % BOOKING_TIME_STEP_MINUTES != 0 else 0
        earliest_start_dt_today = (now_dt + timedelta(minutes=minutes_to_add)).replace(second=0, microsecond=0)

    # Определяем начальную точку для поиска слотов
    effective_start_dt = datetime.combine(selected_date, work_start_time)
    if is_today:
        effective_start_dt = max(effective_start_dt, earliest_start_dt_today)

    current_time_dt = effective_start_dt
    work_end_dt = datetime.combine(selected_date, work_end_time)

    # Обрабатываем бронирования и находим свободные слоты
    for booking in sorted_bookings:
        booking_start_dt = booking['time_start'].replace(tzinfo=None)
        booking_end_dt = booking['time_end'].replace(tzinfo=None)
        
        # Пропускаем бронирования вне выбранной даты
        if booking_end_dt.date() < selected_date or booking_start_dt.date() > selected_date:
            continue
        if booking_start_dt.date() < selected_date:
            booking_start_dt = datetime.combine(selected_date, time(0, 0))
        if booking_end_dt.date() > selected_date:
            booking_end_dt = datetime.combine(selected_date, time(23, 59, 59))

        # Проверяем слот перед бронью
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

        current_time_dt = max(current_time_dt, booking_end_dt)
        if is_today:
            current_time_dt = max(current_time_dt, earliest_start_dt_today)

    # Проверяем промежуток после последней брони до конца рабочего дня
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

    return available_slots
