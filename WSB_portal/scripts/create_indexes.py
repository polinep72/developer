"""
Скрипт для создания индексов в базах данных RM и equipment.
Запуск из корня проекта:

    python scripts/create_indexes.py
"""
from __future__ import annotations

import os
import sys

import psycopg
from psycopg.rows import dict_row

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# --- Параметры БД RM (основная БД бронирований) -----------------------------
DB_HOST = os.getenv("POSTGRE_HOST") or os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("POSTGRE_PORT") or os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("POSTGRE_DBNAME") or os.getenv("DB_NAME", "RM")
DB_USER = os.getenv("POSTGRE_USER") or os.getenv("DB_USER")
DB_PASSWORD = os.getenv("POSTGRE_PASSWORD") or os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("POSTGRE_SSLMODE") or os.getenv("DB_SSLMODE", "prefer")

# --- Параметры БД equipment (модуль учета СИ) -------------------------------
EQUIPMENT_DB_HOST = os.getenv("EQUIPMENT_DB_HOST") or DB_HOST
EQUIPMENT_DB_PORT = os.getenv("EQUIPMENT_DB_PORT") or DB_PORT
EQUIPMENT_DB_NAME = os.getenv("EQUIPMENT_DB_NAME") or "equipment"
EQUIPMENT_DB_USER = os.getenv("EQUIPMENT_DB_USER") or DB_USER
EQUIPMENT_DB_PASSWORD = os.getenv("EQUIPMENT_DB_PASSWORD") or DB_PASSWORD
EQUIPMENT_DB_SSLMODE = os.getenv("EQUIPMENT_DB_SSLMODE") or DB_SSLMODE


RM_INDEXES = [
    """
    CREATE INDEX IF NOT EXISTS idx_bookings_date_cancel
    ON bookings (date)
    WHERE cancel IS NOT TRUE
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bookings_date_equip
    ON bookings (date, equip_id)
    WHERE cancel IS NOT TRUE
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bookings_user_date
    ON bookings (user_id, date)
    WHERE cancel IS NOT TRUE
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bookings_equip_time
    ON bookings (equip_id, time_start)
    WHERE cancel IS NOT TRUE
    """,
]


EQUIPMENT_INDEXES = [
    """
    CREATE INDEX IF NOT EXISTS idx_equipment_type_row
    ON equipment (equipment_type_id, row_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_equipment_type_serial
    ON equipment (equipment_type_id, serial_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_equipment_types_name
    ON equipment_types (type_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gosregister_number
    ON gosregister (gosregister_number)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_calibration_certificates_eq_date
    ON calibration_certificates (equipment_id, certificate_date DESC)
    """,
]


def _run_index_batch(title: str, conn_params: dict, statements: list[str]) -> None:
    if not statements:
        return

    print(f"\n=== {title} ===")
    conn = psycopg.connect(**conn_params)
    try:
        with conn.cursor() as cur:
            for stmt in statements:
                normalized = " ".join(line.strip() for line in stmt.strip().splitlines())
                print(f"→ {normalized}")
                cur.execute(normalized)  # type: ignore[arg-type]
    finally:
        conn.close()


def main() -> int:
    if not DB_USER or not DB_PASSWORD:
        print("✖️  Переменные окружения POSTGRE_* не заданы.")
        return 1

    rm_params = dict(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode=DB_SSLMODE,
        row_factory=dict_row,
        autocommit=True,
    )
    _run_index_batch("Индексы БД RM (bookings)", rm_params, RM_INDEXES)

    if EQUIPMENT_DB_USER and EQUIPMENT_DB_PASSWORD:
        equipment_params = dict(
            host=EQUIPMENT_DB_HOST,
            port=EQUIPMENT_DB_PORT,
            dbname=EQUIPMENT_DB_NAME,
            user=EQUIPMENT_DB_USER,
            password=EQUIPMENT_DB_PASSWORD,
            sslmode=EQUIPMENT_DB_SSLMODE,
            row_factory=dict_row,
            autocommit=True,
        )
        _run_index_batch("Индексы БД equipment (модуль СИ)", equipment_params, EQUIPMENT_INDEXES)
    else:
        print("⚠️  Пропускаем индексы equipment: не заданы логин/пароль EQUIPMENT_DB_*")

    print("\n✅ Индексация завершена.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


