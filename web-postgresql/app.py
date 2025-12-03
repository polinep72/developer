# написать комментарии к каждому модулю программы

import os
from datetime import datetime
from io import BytesIO
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for, make_response
from psycopg2.extras import execute_values
from waitress import serve
from openpyxl.styles import NamedStyle

# Загружаем переменные окружения
load_dotenv() # Загрузка переменных окружения из файла .env

app = Flask(__name__) # Создаем экземпляр приложения Flask
app.secret_key = os.getenv('SECRET_KEY') # Устанавливаем секретный ключ для сессий

@app.context_processor
def inject_user():
    # Передаем логин пользователя в шаблоны, если он вошел в систему
    return {'user_logged_in': 'username' in session, 'username': session.get('username')}

# функция для подключения к БД
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    return conn

def execute_query(query, params=None):
    """Выполняет запрос к базе данных PostgreSQL и возвращает результат."""
    conn = get_db_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if query.strip().lower().startswith("select"):
                result = cur.fetchall()
            else:
                conn.commit()
                result = None
    finally:
        conn.close()

    return result

def execute_query2(query, params=None):
    """Выполняет запрос к базе данных PostgreSQL и возвращает результат."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if query.strip().lower().startswith("select"):
                result = cur.fetchall()
            elif "returning" in query.lower():
                result = cur.fetchone()  # Получаем возвращаемый результат
                conn.commit()
            else:
                conn.commit()
                result = None
    finally:
        conn.close()
    return result


# функция для преобразования данных для БД
def get_reference_id(table_name, column_name, value):
    query = f"SELECT id FROM {table_name} WHERE {column_name} = %s"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, (value,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else None


def get_or_create_id(table, column, value):
    """Возвращает id из вспомогательной таблицы, добавляя запись, если она отсутствует."""
    select_query = f"SELECT id FROM {table} WHERE {column} = %s" # SQL-запрос для поиска записи

    result = execute_query(select_query, (value,)) # Выполняем запрос

    if result:
        return result[0][0]
    #print(result)
    # Если записи нет, добавляем ее
    insert_query = f"INSERT INTO {table} ({column}) VALUES (%s) RETURNING id"
    print(f"Inserting value: {value}")
        # Выполняем запрос
    new_id = execute_query2(insert_query, (value,))
    print(f"Insert value: {value}")
    # Проверяем, что результат не None
    if new_id and new_id[0]:
        return new_id[0]
    else:
        raise ValueError(f"Failed to insert value '{value}' into table '{table}'")

# Стартовая страница
@app.route('/')
def home():
    return render_template('home.html') # Отображаем шаблон home.html



# Страница поступления (inflow)
@app.route('/inflow', methods=['GET', 'POST'])
def inflow():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            return jsonify({"error": "Файл не выбран"}), 400

        try:
            # Имя загружаемого файла
            file_name = file.filename
            # Загрузка данных из Excel
            df = pd.read_excel(file, header=0)
            #print(df.info())
            df['Приход Wafer, шт.'] = df['Приход Wafer, шт.'].fillna(0).astype(int)
            df['Приход GelPack, шт.'] = df['Приход GelPack, шт.'].fillna(0).astype(int)
            df['Приход общий, шт.'] = df['Приход общий, шт.'].fillna(0).astype(int)
            # Преобразование данных в список кортежей для вставки
            for _, row in df.iterrows():
                data_to_insert = []
                id_start = int(get_or_create_id("start_p", "name_start", str(row["Номер запуска"])))
                #print('id_start', id_start, str(row["Номер запуска"]))
                id_pr = int(get_or_create_id("pr", "name_pr", str(row["Производитель"])))
                #print('id_pr',id_pr, str(row["Производитель"]))
                id_tech = int(get_or_create_id("tech", "name_tech", str(row["Технологический процесс"])))
                #print('id_tech', id_tech, str(row["Технологический процесс"]))
                id_lot = int(get_or_create_id("lot", "name_lot", str(row['Партия (Lot ID)'])))
                #print('id_lot',id_lot, str(row['Партия (Lot ID)']))
                id_wafer = int(get_or_create_id("wafer", "name_wafer", str(row['Пластина (Wafer)'])))
                #print('id_wafer',id_wafer, str(row['Пластина (Wafer)']))
                id_quad = int(get_or_create_id("quad", "name_quad", str(row['Quadrant'])))
                #print('id_quad',id_quad, str(row['Quadrant']))
                id_in_lot = int(get_or_create_id("in_lot", "in_lot", str(row['Внутренняя партия'])))
                #print('id_in_lot',id_in_lot, str(row['Внутренняя партия']))
                id_chip = int(get_or_create_id("chip", "name_chip", str(row['Номер кристалла'])))
                #print('id_chip',id_chip, str(row['Номер кристалла']))
                id_n_chip = int(get_or_create_id("n_chip", "n_chip", str(row['Шифр кристалла'])))
                #print('id_n_chip',id_n_chip, str(row['Шифр кристалла']))
                id_size = get_or_create_id("size_c", "size", str(row['Размер кристалла']))
                #print('id_size',id_size, str(row['Размер кристалла']))
                id_pack = int(get_or_create_id("pack", "name_pack", str(row["Упаковка"])))
                #print('id_pack',id_pack, str(row["Упаковка"]))
                id_stor = int(get_or_create_id("stor", "name_stor", str(row['Место хранения'])))
                #print('id_stor',id_stor, str(row['Место хранения']))
                id_cells = int(get_or_create_id("cells", "name_cells", str(row["Ячейка хранения"])))
                #print('id_cells',id_cells, str(row["Ячейка хранения"]))
                data_to_insert.append((
                    id_start, id_tech,  id_chip, id_lot, id_wafer, id_quad, id_in_lot,
                    row['Дата прихода'], row['Приход Wafer, шт.'], row['Примечание'], id_pack, id_cells, id_n_chip,
                    id_pr, id_size, row['Приход GelPack, шт.'], id_stor
                ))

                # SQL-запрос для добавления данных в таблицу invoice
                insert_query = """
                    INSERT INTO invoice (
                    id_start, id_tech, id_chip, id_lot, id_wafer, id_quad, id_in_lot, date, quan_w, 
                    note, id_pack, id_cells, id_n_chip, id_pr, id_size, quan_gp, id_stor
                    ) VALUES %s
                    ON CONFLICT (id)
                    DO UPDATE SET
                        date = EXCLUDED.date,
                        quan_w = EXCLUDED.quan_w,
                        quan_gp = EXCLUDED.quan_gp,
                        note = EXCLUDED.note                    
                """

                # Вставка данных с использованием execute_values для оптимизации
                conn = get_db_connection()
                with conn.cursor() as cur:
                    execute_values(cur, insert_query, data_to_insert)
                conn.commit()
                conn.close()
            # Логирование
            log_user_action(
                user_id=session.get('user_id'),  # ID пользователя из сессии
                action_type='Загрузка файла: Приход',
                file_name=file_name,
                target_table='invoice'  # Название таблицы
            )

            return jsonify({"success": True, "message": "Данные успешно загружены в БД"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('inflow.html')

# Страница расхода (outflow)
@app.route('/outflow', methods=['GET', 'POST'])
def outflow():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            return jsonify({"error": "Файл не выбран"}), 400

        try:
            # Имя загружаемого файла
            file_name = file.filename
            # Загрузка данных из Excel
            data = pd.read_excel(file, header=0)
            data['Расход Wafer, шт.'] = data['Расход Wafer, шт.'].fillna(0).astype(int)
            data['Расход GelPack, шт.'] = data['Расход GelPack, шт.'].fillna(0).astype(int)
            data['Место хранения'] = data['Место хранения'].fillna('-')
            data['Ячейка хранения'] = data['Ячейка хранения'].fillna('-')
            for _, row in data.iterrows():
                data_to_insert = []
                # Извлечение данных из строки Excel
                id_start = int(get_reference_id("start_p", "name_start", str(row["Номер запуска"])))
                id_pr = int(get_reference_id("pr", "name_pr", str(row["Производитель"])))
                id_tech = int(get_reference_id("tech", "name_tech", str(row["Технологический процесс"])))
                id_lot = int(get_reference_id("lot", "name_lot", str(row["Партия (Lot ID)"])))
                id_wafer = int(get_reference_id("wafer", "name_wafer", str(row["Пластина (Wafer)"])))
                id_quad = int(get_reference_id("quad", "name_quad", str(row["Quadrant"])))
                id_in_lot = int(get_reference_id("in_lot", "in_lot", str(row["Внутренняя партия"])))
                id_n_chip = int(get_reference_id("n_chip", "n_chip", str(row["Шифр кристалла"])))
                cons_w = int(row["Расход Wafer, шт."])
                cons_gp = int(row["Расход GelPack, шт."])
                note = str(row["Примечание"])
                transf_man = str(row["Куда передано (Производственная партия)"])
                reciver = str(row["ФИО"])
                id_stor = int(get_reference_id("stor", "name_stor", str(row['Место хранения'])))
                id_cells = int(get_reference_id("cells", "name_cells", str(row["Ячейка хранения"])))
                data_to_insert.append((
                id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                row["Дата расхода"], cons_w, cons_gp, note, transf_man, reciver, id_stor, id_cells
                ))
                # SQL-запрос для вставки данных в таблицу "consumption"
                query = """
                    INSERT INTO consumption (
                        id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                        date, cons_w, cons_gp, note, transf_man, reciver, id_stor, id_cells
                    ) VALUES %s
                """

                # Вставка данных с использованием execute_values для оптимизации
                conn = get_db_connection()
                with conn.cursor() as cur:
                    execute_values(cur, query, data_to_insert)
                conn.commit()
                conn.close()
            # Логирование
            log_user_action(
                user_id=session.get('user_id'),  # ID пользователя из сессии
                action_type='Загрузка файла: Расход',
                file_name=file_name,
                target_table='consumption'  # Название таблицы
            )
            return jsonify({"success": True, "message": "Данные успешно загружены в БД"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('outflow.html')

# Страница расхода (outflow)
@app.route('/refund', methods=['GET', 'POST'])
def refund():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            return jsonify({"error": "Файл не выбран"}), 400

        try:
            # Имя загружаемого файла
            file_name = file.filename
            # Загрузка данных из Excel
            data = pd.read_excel(file, header=0)
            data['Возврат Wafer, шт.'] = data['Возврат Wafer, шт.'].fillna(0).astype(int)
            data['Возврат GelPack, шт.'] = data['Возврат GelPack, шт.'].fillna(0).astype(int)
            data['Место хранения'] = data['Место хранения'].fillna('-')
            data['Ячейка хранения'] = data['Ячейка хранения'].fillna('-')

            for _, row in data.iterrows():
                data_to_insert = []
                # Извлечение данных из строки Excel
                id_start = int(get_reference_id("start_p", "name_start", str(row["Номер запуска"])))
                id_pr = int(get_reference_id("pr", "name_pr", str(row["Производитель"])))
                id_tech = int(get_reference_id("tech", "name_tech", str(row["Технологический процесс"])))
                id_lot = int(get_reference_id("lot", "name_lot", str(row["Партия (Lot ID)"])))
                id_wafer = int(get_reference_id("wafer", "name_wafer", str(row["Пластина (Wafer)"])))
                id_quad = int(get_reference_id("quad", "name_quad", str(row["Quadrant"])))
                id_in_lot = int(get_reference_id("in_lot", "in_lot", str(row["Внутренняя партия"])))
                id_n_chip = int(get_reference_id("n_chip", "n_chip", str(row["Шифр кристалла"])))
                quan_w = int(row['Возврат Wafer, шт.'])
                quan_gp = int(row['Возврат GelPack, шт.'])
                note = "возврат"
                id_stor = int(get_reference_id("stor", "name_stor", str(row['Место хранения'])))
                id_cells = int(get_reference_id("cells", "name_cells", str(row["Ячейка хранения"])))
                data_to_insert.append((
                id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                row["Дата возврата"], quan_w, quan_gp, str(note), id_stor, id_cells
                ))

                # SQL-запрос для вставки данных в таблицу "consumption"
                query = """
                    INSERT INTO invoice (
                        id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                        date, quan_w, quan_gp, note, id_stor, id_cells
                    ) VALUES %s
                """

                # Вставка данных с использованием execute_values для оптимизации
                conn = get_db_connection()
                try:
                    with conn.cursor() as cur:
                        # Печать данных для отладки

                        execute_values(cur, query, data_to_insert)
                    conn.commit()  # Фиксация изменений в базе данных

                except Exception as e:
                    conn.rollback()  # Откат транзакции при ошибке
                    print("Ошибка при вставке данных:", e)
                    return jsonify({"error": str(e)}), 500
                finally:
                    conn.close()
                # Логирование
                log_user_action(
                    user_id=session.get('user_id'),  # ID пользователя из сессии
                    action_type='Загрузка файла: Возврат',
                    file_name=file_name,
                    target_table='invoice'  # Название таблицы
                )
            return jsonify({"success": True, "message": "Данные успешно загружены в БД"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return render_template('refund.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    # Если только загрузка страницы
    if request.method == 'GET' and not request.args.get('chip_name'):
        # Получить список всех производителей для фильтра
        manufacturers_query = "SELECT DISTINCT name_pr FROM pr ORDER BY name_pr"
        manufacturers_raw = execute_query(manufacturers_query)
        # Преобразуем кортежи в список строк
        manufacturers = [row[0] for row in manufacturers_raw]
        return render_template('search.html', manufacturers=manufacturers)

    if request.method == 'POST':
        if 'user_id' not in session:
            return redirect(url_for('login'))
        manufacturers_query = "SELECT DISTINCT name_pr FROM pr ORDER BY name_pr"
        manufacturers_raw = execute_query(manufacturers_query)
        # Преобразуем кортежи в список строк
        manufacturers = [row[0] for row in manufacturers_raw]
        chip_name = request.form.get('chip_name', '').strip()
        manufacturer_filter = request.form.get('manufacturer', '')

        conn = get_db_connection()
        cur = conn.cursor()
        query = """
                WITH consumption_aggregated AS (SELECT id_n_chip,id_quad, item_id, SUM(cons_w) AS total_cons_w, SUM(cons_gp) AS total_cons_gp
                    FROM consumption
                    GROUP BY id_n_chip, id_quad, item_id
                ),
                invoice_aggregated AS (SELECT id_start, id_pr, id_tech, id_wafer, id_lot, id_in_lot, id_n_chip, id_quad, item_id, SUM(quan_w) AS total_quan_w, SUM(quan_gp) AS total_quan_gp, invoice.note, invoice.id_cells, invoice.id_stor
                    FROM invoice
                    GROUP BY id_start, id_pr, id_tech, id_wafer, id_quad, id_lot, id_in_lot, id_n_chip, item_id, invoice.note, invoice.id_cells, invoice.id_stor
                )
                SELECT i.item_id, 
                    i.id_start,
                    s.name_start,
                    p.name_pr,
                    t.name_tech,
                    w.name_wafer,
                    q.name_quad,
                    l.name_lot,
                    il.in_lot,
                    nc.n_chip, 
                    (i.total_quan_w - COALESCE(cons.total_cons_w, 0)) AS ostatok_w, 
                    (i.total_quan_gp - COALESCE(cons.total_cons_gp, 0)) AS ostatok_gp,
                    i.note,
                    st.name_stor,
                    c.name_cells
                    FROM invoice_aggregated i
                LEFT JOIN consumption_aggregated cons ON cons.item_id = i.item_id
                LEFT JOIN n_chip nc ON nc.id = i.id_n_chip  
                LEFT JOIN quad q ON q.id = i.id_quad  
                LEFT JOIN start_p s ON s.id = i.id_start
                LEFT JOIN tech t ON t.id = i.id_tech
                LEFT JOIN pr p ON p.id = i.id_pr
                LEFT JOIN wafer w ON w.id = i.id_wafer 
                LEFT JOIN lot l ON l.id = i.id_lot
                LEFT JOIN in_lot il ON il.id = i.id_in_lot
                LEFT JOIN stor st ON st.id = i.id_stor
                LEFT JOIN cells c ON c.id = i.id_cells
                WHERE 1=1
        """
        # Добавить фильтр по производителю, если выбран
        params = []
        if chip_name:
            query += " AND nc.n_chip ILIKE %s"
            params.append(f"%{chip_name}%")

        if manufacturer_filter and manufacturer_filter != "all":
            query += " AND p.name_pr = %s"
            params.append(manufacturer_filter)

        #print(query, manufacturer_filter)
        # Добавить поиск по запросу, если задан
        # if query_f:
        #     query += " AND (start_p.name_start ILIKE %s OR lot.name_lot ILIKE %s)"
        #     params.extend([f"%{query}%", f"%{query}%"])

        try:
            cur.execute(query, params)
            results = cur.fetchall()
            #print(f"Query results: {results}")
        except Exception as e:
            print(f"Error executing query: {e}")
        finally:
            cur.close()
            conn.close()

            return render_template('search.html', results=results,
                manufacturers=manufacturers,
                query=chip_name,
                manufacturer_filter=manufacturer_filter
            )
    else:
        return render_template('search.html')  # Выводим страницу поиска для GET-запроса

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Пользователь не авторизован'}), 401

    user_id = session['user_id']
    data = request.get_json()
    # Достаем значения из данных
    item_id = data.get('item_id')
    quantity_w = data.get('quantity_w', 0)
    quantity_gp = data.get('quantity_gp', 0)
    start = data.get('launch')
    manufacturer = data.get('manufacturer')
    technology = data.get('technology')
    lot = data.get('lot')
    wafer = data.get('wafer')
    quadrant = data.get('quadrant')
    internal_lot = data.get('internal_lot')
    chip_code = data.get('chip_code')
    note=data.get('note')
    stor=data.get('stor')
    cells=data.get('cells')
    cons_w = data.get('quantity_w', 0)
    cons_gp = data.get('quantity_gp', 0)
    date_added = datetime.now().strftime('%Y-%m-%d')  # Текущая дата

    if not item_id or (quantity_w == 0 and quantity_gp == 0):
        return jsonify({'success': False, 'message': 'Недостаточно данных для добавления в корзину'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            INSERT INTO cart (user_id, item_id, cons_w, cons_gp, manufacturer, technology, lot, wafer, quadrant, internal_lot, chip_code, date_added, start, note, stor, cells)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id) 
            DO UPDATE SET 
                cons_w = cart.cons_w + EXCLUDED.cons_w,
                cons_gp = cart.cons_gp + EXCLUDED.cons_gp;
        """
        cur.execute(query, (user_id, item_id, cons_w, cons_gp, manufacturer, technology, lot, wafer, quadrant, internal_lot, chip_code, date_added, start, note, stor, cells))
        conn.commit()

        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': 'Товар добавлен в корзину'})
    except Exception as e:
        print(f"Ошибка добавления в корзину: {e}")
        return jsonify({'success': False, 'message': 'Ошибка сервера'}), 500


