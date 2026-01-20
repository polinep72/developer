"""
Скрипт для удаления уникального ограничения из таблицы invoices.

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'warehouse')


def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


try:
    conn = psycopg2.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor()
    
    log("Удаление уникального ограничения...")
    cursor.execute("ALTER TABLE invoices DROP CONSTRAINT IF EXISTS unique_invoice_record")
    conn.commit()
    log("[OK] Уникальное ограничение удалено")
    
except Exception as e:
    log(f"[ERROR] {e}")
    sys.exit(1)
finally:
    if cursor:
        cursor.close()
    if conn:
        conn.close()
