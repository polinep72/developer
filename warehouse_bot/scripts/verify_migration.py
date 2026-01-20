"""
Скрипт для проверки корректности миграции данных.
Проверяет соответствие данных в старых и новых таблицах.

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
Лицензионные права: ИнноЦентр ВАО и ИПК Электрон-Маш
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

# Параметры подключения к БД
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'warehouse')


def log(message):
    """Вывод сообщения с временной меткой"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def verify_migration():
    """Проверка корректности миграции данных"""
    
    try:
        # Подключение к БД
        log(f"Подключение к БД {DB_NAME} на {DB_HOST}...")
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        log("Подключение установлено\n")
        
        # 1. Проверка общего количества записей
        log("=== Проверка общего количества записей ===")
        
        cursor.execute("SELECT COUNT(*) as count FROM names_ms")
        old_ms = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM элементы e JOIN типы_элементов t ON e.тип_id = t.id WHERE t.код = 'ms'")
        new_ms = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM names_m")
        old_m = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM элементы e JOIN типы_элементов t ON e.тип_id = t.id WHERE t.код = 'm'")
        new_m = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM names_pp")
        old_pp = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM элементы e JOIN типы_элементов t ON e.тип_id = t.id WHERE t.код = 'pp'")
        new_pp = cursor.fetchone()['count']
        
        log(f"Микросхемы: старые={old_ms}, новые={new_ms}, совпадают={'ДА' if old_ms == new_ms else 'НЕТ'}")
        log(f"Модули: старые={old_m}, новые={new_m}, совпадают={'ДА' if old_m == new_m else 'НЕТ'}")
        log(f"ПП: старые={old_pp}, новые={new_pp}, совпадают={'ДА' if old_pp == new_pp else 'НЕТ'}")
        
        if old_ms == new_ms and old_m == new_m and old_pp == new_pp:
            log("[OK] Количество записей совпадает!\n")
        else:
            log("[ERROR] ОШИБКА: Количество записей не совпадает!\n")
            return False
        
        # 2. Проверка примеров записей
        log("=== Проверка примеров записей ===")
        
        # Микросхемы
        cursor.execute("SELECT name FROM names_ms LIMIT 3")
        old_ms_names = [row['name'] for row in cursor.fetchall()]
        cursor.execute("SELECT e.наименование FROM элементы e JOIN типы_элементов t ON e.тип_id = t.id WHERE t.код = 'ms' LIMIT 3")
        new_ms_names = [row['наименование'] for row in cursor.fetchall()]
        
        log(f"Примеры микросхем:")
        log(f"  Старые: {', '.join(old_ms_names[:3])}")
        log(f"  Новые: {', '.join(new_ms_names[:3])}")
        log(f"  Совпадают: {'ДА' if set(old_ms_names) == set(new_ms_names) else 'НЕТ'}\n")
        
        # 3. Проверка типов элементов
        log("=== Проверка типов элементов ===")
        cursor.execute("SELECT id, код, название FROM типы_элементов ORDER BY код")
        types = cursor.fetchall()
        
        for type_row in types:
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM элементы 
                WHERE тип_id = %s
            """, (type_row['id'],))
            count = cursor.fetchone()['count']
            log(f"  {type_row['код']} ({type_row['название']}): {count} элементов")
        
        log("")
        
        # 4. Проверка индексов
        log("=== Проверка индексов ===")
        cursor.execute("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename IN ('элементы', 'типы_элементов')
            ORDER BY tablename, indexname
        """)
        indexes = cursor.fetchall()
        
        for idx in indexes:
            log(f"  {idx['tablename']}.{idx['indexname']}")
        
        log("")
        
        # 5. Проверка VIEW
        log("=== Проверка VIEW для обратной совместимости ===")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.views 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'names_%_view'
            ORDER BY table_name
        """)
        views = cursor.fetchall()
        
        for view in views:
            log(f"  [OK] {view['table_name']} создан")
        
        log("\n[OK] Проверка завершена успешно!")
        return True
        
    except psycopg2.Error as e:
        log(f"\n[ERROR] ОШИБКА БД: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"\n[ERROR] ОШИБКА: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            log("Подключение закрыто")


if __name__ == "__main__":
    log("=== Проверка миграции данных ===")
    success = verify_migration()
    if success:
        log("\n=== Миграция проверена успешно ===")
        sys.exit(0)
    else:
        log("\n=== Обнаружены проблемы при проверке ===")
        sys.exit(1)
