"""
Скрипт для создания таблицы notification_settings в БД RM
"""
import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

def _get_env(primary: str, fallback: str | None = None, default: str | None = None) -> str | None:
    value = os.getenv(primary)
    if value:
        return value
    if fallback:
        value = os.getenv(fallback)
        if value:
            return value
    return default

DB_USER = _get_env("DB_USER", "POSTGRE_USER")
DB_PASSWORD = _get_env("DB_PASSWORD", "POSTGRE_PASSWORD")
DB_NAME = _get_env("DB_NAME", "POSTGRE_DBNAME", "RM")
DB_HOST = _get_env("DB_HOST", "POSTGRE_HOST", "localhost")
DB_PORT = _get_env("DB_PORT", "POSTGRE_PORT", "5432")
DB_SSLMODE = _get_env("DB_SSLMODE", None, "prefer")

def create_table():
    """Создать таблицу notification_settings"""
    try:
        conn = psycopg.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            sslmode=DB_SSLMODE,
        )
        
        with conn.cursor() as cur:
            # Проверяем, существует ли таблица
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'notification_settings'
                );
            """)
            exists = cur.fetchone()[0]
            
            if exists:
                print("Таблица notification_settings уже существует.")
                return
            
            # Создаем таблицу
            cur.execute("""
                CREATE TABLE notification_settings (
                    user_id BIGINT PRIMARY KEY REFERENCES users(users_id) ON DELETE CASCADE,
                    email_notifications BOOLEAN DEFAULT TRUE,
                    sms_notifications BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Создаем индекс
            cur.execute("""
                CREATE INDEX idx_notification_settings_user_id ON notification_settings(user_id);
            """)
            
            conn.commit()
            print("Таблица notification_settings успешно создана.")
            
            # Создаем настройки по умолчанию для всех существующих пользователей
            cur.execute("""
                INSERT INTO notification_settings (user_id, email_notifications, sms_notifications)
                SELECT users_id, TRUE, FALSE
                FROM users
                WHERE users_id NOT IN (SELECT user_id FROM notification_settings)
                ON CONFLICT (user_id) DO NOTHING;
            """)
            conn.commit()
            
            count = cur.rowcount
            print(f"Созданы настройки по умолчанию для {count} пользователей.")
            
    except Exception as exc:
        print(f"Ошибка при создании таблицы: {exc}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    create_table()

