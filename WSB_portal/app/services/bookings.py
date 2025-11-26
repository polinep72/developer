from __future__ import annotations

import os
import csv
import io
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR.parent / ".env"

if load_dotenv:
    load_dotenv(ENV_PATH)

DB_HOST = os.getenv("POSTGRE_HOST") or os.getenv("DB_HOST")
DB_PORT = int(os.getenv("POSTGRE_PORT") or os.getenv("DB_PORT") or 5432)
DB_NAME = os.getenv("POSTGRE_DBNAME") or os.getenv("DB_NAME") or "RM"
DB_USER = os.getenv("POSTGRE_USER") or os.getenv("DB_USER")
DB_PASSWORD = os.getenv("POSTGRE_PASSWORD") or os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("POSTGRE_SSLMODE") or os.getenv("DB_SSLMODE") or "prefer"

SLOT_MINUTES = 30
BOOKING_STEP = timedelta(minutes=SLOT_MINUTES)
BOOKING_START_TIME = time(7, 0)
BOOKING_END_TIME = time(20, 0)
MAX_DURATION = timedelta(hours=12)


def _connect() -> psycopg.Connection:  # pyright: ignore
    if not DB_HOST or not DB_USER:
        raise psycopg.OperationalError("Параметры подключения к БД не заданы")  # pyright: ignore

    params = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "sslmode": DB_SSLMODE,
        "row_factory": dict_row,
        "connect_timeout": 5,
    }
    return psycopg.connect(**params)  # pyright: ignore


def get_categories() -> Dict[str, Any]:
    # Пытаемся получить из кэша
    try:
        from .cache import get_categories as get_cached_categories, set_categories
        cached = get_cached_categories()
        if cached:
            return {"data": cached}
    except Exception:
        pass
    
    query = "SELECT id, name_cat FROM cat ORDER BY name_cat ASC"
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(query)
            rows = cast(List[Dict[str, Any]], cur.fetchall())
        result = [{"id": row["id"], "name": row["name_cat"]} for row in rows]
        
        # Сохраняем в кэш
        try:
            from .cache import set_categories
            set_categories(result)
        except Exception:
            pass
        
        return {"data": result}
    except Exception as exc:  # pragma: no cover - логирование на уровне выше
        return {"error": f"Не удалось получить список категорий: {exc}"}


def get_equipment_by_category(category_id: int) -> Dict[str, Any]:
    # Пытаемся получить из кэша
    try:
        from .cache import get_equipment_list, set_equipment_list
        cached = get_equipment_list(category_id)
        if cached:
            return {"data": cached}
    except Exception:
        pass
    
    query = """
        SELECT id, name_equip
        FROM equipment
        WHERE category = %s
        ORDER BY name_equip ASC
    """
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(query, (category_id,))
            rows = cast(List[Dict[str, Any]], cur.fetchall())
        result = [{"id": row["id"], "name": row["name_equip"]} for row in rows]
        
        # Сохраняем в кэш
        try:
            from .cache import set_equipment_list
            set_equipment_list(category_id, result)
        except Exception:
            pass
        
        return {"data": result}
    except Exception as exc:
        return {"error": f"Не удалось получить оборудование: {exc}"}


def get_available_slots(equipment_id: int, target_date: date) -> Dict[str, Any]:
    try:
        bookings = _fetch_bookings(equipment_id, target_date)
        slots = _build_slots(target_date, bookings)
        return {
            "data": {
                "slots": slots,
                "step_minutes": SLOT_MINUTES,
                "start_time": BOOKING_START_TIME.strftime("%H:%M"),
                "end_time": BOOKING_END_TIME.strftime("%H:%M"),
            }
        }
    except Exception as exc:
        return {"error": f"Не удалось получить доступные интервалы: {exc}"}


