#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Скрипт для применения SQL-запросов синхронизации структуры БД."""

import os
import sys
from pathlib import Path

# Добавляем корень проекта в путь
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

# Устанавливаем UTF-8 для Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Загружаем переменные окружения
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

TARGET_HOST = "192.168.1.22"
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = "RM"
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_USER or not DB_PASSWORD:
    print("❌ Ошибка: не заданы DB_USER или DB_PASSWORD")
    sys.exit(1)

SQL_FILE = PROJECT_ROOT / "scripts" / "sync_database_structure.sql"


def main():
    """Основная функция."""
    print("=" * 80)
    print("Применение SQL-запросов синхронизации структуры БД")
    print("=" * 80)
    print(f"\nЦелевая БД: {TARGET_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"SQL-файл: {SQL_FILE}")
    print()
    
    if not SQL_FILE.exists():
        print(f"❌ Файл {SQL_FILE} не найден")
        sys.exit(1)
    
    # Читаем SQL-файл
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    # Разбиваем на отдельные запросы (убираем BEGIN/COMMIT)
    statements = []
    for line in sql_content.split("\n"):
        line = line.strip()
        if line and not line.startswith("--") and line.upper() not in ("BEGIN", "COMMIT"):
            if line.endswith(";"):
                statements.append(line)
            else:
                # Многострочные запросы
                if statements:
                    statements[-1] += " " + line
                else:
                    statements.append(line)
    
    print(f"Найдено SQL-запросов: {len(statements)}\n")
    
    try:
        # Подключаемся к БД
        print("Подключение к БД...")
        conn = psycopg.connect(
            host=TARGET_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            row_factory=dict_row,
        )
        print("✅ Подключение установлено\n")
        
        # Выполняем запросы
        success_count = 0
        error_count = 0
        
        with conn.cursor() as cur:
            for i, statement in enumerate(statements, 1):
                if not statement.strip():
                    continue
                
                try:
                    print(f"[{i}/{len(statements)}] Выполнение запроса...")
                    # Показываем первые 80 символов запроса
                    preview = statement[:80].replace("\n", " ")
                    if len(statement) > 80:
                        preview += "..."
                    print(f"  {preview}")
                    
                    cur.execute(statement)
                    success_count += 1
                    print(f"  ✅ Успешно\n")
                    
                except Exception as e:
                    error_count += 1
                    error_msg = str(e)
                    # Проверяем, не является ли это ошибкой "уже существует"
                    if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                        print(f"  ⚠️ Пропущено (уже существует): {error_msg[:100]}\n")
                        success_count += 1  # Считаем как успех
                        error_count -= 1
                    else:
                        print(f"  ❌ Ошибка: {error_msg}\n")
        
        # Коммитим изменения
        if success_count > 0:
            conn.commit()
            print(f"✅ Изменения зафиксированы (commit)")
        
        print("\n" + "=" * 80)
        print("ИТОГОВЫЙ ОТЧЕТ")
        print("=" * 80)
        print(f"\n✅ Успешно выполнено: {success_count}")
        if error_count > 0:
            print(f"❌ Ошибок: {error_count}")
        else:
            print("✅ Все запросы выполнены успешно!")
        
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

