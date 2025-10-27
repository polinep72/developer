#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для управления базой данных оборудования
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

def show_statistics():
    """Показать статистику базы данных"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Статистика по типам оборудования
        cursor.execute("""
            SELECT et.type_name, COUNT(e.id) as count
            FROM equipment_types et
            LEFT JOIN equipment e ON et.id = e.equipment_type_id
            GROUP BY et.id, et.type_name
            ORDER BY et.id
        """)
        
        print("=== СТАТИСТИКА БАЗЫ ДАННЫХ ===")
        print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        print("📊 Оборудование по типам:")
        total_equipment = 0
        for row in cursor.fetchall():
            print(f"  {row['type_name']}: {row['count']} записей")
            total_equipment += row['count']
        
        print(f"  ИТОГО: {total_equipment} записей")
        print()
        
        # Статистика Госреестра
        cursor.execute("SELECT COUNT(*) as count FROM gosregister")
        gosregister_count = cursor.fetchone()['count']
        print(f"📋 Госреестр: {gosregister_count} записей")
        
        # Статистика связанных записей
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM equipment e 
            WHERE e.gosregister_id IS NOT NULL
        """)
        linked_count = cursor.fetchone()['count']
        print(f"🔗 Записей связанных с Госреестром: {linked_count}")
        print()
        
        # Последние добавленные записи
        cursor.execute("""
            SELECT e.id, e.name, et.type_name, e.created_at
            FROM equipment e
            JOIN equipment_types et ON e.equipment_type_id = et.id
            ORDER BY e.id DESC
            LIMIT 5
        """)
        
        print("🆕 Последние добавленные записи:")
        for row in cursor.fetchall():
            created_at = row['created_at'].strftime('%d.%m.%Y %H:%M') if row['created_at'] else 'Не указано'
            print(f"  ID {row['id']}: {row['name'][:50]}... ({row['type_name']}) - {created_at}")
        
    except Exception as e:
        print(f"Ошибка при получении статистики: {e}")
    finally:
        cursor.close()
        conn.close()