def create_booking(
    user_id: int,
    equipment_id: int,
    target_date: date,
    start_time_str: str,
    duration_minutes: int,
) -> Dict[str, Any]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            _ensure_user_active(cur, user_id)

            start_dt = _combine_datetime(target_date, start_time_str)
            duration = timedelta(minutes=duration_minutes)
            if duration <= timedelta(0) or duration > MAX_DURATION or duration_minutes % SLOT_MINUTES != 0:
                raise ValueError("Недопустимая длительность работы.")

            end_dt = start_dt + duration
            if not _is_within_day(start_dt, end_dt):
                raise ValueError("Выбранный интервал выходит за рабочее время.")

            now = datetime.now()
            if start_dt < now:
                raise ValueError("Нельзя бронировать прошедшее время.")

            conflicts = _find_conflicts(cur, equipment_id, start_dt, end_dt)
            if conflicts:
                # Отправка уведомления администраторам о конфликте
                try:
                    from .notifications import send_booking_conflict_notification
                    from .auth import get_user_by_id
                    
                    # Получаем список администраторов
                    cur.execute("SELECT users_id, email FROM users WHERE is_admin = TRUE AND email IS NOT NULL")
                    admin_rows = cur.fetchall()
                    admin_emails = []
                    for row in admin_rows:
                        row_dict = cast(Dict[str, Any], row)
                        email = row_dict.get("email")
                        if email:
                            admin_emails.append(email)
                    
                    if admin_emails:
                        # Получаем название оборудования
                        cur.execute("SELECT name_equip FROM equipment WHERE id = %s", (equipment_id,))
                        equip_row = cur.fetchone()
                        if equip_row:
                            equip_dict = cast(Dict[str, Any], equip_row)
                            equipment_name = equip_dict.get("name_equip", "Оборудование")
                        else:
                            equipment_name = "Оборудование"
                        
                        # Отправляем уведомление о первом конфликте
                        if conflicts:
                            conflict = conflicts[0]
                            send_booking_conflict_notification(
                                admin_emails=admin_emails,
                                equipment_name=equipment_name,
                                booking_date=target_date,
                                start_time=start_dt.time(),
                                end_time=end_dt.time(),
                                conflicting_user=conflict.get("user", "Неизвестный пользователь"),
                                conflicting_time=conflict.get("time_start", "") + " - " + conflict.get("time_end", ""),
                            )
                except Exception as exc:
                    # Не прерываем выполнение при ошибке уведомления
                    print(f"[NOTIFICATION ERROR] Failed to send conflict notification: {exc}")
                
                return {"error": "Интервал занят", "conflicts": conflicts}

            booking_id = _insert_booking(cur, user_id, equipment_id, start_dt, end_dt, duration)
            conn.commit()
            
            # Инвалидация кэша тепловой карты для этой даты
            try:
                from .cache import invalidate_heatmap, invalidate_dashboard
                date_str = target_date.strftime("%Y-%m-%d")
                invalidate_heatmap(date_str)
                invalidate_dashboard()  # Дашборд тоже нужно обновить
            except Exception as exc:
                logger.warning(f"Ошибка при инвалидации кэша: {exc}")
            
            # Отправка уведомления о создании бронирования
            try:
                from .notifications import send_booking_created_notification, should_send_email_notification
                from .auth import get_user_by_id
                
                if should_send_email_notification(user_id):
                    user = get_user_by_id(user_id)
                    if user and user.get("email"):
                        # Получаем название оборудования
                        cur.execute("SELECT name_equip FROM equipment WHERE id = %s", (equipment_id,))
                        equip_row = cast(Optional[Dict[str, Any]], cur.fetchone())
                        equipment_name = equip_row.get("name_equip", "Оборудование") if equip_row else "Оборудование"
                        
                        user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "Пользователь"
                        send_booking_created_notification(
                            user_email=user["email"],
                            user_name=user_name,
                            equipment_name=equipment_name,
                            booking_date=target_date,
                            start_time=start_dt.time(),
                            end_time=end_dt.time(),
                        )
            except Exception as exc:
                # Не прерываем выполнение при ошибке уведомления
                print(f"[NOTIFICATION ERROR] Failed to send booking created notification: {exc}")
            
            return {
                "data": {
                    "booking_id": booking_id,
                    "start_time": start_dt.strftime("%H:%M"),
                    "end_time": end_dt.strftime("%H:%M"),
                }
            }
    except ValueError as exc:
        return {"error": str(exc)}
    except psycopg.OperationalError as exc:  # pyright: ignore
        return {"error": f"Ошибка подключения к БД: {exc}"}
    except Exception as exc:
        return {"error": f"Не удалось создать бронирование: {exc}"}


def _ensure_user_active(cur: psycopg.Cursor, user_id: int) -> None:  # pyright: ignore
    cur.execute("SELECT is_blocked FROM users WHERE users_id = %s", (user_id,))
    row = cast(Optional[Dict[str, Any]], cur.fetchone())
    if not row:
        raise ValueError("Пользователь не найден.")
    if row["is_blocked"]:
        raise ValueError("Ваш профиль заблокирован, бронирование недоступно.")


