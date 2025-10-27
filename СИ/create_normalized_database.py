import pandas as pd
import sqlite3
import os
from datetime import datetime

def create_normalized_database():
    """Создает нормализованную базу данных SQLite с тремя связанными таблицами"""
    conn = sqlite3.connect('equipment_new.db')
    cursor = conn.cursor()
    
    # Удаляем таблицы если они существуют
    cursor.execute("DROP TABLE IF EXISTS equipment")
    cursor.execute("DROP TABLE IF EXISTS equipment_types")
    cursor.execute("DROP TABLE IF EXISTS gosregister")
    
    # 1. Создаем таблицу типов оборудования
    cursor.execute('''
        CREATE TABLE equipment_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_code TEXT UNIQUE NOT NULL,
            type_name TEXT NOT NULL
        )
    ''')
    
    # 2. Создаем таблицу Госреестра
    cursor.execute('''
        CREATE TABLE gosregister (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gosregister_number TEXT UNIQUE NOT NULL,
            si_name TEXT NOT NULL,
            type_designation TEXT,
            manufacturer TEXT
        )
    ''')
    
    # 3. Создаем таблицу оборудования
    cursor.execute('''
        CREATE TABLE equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            row_number INTEGER,
            equipment_type_id INTEGER NOT NULL,
            gosregister_id INTEGER,
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
            note TEXT,
            calibration_cost REAL,
            FOREIGN KEY (equipment_type_id) REFERENCES equipment_types (id),
            FOREIGN KEY (gosregister_id) REFERENCES gosregister (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Нормализованная база данных создана успешно!")

def populate_equipment_types():
    """Заполняет таблицу типов оборудования"""
    conn = sqlite3.connect('equipment_new.db')
    cursor = conn.cursor()
    
    types = [
        ('СИ', 'Средства измерений'),
        ('ИО', 'Испытательное оборудование'),
        ('ВО', 'Вспомогательное оборудование')
    ]
    
    cursor.executemany('INSERT INTO equipment_types (type_code, type_name) VALUES (?, ?)', types)
    conn.commit()
    conn.close()
    print("Таблица типов оборудования заполнена!")

def extract_gosregister_data():
    """Извлекает уникальные данные Госреестра из листа СИ"""
    excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    
    # Читаем данные СИ
    df_si = pd.read_excel(excel_file, sheet_name='СИ', header=1)
    
    # Очищаем данные - убираем первую строку если это заголовки
    if df_si.iloc[0, 0] == '№\\nп/п':
        df_si = df_si.iloc[1:]
    
    # Переименовываем столбцы
    df_si.columns = [
        'row_number', 'name', 'type_designation', 'serial_number', 
        'certificate_number', 'mpi', 'certificate_date', 'next_calibration_date',
        'days_until_calibration', 'inventory_number', 'year_in_service',
        'gosregister_number', 'note', 'calibration_cost'
    ]
    
    # Фильтруем только записи с номером Госреестра
    gosregister_data = df_si[df_si['gosregister_number'].notna() & (df_si['gosregister_number'] != '')]
    
    # Создаем уникальные записи Госреестра
    unique_gosregister = gosregister_data.groupby('gosregister_number').agg({
        'name': 'first',
        'type_designation': 'first'
    }).reset_index()
    
    # Добавляем пустой столбец для изготовителя
    unique_gosregister['manufacturer'] = ''
    
    return unique_gosregister

def import_gosregister_data():
    """Импортирует данные Госреестра в БД"""
    conn = sqlite3.connect('equipment_new.db')
    
    try:
        gosregister_df = extract_gosregister_data()
        
        # Переименовываем столбцы для соответствия таблице
        gosregister_df = gosregister_df.rename(columns={
            'gosregister_number': 'gosregister_number',
            'name': 'si_name',
            'type_designation': 'type_designation',
            'manufacturer': 'manufacturer'
        })
        
        gosregister_df.to_sql('gosregister', conn, if_exists='append', index=False)
        print(f"Импортировано {len(gosregister_df)} записей в Госреестр")
        
    except Exception as e:
        print(f"Ошибка при импорте Госреестра: {e}")
    finally:
        conn.close()

def import_equipment_data():
    """Импортирует данные оборудования в нормализованную структуру"""
    excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    conn = sqlite3.connect('equipment_new.db')
    
    try:
        # Получаем ID типов оборудования
        type_mapping = {
            'СИ': 1,
            'ИО': 2, 
            'ВО': 3
        }
        
        # Создаем маппинг номеров Госреестра к ID
        cursor = conn.cursor()
        gosregister_mapping = {}
        for row in cursor.execute('SELECT id, gosregister_number FROM gosregister'):
            gosregister_mapping[row[1]] = row[0]
        
        # Импорт СИ
        print("Импорт данных СИ...")
        df_si = pd.read_excel(excel_file, sheet_name='СИ', header=1)
        if df_si.iloc[0, 0] == '№\\nп/п':
            df_si = df_si.iloc[1:]
        
        df_si.columns = [
            'row_number', 'name', 'type_designation', 'serial_number', 
            'certificate_number', 'mpi', 'certificate_date', 'next_calibration_date',
            'days_until_calibration', 'inventory_number', 'year_in_service',
            'gosregister_number', 'note', 'calibration_cost'
        ]
        
        df_si = df_si.fillna('')
        
        # Добавляем equipment_type_id для СИ
        df_si['equipment_type_id'] = type_mapping['СИ']
        
        # Добавляем gosregister_id
        df_si['gosregister_id'] = df_si['gosregister_number'].map(gosregister_mapping)
        
        # Удаляем столбец gosregister_number, так как связь идет через внешний ключ
        df_si = df_si.drop('gosregister_number', axis=1)
        
        # Конвертируем даты
        date_columns = ['certificate_date', 'next_calibration_date']
        for col in date_columns:
            if col in df_si.columns:
                df_si[col] = pd.to_datetime(df_si[col], errors='coerce')
        
        # Импортируем СИ
        df_si.to_sql('equipment', conn, if_exists='append', index=False)
        print(f"Импортировано {len(df_si)} записей СИ")
        
        # Импорт ИО
        print("Импорт данных ИО...")
        df_io = pd.read_excel(excel_file, sheet_name='ИО')
        df_io = df_io.fillna('')
        
        # Переименовываем столбцы
        column_mapping_io = {
            '№ п/п': 'row_number',
            'Тип\nприбора\n': 'name',
            'зав.№': 'serial_number',
            '№\nаттестата': 'certificate_number',
            'дата\nпроведения\nаттестации': 'certificate_date',
            'Дата\nочередной\nаттестации': 'next_calibration_date',
            'Количество\nдней\nдо\nокончания\nсрока\nаттестации': 'days_until_calibration',
            'Инв.\n№': 'inventory_number',
            ' год\nввода\nв\nэксп.': 'year_in_service',
            'Примечание': 'note'
        }
        df_io = df_io.rename(columns=column_mapping_io)
        
        # Добавляем обязательные поля для ИО
        df_io['equipment_type_id'] = type_mapping['ИО']
        df_io['gosregister_id'] = None  # ИО не в Госреестре
        df_io['type_designation'] = ''
        df_io['mpi'] = ''
        df_io['calibration_cost'] = None
        
        # Конвертируем дату
        if 'year_in_service' in df_io.columns:
            df_io['year_in_service'] = pd.to_datetime(df_io['year_in_service'], errors='coerce')
        
        df_io.to_sql('equipment', conn, if_exists='append', index=False)
        print(f"Импортировано {len(df_io)} записей ИО")
        
        # Импорт ВО
        print("Импорт данных ВО...")
        df_vo = pd.read_excel(excel_file, sheet_name='ВО')
        df_vo = df_vo.fillna('')
        
        # Переименовываем столбцы
        column_mapping_vo = {
            '№ п/п': 'row_number',
            'Наименование оборудования': 'name',
            'Тип оборудования': 'type_designation',
            'Зав. №': 'serial_number',
            'Инв.\n№': 'inventory_number',
            'Примечание': 'note'
        }
        df_vo = df_vo.rename(columns=column_mapping_vo)
        
        # Добавляем обязательные поля для ВО
        df_vo['equipment_type_id'] = type_mapping['ВО']
        df_vo['gosregister_id'] = None  # ВО не в Госреестре
        df_vo['certificate_number'] = ''
        df_vo['mpi'] = ''
        df_vo['certificate_date'] = None
        df_vo['next_calibration_date'] = None
        df_vo['days_until_calibration'] = None
        df_vo['year_in_service'] = None
        df_vo['calibration_cost'] = None
        
        df_vo.to_sql('equipment', conn, if_exists='append', index=False)
        print(f"Импортировано {len(df_vo)} записей ВО")
        
    except Exception as e:
        print(f"Ошибка при импорте оборудования: {e}")
    finally:
        conn.close()
    
    print("Импорт оборудования завершен!")

def verify_normalized_data():
    """Проверяет импортированные данные в нормализованной структуре"""
    conn = sqlite3.connect('equipment_new.db')
    cursor = conn.cursor()
    
    # Проверяем типы оборудования
    print("Типы оборудования:")
    for row in cursor.execute('SELECT * FROM equipment_types'):
        print(f"  {row[0]}: {row[1]} - {row[2]}")
    
    # Проверяем Госреестр
    cursor.execute("SELECT COUNT(*) FROM gosregister")
    gosregister_count = cursor.fetchone()[0]
    print(f"\nЗаписей в Госреестре: {gosregister_count}")
    
    # Проверяем оборудование по типам
    print("\nОборудование по типам:")
    for row in cursor.execute('''
        SELECT et.type_name, COUNT(e.id) 
        FROM equipment_types et 
        LEFT JOIN equipment e ON et.id = e.equipment_type_id 
        GROUP BY et.id, et.type_name
    '''):
        print(f"  {row[0]}: {row[1]} записей")
    
    # Проверяем связи с Госреестром
    cursor.execute("SELECT COUNT(*) FROM equipment WHERE gosregister_id IS NOT NULL")
    with_gosregister = cursor.fetchone()[0]
    print(f"\nЗаписей с номером Госреестра: {with_gosregister}")
    
    conn.close()

if __name__ == "__main__":
    create_normalized_database()
    populate_equipment_types()
    import_gosregister_data()
    import_equipment_data()
    verify_normalized_data()
