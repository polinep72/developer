"""
Скрипт для проверки структуры таблиц names_ms, names_m, names_pp.
Проверяет наличие всех столбцов, включая description и price.

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


def check_structure():
    """Проверка структуры таблиц names_*"""
    
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
        
        # Проверка структуры каждой таблицы
        tables = ['names_ms', 'names_m', 'names_pp']
        
        for table_name in tables:
            log(f"=== Структура таблицы {table_name} ===")
            
            cursor.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            
            columns = cursor.fetchall()
            
            if not columns:
                log(f"[WARN] Таблица {table_name} не найдена!")
                continue
            
            for col in columns:
                col_type = col['data_type']
                if col['character_maximum_length']:
                    col_type += f"({col['character_maximum_length']})"
                
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                
                log(f"  {col['column_name']}: {col_type} {nullable}{default}")
            
            # Проверка наличия важных полей
            column_names = [col['column_name'] for col in columns]
            log("\n  Наличие полей:")
            log(f"    id: {'ДА' if 'id' in column_names else 'НЕТ'}")
            log(f"    name: {'ДА' if 'name' in column_names else 'НЕТ'}")
            log(f"    description: {'ДА' if 'description' in column_names else 'НЕТ'}")
            log(f"    price: {'ДА' if 'price' in column_names else 'НЕТ'}")
            
            log("")
        
        # Проверка примера данных
        log("=== Примеры данных ===")
        for table_name in tables:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
            row = cursor.fetchone()
            if row:
                log(f"\n{table_name} (пример записи):")
                for key, value in row.items():
                    log(f"  {key}: {value}")
            else:
                log(f"\n{table_name}: таблица пуста")
        
        log("\n[OK] Проверка завершена!")
        
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
    log("=== Проверка структуры таблиц names_* ===")
    check_structure()
    log("=== Готово ===")
