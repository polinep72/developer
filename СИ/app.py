from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
from config import Config
from gosregister_parser import GosregisterParser
from enhanced_gosregister_parser import EnhancedGosregisterParser

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

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

def row_to_dict(row):
    """Конвертирует строку из БД в словарь"""
    if isinstance(row, dict):
        return row
    return dict(row)

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/api/equipment-types')
def get_equipment_types():
    """API для получения типов оборудования"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM equipment_types ORDER BY id')
        types = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify([row_to_dict(row) for row in types])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/gosregister')
def get_gosregister():
    """API для получения данных Госреестра"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM gosregister ORDER BY gosregister_number')
        gosregister = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify([row_to_dict(row) for row in gosregister])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/gosregister/<int:record_id>/mpi', methods=['PUT'])
def update_gosregister_mpi(record_id):
    """API для обновления МПИ записи в Госреестре"""
    try:
        data = request.get_json()
        mpi = data.get('mpi')
        
        if not mpi:
            return jsonify({'error': 'МПИ не указан'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к БД'}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Обновляем МПИ
        cursor.execute('''
            UPDATE gosregister 
            SET mpi = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        ''', (mpi, record_id))
        
        updated_record = cursor.fetchone()
        
        if not updated_record:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Запись не найдена'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': 'МПИ успешно обновлен',
            'record': row_to_dict(updated_record)
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Ошибка обновления МПИ: {str(e)}'}), 500

@app.route('/api/equipment/<equipment_type>')
def get_equipment_by_type(equipment_type):
    """API для получения оборудования по типу"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем ID типа оборудования
        cursor.execute('SELECT id FROM equipment_types WHERE type_code = %s', (equipment_type,))
        type_row = cursor.fetchone()
        if not type_row:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Тип оборудования не найден'}), 404
        
        type_id = type_row['id']
        
        # Получаем оборудование с JOIN для связанных таблиц и последней поверки/аттестации
        # Расчет дней до поверки делаем на лету с приоритетом МПИ из gosregister
        # Для СИ и ИО сортируем по дате следующей поверки/аттестации по убыванию
        if equipment_type == "СИ" or equipment_type == "ИО":
            order_clause = "ORDER BY cc.next_calibration_date DESC NULLS LAST, e.row_number"
        else:
            order_clause = "ORDER BY e.row_number"
        
        cursor.execute(f'''
            SELECT e.*, et.type_code, et.type_name, g.gosregister_number, g.si_name as gosregister_name,
                   g.web_url as gosregister_url, COALESCE(g.mpi, e.mpi) as mpi_priority,
                   cc.certificate_number, cc.certificate_date, cc.next_calibration_date,
                   cc.calibration_cost, cc.certificate_url,
                   (cc.next_calibration_date - CURRENT_DATE) as days_until_calibration
            FROM equipment e
            JOIN equipment_types et ON e.equipment_type_id = et.id
            LEFT JOIN gosregister g ON e.gosregister_id = g.id
            LEFT JOIN LATERAL (
                SELECT certificate_number, certificate_date, next_calibration_date,
                       calibration_cost, certificate_url
                FROM calibration_certificates cc
                WHERE cc.equipment_id = e.id
                ORDER BY cc.certificate_date DESC
                LIMIT 1
            ) cc ON true
            WHERE e.equipment_type_id = %s
            {order_clause}
        ''', (type_id,))
        
        equipment = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify([row_to_dict(row) for row in equipment])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/equipment')
def get_all_equipment():
    """API для получения всего оборудования"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute('''
            SELECT e.*, et.type_code, et.type_name, g.gosregister_number, g.si_name as gosregister_name,
                   g.web_url as gosregister_url,
                   cc.certificate_number, cc.certificate_date, cc.next_calibration_date,
                   cc.calibration_cost, cc.certificate_url,
                   (cc.next_calibration_date - CURRENT_DATE) as days_until_calibration
            FROM equipment e
            JOIN equipment_types et ON e.equipment_type_id = et.id
            LEFT JOIN gosregister g ON e.gosregister_id = g.id
            LEFT JOIN LATERAL (
                SELECT certificate_number, certificate_date, next_calibration_date,
                       calibration_cost, certificate_url
                FROM calibration_certificates cc
                WHERE cc.equipment_id = e.id
                ORDER BY cc.certificate_date DESC
                LIMIT 1
            ) cc ON true
            ORDER BY et.type_code, e.row_number
        ''')
        
        equipment = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify([row_to_dict(row) for row in equipment])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/calibration-certificates/<int:equipment_id>')
def get_calibration_certificates(equipment_id):
    """API для получения истории поверок/аттестаций оборудования"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT * FROM calibration_certificates 
            WHERE equipment_id = %s 
            ORDER BY certificate_date DESC
        ''', (equipment_id,))
        
        certificates = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify([row_to_dict(row) for row in certificates])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/calibration-certificates', methods=['POST'])
def add_calibration_certificate():
    """API для добавления новой поверки/аттестации"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        data = request.get_json()
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT add_calibration_certificate(%s, %s, %s, %s, %s) as id
        ''', (
            data.get('equipment_id'),
            data.get('certificate_number'),
            data.get('certificate_date'),
            data.get('calibration_cost'),
            data.get('certificate_url')
        ))
        
        new_id = cursor.fetchone()['id']
        
        # Получаем полную информацию о созданной записи
        cursor.execute('''
            SELECT * FROM calibration_certificates WHERE id = %s
        ''', (new_id,))
        
        new_certificate = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(row_to_dict(new_certificate)), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """API для получения статистики"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Ошибка подключения к БД'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем статистику по типам оборудования
        cursor.execute('''
            SELECT et.type_code, COUNT(e.id) as count
            FROM equipment_types et
            LEFT JOIN equipment e ON et.id = e.equipment_type_id
            GROUP BY et.id, et.type_code
            ORDER BY et.id
        ''')
        
        stats_query = cursor.fetchall()
        
        stats = {}
        for row in stats_query:
            stats[f'{row["type_code"].lower()}_count'] = row['count']
        
        # Добавляем общую статистику
        cursor.execute('SELECT COUNT(*) FROM equipment')
        stats['total_count'] = cursor.fetchone()['count']
        
        cursor.execute('SELECT COUNT(*) FROM gosregister')
        stats['gosregister_count'] = cursor.fetchone()['count']
        
        cursor.close()
        conn.close()
        
        return jsonify(stats)
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/gosregister/parse', methods=['POST'])
def parse_gosregister():
    """API для парсинга данных Госреестра (без добавления в БД)"""
    try:
        data = request.get_json()
        gosregister_number = data.get('gosregister_number', '').strip()
        
        if not gosregister_number:
            return jsonify({'error': 'Номер Госреестра не может быть пустым'}), 400
        
        # Валидация формата номера
        if len(gosregister_number) < 3:
            return jsonify({'error': 'Номер Госреестра слишком короткий'}), 400
        
        # Создаем экземпляр улучшенного парсера с МПИ
        parser = EnhancedGosregisterParser()
        
        # Проверяем, существует ли уже запись
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к БД'}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM gosregister WHERE gosregister_number = %s', (gosregister_number,))
        existing_record = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if existing_record:
            return jsonify({
                'error': f'Запись с номером {gosregister_number} уже существует в базе данных',
                'existing_record': row_to_dict(existing_record)
            }), 409
        
        # Парсим данные включая МПИ (без добавления в БД)
        parsed_data = parser.parse_gosregister_with_mpi(gosregister_number)
        
        if parsed_data:
            return jsonify({
                'message': f'Данные для номера {gosregister_number} найдены',
                'parsed_data': parsed_data
            }), 200
        else:
            return jsonify({
                'error': f'Не удалось получить данные для номера {gosregister_number} с сайта fgis.gost.ru'
            }), 404
            
    except Exception as e:
        return jsonify({'error': f'Ошибка при парсинге: {str(e)}'}), 500

