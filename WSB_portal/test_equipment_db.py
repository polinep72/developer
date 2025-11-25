"""Тестовый скрипт для проверки подключения к БД equipment"""
import os
import sys
import pathlib
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

# Загружаем .env
env_path = pathlib.Path(__file__).parent / ".env"
print(f"Загрузка .env из: {env_path}")
print(f"Файл существует: {env_path.exists()}")

if env_path.exists():
    load_dotenv(env_path)
    print("[OK] .env файл загружен")
else:
    print("[WARN] .env файл не найден, используем переменные окружения")
    load_dotenv()

# Читаем переменные
EQUIPMENT_DB_NAME = os.getenv("EQUIPMENT_DB_NAME", "equipment")
EQUIPMENT_DB_HOST = os.getenv("EQUIPMENT_DB_HOST") or os.getenv("DB_HOST") or os.getenv("POSTGRE_HOST", "192.168.1.139")
EQUIPMENT_DB_PORT = os.getenv("EQUIPMENT_DB_PORT") or os.getenv("DB_PORT") or os.getenv("POSTGRE_PORT", "5432")
EQUIPMENT_DB_USER = os.getenv("EQUIPMENT_DB_USER") or os.getenv("DB_USER") or os.getenv("POSTGRE_USER", "postgres")
EQUIPMENT_DB_PASSWORD = os.getenv("EQUIPMENT_DB_PASSWORD") or os.getenv("DB_PASSWORD") or os.getenv("POSTGRE_PASSWORD", "27915002")

print("\n[INFO] Параметры подключения:")
print(f"  DB_NAME: {EQUIPMENT_DB_NAME}")
print(f"  DB_HOST: {EQUIPMENT_DB_HOST}")
print(f"  DB_PORT: {EQUIPMENT_DB_PORT}")
print(f"  DB_USER: {EQUIPMENT_DB_USER}")
print(f"  DB_PASSWORD: {'*' * len(EQUIPMENT_DB_PASSWORD) if EQUIPMENT_DB_PASSWORD else 'НЕ УСТАНОВЛЕН'}")

print("\n[INFO] Попытка подключения...")
try:
    conn = psycopg.connect(
        dbname=EQUIPMENT_DB_NAME,
        user=EQUIPMENT_DB_USER,
        password=EQUIPMENT_DB_PASSWORD,
        host=EQUIPMENT_DB_HOST,
        port=EQUIPMENT_DB_PORT,
        connect_timeout=5,
        row_factory=dict_row,
    )
    print("[OK] Подключение успешно!")
    
    with conn.cursor() as cur:
        # Проверяем таблицы
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('equipment_types', 'equipment', 'gosregister', 'calibration_certificates')
            ORDER BY table_name
        """)
        tables = cur.fetchall()
        print(f"\n[INFO] Найденные таблицы: {[t['table_name'] for t in tables]}")
        
        # Проверяем типы оборудования
        cur.execute("SELECT id, type_code, type_name FROM equipment_types ORDER BY id")
        types = cur.fetchall()
        print(f"\n[INFO] Типы оборудования ({len(types)}):")
        for t in types:
            print(f"  - {t['type_code']}: {t['type_name']} (id={t['id']})")
        
        # Проверяем количество записей
        cur.execute("SELECT COUNT(*) as count FROM equipment")
        equipment_count = cur.fetchone()['count']
        print(f"\n[INFO] Количество записей в equipment: {equipment_count}")
        
        cur.execute("SELECT COUNT(*) as count FROM gosregister")
        gosregister_count = cur.fetchone()['count']
        print(f"[INFO] Количество записей в gosregister: {gosregister_count}")
    
    conn.close()
    print("\n[OK] Тест завершен успешно!")
    
except Exception as e:
    print(f"\n[ERROR] Ошибка подключения: {e}")
    print(f"   Тип ошибки: {type(e).__name__}")
    sys.exit(1)

