#!/usr/bin/env python3
"""Скрипт для приведения структуры таблиц wsb_* к актуальной версии.

Исправляет структуру таблиц wsb_time_slots и wsb_notifications_schedule
в соответствии с определением в wsb_core.
"""

import os
import sys
from pathlib import Path

# Добавляем корень проекта в путь
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

# Загружаем переменные окружения
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "RM")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_HOST or not DB_USER:
    print("❌ Ошибка: не заданы DB_HOST или DB_USER")
    sys.exit(1)

# DDL из wsb_core/slots.py
DDL_CREATE_TIME_SLOTS_TABLE = """
CREATE TABLE IF NOT EXISTS wsb_time_slots (
    id           SERIAL PRIMARY KEY,
    equipment_id INTEGER      NOT NULL,
    slot_start   TIMESTAMP    NOT NULL,
    slot_end     TIMESTAMP    NOT NULL,
    status       TEXT         NOT NULL DEFAULT 'free',
    booking_id   INTEGER      NULL,
    CONSTRAINT wsb_time_slots_uniq UNIQUE (equipment_id, slot_start, slot_end)
);
""".strip()

# DDL из wsb_core/notifications_schedule.py
DDL_CREATE_NOTIFICATIONS_SCHEDULE_TABLE = """
CREATE TABLE IF NOT EXISTS wsb_notifications_schedule (
    id              SERIAL PRIMARY KEY,
    booking_id      INTEGER NOT NULL,
    channel         VARCHAR(32) NOT NULL,
    event_type      VARCHAR(32) NOT NULL,
    run_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    payload         JSONB,
    last_error      TEXT,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_run_at
    ON wsb_notifications_schedule (run_at);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_channel_status
    ON wsb_notifications_schedule (channel, status);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_booking
    ON wsb_notifications_schedule (booking_id);
""".strip()