@app.route('/api/gosregister/add', methods=['POST'])
def add_gosregister():
    """API для добавления записи в Госреестр"""
    try:
        data = request.get_json()
        
        # Проверяем обязательные поля
        required_fields = ['gosregister_number', 'si_name', 'type_designation', 'manufacturer']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Поле {field} обязательно для заполнения'}), 400
        
        # Проверяем, существует ли уже запись
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к БД'}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM gosregister WHERE gosregister_number = %s', (data['gosregister_number'],))
        existing_record = cursor.fetchone()
        
        if existing_record:
            cursor.close()
            conn.close()
            return jsonify({
                'error': f'Запись с номером {data["gosregister_number"]} уже существует'
            }), 409
        
        # Парсим МПИ если есть URL карточки
        mpi = None
        if data.get('web_url') and '/fundmetrology/cm/mits/' in data['web_url']:
            try:
                parser = EnhancedGosregisterParser()
                mpi = parser.parse_mpi_from_card_url(data['web_url'])
                if mpi:
                    print(f"✅ МПИ найден и добавлен: {mpi}")
            except Exception as e:
                print(f"⚠️  Ошибка парсинга МПИ: {e}")
        
        # Добавляем новую запись с МПИ
        cursor.execute('''
            INSERT INTO gosregister (gosregister_number, si_name, type_designation, manufacturer, web_url, mpi, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING *
        ''', (
            data['gosregister_number'],
            data['si_name'],
            data['type_designation'],
            data['manufacturer'],
            data.get('web_url', ''),
            mpi
        ))
        
        new_record = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': f'Запись {data["gosregister_number"]} успешно добавлена в базу данных',
            'record': row_to_dict(new_record)
        }), 201
            
    except Exception as e:
        return jsonify({'error': f'Ошибка при добавлении: {str(e)}'}), 500

