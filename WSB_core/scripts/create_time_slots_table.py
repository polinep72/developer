"""Создание ядровой таблицы слотов wsb_time_slots в БД RM.

Скрипт использует переменные окружения из .env (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
Его можно запускать вручную, когда будет принято решение использовать
единый механизм слотов для бота и портала.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from wsb_core.slots import DDL_CREATE_TIME_SLOTS_TABLE


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
    print("[INFO] Подключение к БД RM и создание таблицы wsb_time_slots (если не существует)...")

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(DDL_CREATE_TIME_SLOTS_TABLE)
        conn.commit()

    print("[OK] Таблица wsb_time_slots проверена/создана успешно.")


if __name__ == "__main__":
    main()
