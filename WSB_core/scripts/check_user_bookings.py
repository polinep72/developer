"""Скрипт для проверки бронирований пользователя"""
import sys
import os
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Устанавливаем рабочую директорию
os.chdir(PROJECT_ROOT)

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Загружаем .env
load_dotenv(PROJECT_ROOT / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "RM")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

user_id = 649315739

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.cursor_factory = psycopg2.extras.DictCursor

with conn.cursor() as cur:
        # Получаем бронирования пользователя
        cur.execute("""
            SELECT b.id, b.user_id, b.equip_id, b.date, b.time_start, b.time_end, 
                   b.data_booking, b.cancel, b.finish, e.name_equip
            FROM bookings b
            JOIN equipment e ON b.equip_id = e.id
            WHERE b.user_id = %s
            ORDER BY b.data_booking DESC
            LIMIT 10
        """, (user_id,))
        bookings = cur.fetchall()
        
        print(f"\n=== Бронирования пользователя {user_id} ===")
        for b in bookings:
            print(f"\nID={b['id']}")
            print(f"  Оборудование: {b['name_equip']}")
            print(f"  Дата бронирования: {b['date']}")
            print(f"  Время: {b['time_start']} - {b['time_end']}")
            print(f"  Создано: {b['data_booking']}")
            print(f"  Отменено: {b['cancel']}, Завершено: {b['finish']}")
        
        # Получаем уведомления для этих бронирований
        booking_ids = [b['id'] for b in bookings]
        if booking_ids:
            cur.execute("""
                SELECT id, booking_id, channel, event_type, run_at, status
                FROM wsb_notifications_schedule
                WHERE booking_id = ANY(%s)
                ORDER BY run_at DESC
            """, (booking_ids,))
            notifications = cur.fetchall()
            
            print(f"\n=== Уведомления для этих бронирований ===")
            for n in notifications:
                print(f"\nID={n['id']}, booking_id={n['booking_id']}")
                print(f"  Канал: {n['channel']}, Тип: {n['event_type']}")
                print(f"  Время выполнения: {n['run_at']}")
                print(f"  Статус: {n['status']}")

conn.close()