@app.route('/cart', methods=['GET'])
def cart():
    # SQL-запрос для извлечения данных из таблицы "cart"
    query = """
    SELECT 
        item_id, 
        user_id,
        start,
        manufacturer,
        technology,
        wafer,
        quadrant,
        lot,
        internal_lot,
        chip_code,
        note,
        stor,
        cells,
        date_added,
        cons_w,
        cons_gp
    FROM cart
    WHERE user_id = %s
    """
    user_id = session.get('user_id')  # Предполагается, что пользователь вошел в систему
    results = execute_query(query, (user_id,))  # Получаем данные из БД для текущего пользователя

    # Передаем данные в шаблон
    return render_template('cart.html', results=results)

@app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    data = request.get_json()
    item_id = data.get('item_id')

    if not item_id:
        return jsonify({'success': False, 'message': 'Неверный ID товара'})

    query = "DELETE FROM cart WHERE item_id = %s AND user_id = %s"
    user_id = session.get('user_id')  # Получаем ID текущего пользователя
    print(user_id)
    try:
        execute_query(query, (item_id, user_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/update_cart_item', methods=['POST'])
def update_cart_item():
    data = request.get_json()
    item_id = str(data.get('id'))
    cons_w = data.get('cons_w')
    cons_gp = data.get('cons_gp')
    if not item_id or cons_w is None or cons_gp is None:
        return jsonify({"success": False, "message": "Неполные данные"}), 400

    query = """
    UPDATE cart
    SET cons_w = %s, cons_gp = %s
    WHERE item_id = %s
    """
    try:
        execute_query(query, (cons_w, cons_gp, item_id))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/export_cart', methods=['GET'])
def export_cart():
    user_id = session.get('user_id')  # ID текущего пользователя
    if not user_id:
        return "Необходимо войти в систему для экспорта корзины", 401

    # SQL-запрос для извлечения данных из корзины
    query = """
    SELECT 
        start AS "Номер запуска",
        manufacturer AS "Производитель",
        technology AS "Технологический процесс",
        lot AS "Партия (Lot ID)",
        wafer AS "Пластина (Wafer)",
        quadrant AS "Quadrant",
        internal_lot AS "Внутренняя партия",
        chip_code AS "Шифр кристалла",
        note AS "Примечание",
        stor AS "Место хранения",
        cells AS "Ячейка хранения",
        date_added AS "Дата расхода",
        cons_w AS "Расход Wafer, шт.",
        cons_gp AS "Расход GelPack, шт."
    FROM cart
    WHERE user_id = %s
    """
    results = execute_query(query, (user_id,))

    if not results:
        return "Корзина пуста. Нет данных для экспорта.", 404

    columns = [
        "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)", "Пластина (Wafer)",
        "Quadrant", "Внутренняя партия", "Шифр кристалла", "Дата расхода",
        "Расход Wafer, шт.", "Расход GelPack, шт.", "Расход общий, шт.", "Дата возврата",
        "Возврат Wafer, шт.", "Возврат GelPack, шт.", "Возврат общий, шт.",
        "Примечание", "Куда передано (Производственная партия)", "ФИО", "Место хранения", "Ячейка хранения"
    ]
    # Столбцы, которые заполняются из SQL-запроса
    filled_columns = [
        "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)", "Пластина (Wafer)",
        "Quadrant", "Внутренняя партия", "Шифр кристалла", "Примечание", "Место хранения", "Ячейка хранения", "Дата расхода",
        "Расход Wafer, шт.", "Расход GelPack, шт."
    ]
    # Проверка на наличие данных
    if results:  # Если данные есть
        # Создаем DataFrame из результатов запроса
        df_filled = pd.DataFrame(results, columns=filled_columns)
        # Создаем полный DataFrame, добавляя недостающие столбцы
        df = pd.DataFrame(columns=columns)
        for col in filled_columns:
            df[col] = df_filled[col]
    else:  # Если данных нет
        # Создаем пустой DataFrame с 21 столбцом
        df = pd.DataFrame(columns=columns)

    # Убедитесь, что столбец "Дата" существует и преобразуйте его в формат даты
    if "Дата" in df.columns:
        df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")  # Преобразование в datetime

    # Все пустые столбцы автоматически заполнятся NaN (неявно)
    df = df.infer_objects(copy=False)

    # Создаем временный файл в памяти
    output = BytesIO()
    # Создаем ExcelWriter и записываем DataFrame в файл
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]

        # Применяем форматирование к столбцу с датами
        if "Дата" in df.columns:
            date_style = NamedStyle(name="datetime", number_format="YYYY-MM-DD")
            workbook.add_named_style(date_style)

            # Найти индекс столбца "Дата"
            date_col_index = df.columns.get_loc("Дата") + 1  # Учитываем смещение для Excel
            for row in range(2, len(df) + 2):  # Начинаем с 2, т.к. 1 строка - заголовок
                cell = worksheet.cell(row=row, column=date_col_index)
                cell.style = date_style

    output.seek(0)

    # Отправляем файл клиенту
    response = make_response(send_file(output, as_attachment=True, download_name="cart_export.xlsx"))
    response.headers["Content-Disposition"] = "attachment; filename=cart_export.xlsx"
    return response

# Регистрация пользователя
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        u_password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute("INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id", (username, u_password))
            conn.commit()
            session['user_id'] = cur.fetchone()[0]  # Сохраняем ID пользователя в сессии
            return redirect(url_for('home'))
        except Exception as e:
            print(f"Error during registration: {e}")
            return "Ошибка при регистрации", 500
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        u_password = request.form['password']

        # Формируем запрос с использованием параметров
        select_query = "SELECT * FROM users WHERE username ILIKE %s AND password ILIKE %s;"
        params = (username, u_password)

        # Выполняем запрос
        user = execute_query(select_query, params)

        if user:  # Если пользователь найден
            session['user_id'] = user[0][0]  # ID пользователя
            session['username'] = user[0][1]  # Логин пользователя
            return redirect(url_for('home'))
        else:
            return "Неправильный логин или пароль", 401

    return render_template('login.html')

@app.route('/logout')
def logout():
    # Очищаем данные из сессии
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('home'))  # Возврат на главную страницу

@app.route('/clear_cart', methods=['POST'])
def clear_cart():
    user_id = session.get('user_id')  # ID текущего пользователя
    if not user_id:
        return {"success": False, "message": "Пользователь не идентифицирован."}, 400

    try:
        # Удаляем все записи из таблицы `cart` для текущего пользователя
        query = "DELETE FROM cart WHERE user_id = %s"
        execute_query(query, (user_id,))  # Используем вашу функцию execute_query
        return redirect('/cart')  # Перенаправляем обратно на страницу корзины
    except Exception as e:
        app.logger.error(f"Ошибка очистки корзины: {e}")
        return {"success": False, "message": "Ошибка при очистке корзины."}, 500

def log_user_action(user_id, action_type, file_name, target_table):
    query = """
        INSERT INTO user_logs (user_id, action_type, file_name, target_table)
        VALUES (%s, %s, %s, %s)
    """
    params = (user_id, action_type, file_name, target_table)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()
    except Exception as e:
        print(f"Ошибка логирования: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    serve(app, host="127.0.0.1", port=5000)
