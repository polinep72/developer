"""
Скрипт миграции данных из names_ms, names_m, names_pp в нормализованную структуру (элементы, типы_элементов).
Сохраняет обратную совместимость через VIEW.

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


def migrate_data():
    """Миграция данных из names_ms, names_m, names_pp в элементы"""
    
    try:
        # Подключение к БД
        log(f"Подключение к БД {DB_NAME} на {DB_HOST}...")
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        conn.autocommit = False
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        log("Подключение установлено")
        
        # 1. Проверка существования нормализованной структуры
        log("Проверка нормализованной структуры...")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'типы_элементов'
            )
        """)
        if not cursor.fetchone()['exists']:
            log("ОШИБКА: Таблица 'типы_элементов' не найдена!")
            log("Сначала выполните SQL-скрипт: database/normalized_schema.sql")
            sys.exit(1)
        
        # 2. Получение ID типов элементов
        log("Получение ID типов элементов...")
        cursor.execute("SELECT id, код FROM типы_элементов")
        type_map = {row['код']: row['id'] for row in cursor.fetchall()}
        log(f"Найдены типы: {type_map}")
        
        if 'ms' not in type_map or 'm' not in type_map or 'pp' not in type_map:
            log("ОШИБКА: Не все типы элементов найдены в таблице типы_элементов!")
            sys.exit(1)
        
        # 3. Миграция данных из names_ms
        log("\n=== Миграция names_ms (Микросхемы) ===")
        cursor.execute("SELECT COUNT(*) as count FROM names_ms")
        ms_count = cursor.fetchone()['count']
        log(f"Найдено записей в names_ms: {ms_count}")
        
        cursor.execute("""
            INSERT INTO элементы (тип_id, наименование, обозначение)
            SELECT 
                %s as тип_id,
                name as наименование,
                name as обозначение
            FROM names_ms
            WHERE NOT EXISTS (
                SELECT 1 FROM элементы 
                WHERE тип_id = %s AND наименование = names_ms.name
            )
            RETURNING id, наименование
        """, (type_map['ms'], type_map['ms']))
        
        ms_inserted = cursor.rowcount
        log(f"Мигрировано записей из names_ms: {ms_inserted}")
        
        # 4. Миграция данных из names_m
        log("\n=== Миграция names_m (Модули) ===")
        cursor.execute("SELECT COUNT(*) as count FROM names_m")
        m_count = cursor.fetchone()['count']
        log(f"Найдено записей в names_m: {m_count}")
        
        cursor.execute("""
            INSERT INTO элементы (тип_id, наименование, обозначение)
            SELECT 
                %s as тип_id,
                name as наименование,
                name as обозначение
            FROM names_m
            WHERE NOT EXISTS (
                SELECT 1 FROM элементы 
                WHERE тип_id = %s AND наименование = names_m.name
            )
        """, (type_map['m'], type_map['m']))
        
        m_inserted = cursor.rowcount
        log(f"Мигрировано записей из names_m: {m_inserted}")
        
        # 5. Миграция данных из names_pp
        log("\n=== Миграция names_pp (ПП) ===")
        cursor.execute("SELECT COUNT(*) as count FROM names_pp")
        pp_count = cursor.fetchone()['count']
        log(f"Найдено записей в names_pp: {pp_count}")
        
        cursor.execute("""
            INSERT INTO элементы (тип_id, наименование, обозначение)
            SELECT 
                %s as тип_id,
                name as наименование,
                name as обозначение
            FROM names_pp
            WHERE NOT EXISTS (
                SELECT 1 FROM элементы 
                WHERE тип_id = %s AND наименование = names_pp.name
            )
        """, (type_map['pp'], type_map['pp']))
        
        pp_inserted = cursor.rowcount
        log(f"Мигрировано записей из names_pp: {pp_inserted}")
        
        # 6. Создание VIEW для обратной совместимости
        log("\n=== Создание VIEW для обратной совместимости ===")
        
        # VIEW для names_ms
        cursor.execute("""
            CREATE OR REPLACE VIEW names_ms_view AS
            SELECT 
                e.id,
                e.наименование as name
            FROM элементы e
            JOIN типы_элементов t ON e.тип_id = t.id
            WHERE t.код = 'ms'
        """)
        log("Создан VIEW: names_ms_view")
        
        # VIEW для names_m
        cursor.execute("""
            CREATE OR REPLACE VIEW names_m_view AS
            SELECT 
                e.id,
                e.наименование as name
            FROM элементы e
            JOIN типы_элементов t ON e.тип_id = t.id
            WHERE t.код = 'm'
        """)
        log("Создан VIEW: names_m_view")
        
        # VIEW для names_pp
        cursor.execute("""
            CREATE OR REPLACE VIEW names_pp_view AS
            SELECT 
                e.id,
                e.наименование as name
            FROM элементы e
            JOIN типы_элементов t ON e.тип_id = t.id
            WHERE t.код = 'pp'
        """)
        log("Создан VIEW: names_pp_view")
        
        # 7. Проверка миграции
        log("\n=== Проверка миграции ===")
        cursor.execute("""
            SELECT 
                t.код,
                t.название,
                COUNT(e.id) as количество
            FROM типы_элементов t
            LEFT JOIN элементы e ON e.тип_id = t.id
            GROUP BY t.id, t.код, t.название
            ORDER BY t.код
        """)
        
        log("Результаты миграции:")
        for row in cursor.fetchall():
            log(f"  {row['код']} ({row['название']}): {row['количество']} элементов")
        
        # 8. Проверка совпадения данных
        cursor.execute("SELECT COUNT(*) as count FROM names_ms")
        original_ms = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM элементы WHERE тип_id = %s", (type_map['ms'],))
        migrated_ms = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM names_m")
        original_m = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM элементы WHERE тип_id = %s", (type_map['m'],))
        migrated_m = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM names_pp")
        original_pp = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM элементы WHERE тип_id = %s", (type_map['pp'],))
        migrated_pp = cursor.fetchone()['count']
        
        log("\n=== Сравнение данных ===")
        log(f"Микросхемы: оригинал={original_ms}, мигрировано={migrated_ms}")
        log(f"Модули: оригинал={original_m}, мигрировано={migrated_m}")
        log(f"ПП: оригинал={original_pp}, мигрировано={migrated_pp}")
        
        if original_ms == migrated_ms and original_m == migrated_m and original_pp == migrated_pp:
            log("\n[OK] Миграция успешно завершена!")
        else:
            log("\n[WARN] ВНИМАНИЕ: Количество записей не совпадает!")
            log("Возможные причины: дубликаты в исходных таблицах или проблемы с миграцией")
        
        # Подтверждение транзакции
        conn.commit()
        log("\nТранзакция зафиксирована")
        
    except psycopg2.Error as e:
        log(f"\n[ERROR] ОШИБКА БД: {e}")
        if conn:
            conn.rollback()
            log("Транзакция отменена")
        sys.exit(1)
    except Exception as e:
        log(f"\n[ERROR] ОШИБКА: {e}")
        if conn:
            conn.rollback()
            log("Транзакция отменена")
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            log("Подключение закрыто")


if __name__ == "__main__":
    log("=== Начало миграции данных ===")
    migrate_data()
    log("=== Миграция завершена ===")
