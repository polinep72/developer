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

# Флаг: использовать ли таблицу слотов ядра wsb_time_slots
USE_CORE_SLOTS = (os.getenv("USE_CORE_SLOTS", "false").lower() == "true")

# Используем общие константы ядра WSB_core
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from wsb_core.constants import WORKING_HOURS_START, WORKING_HOURS_END, BOOKING_TIME_STEP_MINUTES, MAX_BOOKING_DURATION_HOURS
    from wsb_core.bookings_core import create_booking_core, cancel_booking_core, extend_booking_core, finish_booking_core
except ImportError:
    WORKING_HOURS_START = time(7, 0)
    WORKING_HOURS_END = time(22, 0)
    BOOKING_TIME_STEP_MINUTES = 30
    MAX_BOOKING_DURATION_HOURS = 8
    create_booking_core = None  # type: ignore
    cancel_booking_core = None  # type: ignore
    extend_booking_core = None  # type: ignore
    finish_booking_core = None  # type: ignore

SLOT_MINUTES = BOOKING_TIME_STEP_MINUTES
BOOKING_STEP = timedelta(minutes=SLOT_MINUTES)
BOOKING_START_TIME = WORKING_HOURS_START
BOOKING_END_TIME = WORKING_HOURS_END
MAX_DURATION = timedelta(hours=MAX_BOOKING_DURATION_HOURS)


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
        if USE_CORE_SLOTS:
            try:
                slots = _get_slots_from_core_table(equipment_id, target_date)
            except Exception as core_exc:
                logger.error(f"Ошибка получения слотов из wsb_time_slots: {core_exc}", exc_info=True)
                # Фоллбэк на старый механизм
                bookings = _fetch_bookings(equipment_id, target_date)
                slots = _build_slots(target_date, bookings)
        else:
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
        logger.error(f"Не удалось получить доступные интервалы: {exc}", exc_info=True)
        return {"error": f"Не удалось получить доступные интервалы: {exc}"}