def search_equipment(search_term):
    """Поиск оборудования по названию"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT e.id, e.name, e.type_designation, e.serial_number, 
                   et.type_name, e.inventory_number, e.mpi,
                   g.gosregister_number, g.web_url,
                   cc.certificate_number, cc.next_calibration_date, cc.days_until_calibration
            FROM equipment e
            JOIN equipment_types et ON e.equipment_type_id = et.id
            LEFT JOIN gosregister g ON e.gosregister_id = g.id
            LEFT JOIN LATERAL (
                SELECT certificate_number, next_calibration_date, days_until_calibration
                FROM calibration_certificates cc
                WHERE cc.equipment_id = e.id
                ORDER BY cc.certificate_date DESC
                LIMIT 1
            ) cc ON true
            WHERE LOWER(e.name) LIKE LOWER(%s) 
               OR LOWER(e.type_designation) LIKE LOWER(%s)
               OR LOWER(e.serial_number) LIKE LOWER(%s)
            ORDER BY e.name
            LIMIT 20
        """, (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
        
        results = cursor.fetchall()
        
        print(f"=== ПОИСК: '{search_term}' ===")
        print(f"Найдено: {len(results)} записей")
        print()
        
        if results:
            for row in results:
                print(f"ID {row['id']}: {row['name']}")
                if row['type_designation']:
                    print(f"  Тип: {row['type_designation']}")
                if row['serial_number']:
                    print(f"  Серийный №: {row['serial_number']}")
                if row['inventory_number']:
                    print(f"  Инв. №: {row['inventory_number']}")
                print(f"  Категория: {row['type_name']}")
                print()
        else:
            print("Записи не найдены.")
            
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
    finally:
        cursor.close()
        conn.close()

def add_equipment():
    """Интерактивное добавление нового оборудования"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        # Показать типы оборудования
        cursor.execute("SELECT id, type_name FROM equipment_types ORDER BY id")
        types = cursor.fetchall()
        
        print("=== ДОБАВЛЕНИЕ НОВОГО ОБОРУДОВАНИЯ ===")
        print("Доступные типы оборудования:")
        for type_id, type_name in types:
            print(f"  {type_id}: {type_name}")
        
        # Ввод данных
        equipment_type_id = input("\nВыберите тип оборудования (ID): ").strip()
        name = input("Наименование: ").strip()
        type_designation = input("Обозначение типа (необязательно): ").strip()
        serial_number = input("Серийный номер (необязательно): ").strip()
        inventory_number = input("Инвентарный номер (необязательно): ").strip()
        note = input("Примечание (необязательно): ").strip()
        
        # Валидация
        if not equipment_type_id or not name:
            print("❌ Ошибка: Тип оборудования и наименование обязательны!")
            return
        
        try:
            equipment_type_id = int(equipment_type_id)
        except ValueError:
            print("❌ Ошибка: Неверный ID типа оборудования!")
            return
        
        # Проверка существования типа
        cursor.execute("SELECT id FROM equipment_types WHERE id = %s", (equipment_type_id,))
        if not cursor.fetchone():
            print("❌ Ошибка: Тип оборудования с таким ID не существует!")
            return
        
        # Добавление записи
        cursor.execute("""
            INSERT INTO equipment (
                equipment_type_id, name, type_designation, serial_number,
                inventory_number, note, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            equipment_type_id, name, 
            type_designation if type_designation else None,
            serial_number if serial_number else None,
            inventory_number if inventory_number else None,
            note if note else None,
            datetime.now()
        ))
        
        conn.commit()
        print("✅ Оборудование успешно добавлено!")
        
    except Exception as e:
        print(f"❌ Ошибка при добавлении: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def manage_calibration_certificates():
    """Управление поверками/аттестациями"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("=== УПРАВЛЕНИЕ ПОВЕРКАМИ/АТТЕСТАЦИЯМИ ===")
        print("1. Показать историю поверок оборудования")
        print("2. Добавить новую поверку/аттестацию")
        print("3. Назад")
        
        choice = input("\nВыберите действие (1-3): ").strip()
        
        if choice == '1':
            # Показать историю поверок
            equipment_id = input("Введите ID оборудования: ").strip()
            if equipment_id:
                try:
                    equipment_id = int(equipment_id)
                    cursor.execute("""
                        SELECT cc.*, e.name as equipment_name
                        FROM calibration_certificates cc
                        JOIN equipment e ON cc.equipment_id = e.id
                        WHERE cc.equipment_id = %s
                        ORDER BY cc.certificate_date DESC
                    """, (equipment_id,))
                    
                    certificates = cursor.fetchall()
                    
                    print(f"\n📋 История поверок/аттестаций:")
                    for cert in certificates:
                        print(f"  📄 {cert['certificate_number']} - {cert['certificate_date']}")
                        print(f"     Следующая: {cert['next_calibration_date']}")
                        print(f"     Дней до: {cert['days_until_calibration']}")
                        if cert['calibration_cost']:
                            print(f"     Стоимость: {cert['calibration_cost']} ₽")
                        print()
                        
                except ValueError:
                    print("❌ Неверный ID оборудования!")
        
        elif choice == '2':
            # Добавить новую поверку
            equipment_id = input("ID оборудования: ").strip()
            certificate_number = input("№ свидетельства/аттестата: ").strip()
            certificate_date = input("Дата поверки/аттестации (YYYY-MM-DD): ").strip()
            next_calibration_date = input("Дата следующей поверки/аттестации (YYYY-MM-DD): ").strip()
            calibration_cost = input("Стоимость (необязательно): ").strip()
            
            if not all([equipment_id, certificate_number, certificate_date]):
                print("❌ Ошибка: ID оборудования, номер и дата обязательны!")
                return
            
            try:
                equipment_id = int(equipment_id)
                cost = float(calibration_cost) if calibration_cost else None
                
                cursor.execute("""
                    SELECT add_calibration_certificate(%s, %s, %s, %s) as id
                """, (equipment_id, certificate_number, certificate_date, cost))
                
                new_id = cursor.fetchone()['id']
                print(f"✅ Поверка/аттестация добавлена с ID: {new_id}")
                
                # Показываем рассчитанные даты
                cursor.execute("""
                    SELECT next_calibration_date, days_until_calibration 
                    FROM calibration_certificates 
                    WHERE id = %s
                """, (new_id,))
                
                dates = cursor.fetchone()
                if dates:
                    print(f"📅 Следующая поверка: {dates['next_calibration_date']}")
                    print(f"⏰ Дней до поверки: {dates['days_until_calibration']}")
                
                conn.commit()
                print("✅ Поверка/аттестация успешно добавлена!")
                
            except ValueError:
                print("❌ Ошибка в формате данных!")
            except Exception as e:
                print(f"❌ Ошибка при добавлении: {e}")
                conn.rollback()
        
        elif choice == '3':
            return
        
        else:
            print("❌ Неверный выбор!")
            
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        cursor.close()
        conn.close()

def export_to_excel():
    """Экспорт данных в Excel файл"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        # Получение данных СИ
        df_si = pd.read_sql("""
            SELECT 
                e.row_number as "№ п/п",
                e.name as "Наименование СИ",
                e.type_designation as "Обозначение типа СИ",
                e.serial_number as "Заводской номер",
                e.certificate_number as "№ свидетельства о поверке",
                e.mpi as "МПИ",
                e.certificate_date as "Дата поверки",
                e.next_calibration_date as "Дата очередной поверки",
                e.days_until_calibration as "Количество дней до окончания срока поверки",
                e.inventory_number as "Инвентарный номер",
                e.year_in_service as "Год ввода в эксплуатацию",
                g.gosregister_number as "Номер в Госреестре",
                e.calibration_cost as "Стоимость поверки",
                e.note as "Примечание"
            FROM equipment e
            LEFT JOIN gosregister g ON e.gosregister_id = g.id
            WHERE e.equipment_type_id = 1
            ORDER BY e.row_number
        """, conn)
        
        # Получение данных ИО
        df_io = pd.read_sql("""
            SELECT 
                e.row_number as "№ п/п",
                e.name as "Наименование",
                e.type_designation as "Обозначение типа",
                e.serial_number as "Зав. №",
                e.certificate_number as "№ аттестата",
                e.mpi as "МПИ",
                e.certificate_date as "Дата проведения аттестации",
                e.next_calibration_date as "Дата очередной аттестации",
                e.days_until_calibration as "Количество дней до окончания срока аттестации",
                e.inventory_number as "Инв. №",
                e.year_in_service as "Год ввода в эксп.",
                e.calibration_cost as "Стоимость аттестации",
                e.note as "Примечание"
            FROM equipment e
            WHERE e.equipment_type_id = 2
            ORDER BY e.row_number
        """, conn)
        
        # Получение данных ВО
        df_vo = pd.read_sql("""
            SELECT 
                e.row_number as "№ п/п",
                e.name as "Наименование оборудования",
                e.type_designation as "Тип оборудования",
                e.serial_number as "Зав. №",
                e.inventory_number as "Инв. №",
                e.note as "Примечание"
            FROM equipment e
            WHERE e.equipment_type_id = 3
            ORDER BY e.row_number
        """, conn)
        
        # Экспорт в Excel
        filename = f"equipment_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            df_si.to_excel(writer, sheet_name='СИ', index=False)
            df_io.to_excel(writer, sheet_name='ИО', index=False)
            df_vo.to_excel(writer, sheet_name='ВО', index=False)
        
        print(f"✅ Данные экспортированы в файл: {filename}")
        
    except Exception as e:
        print(f"❌ Ошибка при экспорте: {e}")
    finally:
        conn.close()

def main():
    """Главное меню"""
    while True:
        print("\n" + "="*50)
        print("🔧 УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ ОБОРУДОВАНИЯ")
        print("="*50)
        print("1. 📊 Показать статистику")
        print("2. 🔍 Поиск оборудования")
        print("3. ➕ Добавить оборудование")
        print("4. 📋 Управление поверками/аттестациями")
        print("5. 📤 Экспорт в Excel")
        print("6. ❌ Выход")
        
        choice = input("\nВыберите действие (1-6): ").strip()
        
        if choice == '1':
            show_statistics()
        elif choice == '2':
            search_term = input("Введите поисковый запрос: ").strip()
            if search_term:
                search_equipment(search_term)
        elif choice == '3':
            add_equipment()
        elif choice == '4':
            manage_calibration_certificates()
        elif choice == '5':
            export_to_excel()
        elif choice == '6':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()
