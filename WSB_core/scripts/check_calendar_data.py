"""Проверка данных календаря"""
import sys
import os
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.chdir(PROJECT_ROOT)

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "RM")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.cursor_factory = psycopg2.extras.DictCursor

# Проверяем данные для декабря 2025
date_from = date(2025, 12, 1)
date_to = date(2025, 12, 31)

with conn.cursor() as cur:
    # Запрос как в get_calendar_overview (обновленный - показывает все бронирования)
    query = """
        SELECT 
            b.date,
            COUNT(*) as booking_count
        FROM bookings b
        WHERE b.date >= %s 
            AND b.date <= %s
        GROUP BY b.date 
        ORDER BY b.date
    """
    cur.execute(query, (date_from, date_to))
    rows = cur.fetchall()
    
    print(f"\n=== Бронирования в декабре 2025 (все, включая отмененные) ===")
    if rows:
        for row in rows:
            print(f"{row['date']}: {row['booking_count']} бронирований")
    else:
        print("Нет бронирований")
    
    # Проверяем все бронирования (включая отмененные)
    cur.execute("""
        SELECT 
            b.date,
            COUNT(*) as booking_count,
            SUM(CASE WHEN b.cancel = TRUE THEN 1 ELSE 0 END) as cancelled_count,
            SUM(CASE WHEN b.finish IS NOT NULL THEN 1 ELSE 0 END) as finished_count
        FROM bookings b
        WHERE b.date >= %s 
            AND b.date <= %s
        GROUP BY b.date 
        ORDER BY b.date
    """, (date_from, date_to))
    all_rows = cur.fetchall()
    
    print(f"\n=== Все бронирования в декабре 2025 (включая отмененные) ===")
    if all_rows:
        for row in all_rows:
            print(f"{row['date']}: всего={row['booking_count']}, отменено={row['cancelled_count']}, завершено={row['finished_count']}")
    else:
        print("Нет бронирований")

conn.close()

