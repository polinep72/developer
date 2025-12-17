#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для применения индексов к базе данных
Версия: 1.4.15
Дата: 2025-12-17
Автор: Полин Е.П.
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def apply_indexes():
    """Применение индексов к базе данных"""
    db_host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME') or os.getenv('DB_NAME2')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_port = os.getenv('DB_PORT', '5432')
    
    if not all([db_host, db_name, db_user, db_password]):
        print("ОШИБКА: Не указаны необходимые переменные окружения (DB_HOST, DB_NAME/DB_NAME2, DB_USER, DB_PASSWORD)")
        sys.exit(1)
    
    # Читаем SQL скрипт
    script_path = os.path.join(os.path.dirname(__file__), 'create_indexes.sql')
    if not os.path.exists(script_path):
        print(f"ОШИБКА: Файл {script_path} не найден")
        sys.exit(1)
    
    with open(script_path, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # Разделяем скрипт на отдельные команды
    # Удаляем комментарии и пустые строки
    commands = []
    for line in sql_script.split('\n'):
        line = line.strip()
        # Пропускаем комментарии и пустые строки
        if line and not line.startswith('--') and not line.startswith('#'):
            commands.append(line)
    
    # Объединяем команды, разделяя по точке с запятой
    full_sql = '\n'.join(commands)
    sql_statements = [stmt.strip() for stmt in full_sql.split(';') if stmt.strip() and not stmt.strip().startswith('--')]
    
    print(f"Подключение к БД: {db_host}:{db_port}/{db_name} (пользователь: {db_user})")
    print(f"Найдено команд для выполнения: {len(sql_statements)}")
    print("-" * 60)
    
    conn = None
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port
        )
        conn.autocommit = True  # Автоматический коммит для DDL команд
        
        cur = conn.cursor()
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for i, statement in enumerate(sql_statements, 1):
            if not statement or statement.upper().startswith('SELECT'):
                # Пропускаем SELECT запросы (они для проверки, не для выполнения)
                skipped_count += 1
                continue
            
            try:
                cur.execute(statement)
                index_name = statement.split()[-1] if 'INDEX' in statement.upper() else 'unknown'
                print(f"[{i}/{len(sql_statements)}] OK: {index_name}")
                success_count += 1
            except psycopg2.errors.DuplicateTable as e:
                # Индекс уже существует - это нормально
                index_name = statement.split()[-1] if 'INDEX' in statement.upper() else 'unknown'
                print(f"[{i}/{len(sql_statements)}] SKIP: {index_name} (уже существует)")
                skipped_count += 1
            except Exception as e:
                index_name = statement.split()[-1] if 'INDEX' in statement.upper() else 'unknown'
                print(f"[{i}/{len(sql_statements)}] ERROR: Ошибка при создании индекса {index_name}: {e}")
                error_count += 1
        
        cur.close()
        
        print("-" * 60)
        print(f"Результат:")
        print(f"  Успешно создано: {success_count}")
        print(f"  Пропущено (уже существуют): {skipped_count}")
        print(f"  Ошибок: {error_count}")
        print(f"  Всего обработано: {success_count + skipped_count + error_count}")
        
        if error_count > 0:
            print("\nВНИМАНИЕ: Некоторые индексы не были созданы. Проверьте ошибки выше.")
            sys.exit(1)
        else:
            print("\nOK: Все индексы успешно применены!")
            
    except psycopg2.Error as e:
        print(f"ОШИБКА подключения к БД: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"НЕПРЕДВИДЕННАЯ ОШИБКА: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            print("\nПодключение к БД закрыто.")

if __name__ == '__main__':
    print("=" * 60)
    print("Применение индексов к базе данных")
    print("=" * 60)
    apply_indexes()

