"""
Скрипт для миграции на английские названия таблиц и добавления недостающих полей (description, price).
Обновляет существующую нормализованную структуру.

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


def migrate_to_english_schema():
    """Миграция на английские названия и добавление недостающих полей"""
    
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
        
        log("Подключение установлено\n")
        
        # 1. Создание таблиц с английскими названиями (если не существуют)
        log("=== Создание таблиц с английскими названиями ===")
        
        # Проверка существования таблицы типов элементов
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'element_types'
            )
        """)
        element_types_exists = cursor.fetchone()['exists']
        
        if not element_types_exists:
            log("Создание таблицы element_types...")
            cursor.execute("""
                CREATE TABLE element_types (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(10) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Перенос данных из типы_элементов в element_types
            cursor.execute("""
                INSERT INTO element_types (id, code, name, description, created_at)
                SELECT id, код, название, описание, created_at
                FROM типы_элементов
                ORDER BY id
            """)
            log(f"Перенесено {cursor.rowcount} типов элементов")
        else:
            log("[OK] Таблица element_types уже существует")
        
        # Проверка существования таблицы elements
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'elements'
            )
        """)
        elements_exists = cursor.fetchone()['exists']
        
        if not elements_exists:
            log("Создание таблицы elements...")
            cursor.execute("""
                CREATE TABLE elements (
                    id SERIAL PRIMARY KEY,
                    element_type_id INTEGER NOT NULL REFERENCES element_types(id) ON DELETE RESTRICT,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    price NUMERIC(12, 2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT unique_element_by_type UNIQUE (element_type_id, name)
                )
            """)
            log("[OK] Таблица elements создана")
        else:
            log("[OK] Таблица elements уже существует")
        
        # 2. Добавление недостающих полей в таблицу элементы (если используется русское название)
        log("\n=== Проверка и добавление недостающих полей ===")
        
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'элементы'
            )
        """)
        russian_table_exists = cursor.fetchone()['exists']
        
        if russian_table_exists:
            # Проверка наличия поля description
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'элементы' 
                    AND column_name = 'description'
                )
            """)
            has_description = cursor.fetchone()['exists']
            
            if not has_description:
                log("Добавление поля description в таблицу элементы...")
                cursor.execute("ALTER TABLE элементы ADD COLUMN description TEXT")
                log("[OK] Поле description добавлено")
            
            # Проверка наличия поля price
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = 'элементы' 
                    AND column_name = 'price'
                )
            """)
            has_price = cursor.fetchone()['exists']
            
            if not has_price:
                log("Добавление поля price в таблицу элементы...")
                cursor.execute("ALTER TABLE элементы ADD COLUMN price NUMERIC(12, 2)")
                log("[OK] Поле price добавлено")
        
        # 3. Перенос данных из таблиц names_* в elements с всеми полями
        log("\n=== Перенос данных из names_* в elements ===")
        
        # Получение маппинга типов
        cursor.execute("SELECT id, code FROM element_types")
        type_map = {row['code']: row['id'] for row in cursor.fetchall()}
        log(f"Найдены типы: {type_map}")
        
        # Перенос из names_ms
        log("\nПеренос из names_ms...")
        cursor.execute("""
            INSERT INTO elements (element_type_id, name, description, price, created_at, updated_at)
            SELECT 
                %s as element_type_id,
                n.name,
                n.description,
                n.price,
                n.created_at,
                n.updated_at
            FROM names_ms n
            WHERE NOT EXISTS (
                SELECT 1 FROM elements 
                WHERE element_type_id = %s AND name = n.name
            )
        """, (type_map['ms'], type_map['ms']))
        log(f"Перенесено {cursor.rowcount} записей из names_ms")
        
        # Перенос из names_m
        log("\nПеренос из names_m...")
        cursor.execute("""
            INSERT INTO elements (element_type_id, name, description, price, created_at, updated_at)
            SELECT 
                %s as element_type_id,
                n.name,
                n.description,
                n.price,
                n.created_at,
                n.updated_at
            FROM names_m n
            WHERE NOT EXISTS (
                SELECT 1 FROM elements 
                WHERE element_type_id = %s AND name = n.name
            )
        """, (type_map['m'], type_map['m']))
        log(f"Перенесено {cursor.rowcount} записей из names_m")
        
        # Перенос из names_pp
        log("\nПеренос из names_pp...")
        cursor.execute("""
            INSERT INTO elements (element_type_id, name, description, price, created_at, updated_at)
            SELECT 
                %s as element_type_id,
                n.name,
                n.description,
                n.price,
                n.created_at,
                n.updated_at
            FROM names_pp n
            WHERE NOT EXISTS (
                SELECT 1 FROM elements 
                WHERE element_type_id = %s AND name = n.name
            )
        """, (type_map['pp'], type_map['pp']))
        log(f"Перенесено {cursor.rowcount} записей из names_pp")
        
        # 4. Создание индексов
        log("\n=== Создание индексов ===")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_elements_element_type_id ON elements(element_type_id)",
            "CREATE INDEX IF NOT EXISTS idx_elements_name ON elements(name)",
            "CREATE INDEX IF NOT EXISTS idx_elements_price ON elements(price)"
        ]
        
        for idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
                log(f"[OK] Индекс создан")
            except Exception as e:
                log(f"[WARN] Ошибка создания индекса: {e}")
        
        # 5. Проверка результатов
        log("\n=== Проверка результатов ===")
        cursor.execute("SELECT COUNT(*) as count FROM elements")
        total_elements = cursor.fetchone()['count']
        log(f"Всего элементов в таблице elements: {total_elements}")
        
        cursor.execute("""
            SELECT 
                et.code,
                et.name,
                COUNT(e.id) as count
            FROM element_types et
            LEFT JOIN elements e ON e.element_type_id = et.id
            GROUP BY et.id, et.code, et.name
            ORDER BY et.code
        """)
        
        log("\nРаспределение по типам:")
        for row in cursor.fetchall():
            log(f"  {row['code']} ({row['name']}): {row['count']} элементов")
        
        # 6. Проверка наличия price и description
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(description) as with_description,
                COUNT(price) as with_price
            FROM elements
        """)
        stats = cursor.fetchone()
        log(f"\nСтатистика полей:")
        log(f"  Всего записей: {stats['total']}")
        log(f"  С description: {stats['with_description']}")
        log(f"  С price: {stats['with_price']}")
        
        # Подтверждение транзакции
        conn.commit()
        log("\n[OK] Миграция завершена успешно!")
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
    log("=== Миграция на английские названия и добавление полей ===")
    migrate_to_english_schema()
    log("=== Готово ===")
