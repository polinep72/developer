import pandas as pd
import sqlite3
import os
from datetime import datetime

def create_database():
    """Создает базу данных SQLite и таблицы"""
    conn = sqlite3.connect('equipment.db')
    cursor = conn.cursor()
    
    # Удаляем таблицы если они существуют
    cursor.execute("DROP TABLE IF EXISTS si_equipment")
    cursor.execute("DROP TABLE IF EXISTS io_equipment") 
    cursor.execute("DROP TABLE IF EXISTS vo_equipment")
    
    # Создаем таблицу для СИ (средства измерения)
    cursor.execute('''
        CREATE TABLE si_equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_number INTEGER,
            name TEXT,
            type_designation TEXT,
            serial_number TEXT,
            certificate_number TEXT,
            mpi TEXT,
            certificate_date DATE,
            next_calibration_date DATE,
            days_until_calibration INTEGER,
            inventory_number TEXT,
            year_in_service INTEGER,
            gosregister_number TEXT,
            note TEXT,
            calibration_cost REAL
        )
    ''')
    
    # Создаем таблицу для ИО (испытательное оборудование)
    cursor.execute('''
        CREATE TABLE io_equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_number INTEGER,
            instrument_type TEXT,
            serial_number TEXT,
            certificate_number TEXT,
            attestation_date DATE,
            next_attestation_date DATE,
            days_until_attestation INTEGER,
            inventory_number TEXT,
            year_in_service DATE,
            note TEXT
        )
    ''')
    
    # Создаем таблицу для ВО (вспомогательное оборудование)
    cursor.execute('''
        CREATE TABLE vo_equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_number INTEGER,
            equipment_name TEXT,
            equipment_type TEXT,
            serial_number TEXT,
            inventory_number TEXT,
            note TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("База данных создана успешно!")

def import_excel_data():
    """Импортирует данные из Excel в базу данных"""
    excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    
    if not os.path.exists(excel_file):
        print(f"Файл {excel_file} не найден!")
        return
    
    conn = sqlite3.connect('equipment.db')
    
    try:
        # Импорт данных СИ
        print("Импорт данных СИ...")
        df_si = pd.read_excel(excel_file, sheet_name='СИ', header=1)
        
        # Очищаем данные - убираем первую строку если это заголовки
        if df_si.iloc[0, 0] == '№\\nп/п':
            df_si = df_si.iloc[1:]
        
        # Переименовываем столбцы для удобства
        df_si.columns = [
            'row_number', 'name', 'type_designation', 'serial_number', 
            'certificate_number', 'mpi', 'certificate_date', 'next_calibration_date',
            'days_until_calibration', 'inventory_number', 'year_in_service',
            'gosregister_number', 'note', 'calibration_cost'
        ]
        
        # Заполняем пустые значения
        df_si = df_si.fillna('')
        
        # Конвертируем даты
        date_columns = ['certificate_date', 'next_calibration_date']
        for col in date_columns:
            if col in df_si.columns:
                df_si[col] = pd.to_datetime(df_si[col], errors='coerce')
        
        df_si.to_sql('si_equipment', conn, if_exists='append', index=False)
        print(f"Импортировано {len(df_si)} записей СИ")
        
        # Импорт данных ИО
        print("Импорт данных ИО...")
        df_io = pd.read_excel(excel_file, sheet_name='ИО')
        df_io = df_io.fillna('')
        
        # Переименовываем столбцы для соответствия таблице
        column_mapping_io = {
            '№ п/п': 'row_number',
            'Тип\nприбора\n': 'instrument_type',
            'зав.№': 'serial_number',
            '№\nаттестата': 'certificate_number',
            'дата\nпроведения\nаттестации': 'attestation_date',
            'Дата\nочередной\nаттестации': 'next_attestation_date',
            'Количество\nдней\nдо\nокончания\nсрока\nаттестации': 'days_until_attestation',
            'Инв.\n№': 'inventory_number',
            ' год\nввода\nв\nэксп.': 'year_in_service',
            'Примечание': 'note'
        }
        df_io = df_io.rename(columns=column_mapping_io)
        
        # Конвертируем дату
        if 'year_in_service' in df_io.columns:
            df_io['year_in_service'] = pd.to_datetime(df_io['year_in_service'], errors='coerce')
        
        df_io.to_sql('io_equipment', conn, if_exists='append', index=False)
        print(f"Импортировано {len(df_io)} записей ИО")
        
        # Импорт данных ВО
        print("Импорт данных ВО...")
        df_vo = pd.read_excel(excel_file, sheet_name='ВО')
        df_vo = df_vo.fillna('')
        
        # Переименовываем столбцы для соответствия таблице
        column_mapping_vo = {
            '№ п/п': 'row_number',
            'Наименование оборудования': 'equipment_name',
            'Тип оборудования': 'equipment_type',
            'Зав. №': 'serial_number',
            'Инв.\n№': 'inventory_number',
            'Примечание': 'note'
        }
        df_vo = df_vo.rename(columns=column_mapping_vo)
        
        df_vo.to_sql('vo_equipment', conn, if_exists='append', index=False)
        print(f"Импортировано {len(df_vo)} записей ВО")
        
    except Exception as e:
        print(f"Ошибка при импорте: {e}")
    finally:
        conn.close()
    
    print("Импорт данных завершен!")

def verify_data():
    """Проверяет импортированные данные"""
    conn = sqlite3.connect('equipment.db')
    cursor = conn.cursor()
    
    tables = ['si_equipment', 'io_equipment', 'vo_equipment']
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Таблица {table}: {count} записей")
    
    conn.close()

if __name__ == "__main__":
    create_database()
    import_excel_data()
    verify_data()
