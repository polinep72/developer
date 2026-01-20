"""
Скрипт для применения нормализованной схемы для invoices и consumptions.

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
Лицензионные права: ИнноЦентр ВАО и ИПК Электрон-Маш
"""

import os
import sys
import psycopg2
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


def apply_schema():
    """Применение нормализованной схемы для invoices и consumptions"""
    
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
        cursor = conn.cursor()
        
        log("Подключение установлено")
        
        # Чтение SQL-скрипта
        script_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'normalized_invoices_consumptions.sql')
        script_path = os.path.abspath(script_path)
        
        if not os.path.exists(script_path):
            log(f"[ERROR] Файл {script_path} не найден!")
            sys.exit(1)
        
        log(f"Чтение SQL-скрипта: {script_path}")
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # Выполнение скрипта
        log("\nПрименение схемы...")
        cursor.execute(sql_script)
        
        # Проверка созданных таблиц
        log("\n=== Проверка созданных таблиц ===")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('invoices', 'consumptions')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        if len(tables) == 2:
            log("[OK] Обе таблицы созданы успешно:")
            for table in tables:
                log(f"  - {table[0]}")
        else:
            log(f"[WARN] Найдено таблиц: {len(tables)} (ожидалось 2)")
            for table in tables:
                log(f"  - {table[0]}")
        
        # Проверка индексов
        log("\n=== Проверка индексов ===")
        cursor.execute("""
            SELECT indexname, tablename 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND tablename IN ('invoices', 'consumptions')
            ORDER BY tablename, indexname
        """)
        
        indexes = cursor.fetchall()
        log(f"[OK] Создано {len(indexes)} индексов:")
        for idx in indexes[:10]:  # Показать первые 10
            log(f"  {idx[1]}.{idx[0]}")
        if len(indexes) > 10:
            log(f"  ... и еще {len(indexes) - 10} индексов")
        
        # Подтверждение транзакции
        conn.commit()
        log("\n[OK] Схема применена успешно!")
        log("Транзакция зафиксирована")
        
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
    log("=== Применение нормализованной схемы для invoices и consumptions ===")
    apply_schema()
    log("=== Готово ===")
