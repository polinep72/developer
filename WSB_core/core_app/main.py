from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from dotenv import load_dotenv
from pydantic import BaseModel

from wsb_core.slots import build_slots_specs_for_day, DDL_CREATE_TIME_SLOTS_TABLE
from wsb_core.constants import BOOKING_TIME_STEP_MINUTES

# Загружаем .env из корня WSB_core
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

app = FastAPI(title="WSB Core Test App")


def get_conn() -> psycopg.Connection:
    params = {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "RM"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "row_factory": dict_row,
        "connect_timeout": 5,
    }
    if not params["host"] or not params["user"]:
        raise RuntimeError("DB_HOST/DB_USER не заданы")
    return psycopg.connect(**params)  # type: ignore[arg-type]


@app.get("/api/core/slots", response_model=Dict[str, Any])
def get_core_slots(equipment_id: int = 33, target_date: str | None = None) -> Dict[str, Any]:
    """Вернуть текущие слоты из wsb_time_slots без пересоздания.

    Предполагается, что инициализацию слотов делает отдельный скрипт/процесс.
    """
    try:
        target = date.fromisoformat(target_date) if target_date else date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты, нужен YYYY-MM-DD")

    with get_conn() as conn, conn.cursor() as cur:
        # гарантируем наличие таблицы, но сами слоты не трогаем
        cur.execute(DDL_CREATE_TIME_SLOTS_TABLE)
        conn.commit()

        cur.execute(
            "SELECT slot_start, slot_end, status FROM wsb_time_slots "
            "WHERE equipment_id = %s AND DATE(slot_start) = %s ORDER BY slot_start",
            (equipment_id, target),
        )
        rows: List[Dict[str, Any]] = cur.fetchall()  # type: ignore[assignment]

    result_slots: List[Dict[str, Any]] = []
    step = BOOKING_TIME_STEP_MINUTES
    for row in rows:
        result_slots.append(
            {
                "time": row["slot_start"].strftime("%H:%M"),
                "duration_minutes": int((row["slot_end"] - row["slot_start"]).total_seconds() // 60),
                "status": row["status"],
            }
        )

    return {
        "equipment_id": equipment_id,
        "date": target.isoformat(),
        "step_minutes": step,
        "slots": result_slots,
    }


class CoreBookingRequest(BaseModel):
    equipment_id: int = 33
    date: str              # YYYY-MM-DD
    time: str              # HH:MM
    duration_minutes: int  # кратно BOOKING_TIME_STEP_MINUTES


@app.post("/api/core/bookings", response_model=Dict[str, Any])
def create_core_booking(req: CoreBookingRequest) -> Dict[str, Any]:
    """Тестовое бронирование только на уровне таблицы слотов.

    Историческая таблица bookings ядром сейчас не трогается, чтобы не
    зависеть от её фактической схемы. Мы отмечаем только занятые слоты
    в wsb_time_slots для equipment_id=33.
    """
    try:
        target = date.fromisoformat(req.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты, нужен YYYY-MM-DD")

    try:
        start_h, start_m = map(int, req.time.split(":"))
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный формат времени, нужен HH:MM")

    start_dt = datetime(target.year, target.month, target.day, start_h, start_m)
    duration = timedelta(minutes=req.duration_minutes)
    if req.duration_minutes <= 0 or req.duration_minutes % BOOKING_TIME_STEP_MINUTES != 0:
        raise HTTPException(status_code=400, detail="Недопустимая длительность")

    end_dt = start_dt + duration

    with get_conn() as conn, conn.cursor() as cur:
        # Помечаем соответствующие слоты как booked (только в wsb_time_slots)
        cur.execute(
            """
            UPDATE wsb_time_slots
            SET status = 'booked', booking_id = NULL
            WHERE equipment_id = %s
              AND slot_start >= %s AND slot_end <= %s
            """,
            (req.equipment_id, start_dt, end_dt),
        )
        affected = cur.rowcount
        conn.commit()

    return {
        "updated_slots": affected,
        "equipment_id": req.equipment_id,
        "date": target.isoformat(),
        "time": req.time,
        "duration_minutes": req.duration_minutes,
    }


@app.delete("/api/core/bookings", response_model=Dict[str, Any])
def cancel_core_booking(req: CoreBookingRequest) -> Dict[str, Any]:
    """Отменить бронирование, освободив слоты в wsb_time_slots.

    Работает аналогично create_core_booking, но переводит статус из booked в free.
    """
    try:
        target = date.fromisoformat(req.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты, нужен YYYY-MM-DD")

    try:
        start_h, start_m = map(int, req.time.split(":"))
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный формат времени, нужен HH:MM")

    start_dt = datetime(target.year, target.month, target.day, start_h, start_m)
    duration = timedelta(minutes=req.duration_minutes)
    if req.duration_minutes <= 0 or req.duration_minutes % BOOKING_TIME_STEP_MINUTES != 0:
        raise HTTPException(status_code=400, detail="Недопустимая длительность")

    end_dt = start_dt + duration

    with get_conn() as conn, conn.cursor() as cur:
        # Освобождаем слоты (переводим из booked в free)
        cur.execute(
            """
            UPDATE wsb_time_slots
            SET status = 'free', booking_id = NULL
            WHERE equipment_id = %s
              AND slot_start >= %s AND slot_end <= %s
              AND status = 'booked'
            """,
            (req.equipment_id, start_dt, end_dt),
        )
        affected = cur.rowcount
        conn.commit()

    return {
        "freed_slots": affected,
        "equipment_id": req.equipment_id,
        "date": target.isoformat(),
        "time": req.time,
        "duration_minutes": req.duration_minutes,
    }