@app.route('/api/equipment/add-si', methods=['POST'])
def add_si_to_equipment():
    """API для добавления СИ в список оборудования"""
    try:
        data = request.get_json()
        
        # Проверяем обязательные поля
        required_fields = ['gosregister_id', 'type', 'serial_number']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Поле {field} обязательно для заполнения'}), 400
        
        # Подключаемся к БД
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к БД'}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем данные из Госреестра
        cursor.execute('SELECT * FROM gosregister WHERE id = %s', (data['gosregister_id'],))
        gosregister_record = cursor.fetchone()
        
        if not gosregister_record:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Запись в Госреестре не найдена'}), 404
        
        # Проверяем, не добавлено ли уже это СИ с таким серийным номером
        cursor.execute('''
            SELECT id FROM equipment 
            WHERE equipment_type_id = (SELECT id FROM equipment_types WHERE type_name = 'Средства измерений')
            AND serial_number = %s 
            AND gosregister_id = %s
        ''', (data['serial_number'], gosregister_record['id']))
        
        existing_equipment = cursor.fetchone()
        if existing_equipment:
            cursor.close()
            conn.close()
            return jsonify({'error': 'СИ с таким серийным номером уже добавлено'}), 409
        
        # Добавляем новую запись в equipment
        cursor.execute('''
            INSERT INTO equipment (
                equipment_type_id, 
                name, 
                type_designation, 
                serial_number, 
                gosregister_id,
                created_at
            ) VALUES (
                (SELECT id FROM equipment_types WHERE type_name = 'Средства измерений'),
                %s, %s, %s, %s, CURRENT_TIMESTAMP
            )
            RETURNING id
        ''', (
            gosregister_record['si_name'],
            data['type'],
            data['serial_number'],
            gosregister_record['id']
        ))
        
        equipment_id = cursor.fetchone()['id']
        
        # Если указан номер свидетельства о поверке, добавляем запись о поверке
        if data.get('certificate_number') or data.get('calibration_date'):
            cursor.execute('''
                INSERT INTO calibration_certificates (
                    equipment_id,
                    certificate_number,
                    calibration_date,
                    next_calibration_date,
                    created_at
                ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            ''', (
                equipment_id,
                data.get('certificate_number'),
                data.get('calibration_date'),
                data.get('calibration_date')  # Пока ставим ту же дату, триггер обновит
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': f'СИ {data["type"]} (№{data["serial_number"]}) успешно добавлено в оборудование',
            'equipment_id': equipment_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Ошибка при добавлении СИ: {str(e)}'}), 500

@app.route('/api/equipment/add-vo', methods=['POST'])
def add_vo_to_equipment():
    """API для добавления ВО в список оборудования"""
    try:
        data = request.get_json()
        
        # Проверяем обязательные поля
        required_fields = ['name', 'type', 'serial_number']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'Поле {field} обязательно для заполнения'}), 400
        
        # Подключаемся к БД
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к БД'}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем, не добавлено ли уже это ВО с таким серийным номером
        cursor.execute('''
            SELECT id FROM equipment 
            WHERE equipment_type_id = (SELECT id FROM equipment_types WHERE type_name = 'Вспомогательное оборудование')
            AND serial_number = %s
        ''', (data['serial_number'],))
        
        existing_equipment = cursor.fetchone()
        if existing_equipment:
            cursor.close()
            conn.close()
            return jsonify({'error': 'ВО с таким серийным номером уже добавлено'}), 409
        
        # Добавляем новую запись в equipment
        cursor.execute('''
            INSERT INTO equipment (
                equipment_type_id, 
                name, 
                type_designation, 
                serial_number,
                note,
                created_at
            ) VALUES (
                (SELECT id FROM equipment_types WHERE type_name = 'Вспомогательное оборудование'),
                %s, %s, %s, %s, CURRENT_TIMESTAMP
            )
            RETURNING id
        ''', (
            data['name'],
            data['type'],
            data['serial_number'],
            data.get('note', '')
        ))
        
        equipment_id = cursor.fetchone()['id']
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': f'ВО {data["name"]} (№{data["serial_number"]}) успешно добавлено в оборудование',
            'equipment_id': equipment_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Ошибка при добавлении ВО: {str(e)}'}), 500

