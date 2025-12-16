#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Скрипт для сравнения структуры таблиц между двумя БД.

Сравнивает структуру всех таблиц между:
- Источник: 192.168.1.139 (продакшн)
- Цель: 192.168.1.22 (тестовая)

Выявляет различия в столбцах, типах данных, ограничениях и индексах.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
from collections import defaultdict

# Устанавливаем UTF-8 для Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Добавляем корень проекта в путь
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row

# Загружаем переменные окружения
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Настройки подключения
SOURCE_HOST = "192.168.1.139"
TARGET_HOST = "192.168.1.22"
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = "RM"
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_USER or not DB_PASSWORD:
    print("❌ Ошибка: не заданы DB_USER или DB_PASSWORD")
    sys.exit(1)


def get_connection(host: str):
    """Создает подключение к БД."""
    return psycopg.connect(
        host=host,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        row_factory=dict_row,
        connect_timeout=10,
    )


def get_table_list(conn) -> List[str]:
    """Получает список всех таблиц в БД."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [row["table_name"] for row in cur.fetchall()]


def get_table_columns(conn, table_name: str) -> List[Dict[str, Any]]:
    """Получает структуру столбцов таблицы."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        return cur.fetchall()


def get_table_indexes(conn, table_name: str) -> List[Dict[str, Any]]:
    """Получает список индексов таблицы."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = %s
            ORDER BY indexname
            """,
            (table_name,),
        )
        return cur.fetchall()


def get_table_constraints(conn, table_name: str) -> List[Dict[str, Any]]:
    """Получает ограничения таблицы."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 
                conname as constraint_name,
                contype as constraint_type,
                pg_get_constraintdef(oid) as constraint_definition
            FROM pg_constraint
            WHERE conrelid = %s::regclass
            ORDER BY conname
            """,
            (table_name,),
        )
        return cur.fetchall()


def format_column_type(col: Dict[str, Any]) -> str:
    """Форматирует тип столбца для сравнения."""
    data_type = col["data_type"]
    
    if data_type == "character varying":
        length = col.get("character_maximum_length")
        return f"VARCHAR({length})" if length else "VARCHAR"
    elif data_type == "numeric":
        precision = col.get("numeric_precision")
        scale = col.get("numeric_scale")
        if precision and scale:
            return f"NUMERIC({precision},{scale})"
        elif precision:
            return f"NUMERIC({precision})"
        return "NUMERIC"
    elif data_type == "timestamp without time zone":
        return "TIMESTAMP"
    elif data_type == "timestamp with time zone":
        return "TIMESTAMPTZ"
    else:
        return data_type.upper()