def _fetch_bookings(equipment_id: int, target_date: date) -> List[Tuple[datetime, datetime]]:
    query = """
        SELECT time_start, COALESCE(finish, time_end) AS time_end
        FROM bookings
        WHERE equip_id = %s
          AND date = %s
          AND cancel = FALSE
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(query, (equipment_id, target_date))
        rows = cast(List[Dict[str, Any]], cur.fetchall())

    bookings: List[Tuple[datetime, datetime]] = []
    for row in rows:
        start_dt = row["time_start"]
        end_dt = row["time_end"]
        if not start_dt or not end_dt:
            continue
        bookings.append((start_dt, end_dt))
    bookings.sort(key=lambda item: item[0])
    return bookings


def _build_slots(target_date: date, bookings: List[Tuple[datetime, datetime]]) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    now = datetime.now()
    start_dt = datetime.combine(target_date, BOOKING_START_TIME)
    end_dt = datetime.combine(target_date, BOOKING_END_TIME)

    iter_dt = start_dt
    while iter_dt <= end_dt:
        if target_date > now.date() or iter_dt >= now.replace(second=0, microsecond=0):
            available_minutes = _calculate_available_minutes(iter_dt, bookings, target_date)
            if available_minutes >= SLOT_MINUTES:
                slots.append(
                    {
                        "time": iter_dt.strftime("%H:%M"),
                        "max_duration_minutes": available_minutes,
                    }
                )
        iter_dt += BOOKING_STEP
    return slots


def _calculate_available_minutes(
    start_dt: datetime,
    bookings: List[Tuple[datetime, datetime]],
    target_date: date,
) -> int:
    max_end = min(
        start_dt + MAX_DURATION,
        datetime.combine(target_date, BOOKING_END_TIME) + BOOKING_STEP,
    )
    minutes = 0
    probe_end = start_dt + BOOKING_STEP

    while probe_end <= max_end:
        if _has_conflict(start_dt, probe_end, bookings):
            break
        minutes = int((probe_end - start_dt).total_seconds() // 60)
        probe_end += BOOKING_STEP
    return minutes


def _has_conflict(
    start_dt: datetime,
    end_dt: datetime,
    bookings: List[Tuple[datetime, datetime]],
) -> bool:
    for booked_start, booked_end in bookings:
        if start_dt < booked_end and end_dt > booked_start:
            return True
    return False


def _combine_datetime(target_date: date, start_time_str: str) -> datetime:
    try:
        hours, minutes = map(int, start_time_str.split(":"))
    except ValueError as exc:
        raise ValueError("Некорректный формат времени.") from exc
    start_time = time(hour=hours, minute=minutes)
    if start_time < BOOKING_START_TIME or start_time > BOOKING_END_TIME:
        raise ValueError("Время начала вне допустимого диапазона.")
    return datetime.combine(target_date, start_time)


def _is_within_day(start_dt: datetime, end_dt: datetime) -> bool:
    day_start = datetime.combine(start_dt.date(), BOOKING_START_TIME)
    day_end = datetime.combine(start_dt.date(), BOOKING_END_TIME) + BOOKING_STEP
    return day_start <= start_dt < day_end and start_dt < end_dt <= day_end


def _find_conflicts(
    cur: psycopg.Cursor,  # pyright: ignore
    equipment_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> List[Dict[str, Any]]:
    query = """
        SELECT b.time_start, COALESCE(b.finish, b.time_end) AS time_end, u.fi
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        WHERE b.equip_id = %s
          AND b.cancel = FALSE
          AND b.time_start < %s
          AND COALESCE(b.finish, b.time_end) > %s
    """
    cur.execute(query, (equipment_id, end_dt, start_dt))
    rows = cast(List[Dict[str, Any]], cur.fetchall())
    conflicts: List[Dict[str, Any]] = []
    for row in rows:
        conflicts.append(
            {
                "user": row["fi"] or "Пользователь",
                "time_start": row["time_start"].strftime("%H:%M"),
                "time_end": row["time_end"].strftime("%H:%M"),
            }
        )
    return conflicts


def get_user_bookings(user_id: int, target_date: Optional[date] = None) -> Dict[str, Any]:
    """Получить бронирования пользователя (опционально фильтр по дате)"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            if target_date:
                query = """
                    SELECT 
                        b.id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.time_interval,
                        b.duration,
                        b.cancel,
                        b.finish,
                        b.data_booking,
                        e.name_equip,
                        c.name_cat
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN cat c ON e.category = c.id
                    WHERE b.user_id = %s AND b.date = %s
                    ORDER BY b.date DESC, b.time_start ASC
                """
                cur.execute(query, (user_id, target_date))
            else:
                query = """
                    SELECT 
                        b.id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.time_interval,
                        b.duration,
                        b.cancel,
                        b.finish,
                        b.data_booking,
                        e.name_equip,
                        c.name_cat
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN cat c ON e.category = c.id
                    WHERE b.user_id = %s
                    ORDER BY b.date DESC, b.time_start ASC
                """
                cur.execute(query, (user_id,))
            rows = cast(List[Dict[str, Any]], cur.fetchall())
        return {"data": [_format_booking_row(row) for row in rows]}
    except Exception as exc:
        return {"error": f"Не удалось получить бронирования: {exc}"}


