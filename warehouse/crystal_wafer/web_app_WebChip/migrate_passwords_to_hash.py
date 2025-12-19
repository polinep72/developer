"""
Скрипт миграции паролей существующих пользователей на хеширование.

ВАЖНО: 
1. Перед запуском сделайте резервную копию БД!
2. Сначала выполните SQL-миграцию expand_password_column.sql для расширения поля password
3. Этот скрипт должен быть запущен один раз после добавления хеширования паролей
4. После миграции все существующие пароли будут хешированы
5. Пользователи смогут войти с теми же паролями, что и раньше

Использование:
    1. Сначала: psql -d <database> -f web_app_WebChip/expand_password_column.sql
    2. Затем: python migrate_passwords_to_hash.py
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from werkzeug.security import generate_password_hash

# Загружаем переменные окружения
load_dotenv()

def get_db_connection():
    """Получение подключения к БД"""
    db_name = os.getenv('DB_NAME') or os.getenv('DB_NAME2')
    db_host = os.getenv('DB_HOST')
    
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT', '5432')
    )
    return conn

def check_password_column_type():
    """Проверяет тип поля password и предупреждает если нужно расширить"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем тип поля password
        query = """
            SELECT data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'users' 
            AND column_name = 'password'
        """
        cur.execute(query)
        result = cur.fetchone()
        
        if result:
            data_type, max_length = result
            if data_type == 'character varying' and max_length and max_length < 200:
                print(f"\n❌ ОШИБКА: Поле password имеет тип VARCHAR({max_length})")
                print("   Хешированные пароли имеют длину ~98-100 символов и могут не поместиться.")
                print("\n   НЕОБХОДИМО сначала выполнить SQL-миграцию для расширения поля:")
                print("   psql -h <host> -U <user> -d <database> -f expand_password_column.sql")
                print("\n   Или выполните SQL команду:")
                print("   ALTER TABLE public.users ALTER COLUMN password TYPE TEXT;")
                print()
                return False
            elif data_type == 'text' or (data_type == 'character varying' and (not max_length or max_length >= 200)):
                print(f"✓ Поле password имеет подходящий тип: {data_type}")
                return True
        return True
    except Exception as e:
        print(f"⚠️  Не удалось проверить тип поля: {e}")
        print("   Продолжаем миграцию (будьте осторожны)...")
        return True
    finally:
        if conn:
            cur.close()
            conn.close()

def migrate_passwords():
    """Миграция всех паролей на хеширование"""
    # Сначала проверяем тип поля
    if not check_password_column_type():
        print("\n❌ Миграция отменена. Выполните SQL-миграцию и попробуйте снова.")
        sys.exit(1)
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Получаем всех пользователей с незахешированными паролями
        # Хешированные пароли начинаются с 'pbkdf2:' или 'scrypt:' (werkzeug может использовать оба формата)
        # Также проверяем, что пароль не пустой
        query = """
            SELECT id, username, password 
            FROM public.users 
            WHERE (password NOT LIKE 'pbkdf2:%' AND password NOT LIKE 'scrypt:%')
            AND password IS NOT NULL
            AND password != ''
        """
        cur.execute(query)
        users = cur.fetchall()
        
        if not users:
            print("✅ Все пароли уже хешированы. Миграция не требуется.")
            return
        
        print(f"\nНайдено {len(users)} пользователей с незахешированными паролями.")
        print("\nВНИМАНИЕ: Этот скрипт хеширует существующие пароли.")
        print("Пользователи смогут войти с теми же паролями, что и раньше.")
        
        confirm = input("\nПродолжить миграцию? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Миграция отменена.")
            return
        
        migrated_count = 0
        skipped_count = 0
        
        for user_id, username, password in users:
            if not password or password.strip() == '':
                print(f"⚠️  Пропущен пользователь {username}: пароль пуст")
                skipped_count += 1
                continue
            
            try:
                # Хешируем пароль
                hashed_password = generate_password_hash(password)
                
                # Обновляем в БД
                update_query = "UPDATE public.users SET password = %s WHERE id = %s"
                cur.execute(update_query, (hashed_password, user_id))
                
                print(f"✓ Хеширован пароль для пользователя: {username}")
                migrated_count += 1
            except Exception as e:
                print(f"❌ Ошибка при хешировании пароля для {username}: {e}")
                skipped_count += 1
        
        # Коммитим изменения
        conn.commit()
        
        print(f"\n✅ Миграция завершена!")
        print(f"   Хешировано паролей: {migrated_count}")
        print(f"   Пропущено: {skipped_count}")
        if migrated_count > 0:
            print(f"\n⚠️  ВАЖНО: Удалите этот скрипт после успешной миграции для безопасности!")
        
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\n❌ Ошибка при миграции: {e}")
        if "too long for type" in str(e).lower() or "character varying" in str(e).lower():
            print("\n⚠️  Похоже, что поле password слишком маленькое.")
            print("   Выполните SQL-миграцию: expand_password_column.sql")
        sys.exit(1)
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Миграция паролей на хеширование")
    print("=" * 60)
    print("\n⚠️  ПРЕДУПРЕЖДЕНИЕ: Сделайте резервную копию БД перед запуском!")
    print("⚠️  Убедитесь, что выполнена SQL-миграция expand_password_column.sql")
    print("    для расширения поля password до TEXT")
    print()
    
    migrate_passwords()
