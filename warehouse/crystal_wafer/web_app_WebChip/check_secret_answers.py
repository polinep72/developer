"""
Скрипт для проверки и обработки незахешированных секретных ответов.

ВАЖНО: 
- Если секретные ответы хранятся в открытом виде, их нельзя безопасно захешировать
- Единственный безопасный способ - удалить незахешированные ответы
- Пользователи должны будут либо зарегистрироваться заново, либо администратор сбросит им пароль

Использование:
    python check_secret_answers.py
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

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

def check_secret_answers():
    """Проверяет наличие незахешированных секретных ответов"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Получаем всех пользователей с незахешированными секретными ответами
        # Хешированные ответы начинаются с 'pbkdf2:' или 'scrypt:'
        query = """
            SELECT id, username, secret_question, secret_answer 
            FROM public.users 
            WHERE secret_answer IS NOT NULL
            AND secret_answer != ''
            AND secret_answer NOT LIKE 'pbkdf2:%'
            AND secret_answer NOT LIKE 'scrypt:%'
        """
        cur.execute(query)
        users = cur.fetchall()
        
        if not users:
            print("[OK] Все секретные ответы захешированы или отсутствуют.")
            return
        
        print(f"[!] Найдено {len(users)} пользователей с незахешированными секретными ответами:\n")
        for user_id, username, secret_question, secret_answer in users:
            print(f"  - {username} (ID: {user_id})")
            if secret_question:
                print(f"    Вопрос: {secret_question}")
            print(f"    Ответ (первые 20 символов): {secret_answer[:20]}...")
            print()
        
        print("\n" + "="*60)
        print("ВАЖНО: Незахешированные ответы представляют угрозу безопасности!")
        print("="*60)
        print("\nВарианты решения:")
        print("1. Удалить незахешированные ответы (безопасно)")
        print("   - Пользователи не смогут восстановить пароль через секретный вопрос")
        print("   - Администратор сможет сбросить пароль через интерфейс управления")
        print("2. Оставить как есть (НЕБЕЗОПАСНО)")
        print("   - Пользователи смогут использовать восстановление пароля")
        print("   - Но при компрометации БД ответы будут видны в открытом виде")
        print()
        
        choice = input("Выберите действие (1 - удалить, 2 - оставить, 0 - отмена): ").strip()
        
        if choice == '1':
            confirm = input("\nВы уверены, что хотите удалить незахешированные ответы? (yes/no): ")
            if confirm.lower() == 'yes':
                # Удаляем незахешированные ответы
                user_ids = [user[0] for user in users]
                placeholders = ','.join(['%s'] * len(user_ids))
                delete_query = f"""
                    UPDATE public.users 
                    SET secret_answer = NULL, secret_question = NULL
                    WHERE id IN ({placeholders})
                """
                cur.execute(delete_query, user_ids)
                conn.commit()
                print(f"\n[OK] Незахешированные секретные ответы удалены для {len(user_ids)} пользователей.")
                print("Пользователи должны либо:")
                print("- Зарегистрироваться заново с новым секретным вопросом")
                print("- Обратиться к администратору для сброса пароля")
            else:
                print("Операция отменена.")
        elif choice == '2':
            print("\n[!] ВНИМАНИЕ: Незахешированные ответы оставлены в БД.")
            print("Это представляет угрозу безопасности!")
            print("Рекомендуется удалить их и попросить пользователей зарегистрироваться заново.")
        else:
            print("Операция отменена.")
            
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"\n[ERROR] Ошибка: {e}")
        sys.exit(1)
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == '__main__':
    print("=" * 60)
    print("Проверка секретных ответов на безопасность")
    print("=" * 60)
    print("\n[!] ПРЕДУПРЕЖДЕНИЕ: Сделайте резервную копию БД перед запуском!")
    print()
    
    check_secret_answers()

