"""
Скрипт для анализа структуры таблиц invoice_* и consumption_*.
Проверяет структуру, различия и возможность нормализации.

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


def analyze_structure():
    """Анализ структуры таблиц invoice_* и consumption_*"""
    
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
        
        # Анализ invoice таблиц
        invoice_tables = ['invoice_ms', 'invoice_m', 'invoice_pp']
        consumption_tables = ['consumption_ms', 'consumption_m', 'consumption_pp']
        
        log("=" * 60)
        log("АНАЛИЗ СТРУКТУРЫ ТАБЛИЦ INVOICE")
        log("=" * 60)
        
        invoice_structures = {}
        for table_name in invoice_tables:
            log(f"\n=== Таблица {table_name} ===")
            
            cursor.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            
            columns = cursor.fetchall()
            column_names = [col['column_name'] for col in columns]
            invoice_structures[table_name] = column_names
            
            if not columns:
                log(f"[WARN] Таблица {table_name} не найдена!")
                continue
            
            for col in columns:
                col_type = col['data_type']
                if col['character_maximum_length']:
                    col_type += f"({col['character_maximum_length']})"
                elif col['numeric_precision']:
                    col_type += f"({col['numeric_precision']},{col['numeric_scale']})"
                
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                
                log(f"  {col['column_name']}: {col_type} {nullable}{default}")
            
            # Проверка наличия pp_id
            has_pp = 'pp_id' in column_names
            log(f"\n  Наличие pp_id: {'ДА' if has_pp else 'НЕТ'}")
            
            # Пример данных
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
            row = cursor.fetchone()
            if row:
                log(f"\n  Пример записи:")
                for key, value in list(row.items())[:10]:  # Первые 10 полей
                    log(f"    {key}: {value}")
                if len(row) > 10:
                    log(f"    ... и еще {len(row) - 10} полей")
        
        # Сравнение структур
        log("\n" + "=" * 60)
        log("СРАВНЕНИЕ СТРУКТУР INVOICE")
        log("=" * 60)
        
        all_columns = set()
        for cols in invoice_structures.values():
            all_columns.update(cols)
        
        log("\nОбщие столбцы (есть во всех таблицах):")
        common_cols = set.intersection(*[set(cols) for cols in invoice_structures.values()])
        for col in sorted(common_cols):
            log(f"  - {col}")
        
        log("\nУникальные столбцы:")
        for table_name, cols in invoice_structures.items():
            unique = set(cols) - common_cols
            if unique:
                log(f"  {table_name}: {', '.join(sorted(unique))}")
        
        # Анализ consumption таблиц
        log("\n" + "=" * 60)
        log("АНАЛИЗ СТРУКТУРЫ ТАБЛИЦ CONSUMPTION")
        log("=" * 60)
        
        consumption_structures = {}
        for table_name in consumption_tables:
            log(f"\n=== Таблица {table_name} ===")
            
            cursor.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))
            
            columns = cursor.fetchall()
            column_names = [col['column_name'] for col in columns]
            consumption_structures[table_name] = column_names
            
            if not columns:
                log(f"[WARN] Таблица {table_name} не найдена!")
                continue
            
            for col in columns:
                col_type = col['data_type']
                if col['character_maximum_length']:
                    col_type += f"({col['character_maximum_length']})"
                elif col['numeric_precision']:
                    col_type += f"({col['numeric_precision']},{col['numeric_scale']})"
                
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                
                log(f"  {col['column_name']}: {col_type} {nullable}{default}")
        
        # Сравнение структур consumption
        log("\n" + "=" * 60)
        log("СРАВНЕНИЕ СТРУКТУР CONSUMPTION")
        log("=" * 60)
        
        all_cons_columns = set()
        for cols in consumption_structures.values():
            all_cons_columns.update(cols)
        
        log("\nОбщие столбцы (есть во всех таблицах):")
        common_cons_cols = set.intersection(*[set(cols) for cols in consumption_structures.values()])
        for col in sorted(common_cons_cols):
            log(f"  - {col}")
        
        log("\nУникальные столбцы:")
        for table_name, cols in consumption_structures.items():
            unique = set(cols) - common_cons_cols
            if unique:
                log(f"  {table_name}: {', '.join(sorted(unique))}")
        
        # Проверка item_id
        log("\n" + "=" * 60)
        log("АНАЛИЗ item_id и pp_id")
        log("=" * 60)
        
        for table_name in invoice_tables:
            has_pp = 'pp_id' in invoice_structures[table_name]
            
            if has_pp:
                cursor.execute(f"""
                    SELECT 
                        item_id,
                        name_id,
                        chip_id,
                        body_id,
                        pp_id
                    FROM {table_name}
                    WHERE pp_id IS NOT NULL
                    LIMIT 5
                """)
                rows = cursor.fetchall()
                
                if rows:
                    log(f"\n{table_name} - записи с pp_id:")
                    for row in rows[:3]:
                        log(f"  item_id={row['item_id']}, name_id={row['name_id']}, chip_id={row['chip_id']}, body_id={row['body_id']}, pp_id={row.get('pp_id', 'NULL')}")
                else:
                    cursor.execute(f"""
                        SELECT 
                            item_id,
                            name_id,
                            chip_id,
                            body_id
                        FROM {table_name}
                        LIMIT 3
                    """)
                    rows = cursor.fetchall()
                    log(f"\n{table_name} - записи (pp_id всегда NULL):")
                    for row in rows[:3]:
                        log(f"  item_id={row['item_id']}, name_id={row['name_id']}, chip_id={row['chip_id']}, body_id={row['body_id']}")
            else:
                cursor.execute(f"""
                    SELECT 
                        item_id,
                        name_id,
                        chip_id,
                        body_id
                    FROM {table_name}
                    LIMIT 3
                """)
                rows = cursor.fetchall()
                log(f"\n{table_name} - примеры записей (pp_id нет в структуре):")
                for row in rows[:3]:
                    log(f"  item_id={row['item_id']}, name_id={row['name_id']}, chip_id={row['chip_id']}, body_id={row['body_id']}")
        
        # Статистика
        log("\n" + "=" * 60)
        log("СТАТИСТИКА")
        log("=" * 60)
        
        for table_name in invoice_tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            log(f"{table_name}: {count} записей")
        
        for table_name in consumption_tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            log(f"{table_name}: {count} записей")
        
        log("\n[OK] Анализ завершен!")
        
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
    log("=== Анализ структуры таблиц invoice_* и consumption_* ===")
    analyze_structure()
    log("=== Готово ===")
