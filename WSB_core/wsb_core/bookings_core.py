"""Общая бизнес-логика бронирований для WSB."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Protocol

from .constants import (
    WORKING_HOURS_START,
    WORKING_HOURS_END,
    BOOKING_TIME_STEP_MINUTES,
    MAX_BOOKING_DURATION_HOURS,
)
from .models import Booking, booking_from_db_row, BookingStatus

BOOKING_STEP = timedelta(minutes=BOOKING_TIME_STEP_MINUTES)
BOOKING_START_TIME = WORKING_HOURS_START
BOOKING_END_TIME = WORKING_HOURS_END
MAX_DURATION = timedelta(hours=MAX_BOOKING_DURATION_HOURS)


class CursorProtocol(Protocol):
    def execute(self, query: Any, params: Any = ...) -> Any: ...
    def fetchone(self) -> Optional[Any]: ...
    def fetchall(self) -> List[Any]: ...


@dataclass
class BookingCoreResult:
    success: bool
    booking: Optional[Booking] = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    conflicts: Optional[List[Dict[str, Any]]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


def create_booking_core(
    cur: CursorProtocol,
    *,
    user_id: int,
    equipment_id: int,
    target_date: date,
    start_time_str: str,
    duration_minutes: int,
    ensure_user_active: bool = True,
    sync_slots: bool = False,
) -> BookingCoreResult:
    """Создание бронирования с едиными проверками."""

    try:
        if ensure_user_active:
            _ensure_user_active(cur, user_id)

        start_dt = _combine_datetime(target_date, start_time_str)
        duration = timedelta(minutes=duration_minutes)
        if duration <= timedelta(0) or duration > MAX_DURATION or duration_minutes % BOOKING_TIME_STEP_MINUTES != 0:
            return BookingCoreResult(False, message="Недопустимая длительность работы", error_code="invalid_duration")

        end_dt = start_dt + duration
        if not _is_within_day(start_dt, end_dt):
            return BookingCoreResult(False, message="Интервал выходит за рамки рабочего дня", error_code="outside_workday")

        now = datetime.now()
        if start_dt < now:
            return BookingCoreResult(False, message="Нельзя бронировать прошедшее время", error_code="past_time")

        conflicts = _find_conflicts(cur, equipment_id, start_dt, end_dt)
        if conflicts:
            return BookingCoreResult(False, message="Интервал занят", error_code="conflict", conflicts=conflicts)

        row = _insert_booking_row(cur, user_id, equipment_id, start_dt, end_dt, duration)

        if sync_slots:
            _sync_slots(cur, equipment_id, target_date, start_dt, end_dt, booked=True, booking_id=row["id"])

        booking = booking_from_db_row(row)
        return BookingCoreResult(True, booking=booking, extra={"start_dt": start_dt, "end_dt": end_dt})
    except ValueError as exc:
        return BookingCoreResult(False, message=str(exc), error_code="invalid_input")
    except Exception as exc:
        return BookingCoreResult(False, message=f"Не удалось создать бронирование: {exc}", error_code="internal_error")


def cancel_booking_core(
    cur: CursorProtocol,
    *,
    booking_id: int,
    actor_user_id: Optional[int] = None,
    is_admin: bool = False,
    sync_slots: bool = False,
) -> BookingCoreResult:
    """Отмена бронирования."""

    try:
        row = _fetch_booking_for_cancel(cur, booking_id, actor_user_id, is_admin)
        if not row:
            return BookingCoreResult(False, message="Бронирование не найдено или нет прав", error_code="not_found")

        if row.get("cancel"):
            return BookingCoreResult(False, message="Бронирование уже отменено", error_code="already_cancelled")
        if row.get("finish"):
            return BookingCoreResult(False, message="Бронирование уже завершено", error_code="already_finished")

        cur.execute("UPDATE bookings SET cancel = TRUE WHERE id = %s", (booking_id,))

        if sync_slots:
            start_dt = row.get("time_start")
            end_dt = row.get("time_end")
            equipment_id_val = row.get("equip_id") or row.get("equipment_id")
            booking_date = row.get("date")
            if (
                isinstance(start_dt, datetime)
                and isinstance(end_dt, datetime)
                and isinstance(booking_date, date)
                and isinstance(equipment_id_val, int)
            ):
                _sync_slots(cur, equipment_id_val, booking_date, start_dt, end_dt, booked=False, booking_id=None)

        booking = booking_from_db_row(row)
        booking.cancel = True
        booking.status = BookingStatus.CANCELLED
        return BookingCoreResult(True, booking=booking, extra={"booking_row": row})
    except ValueError as exc:
        return BookingCoreResult(False, message=str(exc), error_code="invalid_input")
    except Exception as exc:
        return BookingCoreResult(False, message=f"Не удалось отменить бронирование: {exc}", error_code="internal_error")


def _combine_datetime(target_date: date, start_time_str: str) -> datetime:
    try:
        hours, minutes = map(int, start_time_str.split(":"))
    except ValueError as exc:
        raise ValueError("Некорректный формат времени.") from exc

    start_time = time(hour=hours, minute=minutes)
    if start_time < BOOKING_START_TIME or start_time > BOOKING_END_TIME:
        raise ValueError("Время начала вне допустимого диапазона.")
    return datetime.combine(target_date, start_time)


def extend_booking_core(
    cur: CursorProtocol,
    *,
    booking_id: int,
    actor_user_id: Optional[int],
    extension_minutes: int,
    is_admin: bool = False,
    sync_slots: bool = False,
) -> BookingCoreResult:
    """
    Продление существующего бронирования.

    Правила:
    - может выполнять владелец брони или админ;
    - новое время окончания не выходит за пределы рабочего дня;
    - общая длительность не превышает MAX_DURATION;
    - нет конфликтов с другими бронированиями.
    """
    try:
        if extension_minutes <= 0 or extension_minutes % BOOKING_TIME_STEP_MINUTES != 0:
            return BookingCoreResult(
                False,
                message="Недопустимая длительность продления",
                error_code="invalid_extension",
            )

        ext_delta = timedelta(minutes=extension_minutes)

        # Загружаем бронь и проверяем права
        row = _fetch_booking_for_extend(cur, booking_id)
        if not row:
            return BookingCoreResult(
                False, message="Бронирование не найдено", error_code="not_found"
            )

        booking_user_id = row.get("user_id")
        if not is_admin:
            if actor_user_id is None or booking_user_id != actor_user_id:
                return BookingCoreResult(
                    False,
                    message="Нет прав на продление этой брони",
                    error_code="forbidden",
                )

        cancel_flag = row.get("cancel")
        finish_dt = row.get("finish")
        time_start = row.get("time_start")
        time_end = row.get("time_end")

        if cancel_flag:
            return BookingCoreResult(
                False, message="Бронирование отменено", error_code="cancelled"
            )
        if finish_dt is not None:
            return BookingCoreResult(
                False, message="Бронирование завершено", error_code="finished"
            )
        if not isinstance(time_start, datetime) or not isinstance(time_end, datetime):
            return BookingCoreResult(
                False, message="Некорректные данные бронирования", error_code="invalid_data"
            )

        now = datetime.now()
        if time_end <= now:
            return BookingCoreResult(
                False,
                message="Бронирование уже завершилось",
                error_code="already_ended",
            )

        new_end_dt = time_end + ext_delta
        work_end_dt = datetime.combine(time_end.date(), BOOKING_END_TIME)
        if new_end_dt > work_end_dt:
            return BookingCoreResult(
                False,
                message="Продление выходит за пределы рабочего дня",
                error_code="outside_workday",
            )

        total_duration = new_end_dt - time_start
        if total_duration > MAX_DURATION:
            return BookingCoreResult(
                False,
                message="Превышена максимальная длительность работы",
                error_code="limit_exceeded",
            )

        equipment_id_val = row.get("equip_id") or row.get("equipment_id")
        if not isinstance(equipment_id_val, int):
            return BookingCoreResult(
                False, message="Некорректный идентификатор оборудования", error_code="invalid_data"
            )

        # Проверяем конфликты в диапазоне продления
        conflicts = _find_conflicts(
            cur,
            equipment_id_val,
            time_end,
            new_end_dt,
            exclude_booking_id=booking_id,
        )
        if conflicts:
            return BookingCoreResult(
                False,
                message="Интервал продления занят",
                error_code="conflict",
                conflicts=conflicts,
            )

        new_time_interval = f"{time_start.strftime('%H:%M')}-{new_end_dt.strftime('%H:%M')}"
        duration_in_hours = total_duration.total_seconds() / 3600.0

        cur.execute(
            """
            UPDATE bookings
            SET time_end = %s,
                time_interval = %s,
                duration = %s,
                extension = COALESCE(extension, interval '0 hours') + %s
            WHERE id = %s
              AND cancel = FALSE
              AND finish IS NULL
            """,
            (new_end_dt, new_time_interval, duration_in_hours, ext_delta, booking_id),
        )

        booking_date = row.get("date")
        if (
            sync_slots
            and isinstance(booking_date, date)
        ):
            _sync_slots(
                cur,
                equipment_id_val,
                booking_date,
                time_end,
                new_end_dt,
                booked=True,
                booking_id=booking_id,
            )

        # Обновляем представление брони
        row["time_end"] = new_end_dt
        row["time_interval"] = new_time_interval
        row["duration"] = duration_in_hours
        booking = booking_from_db_row(row)

        return BookingCoreResult(
            True,
            booking=booking,
            extra={
                "old_end": time_end,
                "new_end": new_end_dt,
                "extension_minutes": extension_minutes,
                "booking_row": row,
            },
        )
    except ValueError as exc:
        return BookingCoreResult(False, message=str(exc), error_code="invalid_input")
    except Exception as exc:
        return BookingCoreResult(
            False, message=f"Не удалось продлить бронирование: {exc}", error_code="internal_error"
        )


def _is_within_day(start_dt: datetime, end_dt: datetime) -> bool:
    day_start = datetime.combine(start_dt.date(), BOOKING_START_TIME)
    day_end = datetime.combine(start_dt.date(), BOOKING_END_TIME) + BOOKING_STEP
    return day_start <= start_dt < day_end and start_dt < end_dt <= day_end


def _ensure_user_active(cur: CursorProtocol, user_id: int) -> None:
    cur.execute("SELECT is_blocked FROM users WHERE users_id = %s", (user_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Пользователь не найден.")
    if row.get("is_blocked"):
        raise ValueError("Ваш профиль заблокирован, бронирование недоступно.")


def _find_conflicts(
    cur: CursorProtocol,
    equipment_id: int,
    start_dt: datetime,
    end_dt: datetime,
    exclude_booking_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    params: List[Any] = [equipment_id, end_dt, start_dt]
    query = """
        SELECT b.id, b.time_start, COALESCE(b.finish, b.time_end) AS time_end, u.fi
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        WHERE b.equip_id = %s
          AND b.cancel = FALSE
          AND b.time_start < %s
          AND COALESCE(b.finish, b.time_end) > %s
    """
    if exclude_booking_id is not None:
        query += " AND b.id <> %s"
        params.append(exclude_booking_id)

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conflicts: List[Dict[str, Any]] = []
    for row in rows:
        conflicts.append(
            {
                "id": row.get("id"),
                "user": row.get("fi") or "Пользователь",
                "time_start": row["time_start"].strftime("%H:%M"),
                "time_end": row["time_end"].strftime("%H:%M"),
            }
        )
    return conflicts


def _insert_booking_row(
    cur: CursorProtocol,
    user_id: int,
    equipment_id: int,
    start_dt: datetime,
    end_dt: datetime,
    duration: timedelta,
) -> Dict[str, Any]:
    time_interval = f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"
    duration_in_hours = duration.total_seconds() / 3600.0
    data_booking = datetime.now()

    cur.execute(
        """
        INSERT INTO bookings (user_id, equip_id, date, time_start, time_end,
                              time_interval, duration, cancel, finish, data_booking)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, %s)
        RETURNING id, user_id, equip_id, date, time_start, time_end,
                  time_interval, duration, cancel, finish, data_booking
        """,
        (
            user_id,
            equipment_id,
            start_dt.date(),
            start_dt,
            end_dt,
            time_interval,
            duration_in_hours,
            data_booking,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("INSERT не вернул данные.")
    return row


def _fetch_booking_for_cancel(
    cur: CursorProtocol,
    booking_id: int,
    actor_user_id: Optional[int],
    is_admin: bool,
) -> Optional[Dict[str, Any]]:
    if is_admin:
        cur.execute(
            """
            SELECT b.*, e.name_equip, u.email, u.first_name, u.last_name
            FROM bookings b
            JOIN equipment e ON b.equip_id = e.id
            JOIN users u ON b.user_id = u.users_id
            WHERE b.id = %s
            """,
            (booking_id,),
        )
    else:
        cur.execute(
            """
            SELECT b.*, e.name_equip, u.email, u.first_name, u.last_name
            FROM bookings b
            JOIN equipment e ON b.equip_id = e.id
            JOIN users u ON b.user_id = u.users_id
            WHERE b.id = %s AND b.user_id = %s
            """,
            (booking_id, actor_user_id),
        )
    return cur.fetchone()


def _sync_slots(
    cur: CursorProtocol,
    equipment_id: int,
    target_date: date,
    start_dt: datetime,
    end_dt: datetime,
    *,
    booked: bool,
    booking_id: Optional[int],
) -> None:
    try:
        from wsb_core.slots import DDL_CREATE_TIME_SLOTS_TABLE, build_slots_specs_for_day

        cur.execute(DDL_CREATE_TIME_SLOTS_TABLE)

        cur.execute(
            """
            SELECT COUNT(*) as cnt
            FROM wsb_time_slots
            WHERE equipment_id = %s AND DATE(slot_start) = %s
            """,
            (equipment_id, target_date),
        )
        row = cur.fetchone()
        if not row or row.get("cnt", 0) == 0:
            specs = build_slots_specs_for_day(equipment_id, target_date)
            for spec in specs:
                cur.execute(
                    "INSERT INTO wsb_time_slots (equipment_id, slot_start, slot_end, status) VALUES (%s, %s, %s, %s)",
                    (spec.equipment_id, spec.slot_start, spec.slot_end, "free"),
                )

        cur.execute(
            """
            UPDATE wsb_time_slots
            SET status = %s, booking_id = %s
            WHERE equipment_id = %s
              AND slot_start >= %s AND slot_end <= %s
            """,
            ("booked" if booked else "free", booking_id, equipment_id, start_dt, end_dt),
        )
    except Exception:
        # Ядро не должно падать из-за проблем с таблицей слотов – логика выше решает уведомлениями
        pass


def _fetch_booking_for_extend(
    cur: CursorProtocol,
    booking_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Получение брони для операции продления.

    Возвращает все поля bookings + имя оборудования (если нужно для логов/уведомлений).
    """
    cur.execute(
        """
        SELECT b.*, e.name_equip
        FROM bookings b
        JOIN equipment e ON b.equip_id = e.id
        WHERE b.id = %s
        """,
        (booking_id,),
    )
    return cur.fetchone()