def get_all_bookings(target_date: Optional[date] = None) -> Dict[str, Any]:
    """Получить все бронирования (для админов, опционально фильтр по дате)"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            if target_date:
                query = """
                    SELECT 
                        b.id,
                        b.user_id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.time_interval,
                        b.duration,
                        b.cancel,
                        b.finish,
                        b.data_booking,
                        e.name_equip,
                        c.name_cat,
                        u.fi as user_name
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN cat c ON e.category = c.id
                    JOIN users u ON b.user_id = u.users_id
                    WHERE b.date = %s
                    ORDER BY b.date DESC, b.time_start ASC
                """
                cur.execute(query, (target_date,))
            else:
                query = """
                    SELECT 
                        b.id,
                        b.user_id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.time_interval,
                        b.duration,
                        b.cancel,
                        b.finish,
                        b.data_booking,
                        e.name_equip,
                        c.name_cat,
                        u.fi as user_name
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN cat c ON e.category = c.id
                    JOIN users u ON b.user_id = u.users_id
                    ORDER BY b.date DESC, b.time_start ASC
                """
                cur.execute(query)
            rows = cast(List[Dict[str, Any]], cur.fetchall())
        return {"data": [_format_booking_row_admin(row) for row in rows]}
    except Exception as exc:
        return {"error": f"Не удалось получить бронирования: {exc}"}


def cancel_booking(booking_id: int, user_id: int, is_admin: bool = False) -> Dict[str, Any]:
    """Отменить бронирование (пользователь может отменить только своё, админ - любое)"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            # Проверяем существование и права, получаем данные для уведомления
            if is_admin:
                query = """
                    SELECT b.user_id, b.cancel, b.finish, b.date, b.time_start, b.time_end,
                           e.name_equip, u.email, u.first_name, u.last_name
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN users u ON b.user_id = u.users_id
                    WHERE b.id = %s
                """
                cur.execute(query, (booking_id,))
            else:
                query = """
                    SELECT b.user_id, b.cancel, b.finish, b.date, b.time_start, b.time_end,
                           e.name_equip, u.email, u.first_name, u.last_name
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN users u ON b.user_id = u.users_id
                    WHERE b.id = %s AND b.user_id = %s
                """
                cur.execute(query, (booking_id, user_id))
            
            row = cast(Optional[Dict[str, Any]], cur.fetchone())
            if not row:
                return {"error": "Бронирование не найдено или нет прав на отмену"}
            
            if row["cancel"]:
                return {"error": "Бронирование уже отменено"}
            
            if row["finish"]:
                return {"error": "Бронирование уже завершено"}
            
            # Сохраняем данные для уведомления
            booking_user_id = row["user_id"]
            booking_date = row["date"]
            booking_start = row["time_start"]
            booking_end = row["time_end"]
            equipment_name = row.get("name_equip", "Оборудование")
            user_email = row.get("email")
            user_first_name = row.get("first_name", "")
            user_last_name = row.get("last_name", "")
            
            # Отменяем
            update_query = "UPDATE bookings SET cancel = TRUE WHERE id = %s"
            cur.execute(update_query, (booking_id,))
            conn.commit()
            
            # Инвалидация кэша тепловой карты для этой даты
            try:
                from .cache import invalidate_heatmap, invalidate_dashboard
                if isinstance(booking_date, date):
                    date_str = booking_date.strftime("%Y-%m-%d")
                elif isinstance(booking_date, datetime):
                    date_str = booking_date.date().strftime("%Y-%m-%d")
                else:
                    date_str = str(booking_date)
                invalidate_heatmap(date_str)
                invalidate_dashboard()  # Дашборд тоже нужно обновить
            except Exception as exc:
                logger.warning(f"Ошибка при инвалидации кэша: {exc}")
            
            # Отправка уведомления об отмене бронирования
            try:
                from .notifications import send_booking_cancelled_notification, should_send_email_notification
                
                if user_email and should_send_email_notification(booking_user_id):
                    user_name = f"{user_first_name} {user_last_name}".strip() or "Пользователь"
                    start_time = booking_start.time() if isinstance(booking_start, datetime) else booking_start
                    end_time = booking_end.time() if isinstance(booking_end, datetime) else booking_end
                    send_booking_cancelled_notification(
                        user_email=user_email,
                        user_name=user_name,
                        equipment_name=equipment_name,
                        booking_date=booking_date,
                        start_time=start_time,
                        end_time=end_time,
                    )
            except Exception as exc:
                # Не прерываем выполнение при ошибке уведомления
                print(f"[NOTIFICATION ERROR] Failed to send booking cancelled notification: {exc}")
            
            return {"data": {"message": "Бронирование отменено", "booking_id": booking_id}}
    except Exception as exc:
        return {"error": f"Не удалось отменить бронирование: {exc}"}