@app.route('/api/equipment/add-io', methods=['POST'])
def add_io_to_equipment():
    """API для добавления ИО в список оборудования"""
    try:
        data = request.get_json()
        
        # Валидация обязательных полей
        if not data.get('name'):
            return jsonify({'error': 'Наименование обязательно'}), 400
        if not data.get('type'):
            return jsonify({'error': 'Обозначение типа обязательно'}), 400
        if not data.get('serial_number'):
            return jsonify({'error': 'Заводской номер обязателен'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Ошибка подключения к БД'}), 500
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Проверяем, не существует ли уже ИО с таким заводским номером
        cursor.execute('''
            SELECT e.id FROM equipment e
            JOIN equipment_types et ON e.equipment_type_id = et.id
            WHERE et.type_name = 'Испытательное оборудование' 
            AND e.serial_number = %s
        ''', (data['serial_number'],))
        
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'error': f'ИО с заводским номером {data["serial_number"]} уже существует'}), 409
        
        # Добавляем ИО в таблицу equipment
        cursor.execute('''
            INSERT INTO equipment (
                equipment_type_id,
                name, 
                type_designation, 
                serial_number,
                mpi,
                note,
                created_at
            ) VALUES (
                (SELECT id FROM equipment_types WHERE type_name = 'Испытательное оборудование'),
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
            )
            RETURNING id
        ''', (
            data['name'],
            data['type'],
            data['serial_number'],
            data.get('mpi', '1 год'),
            data.get('note', '')
        ))
        
        equipment_id = cursor.fetchone()['id']
        
        # Если указаны данные аттестата, добавляем их в calibration_certificates
        if data.get('certificate_number') and data.get('certificate_date'):
            # Используем МПИ из формы или по умолчанию 1 год
            mpi_text = data.get('mpi', '1 год')
            
            # Парсим МПИ (простая логика: если содержит "2", то 2 года, иначе 1 год)
            if '2' in mpi_text:
                years = 2
            else:
                years = 1
            
            cursor.execute('''
                INSERT INTO calibration_certificates (
                    equipment_id,
                    certificate_number,
                    certificate_date,
                    next_calibration_date,
                    created_at
                ) VALUES (
                    %s, %s, %s::DATE, 
                    %s::DATE + (%s || ' year')::INTERVAL - INTERVAL '1 day',
                    CURRENT_TIMESTAMP
                )
            ''', (
                equipment_id,
                data['certificate_number'],
                data['certificate_date'],
                data['certificate_date'],
                years
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'message': f'ИО {data["name"]} (№{data["serial_number"]}) успешно добавлено в оборудование',
            'equipment_id': equipment_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Ошибка при добавлении ИО: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(
        debug=Config.DEBUG, 
        host=Config.HOST, 
        port=Config.PORT
    )
