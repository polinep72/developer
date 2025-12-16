"""
Скрипт для проверки готовности боевой БД к переключению
Проверяет наличие всех необходимых таблиц, столбцов и индексов
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

PROJECT_ROOT = Path(__file__).parent.parent
ENV_PATH = PROJECT_ROOT / '.env'
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

PROD_HOST = '192.168.1.139'
PROD_DB = 'RM'
PROD_USER = os.getenv('DB_USER', 'postgres')
PROD_PASSWORD = os.getenv('DB_PASSWORD', '')


def check_production_db():
    """Проверяет структуру боевой БД"""
    print("=" * 60)
    print("Проверка готовности боевой БД (192.168.1.139)")
    print("=" * 60)
    print()
    
    try:
        conn = psycopg2.connect(
            host=PROD_HOST,
            database=PROD_DB,
            user=PROD_USER,
            password=PROD_PASSWORD,
            port=5432
        )
        conn.set_client_encoding('UTF8')
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        issues = []
        
        # 1. Проверка столбца status в bookings
        print("1. Проверка столбца status в bookings...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'bookings' 
              AND column_name = 'status'
        """)
        if cur.fetchone():
            print("   ✅ Столбец status существует")
        else:
            print("   ❌ Столбец status отсутствует")
            issues.append("Добавить столбец status в bookings")
        
        # 2. Проверка столбцов в users
        print("\n2. Проверка столбцов в users...")
        required_columns = ['email', 'phone', 'password_hash']
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
              AND table_name = 'users' 
              AND column_name IN %s
        """, (tuple(required_columns),))
        existing = {row['column_name'] for row in cur.fetchall()}
        for col in required_columns:
            if col in existing:
                print(f"   ✅ Столбец {col} существует")
            else:
                print(f"   ❌ Столбец {col} отсутствует")
                issues.append(f"Добавить столбец {col} в users")
        
        # 3. Проверка таблиц wsb_*
        print("\n3. Проверка таблиц wsb_*...")
        required_tables = ['wsb_time_slots', 'wsb_notifications_schedule']
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_type = 'BASE TABLE'
              AND table_name IN %s
        """, (tuple(required_tables),))
        existing_tables = {row['table_name'] for row in cur.fetchall()}
        for table in required_tables:
            if table in existing_tables:
                print(f"   ✅ Таблица {table} существует")
            else:
                print(f"   ❌ Таблица {table} отсутствует")
                issues.append(f"Создать таблицу {table}")
        
        # 4. Проверка индексов в bookings
        print("\n4. Проверка индексов в bookings...")
        required_indexes = [
            'idx_bookings_time_end',
            'idx_bookings_user_start',
            'idx_bookings_active_equip_end',
            'idx_bookings_equip_start',
            'idx_bookings_time_start',
            'idx_bookings_active_user_start'
        ]
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
              AND tablename = 'bookings'
              AND indexname IN %s
        """, (tuple(required_indexes),))
        existing_indexes = {row['indexname'] for row in cur.fetchall()}
        for idx in required_indexes:
            if idx in existing_indexes:
                print(f"   ✅ Индекс {idx} существует")
            else:
                print(f"   ❌ Индекс {idx} отсутствует")
                issues.append(f"Создать индекс {idx}")
        
        # 5. Проверка индексов в users
        print("\n5. Проверка индексов в users...")
        required_user_indexes = [
            'users_email_uindex',
            'users_phone_uindex',
            'idx_users_is_admin',
            'idx_users_users_id',
            'idx_users_is_blocked'
        ]
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
              AND tablename = 'users'
              AND indexname IN %s
        """, (tuple(required_user_indexes),))
        existing_user_indexes = {row['indexname'] for row in cur.fetchall()}
        for idx in required_user_indexes:
            if idx in existing_user_indexes:
                print(f"   ✅ Индекс {idx} существует")
            else:
                print(f"   ❌ Индекс {idx} отсутствует")
                issues.append(f"Создать индекс {idx}")
        
        cur.close()
        conn.close()
        
        print("\n" + "=" * 60)
        if issues:
            print("❌ Обнаружены проблемы:")
            for i, issue in enumerate(issues, 1):
                print(f"   {i}. {issue}")
            print("\nПримените скрипт sync_to_production.sql для исправления")
            return False
        else:
            print("✅ Боевая БД готова к переключению!")
            print("\nМожно безопасно изменить DB_HOST в .env на 192.168.1.139")
            return True
            
    except Exception as e:
        print(f"\n❌ Ошибка при проверке БД: {e}")
        return False


if __name__ == '__main__':
    success = check_production_db()
    sys.exit(0 if success else 1)

