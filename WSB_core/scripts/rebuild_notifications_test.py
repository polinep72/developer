"""Пересборка расписания уведомлений в тестовой БД"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

# Добавляем путь к ядру
sys.path.insert(0, str(Path(__file__).parent.parent))

from wsb_core.notifications_schedule import (
    ensure_notifications_schedule_table,
    rebuild_schedule_for_all_bookings,
)

load_dotenv(Path(__file__).parent.parent / '.env')

DB_HOST = os.getenv('DB_HOST', '192.168.1.22')
DB_NAME = os.getenv('DB_NAME', 'RM')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_PORT = os.getenv('DB_PORT', '5432')

conn = psycopg.connect(
    host=DB_HOST,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    port=DB_PORT,
    row_factory=dict_row
)

try:
    with conn.cursor() as cur:
        ensure_notifications_schedule_table(cur)
        # Очищаем старое расписание
        cur.execute('DELETE FROM wsb_notifications_schedule')
        print('Старое расписание очищено')
        
        # Пересобираем для всех активных броней
        created = rebuild_schedule_for_all_bookings(cur)
        conn.commit()
        
        # Показываем результаты
        cur.execute("""
            SELECT id, booking_id, channel, event_type, run_at, status
            FROM wsb_notifications_schedule
            ORDER BY booking_id, id
        """)
        rows = cur.fetchall()
        
        print(f'\nСоздано записей: {created}')
        print(f'Всего в расписании: {len(rows)}')
        print('\nПервые 20 записей:')
        for r in rows[:20]:
            print(f"ID={r['id']}, booking_id={r['booking_id']}, "
                  f"channel={r['channel']}, event={r['event_type']}, "
                  f"run_at={r['run_at']}, status={r['status']}")
finally:
    conn.close()

