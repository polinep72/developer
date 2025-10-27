#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сравнение подходов: триггеры vs вычисляемые столбцы
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import date

def get_db_connection():
    """Создает подключение к базе данных PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

def show_table_structure():
    """Показать структуру таблиц и различия"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("📊 СТРУКТУРА ТАБЛИЦ И ПОДХОДЫ К РАСЧЕТАМ")
        print("="*60)
        
        # 1. Показываем структуру текущей таблицы (с триггерами)
        print("\n🔧 ТЕКУЩАЯ ТАБЛИЦА (calibration_certificates):")
        print("-" * 50)
        
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                CASE 
                    WHEN column_name IN ('next_calibration_date', 'days_until_calibration') 
                    THEN 'Обычный столбец (расчет через триггеры)'
                    ELSE 'Обычный столбец'
                END as description
            FROM information_schema.columns 
            WHERE table_name = 'calibration_certificates'
            ORDER BY ordinal_position
        """)
        
        current_table = cursor.fetchall()
        
        print(f"{'Столбец':<25} {'Тип':<15} {'Nullable':<10} {'Описание'}")
        print("-" * 70)
        
        for col in current_table:
            print(f"{col['column_name']:<25} {col['data_type']:<15} {col['is_nullable']:<10} {col['description']}")
        
        # 2. Показываем структуру таблицы с вычисляемыми столбцами
        print(f"\n🤖 ТАБЛИЦА С ВЫЧИСЛЯЕМЫМИ СТОЛБЦАМИ:")
        print("-" * 50)
        
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                CASE 
                    WHEN column_name IN ('next_calibration_date', 'days_until_calibration') 
                    THEN 'GENERATED COLUMN (автоматический расчет)'
                    ELSE 'Обычный столбец'
                END as description
            FROM information_schema.columns 
            WHERE table_name = 'calibration_certificates_generated'
            ORDER BY ordinal_position
        """)
        
        generated_table = cursor.fetchall()
        
        print(f"{'Столбец':<25} {'Тип':<15} {'Nullable':<10} {'Описание'}")
        print("-" * 70)
        
        for col in generated_table:
            print(f"{col['column_name']:<25} {col['data_type']:<15} {col['is_nullable']:<10} {col['description']}")
        
        # 3. Показываем триггеры текущей таблицы
        print(f"\n⚡ ТРИГГЕРЫ НА ТЕКУЩЕЙ ТАБЛИЦЕ:")
        print("-" * 40)
        
        cursor.execute("""
            SELECT 
                trigger_name,
                event_manipulation,
                action_timing,
                action_statement
            FROM information_schema.triggers 
            WHERE event_object_table = 'calibration_certificates'
            ORDER BY trigger_name
        """)
        
        triggers = cursor.fetchall()
        
        for trigger in triggers:
            print(f"🔹 {trigger['trigger_name']}")
            print(f"   Событие: {trigger['action_timing']} {trigger['event_manipulation']}")
            print(f"   Функция: {trigger['action_statement']}")
            print()
        
        # 4. Сравнение подходов
        print(f"\n📋 СРАВНЕНИЕ ПОДХОДОВ:")
        print("=" * 30)
        
        print(f"\n🔧 ТРИГГЕРЫ (текущий подход):")
        print("   ✅ Работает со существующей таблицей")
        print("   ✅ Гибкая логика расчета")
        print("   ✅ Можно обновлять существующие записи")
        print("   ✅ Поддерживает сложные условия")
        print("   ❌ Не видно в свойствах столбца")
        print("   ❌ Логика 'скрыта' в функциях")
        
        print(f"\n🤖 ВЫЧИСЛЯЕМЫЕ СТОЛБЦЫ (GENERATED COLUMNS):")
        print("   ✅ Видно в свойствах столбца")
        print("   ✅ Автоматический расчет при INSERT/UPDATE")
        print("   ✅ Проще для понимания")
        print("   ✅ Формула видна в DDL")
        print("   ❌ Требует создания новой таблицы")
        print("   ❌ Менее гибкая логика")
        print("   ❌ Нельзя вручную изменять значения")
        
        # 5. Показываем где искать информацию о расчетах
        print(f"\n🔍 ГДЕ НАЙТИ ИНФОРМАЦИЮ О РАСЧЕТАХ:")
        print("-" * 45)
        
        print(f"🔧 Для триггеров:")
        print("   1. Функции: calculate_calibration_dates()")
        print("   2. Триггеры: trigger_calculate_calibration_dates_*")
        print("   3. Файл: update_calibration_calculations.sql")
        
        print(f"\n🤖 Для вычисляемых столбцов:")
        print("   1. В pgAdmin: Properties → Columns → [столбец] → Definition")
        print("   2. В SQL: \\d+ table_name")
        print("   3. В DDL: GENERATED ALWAYS AS (...)")
        
        # 6. Рекомендация
        print(f"\n💡 РЕКОМЕНДАЦИЯ:")
        print("-" * 20)
        print("   Оставить текущий подход с триггерами:")
        print("   • Уже работает и протестирован")
        print("   • Более гибкий для бизнес-логики")
        print("   • Можно обновлять существующие записи")
        print("   • Поддерживает сложные условия МПИ")
        
        print(f"\n📚 Документация по расчетам:")
        print("   • CALIBRATION_CALCULATIONS.md")
        print("   • HOW_TO_ADD_CALIBRATION.md")
        print("   • update_calibration_calculations.sql")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        cursor.close()
        conn.close()

def main():
    """Главная функция"""
    show_table_structure()
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