def export_bookings_csv(target_date: date, user_id: int, include_all: bool = False) -> Dict[str, Any]:
    """Сформировать CSV с бронированиями за выбранную дату."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            if include_all:
                query = """
                    SELECT 
                        b.id,
                        b.user_id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.time_interval,
                        b.duration,
                        b.cancel,
                        b.finish,
                        e.name_equip,
                        c.name_cat,
                        u.fi AS user_name
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN cat c ON e.category = c.id
                    JOIN users u ON b.user_id = u.users_id
                    WHERE b.date = %s
                    ORDER BY b.time_start ASC
                """
                cur.execute(query, (target_date,))
                rows = cast(List[Dict[str, Any]], cur.fetchall())
                formatted_rows = [_format_booking_row_admin(row) for row in rows]
            else:
                query = """
                    SELECT 
                        b.id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.time_interval,
                        b.duration,
                        b.cancel,
                        b.finish,
                        e.name_equip,
                        c.name_cat
                    FROM bookings b
                    JOIN equipment e ON b.equip_id = e.id
                    JOIN cat c ON e.category = c.id
                    WHERE b.user_id = %s AND b.date = %s
                    ORDER BY b.time_start ASC
                """
                cur.execute(query, (user_id, target_date))
                rows = cast(List[Dict[str, Any]], cur.fetchall())
                formatted_rows = [_format_booking_row(row) for row in rows]
    except Exception as exc:
        logger.error("Не удалось подготовить экспорт бронирований: %s", exc)
        return {"error": f"Не удалось подготовить экспорт: {exc}"}

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")

    common_header = [
        "Дата",
        "Время начала",
        "Время окончания",
        "Интервал",
        "Длительность (ч)",
        "Оборудование",
        "Категория",
    ]
    header = common_header.copy()
    if include_all:
        header.append("Пользователь")
    header.append("Статус")
    writer.writerow(header)

    for row in formatted_rows:
        date_str = row.get("date")
        if date_str:
            try:
                date_str = datetime.fromisoformat(date_str).strftime("%d.%m.%Y")
            except ValueError:
                pass
        duration_val = row.get("duration")
        if isinstance(duration_val, (int, float)):
            duration_str = f"{float(duration_val):.1f}"
        else:
            duration_str = ""
        csv_row = [
            date_str or "",
            row.get("time_start") or "",
            row.get("time_end") or "",
            row.get("time_interval") or "",
            duration_str,
            row.get("equipment") or "",
            row.get("category") or "",
        ]
        if include_all:
            csv_row.append(row.get("user_name") or "")
        csv_row.append(row.get("status") or "")
        writer.writerow(csv_row)

    csv_bytes = buffer.getvalue().encode("utf-8-sig")
    filename = f"bookings_{target_date.strftime('%Y%m%d')}_{'all' if include_all else 'mine'}.csv"
    return {"filename": filename, "content": csv_bytes, "rows": len(formatted_rows)}


def _format_booking_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Форматирование строки бронирования для обычного пользователя"""
    start_dt = row.get("time_start")
    end_dt = row.get("time_end")
    finish_dt = row.get("finish")
    booking_date = row.get("date")
    today = datetime.now().date()
    
    status = "Активное"
    if row.get("cancel"):
        status = "Отменено"
    elif finish_dt:
        status = "Завершено"
    elif start_dt and end_dt:
        now = datetime.now()
        if now < start_dt:
            status = "Запланировано"
        elif now >= end_dt:
            status = "Завершено"
    
    can_cancel = (
        bool(booking_date)
        and booking_date >= today
        and not row.get("cancel")
        and not finish_dt
    )

    return {
        "id": row["id"],
        "date": row["date"].isoformat() if row.get("date") else None,
        "time_start": start_dt.strftime("%H:%M") if start_dt else None,
        "time_end": end_dt.strftime("%H:%M") if end_dt else None,
        "time_interval": row.get("time_interval"),
        "duration": float(row.get("duration", 0)),
        "equipment": row.get("name_equip", ""),
        "category": row.get("name_cat", ""),
        "status": status,
        "can_cancel": can_cancel,
    }


