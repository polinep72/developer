"""Очистка устаревших слотов в wsb_time_slots.

Удаляет все записи, у которых slot_start < CURRENT_DATE.
Запускать вручную или по расписанию (через планировщик).
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from wsb_core.slots import cleanup_old_slots_sql

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
    sql = cleanup_old_slots_sql()
    print("[INFO] Очистка устаревших слотов в wsb_time_slots...")

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        deleted = cur.rowcount
        conn.commit()

    print(f"[OK] Удалено {deleted} записей из wsb_time_slots со старыми датами.")


if __name__ == "__main__":
    main()
