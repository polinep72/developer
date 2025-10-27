#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для управления данными Госреестра
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
import pandas as pd
from datetime import datetime

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

def show_gosregister_stats():
    """Показать статистику Госреестра"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Общая статистика
        cursor.execute("SELECT COUNT(*) as total FROM gosregister")
        total = cursor.fetchone()['total']
        
        cursor.execute("""
            SELECT COUNT(*) as linked 
            FROM equipment e 
            WHERE e.gosregister_id IS NOT NULL
        """)
        linked = cursor.fetchone()['linked']
        
        cursor.execute("""
            SELECT COUNT(*) as unlinked 
            FROM equipment e 
            WHERE e.gosregister_id IS NULL AND e.equipment_type_id = 1
        """)
        unlinked = cursor.fetchone()['unlinked']
        
        print("=== СТАТИСТИКА ГОСРЕЕСТРА ===")
        print(f"📋 Всего записей в Госреестре: {total}")
        print(f"🔗 Связанных с оборудованием: {linked}")
        print(f"❌ Не связанных СИ: {unlinked}")
        print()
        
        # Топ изготовителей
        cursor.execute("""
            SELECT manufacturer, COUNT(*) as count
            FROM gosregister
            GROUP BY manufacturer
            ORDER BY count DESC
            LIMIT 10
        """)
        
        print("🏭 Топ-10 изготовителей:")
        for row in cursor.fetchall():
            print(f"  {row['manufacturer']}: {row['count']} записей")
        
    except Exception as e:
        print(f"Ошибка при получении статистики: {e}")
    finally:
        cursor.close()
        conn.close()

def search_gosregister(search_term):
    """Поиск в Госреестре"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT g.*, 
                   COUNT(e.id) as equipment_count
            FROM gosregister g
            LEFT JOIN equipment e ON g.id = e.gosregister_id
            WHERE LOWER(g.gosregister_number) LIKE LOWER(%s) 
               OR LOWER(g.si_name) LIKE LOWER(%s)
               OR LOWER(g.type_designation) LIKE LOWER(%s)
               OR LOWER(g.manufacturer) LIKE LOWER(%s)
            GROUP BY g.id
            ORDER BY g.gosregister_number
            LIMIT 20
        """, (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
        
        results = cursor.fetchall()
        
        print(f"=== ПОИСК В ГОСРЕЕСТРЕ: '{search_term}' ===")
        print(f"Найдено: {len(results)} записей")
        print()
        
        if results:
            for row in results:
                print(f"📋 {row['gosregister_number']}")
                print(f"  Наименование: {row['si_name']}")
                print(f"  Тип: {row['type_designation']}")
                print(f"  Изготовитель: {row['manufacturer']}")
                print(f"  Связанного оборудования: {row['equipment_count']}")
                print()
        else:
            print("Записи не найдены.")
            
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
    finally:
        cursor.close()
        conn.close()

def add_gosregister_entry():
    """Добавление записи в Госреестр"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        print("=== ДОБАВЛЕНИЕ В ГОСРЕЕСТР ===")
        
        gosregister_number = input("Номер в Госреестре: ").strip()
        si_name = input("Наименование СИ: ").strip()
        type_designation = input("Обозначение типа СИ: ").strip()
        manufacturer = input("Изготовитель: ").strip()
        
        if not gosregister_number or not si_name:
            print("❌ Ошибка: Номер в Госреестре и наименование СИ обязательны!")
            return
        
        # Проверка на дубликат
        cursor.execute("SELECT id FROM gosregister WHERE gosregister_number = %s", (gosregister_number,))
        if cursor.fetchone():
            print("❌ Ошибка: Запись с таким номером уже существует!")
            return
        
        # Добавление записи
        cursor.execute("""
            INSERT INTO gosregister (
                gosregister_number, si_name, type_designation, manufacturer, created_at
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            gosregister_number, si_name,
            type_designation if type_designation else None,
            manufacturer if manufacturer else None,
            datetime.now()
        ))
        
        conn.commit()
        print("✅ Запись успешно добавлена в Госреестр!")
        
    except Exception as e:
        print(f"❌ Ошибка при добавлении: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def link_equipment_to_gosregister():
    """Связывание оборудования с Госреестром"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("=== СВЯЗЫВАНИЕ ОБОРУДОВАНИЯ С ГОСРЕЕСТРОМ ===")
        
        # Показать несвязанные СИ
        cursor.execute("""
            SELECT e.id, e.name, e.type_designation, e.serial_number
            FROM equipment e
            WHERE e.equipment_type_id = 1 AND e.gosregister_id IS NULL
            ORDER BY e.name
            LIMIT 20
        """)
        
        equipment_list = cursor.fetchall()
        
        if not equipment_list:
            print("✅ Все СИ уже связаны с Госреестром!")
            return
        
        print("📋 Несвязанные СИ:")
        for eq in equipment_list:
            print(f"  {eq['id']}: {eq['name']} - {eq['type_designation']}")
        
        equipment_id = input("\nВведите ID оборудования для связывания: ").strip()
        gosregister_number = input("Введите номер в Госреестре: ").strip()
        
        if not equipment_id or not gosregister_number:
            print("❌ Ошибка: ID оборудования и номер Госреестра обязательны!")
            return
        
        try:
            equipment_id = int(equipment_id)
        except ValueError:
            print("❌ Ошибка: Неверный ID оборудования!")
            return
        
        # Поиск записи в Госреестре
        cursor.execute("SELECT id FROM gosregister WHERE gosregister_number = %s", (gosregister_number,))
        gosregister_result = cursor.fetchone()
        
        if not gosregister_result:
            print("❌ Ошибка: Запись с таким номером не найдена в Госреестре!")
            return
        
        gosregister_id = gosregister_result['id']
        
        # Проверка оборудования
        cursor.execute("SELECT id FROM equipment WHERE id = %s AND equipment_type_id = 1", (equipment_id,))
        if not cursor.fetchone():
            print("❌ Ошибка: СИ с таким ID не найдено!")
            return
        
        # Связывание
        cursor.execute("""
            UPDATE equipment 
            SET gosregister_id = %s 
            WHERE id = %s
        """, (gosregister_id, equipment_id))
        
        conn.commit()
        print("✅ Оборудование успешно связано с Госреестром!")
        
    except Exception as e:
        print(f"❌ Ошибка при связывании: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def export_gosregister_to_excel():
    """Экспорт Госреестра в Excel"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        df = pd.read_sql("""
            SELECT 
                g.gosregister_number as "Номер в Госреестре",
                g.si_name as "Наименование СИ",
                g.type_designation as "Обозначение типа СИ",
                g.manufacturer as "Изготовитель",
                COUNT(e.id) as "Количество оборудования"
            FROM gosregister g
            LEFT JOIN equipment e ON g.id = e.gosregister_id
            GROUP BY g.id, g.gosregister_number, g.si_name, g.type_designation, g.manufacturer
            ORDER BY g.gosregister_number
        """, conn)
        
        filename = f"gosregister_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(filename, index=False, engine='openpyxl')
        
        print(f"✅ Госреестр экспортирован в файл: {filename}")
        
    except Exception as e:
        print(f"❌ Ошибка при экспорте: {e}")
    finally:
        conn.close()

def main():
    """Главное меню Госреестра"""
    while True:
        print("\n" + "="*50)
        print("📋 УПРАВЛЕНИЕ ГОСРЕЕСТРОМ")
        print("="*50)
        print("1. 📊 Статистика Госреестра")
        print("2. 🔍 Поиск в Госреестре")
        print("3. ➕ Добавить запись в Госреестр")
        print("4. 🔗 Связать оборудование с Госреестром")
        print("5. 📤 Экспорт Госреестра в Excel")
        print("6. ❌ Выход")
        
        choice = input("\nВыберите действие (1-6): ").strip()
        
        if choice == '1':
            show_gosregister_stats()
        elif choice == '2':
            search_term = input("Введите поисковый запрос: ").strip()
            if search_term:
                search_gosregister(search_term)
        elif choice == '3':
            add_gosregister_entry()
        elif choice == '4':
            link_equipment_to_gosregister()
        elif choice == '5':
            export_gosregister_to_excel()
        elif choice == '6':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()