def _format_booking_row_admin(row: Dict[str, Any]) -> Dict[str, Any]:
    """Форматирование строки бронирования для админа (с именем пользователя)"""
    formatted = _format_booking_row(row)
    formatted["user_id"] = row.get("user_id")
    formatted["user_name"] = row.get("user_name", "")
    # Для админа та же логика доступности отмены: только для сегодняшних и будущих дат
    formatted["can_cancel"] = formatted.get("can_cancel", False)
    return formatted


def _insert_booking(
    cur: psycopg.Cursor,  # pyright: ignore
    user_id: int,
    equipment_id: int,
    start_dt: datetime,
    end_dt: datetime,
    duration: timedelta,
) -> int:
    query = """
        INSERT INTO bookings (
            user_id,
            equip_id,
            date,
            time_start,
            time_end,
            time_interval,
            duration,
            cancel,
            extension,
            finish,
            data_booking
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, NULL, %s)
        RETURNING id
    """
    time_interval = f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"
    duration_hours = duration.total_seconds() / 3600
    cur.execute(
        query,
        (
            user_id,
            equipment_id,
            start_dt.date(),
            start_dt,
            end_dt,
            time_interval,
            duration_hours,
            datetime.now(),
        ),
    )
    row = cast(Optional[Dict[str, Any]], cur.fetchone())
    if not row:
        raise ValueError("Бронирование не создано.")
    return row["id"]


def get_calendar_overview(year: int, month: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Получить обзор бронирований для календаря на указанный месяц.
    
    Args:
        year: Год
        month: Месяц (1-12)
        user_id: ID пользователя (если None, возвращаются все бронирования)
    
    Returns:
        Словарь с данными календаря: {date: count, ...}
    """
    conn = _connect()
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            # Определяем диапазон дат для месяца
            from calendar import monthrange
            _, last_day = monthrange(year, month)
            date_from = date(year, month, 1)
            date_to = date(year, month, last_day)
            
            # Базовый запрос
            query = """
                SELECT 
                    b.date,
                    COUNT(*) as booking_count
                FROM bookings b
                WHERE b.date >= %s 
                    AND b.date <= %s
                    AND b.cancel = FALSE
            """
            params: List[Any] = [date_from, date_to]
            
            # Если указан user_id, фильтруем по пользователю
            if user_id:
                query += " AND b.user_id = %s"
                params.append(user_id)
            
            query += " GROUP BY b.date ORDER BY b.date"
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
            # Формируем словарь {date: count}
            calendar_data: Dict[str, int] = {}
            for row in rows:
                date_str = row["date"].isoformat()
                calendar_data[date_str] = int(row["booking_count"])
            
            return {
                "year": year,
                "month": month,
                "bookings": calendar_data,
            }
    except Exception as e:
        logger.error(f"Ошибка получения данных календаря: {e}", exc_info=True)
        return {
            "year": year,
            "month": month,
            "bookings": {},
            "error": str(e),
        }
    finally:
        conn.close()

