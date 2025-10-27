#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для импорта данных из Excel файла в базу данных
"""

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import datetime
import os

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

def clear_table_data(table_name):
    """Очистить данные из таблицы"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        if table_name == 'equipment':
            cursor.execute("DELETE FROM equipment")
        elif table_name == 'gosregister':
            cursor.execute("DELETE FROM gosregister")
        elif table_name == 'all':
            cursor.execute("DELETE FROM equipment")
            cursor.execute("DELETE FROM gosregister")
        
        conn.commit()
        print(f"✅ Таблица {table_name} очищена")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при очистке таблицы {table_name}: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def import_from_excel(excel_file, clear_existing=False):
    """Импорт данных из Excel файла"""
    
    if not os.path.exists(excel_file):
        print(f"❌ Файл {excel_file} не найден!")
        return False
    
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    
    try:
        print(f"📁 Импорт данных из файла: {excel_file}")
        
        if clear_existing:
            print("🧹 Очистка существующих данных...")
            clear_table_data('all')
        
        # Получаем типы оборудования
        cursor.execute("SELECT id, type_code FROM equipment_types")
        type_mapping = {row[1]: row[0] for row in cursor.fetchall()}
        
        # Импорт СИ
        print("📋 Импорт СИ...")
        df_si = pd.read_excel(excel_file, sheet_name='СИ')
        df_si = df_si.fillna('')
        
        si_count = 0
        for _, row in df_si.iterrows():
            try:
                # Обработка данных СИ
                row_number = int(row['№ п/п']) if pd.notna(row['№ п/п']) and str(row['№ п/п']).strip() != '' else None
                year_in_service = row['Год ввода в эксплуатацию'] if pd.notna(row['Год ввода в эксплуатацию']) and str(row['Год ввода в эксплуатацию']).strip() != '' else None
                
                # Обработка данных поверки (для отдельной таблицы)
                certificate_number = str(row['№ свидетельства о поверке']).strip() if pd.notna(row['№ свидетельства о поверке']) and str(row['№ свидетельства о поверке']).strip() != '' else None
                certificate_date = row['Дата поверки'] if pd.notna(row['Дата поверки']) and str(row['Дата поверки']).strip() != '' else None
                next_calibration_date = row['Дата очередной поверки'] if pd.notna(row['Дата очередной поверки']) and str(row['Дата очередной поверки']).strip() != '' else None
                days_until_calibration = int(row['Количество дней до окончания срока поверки']) if pd.notna(row['Количество дней до окончания срока поверки']) and str(row['Количество дней до окончания срока поверки']).strip() != '' else None
                calibration_cost = float(row['Стоимость поверки']) if pd.notna(row['Стоимость поверки']) and str(row['Стоимость поверки']).strip() != '' else None
                
                # Поиск gosregister_id по номеру
                gosregister_id = None
                if pd.notna(row['Номер в Госреестре']) and str(row['Номер в Госреестре']).strip() != '':
                    cursor.execute("SELECT id FROM gosregister WHERE gosregister_number = %s", (str(row['Номер в Госреестре']).strip(),))
                    result = cursor.fetchone()
                    if result:
                        gosregister_id = result[0]
                
                # Вставляем основную информацию об оборудовании
                cursor.execute('''
                    INSERT INTO equipment (
                        row_number, equipment_type_id, gosregister_id, name, type_designation,
                        serial_number, mpi, inventory_number, year_in_service, note
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    row_number, type_mapping['СИ'], gosregister_id,
                    str(row['Наименование СИ']).strip() if pd.notna(row['Наименование СИ']) else '',
                    str(row['Обозначение типа СИ']).strip() if pd.notna(row['Обозначение типа СИ']) else '',
                    str(row['Заводской номер']).strip() if pd.notna(row['Заводской номер']) else '',
                    str(row['МПИ']).strip() if pd.notna(row['МПИ']) else '',
                    str(row['Инвентарный номер']).strip() if pd.notna(row['Инвентарный номер']) else '',
                    year_in_service,
                    str(row['Примечание']).strip() if pd.notna(row['Примечание']) else ''
                ))
                
                equipment_id = cursor.fetchone()[0]
                
                # Если есть данные о поверке, добавляем их в отдельную таблицу
                if certificate_number and certificate_date:
                    cursor.execute('''
                        SELECT add_calibration_certificate(%s, %s, %s, %s) as id
                    ''', (equipment_id, certificate_number, certificate_date, calibration_cost))
                si_count += 1
                
            except Exception as e:
                print(f"⚠️ Ошибка при импорте СИ строка {row_number}: {e}")
                continue
        
        print(f"✅ Импортировано {si_count} записей СИ")
        
        # Импорт ИО
        print("🧪 Импорт ИО...")
        df_io = pd.read_excel(excel_file, sheet_name='ИО')
        df_io = df_io.fillna('')
        
        io_count = 0
        for _, row in df_io.iterrows():
            try:
                row_number = int(row['№ п/п']) if pd.notna(row['№ п/п']) and str(row['№ п/п']).strip() != '' else None
                days_until_calibration = int(row['Количество дней до окончания срока аттестации']) if pd.notna(row['Количество дней до окончания срока аттестации']) and str(row['Количество дней до окончания срока аттестации']).strip() != '' else None
                calibration_cost = float(row['Стоимость аттестации']) if pd.notna(row['Стоимость аттестации']) and str(row['Стоимость аттестации']).strip() != '' else None
                
                certificate_date = row['Дата проведения аттестации'] if pd.notna(row['Дата проведения аттестации']) and str(row['Дата проведения аттестации']).strip() != '' else None
                next_calibration_date = row['Дата очередной аттестации'] if pd.notna(row['Дата очередной аттестации']) and str(row['Дата очередной аттестации']).strip() != '' else None
                year_in_service = row['Год ввода в эксп.'] if pd.notna(row['Год ввода в эксп.']) and str(row['Год ввода в эксп.']).strip() != '' else None
                
                # Вставляем основную информацию об оборудовании ИО
                cursor.execute('''
                    INSERT INTO equipment (
                        row_number, equipment_type_id, name, type_designation, serial_number,
                        mpi, inventory_number, year_in_service, note
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (
                    row_number, type_mapping['ИО'],
                    str(row['Наименование']).strip() if pd.notna(row['Наименование']) else '',
                    str(row['Обозначение типа']).strip() if pd.notna(row['Обозначение типа']) else '',
                    str(row['Зав. №']).strip() if pd.notna(row['Зав. №']) else '',
                    str(row['МПИ']).strip() if pd.notna(row['МПИ']) else '',
                    str(row['Инв. №']).strip() if pd.notna(row['Инв. №']) else '',
                    year_in_service,
                    str(row['Примечание']).strip() if pd.notna(row['Примечание']) else ''
                ))
                
                equipment_id = cursor.fetchone()[0]
                
                # Если есть данные об аттестации, добавляем их в отдельную таблицу
                certificate_number = str(row['№ аттестата']).strip() if pd.notna(row['№ аттестата']) and str(row['№ аттестата']).strip() != '' else None
                if certificate_number and certificate_date:
                    cursor.execute('''
                        SELECT add_calibration_certificate(%s, %s, %s, %s) as id
                    ''', (equipment_id, certificate_number, certificate_date, calibration_cost))
                io_count += 1
                
            except Exception as e:
                print(f"⚠️ Ошибка при импорте ИО строка {row_number}: {e}")
                continue
        
        print(f"✅ Импортировано {io_count} записей ИО")
        
        # Импорт ВО
        print("🔧 Импорт ВО...")
        df_vo = pd.read_excel(excel_file, sheet_name='ВО')
        df_vo = df_vo.fillna('')
        
        vo_count = 0
        for _, row in df_vo.iterrows():
            try:
                row_number = int(row['№ п/п']) if pd.notna(row['№ п/п']) and str(row['№ п/п']).strip() != '' else None
                
                cursor.execute('''
                    INSERT INTO equipment (
                        row_number, equipment_type_id, name, type_designation, serial_number,
                        inventory_number, note
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    row_number, type_mapping['ВО'],
                    str(row['Наименование оборудования']).strip() if pd.notna(row['Наименование оборудования']) else '',
                    str(row['Тип оборудования']).strip() if pd.notna(row['Тип оборудования']) else '',
                    str(row['Зав. №']).strip() if pd.notna(row['Зав. №']) else '',
                    str(row['Инв. №']).strip() if pd.notna(row['Инв. №']) else '',
                    str(row['Примечание']).strip() if pd.notna(row['Примечание']) else ''
                ))
                vo_count += 1
                
            except Exception as e:
                print(f"⚠️ Ошибка при импорте ВО строка {row_number}: {e}")
                continue
        
        print(f"✅ Импортировано {vo_count} записей ВО")
        
        conn.commit()
        print(f"🎉 Импорт завершен! Всего импортировано: {si_count + io_count + vo_count} записей")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при импорте: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def main():
    """Главное меню импорта"""
    print("📥 ИМПОРТ ДАННЫХ ИЗ EXCEL")
    print("="*40)
    
    excel_file = input("Введите путь к Excel файлу (или Enter для 'ПЕРЕЧЕНЬ СИ и ИО.xlsx'): ").strip()
    if not excel_file:
        excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    
    clear_choice = input("Очистить существующие данные? (y/N): ").strip().lower()
    clear_existing = clear_choice in ['y', 'yes', 'да', 'д']
    
    if clear_existing:
        confirm = input("⚠️ Вы уверены? Все данные будут удалены! (y/N): ").strip().lower()
        if confirm not in ['y', 'yes', 'да', 'д']:
            print("❌ Импорт отменен")
            return
    
    success = import_from_excel(excel_file, clear_existing)
    
    if success:
        print("\n✅ Импорт успешно завершен!")
    else:
        print("\n❌ Импорт завершился с ошибками")

if __name__ == "__main__":
    main()