def compare_columns(
    source_cols: List[Dict[str, Any]], target_cols: List[Dict[str, Any]]
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Сравнивает столбцы двух таблиц.
    
    Returns:
        (missing_in_target, missing_in_source, different_types)
    """
    source_dict = {col["column_name"]: col for col in source_cols}
    target_dict = {col["column_name"]: col for col in target_cols}
    
    missing_in_target = []
    missing_in_source = []
    different_types = []
    
    # Столбцы, которые есть в источнике, но отсутствуют в цели
    for col_name, col in source_dict.items():
        if col_name not in target_dict:
            missing_in_target.append(col)
        else:
            # Сравниваем типы
            source_type = format_column_type(col)
            target_type = format_column_type(target_dict[col_name])
            source_nullable = col["is_nullable"] == "YES"
            target_nullable = target_dict[col_name]["is_nullable"] == "YES"
            
            if source_type != target_type or source_nullable != target_nullable:
                different_types.append({
                    "column": col_name,
                    "source": {
                        "type": source_type,
                        "nullable": source_nullable,
                        "default": col.get("column_default"),
                    },
                    "target": {
                        "type": target_type,
                        "nullable": target_nullable,
                        "default": target_dict[col_name].get("column_default"),
                    },
                })
    
    # Столбцы, которые есть в цели, но отсутствуют в источнике
    for col_name, col in target_dict.items():
        if col_name not in source_dict:
            missing_in_source.append(col)
    
    return missing_in_target, missing_in_source, different_types


def compare_indexes(
    source_idx: List[Dict[str, Any]], target_idx: List[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    """Сравнивает индексы двух таблиц.
    
    Returns:
        (missing_in_target, missing_in_source)
    """
    source_names = {idx["indexname"] for idx in source_idx}
    target_names = {idx["indexname"] for idx in target_idx}
    
    missing_in_target = list(source_names - target_names)
    missing_in_source = list(target_names - source_names)
    
    return missing_in_target, missing_in_source


def generate_alter_statements(
    table_name: str,
    missing_cols: List[Dict[str, Any]],
    different_types: List[Dict[str, Any]],
    missing_indexes: List[str],
    source_conn,
) -> List[str]:
    """Генерирует SQL-запросы для исправления структуры."""
    statements = []
    
    for col in missing_cols:
        col_name = col["column_name"]
        col_type = format_column_type(col)
        nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"
        default = col.get("column_default")
        
        default_clause = ""
        if default:
            default_clause = f" DEFAULT {default}"
        
        statements.append(
            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type} {nullable}{default_clause};"
        )
    
    for diff in different_types:
        col_name = diff["column"]
        source = diff["source"]
        target = diff["target"]
        
        # Изменение типа (если отличается)
        if source["type"] != target["type"]:
            statements.append(
                f"ALTER TABLE {table_name} ALTER COLUMN {col_name} TYPE {source['type']};"
            )
        
        # Изменение NULL/NOT NULL
        if source["nullable"] != target["nullable"]:
            if source["nullable"]:
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {col_name} DROP NOT NULL;"
                )
            else:
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {col_name} SET NOT NULL;"
                )
        
        # Изменение DEFAULT (если отличается)
        if source["default"] != target["default"]:
            if source["default"]:
                default_val = str(source["default"]).replace("'", "").replace("::text", "").replace("::character varying", "")
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {col_name} SET DEFAULT {default_val};"
                )
            else:
                statements.append(
                    f"ALTER TABLE {table_name} ALTER COLUMN {col_name} DROP DEFAULT;"
                )
    
    # Добавляем недостающие индексы
    if missing_indexes:
        source_idx = get_table_indexes(source_conn, table_name)
        for idx_name in missing_indexes:
            idx_def = next((idx["indexdef"] for idx in source_idx if idx["indexname"] == idx_name), None)
            if idx_def:
                # Заменяем CREATE INDEX на CREATE INDEX IF NOT EXISTS
                idx_def_safe = idx_def.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ")
                idx_def_safe = idx_def_safe.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ")
                statements.append(idx_def_safe + ";")
    
    return statements


def main():
    """Основная функция."""
    print("=" * 80)
    print("Сравнение структуры БД")
    print("=" * 80)
    print(f"\nИсточник (продакшн): {SOURCE_HOST}:{DB_PORT}/{DB_NAME}")
    print(f"Цель (тестовая): {TARGET_HOST}:{DB_PORT}/{DB_NAME}")
    print()
    
    try:
        # Подключаемся к обеим БД
        print("Подключение к БД...")
        source_conn = get_connection(SOURCE_HOST)
        target_conn = get_connection(TARGET_HOST)
        print("✅ Подключение установлено\n")
        
        # Получаем списки таблиц
        print("Получение списка таблиц...")
        source_tables = set(get_table_list(source_conn))
        target_tables = set(get_table_list(target_conn))
        all_tables = sorted(source_tables | target_tables)
        print(f"✅ Найдено таблиц: источник={len(source_tables)}, цель={len(target_tables)}, всего={len(all_tables)}\n")
        
        # Отчет о различиях
        report = {
            "tables_missing_in_target": [],
            "tables_missing_in_source": [],
            "tables_differences": [],
            "all_sql_statements": [],
        }
        
        # Сравниваем каждую таблицу
        for table_name in all_tables:
            print(f"Проверка таблицы: {table_name}")
            
            if table_name not in source_tables:
                print(f"  ⚠️ Таблица отсутствует в источнике (только в цели)")
                report["tables_missing_in_source"].append(table_name)
                continue
            
            if table_name not in target_tables:
                print(f"  ⚠️ Таблица отсутствует в цели (есть в источнике)")
                report["tables_missing_in_target"].append(table_name)
                continue
            
            # Получаем структуру столбцов
            source_cols = get_table_columns(source_conn, table_name)
            target_cols = get_table_columns(target_conn, table_name)
            
            missing_in_target, missing_in_source, different_types = compare_columns(
                source_cols, target_cols
            )
            
            # Получаем индексы
            source_idx = get_table_indexes(source_conn, table_name)
            target_idx = get_table_indexes(target_conn, table_name)
            missing_idx_target, missing_idx_source = compare_indexes(source_idx, target_idx)
            
            # Формируем отчет
            if missing_in_target or missing_in_source or different_types or missing_idx_target:
                table_diff = {
                    "table": table_name,
                    "missing_columns_in_target": [
                        {
                            "name": col["column_name"],
                            "type": format_column_type(col),
                            "nullable": col["is_nullable"] == "YES",
                        }
                        for col in missing_in_target
                    ],
                    "missing_columns_in_source": [
                        {
                            "name": col["column_name"],
                            "type": format_column_type(col),
                        }
                        for col in missing_in_source
                    ],
                    "different_types": different_types,
                    "missing_indexes_in_target": missing_idx_target,
                }
                report["tables_differences"].append(table_diff)
                
                # Генерируем SQL для исправления
                sql_statements = generate_alter_statements(
                    table_name, missing_in_target, different_types, missing_idx_target, source_conn
                )
                if sql_statements:
                    report["all_sql_statements"].extend(sql_statements)
                
                # Выводим различия
                if missing_in_target:
                    print(f"  ❌ Отсутствуют столбцы в цели: {[c['column_name'] for c in missing_in_target]}")
                if missing_in_source:
                    print(f"  ⚠️ Лишние столбцы в цели: {[c['column_name'] for c in missing_in_source]}")
                if different_types:
                    print(f"  ⚠️ Различаются типы: {[d['column'] for d in different_types]}")
                if missing_idx_target:
                    print(f"  ⚠️ Отсутствуют индексы в цели: {missing_idx_target}")
            else:
                print(f"  ✅ Структура совпадает")
        
        # Выводим итоговый отчет
        print("\n" + "=" * 80)
        print("ИТОГОВЫЙ ОТЧЕТ")
        print("=" * 80)
        
        if report["tables_missing_in_target"]:
            print(f"\n❌ Таблицы, отсутствующие в цели ({len(report['tables_missing_in_target'])}):")
            for table in report["tables_missing_in_target"]:
                print(f"  - {table}")
        
        if report["tables_missing_in_source"]:
            print(f"\n⚠️ Таблицы, присутствующие только в цели ({len(report['tables_missing_in_source'])}):")
            for table in report["tables_missing_in_source"]:
                print(f"  - {table}")
        
        if report["tables_differences"]:
            print(f"\n⚠️ Таблицы с различиями в структуре ({len(report['tables_differences'])}):")
            for diff in report["tables_differences"]:
                print(f"\n  Таблица: {diff['table']}")
                if diff["missing_columns_in_target"]:
                    print(f"    Отсутствуют столбцы: {[c['name'] for c in diff['missing_columns_in_target']]}")
                if diff["different_types"]:
                    print(f"    Различаются типы: {[d['column'] for d in diff['different_types']]}")
                if diff["missing_indexes_in_target"]:
                    print(f"    Отсутствуют индексы: {diff['missing_indexes_in_target']}")
        
        if report["all_sql_statements"]:
            print(f"\n📝 SQL-запросы для синхронизации ({len(report['all_sql_statements'])}):")
            print("\n".join(report["all_sql_statements"]))
            
            # Сохраняем SQL в файл
            sql_file = PROJECT_ROOT / "scripts" / "sync_database_structure.sql"
            with open(sql_file, "w", encoding="utf-8") as f:
                f.write("-- SQL-запросы для синхронизации структуры БД\n")
                f.write(f"-- Источник: {SOURCE_HOST}, Цель: {TARGET_HOST}\n")
                f.write(f"-- Сгенерировано автоматически\n\n")
                f.write("BEGIN;\n\n")
                f.write("\n".join(report["all_sql_statements"]))
                f.write("\n\nCOMMIT;\n")
            print(f"\n✅ SQL-запросы сохранены в: {sql_file}")
        else:
            print("\n✅ Структура всех таблиц совпадает!")
        
        source_conn.close()
        target_conn.close()
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

