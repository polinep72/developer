#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для проверки индексов в базе данных
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def check_indexes():
    """Проверка индексов в базе данных"""
    db_host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME') or os.getenv('DB_NAME2')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_port = os.getenv('DB_PORT', '5432')
    
    if not all([db_host, db_name, db_user, db_password]):
        print("ERROR: Не указаны необходимые переменные окружения")
        sys.exit(1)
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port
        )
        
        cur = conn.cursor()
        
        # Общее количество индексов с префиксом idx_
        cur.execute("""
            SELECT COUNT(*) 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND indexname LIKE 'idx_%'
        """)
        total_count = cur.fetchone()[0]
        print(f"Всего индексов с префиксом idx_: {total_count}")
        
        # Количество индексов по таблицам
        cur.execute("""
            SELECT tablename, COUNT(*) as idx_count 
            FROM pg_indexes 
            WHERE schemaname = 'public' 
            AND indexname LIKE 'idx_%'
            GROUP BY tablename 
            ORDER BY tablename
        """)
        results = cur.fetchall()
        
        print("\nИндексы по таблицам:")
        print("-" * 50)
        for row in results:
            print(f"  {row[0]:30} {row[1]:3} индексов")
        
        # Проверка ключевых индексов
        print("\nПроверка ключевых индексов:")
        print("-" * 50)
        key_indexes = [
            'idx_users_username',
            'idx_cart_user_warehouse',
            'idx_invoice_status',
            'idx_invoice_item_id',
            'idx_invoice_status_date',
            'idx_n_chip_n_chip',
            'idx_pr_name_pr',
            'idx_lot_name_lot'
        ]
        
        for idx_name in key_indexes:
            cur.execute("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE schemaname = 'public' 
                AND indexname = %s
            """, (idx_name,))
            exists = cur.fetchone()[0] > 0
            status = "OK" if exists else "MISSING"
            print(f"  {idx_name:35} {status}")
        
        cur.close()
        conn.close()
        
        print("\n" + "=" * 50)
        if total_count >= 100:
            print("OK: Индексы успешно применены к базе данных")
        else:
            print(f"WARNING: Ожидалось около 105 индексов, найдено {total_count}")
            
    except psycopg2.Error as e:
        print(f"ОШИБКА подключения к БД: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"НЕПРЕДВИДЕННАЯ ОШИБКА: {e}")
        sys.exit(1)

if __name__ == '__main__':
    check_indexes()

