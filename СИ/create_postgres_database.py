import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import pandas as pd
import os
from datetime import datetime

# Настройки подключения к PostgreSQL
DB_CONFIG = {
    'user': 'postgres',
    'password': '27915002',
    'host': '192.168.1.139',
    'port': '5432',
    'database': 'equipment'
}

def create_database():
    """Создает базу данных если она не существует"""
    # Подключаемся к PostgreSQL без указания базы данных
    conn_config = DB_CONFIG.copy()
    del conn_config['database']
    
    try:
        conn = psycopg2.connect(**conn_config)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Проверяем существует ли база данных
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_CONFIG['database'],))
        exists = cursor.fetchone()
        
        if not exists:
            # Создаем базу данных
            cursor.execute(f'CREATE DATABASE {DB_CONFIG["database"]}')
            print(f"База данных {DB_CONFIG['database']} создана успешно!")
        else:
            print(f"База данных {DB_CONFIG['database']} уже существует")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Ошибка при создании базы данных: {e}")

def create_tables():
    """Создает таблицы в PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Удаляем таблицы если они существуют (в правильном порядке из-за внешних ключей)
        cursor.execute("DROP TABLE IF EXISTS equipment CASCADE")
        cursor.execute("DROP TABLE IF EXISTS equipment_types CASCADE")
        cursor.execute("DROP TABLE IF EXISTS gosregister CASCADE")
        
        # 1. Создаем таблицу типов оборудования
        cursor.execute('''
            CREATE TABLE equipment_types (
                id SERIAL PRIMARY KEY,
                type_code VARCHAR(10) UNIQUE NOT NULL,
                type_name VARCHAR(100) NOT NULL
            )
        ''')
        
        # 2. Создаем таблицу Госреестра
        cursor.execute('''
            CREATE TABLE gosregister (
                id SERIAL PRIMARY KEY,
                gosregister_number VARCHAR(50) UNIQUE NOT NULL,
                si_name TEXT NOT NULL,
                type_designation VARCHAR(200),
                manufacturer VARCHAR(200)
            )
        ''')
        
        # 3. Создаем таблицу оборудования
        cursor.execute('''
            CREATE TABLE equipment (
                id SERIAL PRIMARY KEY,
                row_number INTEGER,
                equipment_type_id INTEGER NOT NULL,
                gosregister_id INTEGER,
                name TEXT,
                type_designation VARCHAR(200),
                serial_number VARCHAR(100),
                certificate_number VARCHAR(100),
                mpi VARCHAR(50),
                certificate_date DATE,
                next_calibration_date DATE,
                days_until_calibration INTEGER,
                inventory_number VARCHAR(50),
                year_in_service DATE,
                note TEXT,
                calibration_cost DECIMAL(10,2),
                FOREIGN KEY (equipment_type_id) REFERENCES equipment_types (id),
                FOREIGN KEY (gosregister_id) REFERENCES gosregister (id)
            )
        ''')
        
        # Создаем индексы для улучшения производительности
        cursor.execute('CREATE INDEX idx_equipment_type_id ON equipment (equipment_type_id)')
        cursor.execute('CREATE INDEX idx_equipment_gosregister_id ON equipment (gosregister_id)')
        cursor.execute('CREATE INDEX idx_equipment_row_number ON equipment (row_number)')
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Таблицы PostgreSQL созданы успешно!")
        
    except Exception as e:
        print(f"Ошибка при создании таблиц: {e}")

def populate_equipment_types():
    """Заполняет таблицу типов оборудования"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        types = [
            ('СИ', 'Средства измерений'),
            ('ИО', 'Испытательное оборудование'),
            ('ВО', 'Вспомогательное оборудование')
        ]
        
        cursor.executemany('INSERT INTO equipment_types (type_code, type_name) VALUES (%s, %s)', types)
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Таблица типов оборудования заполнена!")
        
    except Exception as e:
        print(f"Ошибка при заполнении типов оборудования: {e}")

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
    """Импортирует данные Госреестра в PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        gosregister_df = extract_gosregister_data()
        
        for _, row in gosregister_df.iterrows():
            cursor.execute('''
                INSERT INTO gosregister (gosregister_number, si_name, type_designation, manufacturer)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (gosregister_number) DO NOTHING
            ''', (row['gosregister_number'], row['name'], row['type_designation'], row['manufacturer']))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"Импортировано {len(gosregister_df)} записей в Госреестр")
        
    except Exception as e:
        print(f"Ошибка при импорте Госреестра: {e}")

def import_equipment_data():
    """Импортирует данные оборудования в PostgreSQL"""
    excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Получаем ID типов оборудования
        type_mapping = {'СИ': 1, 'ИО': 2, 'ВО': 3}
        
        # Создаем маппинг номеров Госреестра к ID
        gosregister_mapping = {}
        cursor.execute('SELECT id, gosregister_number FROM gosregister')
        for row in cursor.fetchall():
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
        
        for _, row in df_si.iterrows():
            gosregister_id = gosregister_mapping.get(row['gosregister_number']) if row['gosregister_number'] else None
            
            # Обрабатываем числовые поля
            row_number = int(row['row_number']) if pd.notna(row['row_number']) and str(row['row_number']).strip() != '' else None
            days_until_calibration = int(row['days_until_calibration']) if pd.notna(row['days_until_calibration']) and str(row['days_until_calibration']).strip() != '' else None
            # Для СИ year_in_service может быть числом, для ИО - датой
            year_in_service = row['year_in_service'] if pd.notna(row['year_in_service']) and str(row['year_in_service']).strip() != '' else None
            calibration_cost = float(row['calibration_cost']) if pd.notna(row['calibration_cost']) and str(row['calibration_cost']).strip() != '' else None
            
            # Обрабатываем даты
            certificate_date = row['certificate_date'] if pd.notna(row['certificate_date']) and str(row['certificate_date']).strip() != '' else None
            next_calibration_date = row['next_calibration_date'] if pd.notna(row['next_calibration_date']) and str(row['next_calibration_date']).strip() != '' else None
            
            cursor.execute('''
                INSERT INTO equipment (
                    row_number, equipment_type_id, gosregister_id, name, type_designation,
                    serial_number, certificate_number, mpi, certificate_date, next_calibration_date,
                    days_until_calibration, inventory_number, year_in_service, note, calibration_cost
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                row_number, type_mapping['СИ'], gosregister_id, row['name'], 
                row['type_designation'], row['serial_number'], row['certificate_number'],
                row['mpi'], certificate_date, next_calibration_date,
                days_until_calibration, row['inventory_number'], 
                year_in_service, row['note'], calibration_cost
            ))
        
        print(f"Импортировано {len(df_si)} записей СИ")
        
        # Импорт ИО
        print("Импорт данных ИО...")
        df_io = pd.read_excel(excel_file, sheet_name='ИО')
        df_io = df_io.fillna('')
        
        column_mapping_io = {
            '№ п/п': 'row_number',
            'Наименование\n': 'name',
            'Обозначение типа': 'type_designation',
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
        
        for _, row in df_io.iterrows():
            # Обрабатываем числовые поля
            row_number = int(row['row_number']) if pd.notna(row['row_number']) and str(row['row_number']).strip() != '' else None
            days_until_calibration = int(row['days_until_calibration']) if pd.notna(row['days_until_calibration']) and str(row['days_until_calibration']).strip() != '' else None
            
            # Обрабатываем даты
            certificate_date = row['certificate_date'] if pd.notna(row['certificate_date']) and str(row['certificate_date']).strip() != '' else None
            next_calibration_date = row['next_calibration_date'] if pd.notna(row['next_calibration_date']) and str(row['next_calibration_date']).strip() != '' else None
            year_in_service = row['year_in_service'] if pd.notna(row['year_in_service']) and str(row['year_in_service']).strip() != '' else None
            
            cursor.execute('''
                INSERT INTO equipment (
                    row_number, equipment_type_id, name, type_designation, serial_number, certificate_number,
                    certificate_date, next_calibration_date, days_until_calibration,
                    inventory_number, year_in_service, note
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                row_number, type_mapping['ИО'], row['name'], row['type_designation'], row['serial_number'],
                row['certificate_number'], certificate_date, next_calibration_date,
                days_until_calibration, row['inventory_number'], 
                year_in_service, row['note']
            ))
        
        print(f"Импортировано {len(df_io)} записей ИО")
        
        # Импорт ВО
        print("Импорт данных ВО...")
        df_vo = pd.read_excel(excel_file, sheet_name='ВО')
        df_vo = df_vo.fillna('')
        
        column_mapping_vo = {
            '№ п/п': 'row_number',
            'Наименование оборудования': 'name',
            'Тип оборудования': 'type_designation',
            'Зав. №': 'serial_number',
            'Инв.\n№': 'inventory_number',
            'Примечание': 'note'
        }
        df_vo = df_vo.rename(columns=column_mapping_vo)
        
        for _, row in df_vo.iterrows():
            # Обрабатываем числовые поля
            row_number = int(row['row_number']) if pd.notna(row['row_number']) and str(row['row_number']).strip() != '' else None
            
            cursor.execute('''
                INSERT INTO equipment (
                    row_number, equipment_type_id, name, type_designation, serial_number,
                    inventory_number, note
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                row_number, type_mapping['ВО'], row['name'], row['type_designation'],
                row['serial_number'], row['inventory_number'], row['note']
            ))
        
        print(f"Импортировано {len(df_vo)} записей ВО")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("Импорт оборудования в PostgreSQL завершен!")
        
    except Exception as e:
        print(f"Ошибка при импорте оборудования: {e}")

def verify_postgres_data():
    """Проверяет импортированные данные в PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Проверяем типы оборудования
        print("Типы оборудования:")
        cursor.execute('SELECT * FROM equipment_types ORDER BY id')
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} - {row[2]}")
        
        # Проверяем Госреестр
        cursor.execute("SELECT COUNT(*) FROM gosregister")
        gosregister_count = cursor.fetchone()[0]
        print(f"\nЗаписей в Госреестре: {gosregister_count}")
        
        # Проверяем оборудование по типам
        print("\nОборудование по типам:")
        cursor.execute('''
            SELECT et.type_name, COUNT(e.id) 
            FROM equipment_types et 
            LEFT JOIN equipment e ON et.id = e.equipment_type_id 
            GROUP BY et.id, et.type_name
            ORDER BY et.id
        ''')
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]} записей")
        
        # Проверяем связи с Госреестром
        cursor.execute("SELECT COUNT(*) FROM equipment WHERE gosregister_id IS NOT NULL")
        with_gosregister = cursor.fetchone()[0]
        print(f"\nЗаписей с номером Госреестра: {with_gosregister}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Ошибка при проверке данных: {e}")

if __name__ == "__main__":
    create_database()
    create_tables()
    populate_equipment_types()
    import_gosregister_data()
    import_equipment_data()
    verify_postgres_data()