def _get_slots_from_core_table(equipment_id: int, target_date: date) -> List[Dict[str, Any]]:
    """
    Получить слоты из таблицы ядра wsb_time_slots.

    Таблица хранит слоты с шагом SLOT_MINUTES. Здесь мы аггрегируем
    последовательные свободные слоты в один слот с max_duration_minutes,
    чтобы интерфейс портала оставался прежним.
    """
    now = datetime.now()

    query = """
        SELECT slot_start, slot_end, status
        FROM wsb_time_slots
        WHERE equipment_id = %s
          AND DATE(slot_start) = %s
        ORDER BY slot_start ASC
    """

    rows: List[Dict[str, Any]] = []
    with _connect() as conn, conn.cursor() as cur:
        # Убеждаемся, что слоты для этой даты существуют
        _ensure_core_slots_exist(cur, equipment_id, target_date)
        conn.commit()
        
        cur.execute(query, (equipment_id, target_date))
        rows = cast(List[Dict[str, Any]], cur.fetchall())

    # Фильтруем только свободные слоты, с учётом текущего времени
    free_slots: List[Tuple[datetime, datetime]] = []
    now_floor = now.replace(second=0, microsecond=0)

    for row in rows:
        status = row.get("status")
        slot_start = row.get("slot_start")
        slot_end = row.get("slot_end")
        if status != "free" or not slot_start or not slot_end:
            continue
        # Логика совпадает с прежней: для сегодняшнего дня не показываем прошедшие слоты
        if target_date > now.date() or slot_start >= now_floor:
            free_slots.append((cast(datetime, slot_start), cast(datetime, slot_end)))

    # Формируем список отдельных слотов - каждый свободный слот становится отдельным временем начала
    # Используем ту же логику, что и _build_slots: для каждого слота рассчитываем максимальную доступную длительность
    result: List[Dict[str, Any]] = []
    if not free_slots:
        return result

    # Сортируем слоты по времени начала
    free_slots.sort(key=lambda x: x[0])
    
    # Создаём словарь для быстрого поиска: начало -> конец
    slots_dict = {start: end for start, end in free_slots}
    
    # Для каждого свободного слота рассчитываем максимальную доступную длительность
    step_minutes = SLOT_MINUTES
    max_end_time = datetime.combine(target_date, BOOKING_END_TIME) + timedelta(minutes=step_minutes)
    max_duration_minutes = int(MAX_DURATION.total_seconds() // 60)
    
    for slot_start, slot_end in free_slots:
        # Рассчитываем максимальную доступную длительность с этого момента
        available_minutes = step_minutes  # минимум один слот доступен
        probe_end = slot_end
        
        # Проверяем, сколько последовательных свободных слотов доступно
        while probe_end < max_end_time and available_minutes < max_duration_minutes:
            # Ищем следующий слот в словаре (конец текущего должен совпадать с началом следующего)
            if probe_end in slots_dict:
                available_minutes += step_minutes
                probe_end = slots_dict[probe_end]
            else:
                break
        
        result.append(
            {
                "time": slot_start.strftime("%H:%M"),
                "max_duration_minutes": available_minutes,
            }
        )

    return result


def _ensure_core_slots_exist(cur: psycopg.Cursor, equipment_id: int, target_date: date) -> None:  # pyright: ignore
    """Убедиться, что слоты для оборудования/даты существуют в wsb_time_slots."""
    try:
        from wsb_core.slots import DDL_CREATE_TIME_SLOTS_TABLE, build_slots_specs_for_day

        # Гарантируем наличие таблицы
        cur.execute(DDL_CREATE_TIME_SLOTS_TABLE)
        
        # Проверяем, есть ли уже слоты для этой даты
        check_query = """
            SELECT COUNT(*) as cnt FROM wsb_time_slots
            WHERE equipment_id = %s AND DATE(slot_start) = %s
        """
        cur.execute(check_query, (equipment_id, target_date))
        row = cast(Optional[Dict[str, Any]], cur.fetchone())
        count = row.get("cnt", 0) if row else 0
        
        if count == 0:
            # Генерируем и вставляем слоты
            specs = build_slots_specs_for_day(equipment_id, target_date)
            for spec in specs:
                cur.execute(
                    "INSERT INTO wsb_time_slots (equipment_id, slot_start, slot_end, status) VALUES (%s, %s, %s, %s)",
                    (spec.equipment_id, spec.slot_start, spec.slot_end, "free"),
                )
    except Exception as exc:
        logger.warning(f"Ошибка инициализации слотов в wsb_time_slots: {exc}")


def create_booking(
    user_id: int,
    equipment_id: int,
    target_date: date,
    start_time_str: str,
    duration_minutes: int,
) -> Dict[str, Any]:
    try:
        with _connect() as conn, conn.cursor() as cur:
            if create_booking_core is None:
                raise RuntimeError("Модуль ядра wsb_core недоступен")
            core_result = create_booking_core(
                cur,
                user_id=user_id,
                equipment_id=equipment_id,
                target_date=target_date,
                start_time_str=start_time_str,
                duration_minutes=duration_minutes,
                ensure_user_active=True,
                sync_slots=USE_CORE_SLOTS,
            )

            if not core_result.success:
                conn.rollback()
                response: Dict[str, Any] = {"error": core_result.message or "Не удалось создать бронирование"}
                if core_result.conflicts:
                    response["conflicts"] = core_result.conflicts
                return response

            conn.commit()

            booking = core_result.booking
            start_dt = core_result.extra.get("start_dt") if core_result.extra else None
            end_dt = core_result.extra.get("end_dt") if core_result.extra else None

            # Инвалидация кэша тепловой карты для этой даты
            try:
                from .cache import invalidate_heatmap, invalidate_dashboard

                date_str = target_date.strftime("%Y-%m-%d")
                invalidate_heatmap(date_str)
                invalidate_dashboard()
            except Exception as exc:
                logger.warning(f"Ошибка при инвалидации кэша: {exc}")

            # Отправка уведомления о создании бронирования
            try:
                from .notifications import send_booking_created_notification, should_send_email_notification
                from .auth import get_user_by_id

                if start_dt and end_dt and isinstance(start_dt, datetime) and isinstance(end_dt, datetime):
                    if should_send_email_notification(user_id):
                        user = get_user_by_id(user_id)
                        if user and user.get("email"):
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
                print(f"[NOTIFICATION ERROR] Failed to send booking created notification: {exc}")

            return {
                "data": {
                    "booking_id": booking.id if booking else None,
                    "start_time": start_dt.strftime("%H:%M") if isinstance(start_dt, datetime) else start_time_str,
                    "end_time": end_dt.strftime("%H:%M") if isinstance(end_dt, datetime) else "",
                }
            }
    except ValueError as exc:
        return {"error": str(exc)}
    except psycopg.OperationalError as exc:  # pyright: ignore
        return {"error": f"Ошибка подключения к БД: {exc}"}
    except Exception as exc:
        return {"error": f"Не удалось создать бронирование: {exc}"}


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
    """
    Построение списка доступных слотов по дате и списку уже занятых интервалов.

    Список базовых слотов (по времени дня) берём из ядра WSB_core (generate_daily_slots),
    а фильтрацию по текущему времени и занятым интервалам делаем здесь.
    """
    from wsb_core.slots import generate_daily_slots  # локальный импорт, чтобы не ломать импорт, если ядро недоступно

    slots: List[Dict[str, Any]] = []
    now = datetime.now()

    base_slots = generate_daily_slots(target_date)

    for iter_dt in base_slots:
        if target_date > now.date() or iter_dt >= now.replace(second=0, microsecond=0):
            available_minutes = _calculate_available_minutes(iter_dt, bookings, target_date)
            if available_minutes >= SLOT_MINUTES:
                slots.append(
                    {
                        "time": iter_dt.strftime("%H:%M"),
                        "max_duration_minutes": available_minutes,
                    }
                )
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
    """Отменить бронирование (пользователь может отменить только своё, админ - любое)."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            if cancel_booking_core is None:
                raise RuntimeError("Модуль ядра wsb_core недоступен")
            core_result = cancel_booking_core(
                cur,
                booking_id=booking_id,
                actor_user_id=user_id,
                is_admin=is_admin,
                sync_slots=USE_CORE_SLOTS,
            )

            if not core_result.success:
                conn.rollback()
                return {"error": core_result.message or "Бронирование не найдено или нет прав на отмену"}

            conn.commit()

            extra_payload = core_result.extra or {}
            booking_row = cast(Dict[str, Any], extra_payload.get("booking_row", {}))
            booking_date = booking_row.get("date")
            booking_start = booking_row.get("time_start")
            booking_end = booking_row.get("time_end")
            equipment_id_value = booking_row.get("equip_id") or booking_row.get("equipment_id")
            booking_user_id = booking_row.get("user_id")
            equipment_name = booking_row.get("name_equip", "Оборудование")
            user_email = booking_row.get("email")
            user_first_name = booking_row.get("first_name", "")
            user_last_name = booking_row.get("last_name", "")

            if isinstance(booking_date, datetime):
                booking_date_value: Optional[date] = booking_date.date()
            elif isinstance(booking_date, date):
                booking_date_value = booking_date
            else:
                booking_date_value = None

            try:
                from .cache import invalidate_heatmap, invalidate_dashboard

                if booking_date_value:
                    date_str = booking_date_value.strftime("%Y-%m-%d")
                elif isinstance(booking_date, datetime):
                    date_str = booking_date.date().strftime("%Y-%m-%d")
                else:
                    date_str = str(booking_date)
                invalidate_heatmap(date_str)
                invalidate_dashboard()
            except Exception as exc:
                logger.warning(f"Ошибка при инвалидации кэша: {exc}")

            try:
                from .notifications import send_booking_cancelled_notification, should_send_email_notification

                start_time_obj: Optional[time]
                if isinstance(booking_start, datetime):
                    start_time_obj = booking_start.time()
                elif isinstance(booking_start, time):
                    start_time_obj = booking_start
                else:
                    start_time_obj = None

                end_time_obj: Optional[time]
                if isinstance(booking_end, datetime):
                    end_time_obj = booking_end.time()
                elif isinstance(booking_end, time):
                    end_time_obj = booking_end
                else:
                    end_time_obj = None

                if (
                    user_email
                    and isinstance(booking_user_id, int)
                    and booking_date_value
                    and start_time_obj
                    and end_time_obj
                    and should_send_email_notification(booking_user_id)
                ):
                    user_name = f"{user_first_name} {user_last_name}".strip() or "Пользователь"
                    send_booking_cancelled_notification(
                        user_email=user_email,
                        user_name=user_name,
                        equipment_name=equipment_name,
                        booking_date=booking_date_value,
                        start_time=start_time_obj,
                        end_time=end_time_obj,
                    )
            except Exception as exc:
                print(f"[NOTIFICATION ERROR] Failed to send booking cancelled notification: {exc}")

            return {
                "data": {
                    "message": "Бронирование отменено",
                    "booking_id": booking_id,
                    "date": booking_date_value.isoformat() if booking_date_value else (booking_date.date().isoformat() if isinstance(booking_date, datetime) else str(booking_date)),
                    "equipment_id": equipment_id_value,
                }
            }
    except Exception as exc:
        return {"error": f"Не удалось отменить бронирование: {exc}"}


def finish_booking(
    booking_id: int,
    user_id: int,
    is_admin: bool = False,  # админ может завершать любые брони
) -> Dict[str, Any]:
    """
    Завершить бронирование:
    - владелец может завершить свою активную бронь;
    - админ может завершить любую активную бронь.
    Использует ядровую функцию finish_booking_core с синхронизацией слотов.
    """
    if finish_booking_core is None:
        return {"error": "Функция завершения бронирования недоступна"}
    
    try:
        with _connect() as conn, conn.cursor() as cur:
            # Используем ядровую функцию с синхронизацией слотов
            result = finish_booking_core(
                cur,
                booking_id=booking_id,
                actor_user_id=user_id,
                is_admin=is_admin,
                sync_slots=True,  # Важно: синхронизируем слоты при завершении
            )
            
            if not result.success:
                return {"error": result.message or "Не удалось завершить бронирование"}
            
            conn.commit()
            
            # Инвалидация кэша тепловой карты и дашборда
            try:
                from .cache import invalidate_heatmap, invalidate_dashboard
                
                booking = result.booking
                if booking and booking.date:
                    date_str = booking.date.strftime("%Y-%m-%d")
                    invalidate_heatmap(date_str)
                    invalidate_dashboard()
                    
                # Также используем данные из extra, если есть
                if result.extra and "booking_row" in result.extra:
                    booking_row = result.extra["booking_row"]
                    booking_date = booking_row.get("date")
                    if booking_date:
                        if isinstance(booking_date, datetime):
                            date_str = booking_date.date().strftime("%Y-%m-%d")
                        elif isinstance(booking_date, date):
                            date_str = booking_date.strftime("%Y-%m-%d")
                        else:
                            date_str = str(booking_date)
                        invalidate_heatmap(date_str)
                        invalidate_dashboard()
            except Exception as exc:
                logger.warning(f"Ошибка при инвалидации кэша после завершения: {exc}")
            
            # Формируем сообщение об успехе
            finish_time = result.extra.get("finish_time") if result.extra else None
            equip_name = "Оборудование"
            if result.extra and "booking_row" in result.extra:
                equip_name = result.extra["booking_row"].get("name_equip", "Оборудование")
            elif result.booking and result.booking.equipment_name:
                equip_name = result.booking.equipment_name
            
            if finish_time:
                time_str = finish_time.strftime("%H:%M:%S")
                message = f"Использование '{equip_name}' завершено в {time_str}"
            else:
                message = f"Использование '{equip_name}' завершено"
            
            return {
                "data": {
                    "message": message,
                    "booking_id": booking_id,
                }
            }
    except Exception as exc:
        logger.error(f"Ошибка при завершении бронирования {booking_id}: {exc}", exc_info=True)
        return {"error": f"Не удалось завершить бронирование: {exc}"}


def extend_booking(
    booking_id: int,
    user_id: int,
    extension_minutes: int,
    is_admin: bool = False,
) -> Dict[str, Any]:
    """
    Продлить существующее бронирование.
    """
    try:
        if extend_booking_core is None:
            raise RuntimeError("Модуль ядра wsb_core недоступен")

        if extension_minutes <= 0:
            return {"error": "Длительность продления должна быть больше нуля"}

        with _connect() as conn, conn.cursor() as cur:
            core_result = extend_booking_core(
                cur,
                booking_id=booking_id,
                actor_user_id=user_id,
                extension_minutes=extension_minutes,
                is_admin=is_admin,
                sync_slots=USE_CORE_SLOTS,
            )

            if not core_result.success:
                conn.rollback()
                response: Dict[str, Any] = {
                    "error": core_result.message or "Не удалось продлить бронирование"
                }
                if core_result.conflicts:
                    response["conflicts"] = core_result.conflicts
                return response

            conn.commit()

            extra_payload = core_result.extra or {}
            booking_row = cast(Dict[str, Any], extra_payload.get("booking_row", {}))
            booking_date = booking_row.get("date")
            equipment_id_value = booking_row.get("equip_id") or booking_row.get("equipment_id")
            new_end_dt = extra_payload.get("new_end")

            # Инвалидация кэша тепловой карты и дашборда
            try:
                from .cache import invalidate_heatmap, invalidate_dashboard

                if isinstance(booking_date, datetime):
                    booking_date_value: Optional[date] = booking_date.date()
                elif isinstance(booking_date, date):
                    booking_date_value = booking_date
                else:
                    booking_date_value = None

                if booking_date_value:
                    date_str = booking_date_value.strftime("%Y-%m-%d")
                elif isinstance(booking_date, datetime):
                    date_str = booking_date.date().strftime("%Y-%m-%d")
                else:
                    date_str = str(booking_date)

                invalidate_heatmap(date_str)
                invalidate_dashboard()
            except Exception as exc:
                logger.warning(f"Ошибка при инвалидации кэша после продления: {exc}")

            # Текстовое сообщение для пользователя
            if isinstance(new_end_dt, datetime):
                new_end_str = new_end_dt.strftime("%H:%M")
                message = f"Ваше бронирование продлено до {new_end_str}"
            else:
                message = "Бронирование продлено"

            return {
                "data": {
                    "message": message,
                    "booking_id": booking_id,
                    "equipment_id": equipment_id_value,
                    "new_end": new_end_dt.isoformat() if isinstance(new_end_dt, datetime) else None,
                }
            }
    except ValueError as exc:
        return {"error": str(exc)}
    except psycopg.OperationalError as exc:  # pyright: ignore
        return {"error": f"Ошибка подключения к БД: {exc}"}
    except Exception as exc:
        return {"error": f"Не удалось продлить бронирование: {exc}"}


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

    # Кнопка «Завершить» доступна только для активных броней пользователя
    can_finish = status == "Активное"

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
        "can_finish": can_finish,
    }


def _format_booking_row_admin(row: Dict[str, Any]) -> Dict[str, Any]:
    """Форматирование строки бронирования для админа (с именем пользователя)"""
    formatted = _format_booking_row(row)
    formatted["user_id"] = row.get("user_id")
    formatted["user_name"] = row.get("user_name", "")
    # Для админа та же логика доступности отмены: только для сегодняшних и будущих дат
    formatted["can_cancel"] = formatted.get("can_cancel", False)
    return formatted


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

