"""
Скрипт для создания таблицы audit_log в базе данных.

Этот скрипт выполняет SQL миграцию create_audit_log.sql для создания
таблицы логирования действий пользователей.

ВАЖНО: 
1. Перед запуском сделайте резервную копию БД!
2. Этот скрипт можно запускать несколько раз - используется IF NOT EXISTS
3. После выполнения миграции система начнет логировать все действия пользователей

Использование:
    python create_audit_log_migration.py
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

# Загружаем переменные окружения
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

def get_db_connection():
    """Получение подключения к БД"""
    db_name = os.getenv('DB_NAME') or os.getenv('DB_NAME2')
    db_host = os.getenv('DB_HOST')
    
    if not db_name or not db_host:
        print("ОШИБКА: Не указаны DB_NAME или DB_HOST в переменных окружения")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            port=os.getenv('DB_PORT', '5432')
        )
        return conn
    except Exception as e:
        print(f"ОШИБКА подключения к БД: {e}")
        sys.exit(1)

def check_table_exists(conn):
    """Проверка существования таблицы audit_log"""
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
           SELECT FROM information_schema.tables 
           WHERE table_schema = 'public' 
           AND table_name = 'audit_log'
        );
    """)
    exists = cur.fetchone()[0]
    cur.close()
    return exists

def create_audit_log_table(conn):
    """Создание таблицы audit_log и индексов"""
    cur = conn.cursor()
    
    try:
        # Создание таблицы
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.audit_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
                action_type VARCHAR(50) NOT NULL,
                table_name VARCHAR(100),
                record_id INTEGER,
                details TEXT,
                ip_address INET,
                user_agent TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("✓ Таблица audit_log создана или уже существует")
        
        # Создание индексов
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON public.audit_log(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON public.audit_log(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_action_type ON public.audit_log(action_type);",
            "CREATE INDEX IF NOT EXISTS idx_audit_log_table_name ON public.audit_log(table_name);"
        ]
        
        for index_sql in indexes:
            cur.execute(index_sql)
        print("✓ Индексы созданы или уже существуют")
        
        # Комментарии к столбцам
        comments = [
            ("TABLE", "public.audit_log", "Журнал аудита действий пользователей"),
            ("COLUMN", "public.audit_log.user_id", "ID пользователя (может быть NULL для неавторизованных действий)"),
            ("COLUMN", "public.audit_log.action_type", "Тип действия: login, logout, create, update, delete, export, file_upload"),
            ("COLUMN", "public.audit_log.table_name", "Имя таблицы, если действие связано с БД"),
            ("COLUMN", "public.audit_log.record_id", "ID записи в таблице, если действие связано с конкретной записью"),
            ("COLUMN", "public.audit_log.details", "Дополнительная информация в виде JSON или текста"),
            ("COLUMN", "public.audit_log.ip_address", "IP адрес пользователя"),
            ("COLUMN", "public.audit_log.user_agent", "User-Agent браузера пользователя"),
            ("COLUMN", "public.audit_log.created_at", "Дата и время действия")
        ]
        
        for comment_type, obj_name, comment_text in comments:
            try:
                if comment_type == "TABLE":
                    cur.execute(f"COMMENT ON TABLE {obj_name} IS %s;", (comment_text,))
                else:
                    cur.execute(f"COMMENT ON COLUMN {obj_name} IS %s;", (comment_text,))
            except Exception as e:
                # Комментарии могут не поддерживаться или уже существовать
                pass
        print("✓ Комментарии добавлены")
        
        conn.commit()
        cur.close()
        return True
        
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"ОШИБКА при создании таблицы: {e}")
        return False

def main():
    """Основная функция"""
    print("=" * 60)
    print("Миграция: Создание таблицы audit_log")
    print("=" * 60)
    
    # Подключение к БД
    print("\n1. Подключение к базе данных...")
    conn = get_db_connection()
    db_name = os.getenv('DB_NAME') or os.getenv('DB_NAME2')
    print(f"   Подключено к БД: {db_name}")
    
    # Проверка существования таблицы
    print("\n2. Проверка существования таблицы audit_log...")
    if check_table_exists(conn):
        print("   ⚠ Таблица audit_log уже существует")
        response = input("   Продолжить миграцию? (y/n): ")
        if response.lower() != 'y':
            print("   Миграция отменена")
            conn.close()
            return
    else:
        print("   ✓ Таблица audit_log не существует, будет создана")
    
    # Создание таблицы
    print("\n3. Создание таблицы и индексов...")
    if create_audit_log_table(conn):
        print("\n" + "=" * 60)
        print("✓ Миграция успешно завершена!")
        print("=" * 60)
        print("\nТеперь система будет логировать все действия пользователей:")
        print("  - login (вход в систему)")
        print("  - logout (выход из системы)")
        print("  - update (обновление данных)")
        print("  - delete (удаление записей)")
        print("  - export (экспорт данных)")
        print("  - file_upload (загрузка файлов)")
    else:
        print("\n" + "=" * 60)
        print("✗ Миграция завершилась с ошибками!")
        print("=" * 60)
        sys.exit(1)
    
    conn.close()

if __name__ == "__main__":
    main()