def check_column_exists(cur, table_name: str, column_name: str) -> bool:
    """Проверяет существование столбца в таблице."""
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
        ) as exists
        """,
        (table_name, column_name),
    )
    row = cur.fetchone()
    return row["exists"] if isinstance(row, dict) else row[0]


def add_missing_columns(cur, table_name: str, columns_def: list[tuple[str, str]]) -> int:
    """Добавляет отсутствующие столбцы в таблицу.
    
    Args:
        cur: курсор БД
        table_name: имя таблицы
        columns_def: список кортежей (имя_столбца, определение_столбца)
    
    Returns:
        количество добавленных столбцов
    """
    added = 0
    for col_name, col_def in columns_def:
        if not check_column_exists(cur, table_name, col_name):
            try:
                cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_def}")
                print(f"  ✅ Добавлен столбец {table_name}.{col_name}")
                added += 1
            except Exception as e:
                print(f"  ❌ Ошибка при добавлении {table_name}.{col_name}: {e}")
    return added


def fix_time_slots_table(cur):
    """Исправляет структуру таблицы wsb_time_slots."""
    print("\n=== Исправление wsb_time_slots ===")
    
    # Проверяем существование таблицы
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'wsb_time_slots'
        ) as exists
        """
    )
    row = cur.fetchone()
    exists = row["exists"] if isinstance(row, dict) else row[0]
    if not exists:
        print("  Создание таблицы wsb_time_slots...")
        cur.execute(DDL_CREATE_TIME_SLOTS_TABLE)
        print("  ✅ Таблица wsb_time_slots создана")
        return
    
    # Проверяем и добавляем отсутствующие столбцы
    columns_to_add = [
        ("id", "id SERIAL PRIMARY KEY"),
        ("equipment_id", "equipment_id INTEGER NOT NULL"),
        ("slot_start", "slot_start TIMESTAMP NOT NULL"),
        ("slot_end", "slot_end TIMESTAMP NOT NULL"),
        ("status", "status TEXT NOT NULL DEFAULT 'free'"),
        ("booking_id", "booking_id INTEGER NULL"),
    ]
    
    # Упрощенная проверка - только отсутствующие столбцы
    missing_cols = []
    for col_name, col_def in columns_to_add:
        if col_name == "id":
            continue  # PRIMARY KEY уже должен быть
        if not check_column_exists(cur, "wsb_time_slots", col_name):
            missing_cols.append((col_name, col_def.split(" ", 1)[1]))  # Без имени столбца
    
    if missing_cols:
        print(f"  Найдено {len(missing_cols)} отсутствующих столбцов")
        for col_name, col_def in missing_cols:
            try:
                cur.execute(f"ALTER TABLE wsb_time_slots ADD COLUMN {col_name} {col_def}")
                print(f"  ✅ Добавлен столбец {col_name}")
            except Exception as e:
                print(f"  ❌ Ошибка при добавлении {col_name}: {e}")
    else:
        print("  ✅ Все столбцы присутствуют")
    
    # Проверяем уникальный индекс
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'wsb_time_slots'
              AND indexname = 'wsb_time_slots_uniq'
        ) as exists
        """
    )
    row = cur.fetchone()
    exists = row["exists"] if isinstance(row, dict) else row[0]
    if not exists:
        try:
            cur.execute(
                """
                ALTER TABLE wsb_time_slots
                ADD CONSTRAINT wsb_time_slots_uniq
                UNIQUE (equipment_id, slot_start, slot_end)
                """
            )
            print("  ✅ Добавлен уникальный индекс wsb_time_slots_uniq")
        except Exception as e:
            print(f"  ⚠️ Не удалось добавить индекс (возможно, уже существует): {e}")
    else:
        print("  ✅ Уникальный индекс присутствует")


def fix_notifications_schedule_table(cur):
    """Исправляет структуру таблицы wsb_notifications_schedule."""
    print("\n=== Исправление wsb_notifications_schedule ===")
    
    # Проверяем существование таблицы
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'wsb_notifications_schedule'
        ) as exists
        """
    )
    row = cur.fetchone()
    exists = row["exists"] if isinstance(row, dict) else row[0]
    if not exists:
        print("  Создание таблицы wsb_notifications_schedule...")
        cur.execute(DDL_CREATE_NOTIFICATIONS_SCHEDULE_TABLE)
        print("  ✅ Таблица wsb_notifications_schedule создана")
        return
    
    # Проверяем и добавляем отсутствующие столбцы
    columns_to_check = [
        ("id", "id SERIAL PRIMARY KEY"),
        ("booking_id", "booking_id INTEGER NOT NULL"),
        ("channel", "channel VARCHAR(32) NOT NULL"),
        ("event_type", "event_type VARCHAR(32) NOT NULL"),
        ("run_at", "run_at TIMESTAMP WITHOUT TIME ZONE NOT NULL"),
        ("status", "status VARCHAR(16) NOT NULL DEFAULT 'pending'"),
        ("payload", "payload JSONB"),
        ("last_error", "last_error TEXT"),
        ("created_at", "created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
        ("updated_at", "updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP"),
    ]
    
    missing_cols = []
    for col_name, col_def in columns_to_check:
        if col_name == "id":
            continue  # PRIMARY KEY уже должен быть
        if not check_column_exists(cur, "wsb_notifications_schedule", col_name):
            # Извлекаем определение без имени столбца
            col_def_parts = col_def.split(" ", 1)
            if len(col_def_parts) > 1:
                missing_cols.append((col_name, col_def_parts[1]))
    
    if missing_cols:
        print(f"  Найдено {len(missing_cols)} отсутствующих столбцов")
        for col_name, col_def in missing_cols:
            try:
                cur.execute(f"ALTER TABLE wsb_notifications_schedule ADD COLUMN {col_name} {col_def}")
                print(f"  ✅ Добавлен столбец {col_name}")
            except Exception as e:
                print(f"  ❌ Ошибка при добавлении {col_name}: {e}")
    else:
        print("  ✅ Все столбцы присутствуют")
    
    # Проверяем индексы
    indexes_to_check = [
        ("idx_wsb_notif_sched_run_at", "CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_run_at ON wsb_notifications_schedule (run_at)"),
        ("idx_wsb_notif_sched_channel_status", "CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_channel_status ON wsb_notifications_schedule (channel, status)"),
        ("idx_wsb_notif_sched_booking", "CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_booking ON wsb_notifications_schedule (booking_id)"),
    ]
    
    for idx_name, idx_sql in indexes_to_check:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'wsb_notifications_schedule'
                  AND indexname = %s
            ) as exists
            """,
            (idx_name,),
        )
        row = cur.fetchone()
        exists = row["exists"] if isinstance(row, dict) else row[0]
        if not exists:
            try:
                cur.execute(idx_sql)
                print(f"  ✅ Добавлен индекс {idx_name}")
            except Exception as e:
                print(f"  ⚠️ Не удалось добавить индекс {idx_name}: {e}")
        else:
            print(f"  ✅ Индекс {idx_name} присутствует")


def fix_users_table(cur):
    """Исправляет структуру таблицы users (добавляет отсутствующие столбцы)."""
    print("\n=== Исправление users ===")
    
    # Проверяем существование таблицы
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'users'
        ) as exists
        """
    )
    row = cur.fetchone()
    exists = row["exists"] if isinstance(row, dict) else row[0]
    if not exists:
        print("  ⚠️ Таблица users не найдена, пропускаем")
        return
    
    # Столбцы, которые должны быть в таблице users (на основе использования в коде)
    columns_to_add = [
        ("email", "email VARCHAR(255) NULL"),
        ("phone", "phone VARCHAR(50) NULL"),
        ("password_hash", "password_hash VARCHAR(255) NULL"),
    ]
    
    added = 0
    for col_name, col_def in columns_to_add:
        if not check_column_exists(cur, "users", col_name):
            try:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col_def}")
                print(f"  ✅ Добавлен столбец {col_name}")
                added += 1
            except Exception as e:
                print(f"  ❌ Ошибка при добавлении {col_name}: {e}")
        else:
            print(f"  ✅ Столбец {col_name} уже существует")
    
    if added == 0:
        print("  ✅ Все необходимые столбцы присутствуют")


def main():
    """Основная функция."""
    print("=" * 60)
    print("Исправление структуры таблиц wsb_* и users")
    print("=" * 60)
    print(f"\nПодключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    try:
        with psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            row_factory=dict_row,
        ) as conn:
            with conn.cursor() as cur:
                fix_time_slots_table(cur)
                fix_notifications_schedule_table(cur)
                fix_users_table(cur)
                conn.commit()
                print("\n✅ Все изменения применены успешно")
                
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

