"""Отладочный скрипт для генерации и просмотра слотов wsb_time_slots.

Запускается вручную, не используется боевыми сервисами.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from wsb_core.slots import build_slots_specs_for_day, describe_slots_for_debug, DDL_CREATE_TIME_SLOTS_TABLE

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def load_env() -> None:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        print(f"[WARN] .env не найден по пути {ENV_PATH}, будут использованы переменные окружения системы")


def get_connection() -> psycopg.Connection:
    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", "5432"))
    name = os.getenv("DB_NAME", "RM")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not host or not user:
        raise RuntimeError("Не заданы параметры DB_HOST/DB_USER для подключения к БД")

    params = {
        "host": host,
        "port": port,
        "dbname": name,
        "user": user,
        "password": password,
        "row_factory": dict_row,
        "connect_timeout": 5,
    }
    return psycopg.connect(**params)  # type: ignore[arg-type]


def main() -> None:
    load_env()

    equipment_id = int(os.getenv("WSB_DEBUG_EQUIPMENT_ID", "1"))
    target_date_str = os.getenv("WSB_DEBUG_DATE", date.today().isoformat())
    target_date = date.fromisoformat(target_date_str)

    print(f"[INFO] Генерируем слоты для equipment_id={equipment_id}, date={target_date}")

    specs = build_slots_specs_for_day(equipment_id, target_date)
    print(f"[INFO] Слотов в расчёте: {len(specs)}")
    print("[DEBUG] ", describe_slots_for_debug(specs))

    with get_connection() as conn, conn.cursor() as cur:
        # На всякий случай убеждаемся, что таблица есть
        cur.execute(DDL_CREATE_TIME_SLOTS_TABLE)
        conn.commit()

        # Удаляем старые слоты для этого оборудования/даты
        cur.execute(
            "DELETE FROM wsb_time_slots WHERE equipment_id = %s AND DATE(slot_start) = %s",
            (equipment_id, target_date),
        )

        # Вставляем новые
        for s in specs:
            cur.execute(
                "INSERT INTO wsb_time_slots (equipment_id, slot_start, slot_end, status) VALUES (%s, %s, %s, %s)",
                (s.equipment_id, s.slot_start, s.slot_end, "free"),
            )

        conn.commit()

        # Читаем обратно и печатаем несколько строк
        cur.execute(
            "SELECT equipment_id, slot_start, slot_end, status, booking_id FROM wsb_time_slots "
            "WHERE equipment_id = %s AND DATE(slot_start) = %s ORDER BY slot_start ASC",
            (equipment_id, target_date),
        )
        rows = cur.fetchall()

    print(f"[OK] В таблице wsb_time_slots записано {len(rows)} слотов для equipment_id={equipment_id} на {target_date}")
    for row in rows[:10]:
        print(row)


if __name__ == "__main__":
    main()
