#!/usr/bin/env python3
"""
Отладочный парсер МПИ
"""

import psycopg2
from config import Config

def get_db_connection():
    """Создает подключение к базе данных"""
    try:
        db_config = {
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'database': Config.DB_NAME,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD
        }
        return psycopg2.connect(**db_config)
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

def main():
    """Основная функция"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        print("🔍 Проверяем записи в базе данных...")
        
        # Проверяем все записи
        cursor.execute('''
            SELECT id, gosregister_number, web_url, mpi
            FROM gosregister 
            ORDER BY id
            LIMIT 10
        ''')
        
        records = cursor.fetchall()
        print(f"📊 Всего записей: {len(records)}")
        
        for record in records:
            print(f"ID: {record[0]}, Номер: {record[1]}, URL: {record[2][:50] if record[2] else 'None'}..., МПИ: {record[3]}")
        
        print("\n" + "="*60)
        
        # Проверяем записи с URL карточек
        cursor.execute('''
            SELECT id, gosregister_number, web_url, mpi
            FROM gosregister 
            WHERE web_url IS NOT NULL 
            AND web_url LIKE '%/fundmetrology/cm/mits/%'
            AND web_url NOT LIKE '%?page=%'
            ORDER BY id
            LIMIT 5
        ''')
        
        card_records = cursor.fetchall()
        print(f"📋 Записей с карточками: {len(card_records)}")
        
        for record in card_records:
            print(f"ID: {record[0]}, Номер: {record[1]}, URL: {record[2][:50]}..., МПИ: {record[3]}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
