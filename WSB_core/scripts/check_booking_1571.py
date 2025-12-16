"""Проверка бронирования 1571 и его уведомлений"""
import sys
import os
from pathlib import Path
from datetime import datetime

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

booking_id = 1571

with conn.cursor() as cur:
    # Проверяем бронирование
    cur.execute("""
        SELECT b.*, e.name_equip
        FROM bookings b
        JOIN equipment e ON b.equip_id = e.id
        WHERE b.id = %s
    """, (booking_id,))
    booking = cur.fetchone()
    
    if booking:
        print(f"\n=== Бронирование ID={booking_id} ===")
        print(f"Оборудование: {booking['name_equip']}")
        print(f"Дата бронирования: {booking['date']}")
        print(f"Время: {booking['time_start']} - {booking['time_end']}")
        print(f"Создано: {booking['data_booking']}")
        print(f"Отменено: {booking['cancel']}, Завершено: {booking['finish']}")
        
        now = datetime.now()
        print(f"\nТекущее время: {now}")
        print(f"Время начала брони: {booking['time_start']}")
        print(f"Время окончания брони: {booking['time_end']}")
        print(f"Бронь уже прошла: {booking['time_end'] < now}")
        
        # Проверяем уведомления
        cur.execute("""
            SELECT id, booking_id, channel, event_type, run_at, status, created_at, updated_at
            FROM wsb_notifications_schedule
            WHERE booking_id = %s
            ORDER BY run_at
        """, (booking_id,))
        notifications = cur.fetchall()
        
        print(f"\n=== Уведомления для бронирования {booking_id} ===")
        for n in notifications:
            print(f"\nID={n['id']}")
            print(f"  Канал: {n['channel']}, Тип: {n['event_type']}")
            print(f"  Время выполнения: {n['run_at']}")
            print(f"  Статус: {n['status']}")
            print(f"  Создано: {n.get('created_at', 'N/A')}")
            print(f"  Обновлено: {n.get('updated_at', 'N/A')}")
            print(f"  Уже прошло: {n['run_at'] < now}")
    
    # Проверяем все бронирования на "Стенд большой мощности" на сегодня
    cur.execute("""
        SELECT b.id, b.date, b.time_start, b.time_end, b.data_booking, b.cancel, b.finish
        FROM bookings b
        JOIN equipment e ON b.equip_id = e.id
        WHERE e.name_equip LIKE '%Стенд большой мощности%'
          AND b.date = CURRENT_DATE
        ORDER BY b.time_start
    """)
    today_bookings = cur.fetchall()
    
    print(f"\n=== Бронирования 'Стенд большой мощности' на сегодня ({datetime.now().date()}) ===")
    if today_bookings:
        for b in today_bookings:
            print(f"\nID={b['id']}")
            print(f"  Время: {b['time_start']} - {b['time_end']}")
            print(f"  Создано: {b['data_booking']}")
            print(f"  Отменено: {b['cancel']}, Завершено: {b['finish']}")
    else:
        print("Нет бронирований на сегодня")

conn.close()

