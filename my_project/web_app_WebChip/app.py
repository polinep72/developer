# my_project/web_app_WebChip/app.py
import logging  # <--- ДОБАВИТЬ
import os
from datetime import datetime
from io import BytesIO
import pandas as pd
import psycopg2  # Убедитесь, что psycopg2 или psycopg2-binary есть в requirements.txt
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for, make_response, flash
from werkzeug.security import check_password_hash, generate_password_hash
from psycopg2.extras import execute_values
# from waitress import serve
from openpyxl.styles import NamedStyle
from urllib.parse import quote

# Импортируем WSGIMiddleware
try:
    from uvicorn.middleware.wsgi import WSGIMiddleware
except ImportError:
    from starlette.middleware.wsgi import WSGIMiddleware

# Настраиваем корневой логгер, чтобы он выводил INFO и выше
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

# Загружаем переменные окружения
load_dotenv()

_flask_app = Flask(__name__)
_flask_app.secret_key = os.getenv('SECRET_KEY', 'a_default_secret_key_change_it')  # Добавим дефолтный ключ

if not _flask_app.debug:  # Обычно в debug режиме Flask более многословен
    # Устанавливаем уровень INFO для логгера приложения
    _flask_app.logger.setLevel(logging.INFO)


@_flask_app.context_processor
def inject_user():
    return {'user_logged_in': 'username' in session, 'username': session.get('username')}


# --- НАЧАЛО ОПРЕДЕЛЕНИЙ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ ---
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        # Основное имя базы — DB_NAME; DB_NAME2 оставляем как fallback для обратной совместимости
        database=os.getenv('DB_NAME') or os.getenv('DB_NAME2'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT', '5432')  # Используем порт из env или дефолтный
    )
    return conn


def execute_query(query, params=None, fetch=True):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        stripped_query = query.strip().lower()
        is_modifying_query = stripped_query.startswith(('insert', 'update', 'delete'))

        cur.execute(query, params)

        if is_modifying_query:
            conn.commit()  # ВСЕГДА коммитим изменяющие запросы

        if fetch:
            # cur.description будет None для INSERT/UPDATE без RETURNING
            # Поэтому проверяем его наличие перед fetchall
            if cur.description:
                results = cur.fetchall()
            else:
                results = None  # Если нет данных для fetch (например, INSERT без RETURNING)
        else:
            results = cur.rowcount  # Возвращаем количество затронутых строк для не-fetch запросов

        cur.close()
        return results
    except (Exception, psycopg2.Error) as error:
        _flask_app.logger.error(f"Ошибка при выполнении SQL: {error}. Запрос: {query}, Параметры: {params}",
                                exc_info=True)
        if conn:
            conn.rollback()
        raise  # Пробрасываем ошибку дальше
    finally:
        if conn:
            conn.close()


def get_or_create_id(table_name, column_name, value):
    # Простая реализация, нужно адаптировать под вашу БД (проверка на None, типы и т.д.)
    # Экранирование имен таблиц/столбцов здесь не сделано для простоты,
    # предполагается, что table_name и column_name приходят из кода, а не от пользователя.
    select_query = f"SELECT id FROM {table_name} WHERE {column_name} = %s"
    existing = execute_query(select_query, (value,), fetch=True)
    if existing:
        return existing[0][0]
    else:
        insert_query = f"INSERT INTO {table_name} ({column_name}) VALUES (%s) RETURNING id"
        new_id_result = execute_query(insert_query, (value,), fetch=True)  # fetch=True из-за RETURNING
        if new_id_result:
            return new_id_result[0][0]
        else:  # Если RETURNING не сработал или не вернул id
            # Можно попробовать SELECT MAX(id) или другой способ, но это плохая практика
            # Лучше убедиться, что RETURNING id работает
            raise Exception(f"Не удалось создать или получить ID для {table_name}.{column_name} = {value}")


def get_reference_id(table_name, column_name, value):
    # Простая реализация
    select_query = f"SELECT id FROM {table_name} WHERE {column_name} = %s"
    existing = execute_query(select_query, (value,), fetch=True)
    if existing:
        return existing[0][0]
    else:
        raise ValueError(f"Справочная запись не найдена: {table_name}.{column_name} = {value}")


def log_user_action(user_id, action_type, file_name=None, target_table=None, details=None):
    # Простая заглушка, чтобы не было NameError
    print(f"LOG: User {user_id}, Action: {action_type}, File: {file_name}, Table: {target_table}, Details: {details}")
    _flask_app.logger.info(
        f"USER ACTION: UserID='{user_id}', Action='{action_type}', File='{file_name}', "
        f"Table='{target_table}', Details='{details}'"
    )
    # В реальном приложении здесь будет INSERT в таблицу логов
    # query = """
    #     INSERT INTO user_logs (user_id, action_type, file_name, target_table, details, timestamp)
    #     VALUES (%s, %s, %s, %s, %s, NOW())
    # """
    # try:
    #     execute_query(query, (user_id, action_type, file_name, target_table, details), fetch=False)
    # except Exception as e:
    #     print(f"Ошибка логирования: {e}")
    pass


# --- КОНЕЦ ОПРЕДЕЛЕНИЙ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ ---


# Стартовая страница
@_flask_app.route('/')
def home():
    return render_template('home.html')


# Страница поступления (inflow)
@_flask_app.route('/inflow', methods=['GET', 'POST'])
def inflow():
    # Эта часть для GET-запроса (когда пользователь просто открывает страницу) остается без изменений
    if request.method == 'GET':
        _flask_app.logger.info(f"Route /inflow called, method: GET")
        return render_template('inflow.html')

    # --- ВСЯ ЛОГИКА НИЖЕ - ТОЛЬКО ДЛЯ POST-ЗАПРОСА ---
    _flask_app.logger.info(f"Route /inflow called, method: POST")

    if 'user_id' not in session:
        _flask_app.logger.warning("Inflow POST attempted without user_id in session.")
        return jsonify({"success": False, "message": "Ошибка авторизации. Пожалуйста, войдите в систему снова."}), 401

    _flask_app.logger.info(f"POST data to /inflow: files={request.files}, form={request.form}")

    file = request.files.get('file')
    if not file or file.filename == '':
        _flask_app.logger.warning("Inflow POST: No file selected.")
        return jsonify({"success": False, "message": "Файл не выбран."}), 400
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        _flask_app.logger.warning(f"Inflow POST: Invalid file format: {file.filename}")
        return jsonify({"success": False, "message": "Неверный формат файла. Допускаются только .xlsx и .xls"}), 400

    # --- НОВЫЕ ПЕРЕМЕННЫЕ ---
    user_id = session['user_id']
    file_name = file.filename
    # date_time_entry будет устанавливаться через NOW() в SQL
    # --- КОНЕЦ НОВЫХ ПЕРЕМЕННЫХ ---

    conn_loop = None
    try:
        df = pd.read_excel(file, header=0)

        if df.empty:
            _flask_app.logger.warning("Inflow POST: Uploaded file is empty.")
            return jsonify({"success": False, "message": "Загруженный файл не содержит данных."}), 400

        df['Приход Wafer, шт.'] = pd.to_numeric(df['Приход Wafer, шт.'], errors='coerce').fillna(0).astype(int)
        df['Приход GelPack, шт.'] = pd.to_numeric(df['Приход GelPack, шт.'], errors='coerce').fillna(0).astype(int)

        all_data_to_insert = []
        status_приход = 1

        for idx, row in df.iterrows():
            try:
                date_val = row['Дата прихода']
                if pd.isna(date_val):
                    raise ValueError(f"Строка {idx + 2}: Дата прихода не может быть пустой.")
                formatted_date = pd.to_datetime(date_val).strftime('%Y-%m-%d')

                # ... (получение всех ID ... без изменений) ...
                id_start = int(get_or_create_id("start_p", "name_start", str(row["Номер запуска"])))
                id_pr = int(get_or_create_id("pr", "name_pr", str(row["Производитель"])))
                id_tech = int(get_or_create_id("tech", "name_tech", str(row["Технологический процесс"])))
                id_lot = int(get_or_create_id("lot", "name_lot", str(row['Партия (Lot ID)'])))
                id_wafer = int(get_or_create_id("wafer", "name_wafer", str(row['Пластина (Wafer)'])))
                id_quad = int(get_or_create_id("quad", "name_quad", str(row['Quadrant'])))
                id_in_lot = int(get_or_create_id("in_lot", "in_lot", str(row['Внутренняя партия'])))
                id_chip = int(get_or_create_id("chip", "name_chip", str(row['Номер кристалла'])))
                id_n_chip = int(get_or_create_id("n_chip", "n_chip", str(row['Шифр кристалла'])))
                id_size_val = row.get('Размер кристалла')
                id_size = get_or_create_id("size_c", "size",
                                           str(id_size_val).replace('х', 'x').replace('Х', 'x')) if pd.notna(
                    id_size_val) and str(id_size_val).strip() else None
                id_pack = int(get_or_create_id("pack", "name_pack", str(row["Упаковка"])))
                id_stor = int(get_or_create_id("stor", "name_stor", str(row['Место хранения'])))
                id_cells = int(get_or_create_id("cells", "name_cells", str(row["Ячейка хранения"])))

                # --- ИЗМЕНЕНИЕ: Добавляем user_id и file_name в кортеж ---
                all_data_to_insert.append((
                    id_start, id_tech, id_chip, id_lot, id_wafer, id_quad, id_in_lot,
                    formatted_date,  # date
                    row['Приход Wafer, шт.'],  # quan_w
                    str(row.get('Примечание', '')).strip() or None,  # note
                    id_pack, id_cells, id_n_chip,
                    id_pr, id_size,
                    row['Приход GelPack, шт.'],  # quan_gp
                    id_stor,
                    status_приход,  # status
                    user_id,  # user_entry_id
                    file_name  # file_name_entry
                ))
            except (KeyError, ValueError, Exception) as e_row:
                _flask_app.logger.error(f"Error processing row {idx + 2} in {file_name}: {e_row}", exc_info=True)
                return jsonify({"success": False, "message": f"Ошибка в строке {idx + 2}: {e_row}"}), 400

        if not all_data_to_insert:
            return jsonify(
                {"success": False, "message": "Нет данных для импорта (возможно, все строки содержали ошибки)."}), 400

        # --- ИЗМЕНЕНИЕ: Обновлен SQL-запрос ---
        # Добавлены поля: date_time_entry, user_entry_id, file_name_entry
        # Для date_time_entry используется функция SQL NOW()
        insert_query = """
            INSERT INTO invoice (
                id_start, id_tech, id_chip, id_lot, id_wafer, id_quad, id_in_lot, date, quan_w, 
                note, id_pack, id_cells, id_n_chip, id_pr, id_size, quan_gp, id_stor,
                status, user_entry_id, file_name_entry, date_time_entry
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            ); 
        """
        # Так как execute_values работает с VALUES %s, мы не можем использовать его с NOW() напрямую.
        # Вместо этого придется выполнять вставку в цикле. Это менее производительно, но проще и надежнее.
        # Либо можно создать временную таблицу.
        # Давайте пойдем по пути цикла - для большинства случаев это будет достаточно быстро.

        conn_loop = get_db_connection()
        try:
            with conn_loop.cursor() as cur:
                # Вместо execute_values используем цикл
                for record in all_data_to_insert:
                    cur.execute(insert_query, record)  # psycopg2 подставит значения в %s

            conn_loop.commit()

            log_user_action(
                user_id=user_id,  # Используем переменную, определенную ранее
                action_type='Загрузка файла: Приход',
                file_name=file_name,
                target_table='invoice'
            )
            return jsonify({"success": True,
                            "message": f"Данные из файла '{file_name}' успешно загружены ({len(all_data_to_insert)} строк)."}), 200

        except psycopg2.Error as db_err:
            if conn_loop: conn_loop.rollback()
            _flask_app.logger.error(f"Inflow - psycopg2.Error: {db_err}", exc_info=True)
            return jsonify({"success": False, "message": f"Ошибка базы данных: {db_err}"}), 500
        except Exception as e:
            if conn_loop: conn_loop.rollback()
            _flask_app.logger.error(f"Inflow - General error during DB insert: {e}", exc_info=True)
            return jsonify({"success": False, "message": f"Ошибка при загрузке данных в БД: {e}"}), 500
        finally:
            if conn_loop:
                conn_loop.close()

    except pd.errors.EmptyDataError:
        _flask_app.logger.warning("Inflow POST: Uploaded file is empty (pandas error).")
        return jsonify({"success": False, "message": "Загруженный файл пуст."}), 400
    except KeyError as e:
        _flask_app.logger.error(f"Inflow - File format error (Missing column): {e}", exc_info=False)
        return jsonify({"success": False,
                        "message": f"Ошибка в файле: отсутствует необходимый столбец '{e}'. Проверьте шаблон файла."}), 400
    except Exception as e_outer:
        _flask_app.logger.error(f"Ошибка обработки файла /inflow: {e_outer}", exc_info=True)
        return jsonify(
            {"success": False, "message": f"Произошла непредвиденная ошибка при обработке файла: {e_outer}"}), 500


@_flask_app.route('/outflow', methods=['GET', 'POST'])
def outflow():
    if request.method == 'GET':
        return render_template('outflow.html')

    # --- Логика для POST-запроса ---
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Пользователь не авторизован. Пожалуйста, войдите."}), 401

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"success": False, "message": "Файл не выбран."}), 400

    user_id = session['user_id']
    file_name = file.filename

    conn_loop_out = None
    try:
        df = pd.read_excel(file, header=0, na_filter=False)

        if df.empty:
            return jsonify({"success": False, "message": "Загруженный файл не содержит данных."}), 400

        df['Расход Wafer, шт.'] = pd.to_numeric(df['Расход Wafer, шт.'], errors='coerce').fillna(0).astype(int)
        df['Расход GelPack, шт.'] = pd.to_numeric(df['Расход GelPack, шт.'], errors='coerce').fillna(0).astype(int)

        all_data_to_insert = []
        status_расход = 2

        for idx, row in df.iterrows():
            try:
                date_val = row["Дата расхода"]
                if not date_val or pd.isna(date_val):
                    raise ValueError(f"Строка {idx + 2}: Дата расхода не может быть пустой.")
                formatted_date = pd.to_datetime(date_val).strftime('%Y-%m-%d')

                cons_w = int(row["Расход Wafer, шт."])
                cons_gp = int(row["Расход GelPack, шт."])

                id_start = int(get_reference_id("start_p", "name_start", str(row["Номер запуска"])))
                id_pr = int(get_reference_id("pr", "name_pr", str(row["Производитель"])))
                id_tech = int(get_reference_id("tech", "name_tech", str(row["Технологический процесс"])))
                id_lot = int(get_reference_id("lot", "name_lot", str(row["Партия (Lot ID)"])))
                id_wafer = int(get_reference_id("wafer", "name_wafer", str(row["Пластина (Wafer)"])))
                id_quad = int(get_reference_id("quad", "name_quad", str(row["Quadrant"])))
                id_in_lot = int(get_reference_id("in_lot", "in_lot", str(row["Внутренняя партия"])))
                id_n_chip = int(get_reference_id("n_chip", "n_chip", str(row["Шифр кристалла"])))

                id_chip = int(get_reference_id("chip", "name_chip", str(row["Номер кристалла"])))
                id_pack = int(get_reference_id("pack", "name_pack", str(row.get("Упаковка", ""))))
                id_stor = int(get_reference_id("stor", "name_stor", str(row.get('Место хранения', ''))))

                # --- ИЗМЕНЕНИЕ ЗДЕСЬ: используем id_cells ---
                id_cells = int(get_reference_id("cells", "name_cells", str(row.get("Ячейка хранения", ''))))

                note = str(row.get("Примечание", "")).strip() or None
                transf_man = str(row.get("Куда передано (Производственная партия)", "")).strip() or None
                reciver = str(row.get("ФИО", "")).strip() or None

                # --- ИЗМЕНЕНИЕ ЗДЕСЬ: передаем id_cells ---
                all_data_to_insert.append((
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    id_chip, id_pack, id_stor, id_cells,
                    formatted_date, cons_w, cons_gp,
                    note, transf_man, reciver,
                    status_расход, user_id, file_name
                ))
            except (KeyError, ValueError) as e_row:
                _flask_app.logger.error(f"Outflow - Error processing row {idx + 2}: {e_row}", exc_info=True)
                return jsonify({"success": False, "message": f"Ошибка в строке {idx + 2}: {e_row}"}), 400

        if not all_data_to_insert:
            return jsonify({"success": False, "message": "Нет корректных данных для импорта в файле."}), 400

        # --- ИЗМЕНЕНИЕ ЗДЕСЬ: в SQL запросе id_cells ---
        query_consumption = """
            INSERT INTO consumption (
                id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                id_chip, id_pack, id_stor, id_cells,
                date, cons_w, cons_gp, 
                note, transf_man, reciver,
                status, user_entry_id, file_name_entry, date_time_entry
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, NOW()
            );
        """

        conn_loop_out = get_db_connection()
        try:
            with conn_loop_out.cursor() as cur:
                for record in all_data_to_insert:
                    cur.execute(query_consumption, record)
            conn_loop_out.commit()

            log_user_action(
                user_id=user_id,
                action_type='Загрузка файла: Расход',
                file_name=file_name,
                target_table='consumption'
            )
            return jsonify({"success": True,
                            "message": f"Данные расхода из файла '{file_name}' успешно загружены ({len(all_data_to_insert)} строк)."}), 200

        except psycopg2.Error as db_err:
            if conn_loop_out: conn_loop_out.rollback()
            _flask_app.logger.error(f"Ошибка БД при обработке файла расхода: {db_err}", exc_info=True)
            return jsonify({"success": False, "message": f"Ошибка базы данных: {db_err}"}), 500
        except Exception as e:
            if conn_loop_out: conn_loop_out.rollback()
            _flask_app.logger.error(f"Непредвиденная ошибка обработки файла /outflow: {e}", exc_info=True)
            return jsonify({"success": False, "message": f"Произошла непредвиденная ошибка на сервере: {str(e)}"}), 500
        finally:
            if conn_loop_out:
                conn_loop_out.close()

    except Exception as e_outer:
        _flask_app.logger.error(f"Ошибка обработки файла /outflow: {e_outer}", exc_info=True)
        return jsonify(
            {"success": False, "message": f"Произошла непредвиденная ошибка при обработке файла: {e_outer}"}), 500


@_flask_app.route('/refund', methods=['GET', 'POST'])
def refund():
    if request.method == 'GET':
        return render_template('refund.html')

    # --- Логика для POST-запроса ---
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Пользователь не авторизован."}), 401

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"success": False, "message": "Файл не выбран."}), 400

    user_id = session['user_id']
    file_name = file.filename

    conn_refund_loop = None
    try:
        df = pd.read_excel(file, header=0, na_filter=False)

        if df.empty:
            return jsonify({"success": False, "message": "Загруженный файл не содержит данных."}), 400

        df['Возврат Wafer, шт.'] = pd.to_numeric(df['Возврат Wafer, шт.'], errors='coerce').fillna(0).astype(int)
        df['Возврат GelPack, шт.'] = pd.to_numeric(df['Возврат GelPack, шт.'], errors='coerce').fillna(0).astype(int)

        all_data_to_insert = []
        status_возврат = 3

        for idx, row in df.iterrows():
            try:
                date_val_str = str(row["Дата возврата"]).strip()
                if not date_val_str:
                    raise ValueError(f"Строка {idx + 2}: Дата возврата не может быть пустой.")
                formatted_date = pd.to_datetime(date_val_str).strftime('%Y-%m-%d')

                id_start = int(get_reference_id("start_p", "name_start", str(row["Номер запуска"])))
                id_pr = int(get_reference_id("pr", "name_pr", str(row["Производитель"])))
                id_tech = int(get_reference_id("tech", "name_tech", str(row["Технологический процесс"])))
                id_lot = int(get_reference_id("lot", "name_lot", str(row["Партия (Lot ID)"])))
                id_wafer = int(get_reference_id("wafer", "name_wafer", str(row["Пластина (Wafer)"])))
                id_quad = int(get_reference_id("quad", "name_quad", str(row["Quadrant"])))
                id_in_lot = int(get_reference_id("in_lot", "in_lot", str(row["Внутренняя партия"])))
                id_n_chip = int(get_reference_id("n_chip", "n_chip", str(row["Шифр кристалла"])))

                id_chip_val = row.get('Номер кристалла')
                id_size_val = row.get('Размер кристалла')
                id_pack_val = row.get('Упаковка')

                id_chip = int(get_reference_id("chip", "name_chip", str(id_chip_val))) if id_chip_val and pd.notna(
                    id_chip_val) else None
                id_size = int(get_reference_id("size_c", "size", str(id_size_val))) if id_size_val and pd.notna(
                    id_size_val) else None
                id_pack = int(get_reference_id("pack", "name_pack", str(id_pack_val))) if id_pack_val and pd.notna(
                    id_pack_val) else None

                quan_w = int(row['Возврат Wafer, шт.'])
                quan_gp = int(row['Возврат GelPack, шт.'])
                note_to_db = str(row.get('Примечание', '')).strip() or None

                stor_val = str(row.get('Место хранения', ''))
                cells_val = str(row.get("Ячейка хранения", ''))
                id_stor = int(get_reference_id("stor", "name_stor", stor_val)) if stor_val else None

                # --- ИЗМЕНЕНИЕ ЗДЕСЬ: используем id_cells ---
                id_cells = int(get_reference_id("cells", "name_cells", cells_val)) if cells_val else None

                # --- ИЗМЕНЕНИЕ ЗДЕСЬ: передаем id_cells ---
                all_data_to_insert.append((
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    id_chip, id_size, id_pack, id_stor, id_cells,
                    formatted_date, quan_w, quan_gp, note_to_db,
                    status_возврат, user_id, file_name
                ))

            except (KeyError, ValueError) as e_row:
                _flask_app.logger.error(f"Refund - Error processing row {idx + 2}: {e_row}", exc_info=True)
                return jsonify({"success": False, "message": f"Ошибка в строке {idx + 2}: {e_row}"}), 400

        if not all_data_to_insert:
            return jsonify({"success": False, "message": "Нет корректных данных для импорта в файле возврата."}), 400

        # --- ИЗМЕНЕНИЕ ЗДЕСЬ: в SQL запросе id_cells ---
        query_refund_insert = """
            INSERT INTO invoice (
                id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                id_chip, id_size, id_pack, id_stor, id_cells, 
                date, quan_w, quan_gp, note, 
                status, user_entry_id, file_name_entry, date_time_entry
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                NOW()
            );
        """

        conn_refund_loop = get_db_connection()
        try:
            with conn_refund_loop.cursor() as cur:
                for record in all_data_to_insert:
                    cur.execute(query_refund_insert, record)
            conn_refund_loop.commit()

            log_user_action(
                user_id=user_id,
                action_type='Загрузка файла: Возврат',
                file_name=file_name,
                target_table='invoice'
            )
            return jsonify({"success": True,
                            "message": f"Данные возврата из файла '{file_name}' успешно загружены ({len(all_data_to_insert)} строк)."}), 200

        except psycopg2.Error as db_err:
            if conn_refund_loop: conn_refund_loop.rollback()
            _flask_app.logger.error(f"Refund - psycopg2.Error: {db_err}", exc_info=True)
            return jsonify({"success": False, "message": f"Ошибка базы данных при возврате: {str(db_err)}"}), 500
        except Exception as e:
            if conn_refund_loop: conn_refund_loop.rollback()
            _flask_app.logger.error(f"Refund - Unexpected Error: {e}", exc_info=True)
            return jsonify({"success": False, "message": f"Произошла непредвиденная ошибка на сервере: {str(e)}"}), 500
        finally:
            if conn_refund_loop:
                conn_refund_loop.close()

    except Exception as e_outer:
        _flask_app.logger.error(f"Refund - Outer Exception: {e_outer}", exc_info=True)
        return jsonify(
            {"success": False, "message": f"Произошла непредвиденная ошибка на сервере: {str(e_outer)}"}), 500


@_flask_app.route('/search', methods=['GET', 'POST'])
def search():
    manufacturers = []
    try:
        manufacturers_query = "SELECT DISTINCT name_pr FROM pr ORDER BY name_pr"
        manufacturers_raw = execute_query(manufacturers_query)
        if manufacturers_raw:
            manufacturers = [row[0] for row in manufacturers_raw]
    except Exception as e:
        flash(f"Ошибка загрузки списка производителей: {e}", "danger")
        _flask_app.logger.error(f"Ошибка загрузки списка производителей: {e}")

    results = []
    chip_name_form = ''
    manufacturer_filter_form = 'all'

    if request.method == 'POST':
        if 'user_id' not in session:
            flash("Пожалуйста, войдите в систему для выполнения поиска.", "warning")
            return redirect(url_for('login', next=request.url))

        chip_name_form = request.form.get('chip_name', '').strip()
        manufacturer_filter_form = request.form.get('manufacturer', 'all')

        query_search = """
        WITH 
        invoice_sum_by_item_note AS (
            SELECT
                item_id, note, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                MAX(id_stor) AS latest_id_stor, MAX(id_cells) AS latest_id_cells,
                SUM(quan_w) as total_received_w, SUM(quan_gp) as total_received_gp
            FROM invoice
            GROUP BY item_id, note, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
        ),
        consumption_sum_by_item_note AS (
            SELECT
                item_id, note, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                SUM(cons_w) as total_consumed_w, SUM(cons_gp) as total_consumed_gp
            FROM consumption -- ПРЕДПОЛАГАЕТСЯ, ЧТО ЗДЕСЬ ЕСТЬ NOTE И ВСЕ ID_*
            GROUP BY item_id, note, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
        )
        SELECT 
            COALESCE(inv.item_id, cons.item_id) AS display_item_id,         -- 0
            COALESCE(inv.id_start, cons.id_start) AS actual_id_start,     -- 1
            s.name_start,                                                 -- 2
            p.name_pr,                                                    -- 3
            t.name_tech,                                                  -- 4
            w.name_wafer,                                                 -- 5
            q.name_quad,                                                  -- 6
            l.name_lot,                                                   -- 7
            il.in_lot,                                                    -- 8
            nc.n_chip,                                                    -- 9
            (COALESCE(inv.total_received_w, 0) - COALESCE(cons.total_consumed_w, 0)) AS ostatok_w,     -- 10
            (COALESCE(inv.total_received_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) AS ostatok_gp,   -- 11
            COALESCE(inv.note, cons.note) AS display_note,                -- 12
            st.name_stor,                                                 -- 13
            c.name_cells,                                                 -- 14
            COALESCE(inv.id_pr, cons.id_pr) AS actual_id_pr,              -- 15
            COALESCE(inv.id_tech, cons.id_tech) AS actual_id_tech,        -- 16
            COALESCE(inv.id_lot, cons.id_lot) AS actual_id_lot,            -- 17
            COALESCE(inv.id_wafer, cons.id_wafer) AS actual_id_wafer,      -- 18
            COALESCE(inv.id_quad, cons.id_quad) AS actual_id_quad,        -- 19
            COALESCE(inv.id_in_lot, cons.id_in_lot) AS actual_id_in_lot,   -- 20
            COALESCE(inv.id_n_chip, cons.id_n_chip) AS actual_id_n_chip    -- 21
        FROM invoice_sum_by_item_note inv
        FULL OUTER JOIN consumption_sum_by_item_note cons 
            ON inv.item_id = cons.item_id 
            AND inv.note IS NOT DISTINCT FROM cons.note
            AND inv.id_start = cons.id_start AND inv.id_pr = cons.id_pr AND inv.id_tech = cons.id_tech 
            AND inv.id_lot = cons.id_lot AND inv.id_wafer = cons.id_wafer AND inv.id_quad = cons.id_quad
            AND inv.id_in_lot = cons.id_in_lot AND inv.id_n_chip = cons.id_n_chip
        LEFT JOIN start_p s ON s.id = COALESCE(inv.id_start, cons.id_start)
        LEFT JOIN pr p ON p.id = COALESCE(inv.id_pr, cons.id_pr)
        LEFT JOIN tech t ON t.id = COALESCE(inv.id_tech, cons.id_tech)
        LEFT JOIN wafer w ON w.id = COALESCE(inv.id_wafer, cons.id_wafer)
        LEFT JOIN quad q ON q.id = COALESCE(inv.id_quad, cons.id_quad)
        LEFT JOIN lot l ON l.id = COALESCE(inv.id_lot, cons.id_lot)
        LEFT JOIN in_lot il ON il.id = COALESCE(inv.id_in_lot, cons.id_in_lot)
        LEFT JOIN n_chip nc ON nc.id = COALESCE(inv.id_n_chip, cons.id_n_chip)
        LEFT JOIN stor st ON st.id = inv.latest_id_stor
        LEFT JOIN cells c ON c.id = inv.latest_id_cells
        WHERE 
            ( (COALESCE(inv.total_received_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) != 0 OR
              (COALESCE(inv.total_received_w, 0) - COALESCE(cons.total_consumed_w, 0)) != 0 OR
              COALESCE(inv.total_received_gp, 0) != 0 OR COALESCE(inv.total_received_w, 0) != 0 OR
              COALESCE(cons.total_consumed_gp, 0) != 0 OR COALESCE(cons.total_consumed_w, 0) != 0 )
        """
        params_search = []
        filter_conditions = []
        if chip_name_form:
            filter_conditions.append("nc.n_chip ILIKE %s")
            params_search.append(f"%{chip_name_form}%")
        if manufacturer_filter_form and manufacturer_filter_form != "all":
            filter_conditions.append("p.name_pr = %s")
            params_search.append(manufacturer_filter_form)

        if filter_conditions:
            query_search += " AND " + " AND ".join(filter_conditions)
        query_search += " ORDER BY display_item_id, display_note;"

        try:
            results = execute_query(query_search, tuple(params_search))
            if not results:
                flash("По вашему запросу ничего не найдено.", "info")
        except Exception as e:
            flash(f"Ошибка при выполнении поиска: {e}", "danger")
            _flask_app.logger.error(f"Ошибка поиска: {e}", exc_info=True)
            results = []

    return render_template('search.html',
                           results=results,
                           manufacturers=manufacturers,
                           chip_name=chip_name_form,
                           manufacturer_filter=manufacturer_filter_form
                           )


@_flask_app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Пользователь не авторизован'}), 401

    user_id = session['user_id']
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Нет данных'}), 400

    item_id = data.get('item_id')
    quantity_w = int(data.get('quantity_w', 0))
    quantity_gp = int(data.get('quantity_gp', 0))

    # ... (получение всех имен: start_name, manufacturer_name и т.д. из data) ...
    start_name = data.get('launch')
    manufacturer_name = data.get('manufacturer')
    # ... и так далее

    if not item_id or (quantity_w <= 0 and quantity_gp <= 0):
        return jsonify({'success': False, 'message': 'Некорректные данные для добавления (ID или количество)'}), 400

    try:
        # --- НОВЫЙ БЛОК: Получаем id_chip и id_pack из invoice по item_id ---
        id_chip_val = None
        id_pack_val = None
        if item_id:
            # item_id из поиска - это id из таблицы invoice
            invoice_data = execute_query("SELECT id_chip, id_pack FROM invoice WHERE item_id = %s LIMIT 1", (item_id,), fetch=True)
            if invoice_data:
                id_chip_val = invoice_data[0][0]
                id_pack_val = invoice_data[0][1]
        # --- КОНЕЦ НОВОГО БЛОКА ---

        date_added = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Обновляем запрос на вставку в корзину
        query_insert_cart = """
            INSERT INTO cart (
                user_id, item_id, 
                cons_w, cons_gp, 
                start, manufacturer, technology, lot, wafer, quadrant, internal_lot, chip_code, 
                note, stor, cells, 
                id_chip, id_pack, -- <--- НОВЫЕ ПОЛЯ
                date_added
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, item_id) 
            DO UPDATE SET 
                cons_w = cart.cons_w + EXCLUDED.cons_w,
                cons_gp = cart.cons_gp + EXCLUDED.cons_gp,
                date_added = EXCLUDED.date_added; 
        """
        params_cart = (
            user_id, item_id,
            quantity_w, quantity_gp,
            data.get('launch'), data.get('manufacturer'), data.get('technology'), data.get('lot'),
            data.get('wafer'), data.get('quadrant'), data.get('internal_lot'), data.get('chip_code'),
            data.get('note'), data.get('stor'), data.get('cells'),
            id_chip_val, id_pack_val,  # <--- НОВЫЕ ПАРАМЕТРЫ
            date_added
        )

        execute_query(query_insert_cart, params_cart, fetch=False)
        return jsonify({'success': True, 'message': 'Товар добавлен/обновлен в корзине'})
    except Exception as e:
        _flask_app.logger.error(f"Ошибка добавления в корзину: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Ошибка сервера: {e}'}), 500


@_flask_app.route('/cart', methods=['GET'])
def cart_view():  # Переименовал, чтобы не конфликтовать с импортом, если он будет
    if 'user_id' not in session:
        flash("Пожалуйста, войдите, чтобы просмотреть корзину.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    # Запрос для отображения корзины. Имена столбцов должны соответствовать вашей таблице cart.
    query_get_cart = """
    SELECT 
        item_id, user_id,
        start, manufacturer, technology, wafer, quadrant, lot, internal_lot, chip_code,
        note, stor, cells, date_added, cons_w, cons_gp
    FROM cart
    WHERE user_id = %s
    ORDER BY date_added DESC
    """
    try:
        cart_items = execute_query(query_get_cart, (user_id,))
    except Exception as e:
        _flask_app.logger.error(f"Ошибка загрузки корзины: {e}")
        flash("Не удалось загрузить корзину.", "danger")
        cart_items = []

    return render_template('cart.html', results=cart_items if cart_items else [])


@_flask_app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Пользователь не авторизован'}), 401

    user_id = session['user_id']
    data = request.get_json()
    item_id = data.get('item_id')  # ID товара (row[0] из search.html)

    if not item_id:
        return jsonify({'success': False, 'message': 'Неверный ID товара'}), 400

    query_delete_cart = "DELETE FROM cart WHERE item_id = %s AND user_id = %s"
    try:
        rows_deleted = execute_query(query_delete_cart, (item_id, user_id), fetch=False)
        if rows_deleted > 0:
            return jsonify({'success': True, 'message': 'Товар удален'})
        else:
            return jsonify({'success': False, 'message': 'Товар не найден в корзине'})
    except Exception as e:
        _flask_app.logger.error(f"Ошибка удаления из корзины: {e}")
        return jsonify({'success': False, 'message': f'Ошибка сервера: {e}'}), 500


@_flask_app.route('/update_cart_item', methods=['POST'])
def update_cart_item():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Пользователь не авторизован'}), 401

    user_id = session['user_id']
    data = request.get_json()
    # В вашем HTML было data-id="{{ row[0] }}", что соответствует item_id
    item_id = data.get('id')  # Или 'item_id', если вы так передаете из JS
    cons_w_str = data.get('cons_w')
    cons_gp_str = data.get('cons_gp')

    if not item_id or cons_w_str is None or cons_gp_str is None:
        return jsonify({"success": False, "message": "Неполные данные"}), 400

    try:
        cons_w = int(cons_w_str)
        cons_gp = int(cons_gp_str)
        if cons_w < 0 or cons_gp < 0:
            return jsonify({"success": False, "message": "Количество не может быть отрицательным"}), 400

        # Проверка на максимальное количество перед обновлением (аналогично add_to_cart) - здесь опущено для краткости

        if cons_w == 0 and cons_gp == 0:
            query_delete = "DELETE FROM cart WHERE item_id = %s AND user_id = %s"
            execute_query(query_delete, (item_id, user_id), fetch=False)
            return jsonify({"success": True, "removed": True, "message": "Товар удален (количество 0)"})
        else:
            query_update = "UPDATE cart SET cons_w = %s, cons_gp = %s WHERE item_id = %s AND user_id = %s"
            rows_updated = execute_query(query_update, (cons_w, cons_gp, item_id, user_id), fetch=False)
            if rows_updated > 0:
                return jsonify({"success": True, "message": "Количество обновлено"})
            else:
                # Это может случиться, если товар был удален в другой вкладке
                return jsonify({"success": False, "message": "Товар не найден для обновления"})
    except ValueError:  # Ошибка при int()
        return jsonify({"success": False, "message": "Неверный формат количества"}), 400
    except Exception as e:
        _flask_app.logger.error(f"Ошибка обновления корзины: {e}")
        return jsonify({"success": False, "message": f'Ошибка сервера: {e}'}), 500


# Убедитесь, что этот импорт есть в самом верху вашего app.py
from urllib.parse import quote


@_flask_app.route('/export_cart', methods=['GET'])
def export_cart():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите, чтобы экспортировать корзину.", "warning")
        return redirect(url_for('login'))

    user_id = session['user_id']
    # --- ИЗМЕНЕНИЕ: Добавляем выборку stor и cells ---
    query_export = """
    SELECT 
        c.start AS "Номер запуска",
        c.manufacturer AS "Производитель",
        c.technology AS "Технологический процесс",
        c.lot AS "Партия (Lot ID)",
        c.wafer AS "Пластина (Wafer)",
        c.quadrant AS "Quadrant",
        c.internal_lot AS "Внутренняя партия",
        chip.name_chip AS "Номер кристалла",
        c.chip_code AS "Шифр кристалла",
        pack.name_pack AS "Упаковка",
        c.stor AS "Место хранения",          -- <--- ДОБАВЛЕНО
        c.cells AS "Ячейка хранения",        -- <--- ДОБАВЛЕНО
        c.note AS "Примечание",
        TO_CHAR(c.date_added, 'YYYY-MM-DD') AS "Дата расхода",
        c.cons_w AS "Расход Wafer, шт.",
        c.cons_gp AS "Расход GelPack, шт."
    FROM cart c
    LEFT JOIN chip ON c.id_chip = chip.id
    LEFT JOIN pack ON c.id_pack = pack.id
    WHERE c.user_id = %s
    ORDER BY c.date_added DESC
    """
    try:
        results = execute_query(query_export, (user_id,))
    except Exception as e:
        _flask_app.logger.error(f"Ошибка при экспорте корзины (SQL): {e}")
        flash("Не удалось подготовить данные для экспорта.", "danger")
        return redirect(url_for('cart_view'))

    if not results:
        flash("Корзина пуста. Нет данных для экспорта.", "info")
        return redirect(url_for('cart_view'))

    # --- ИЗМЕНЕНИЕ: Добавляем названия колонок в список ---
    filled_columns = [
        "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)", "Пластина (Wafer)",
        "Quadrant", "Внутренняя партия", "Номер кристалла", "Шифр кристалла", "Упаковка",
        "Место хранения", "Ячейка хранения", "Примечание",  # <--- ДОБАВЛЕНЫ
        "Дата расхода", "Расход Wafer, шт.", "Расход GelPack, шт."
    ]
    df_from_db = pd.DataFrame(results, columns=filled_columns)

    # Список для финального Excel файла уже содержит "Место хранения" и "Ячейка хранения", так что его менять не надо.
    final_excel_columns = [
        "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)", "Пластина (Wafer)",
        "Quadrant", "Внутренняя партия", "Номер кристалла", "Шифр кристалла", "Упаковка",
        "Дата расхода", "Расход Wafer, шт.", "Расход GelPack, шт.", "Расход общий, шт.",
        "Дата возврата", "Возврат Wafer, шт.", "Возврат GelPack, шт.", "Возврат общий, шт.",
        "Примечание", "Куда передано (Производственная партия)", "ФИО",
        "Место хранения", "Ячейка хранения"
    ]

    df_export = pd.DataFrame(columns=final_excel_columns)

    # Копируем данные из df_from_db в df_export.
    for col in df_from_db.columns:
        if col in df_export.columns:
            df_export[col] = df_from_db[col]

    # Вычисляем "Расход общий, шт."
    df_export["Расход общий, шт."] = df_export["Расход Wafer, шт."].fillna(0) + df_export["Расход GelPack, шт."].fillna(
        0)

    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Расход")
        output.seek(0)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base_filename = f'Расход_из_корзины_{timestamp}.xlsx'
        ascii_filename = f'cart_export_{timestamp}.xlsx'
        disposition = f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(base_filename, safe='')}"

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = disposition

        log_user_action(
            user_id=session.get('user_id'),
            action_type='Экспорт корзины',
            file_name=base_filename,
            target_table='cart_export'
        )
        return response

    except Exception as e:
        _flask_app.logger.error(f"Ошибка при создании Excel файла для экспорта: {e}")
        flash("Не удалось создать файл для экспорта.", "danger")
        return redirect(url_for('cart_view'))

# Регистрация пользователя
@_flask_app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        u_password = request.form.get('password')

        if not username or not u_password:
            flash("Имя пользователя и пароль не могут быть пустыми.", "danger")
            return render_template('register.html')

        # Хешируем пароль перед сохранением в БД
        hashed_password = generate_password_hash(u_password)

        try:
            # Проверка, существует ли пользователь
            existing_user = execute_query("SELECT id FROM users WHERE username = %s", (username,))
            if existing_user:
                flash("Пользователь с таким именем уже существует.", "warning")
                return render_template('register.html')

            # Сохраняем хешированный пароль
            query_register = "INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id"
            params_register = (username, hashed_password)

            new_user_id_tuple = execute_query(query_register, params_register, fetch=True)  # fetch=True из-за RETURNING

            if new_user_id_tuple and new_user_id_tuple[0]:
                new_user_id = new_user_id_tuple[0][0]
                session['user_id'] = new_user_id
                session['username'] = username
                flash("Регистрация прошла успешно!", "success")
                return redirect(url_for('home'))
            else:
                flash("Не удалось создать пользователя.", "danger")
        except psycopg2.IntegrityError:  # Если есть UNIQUE constraint на username
            flash("Пользователь с таким именем уже существует.", "warning")
        except Exception as e:
            _flask_app.logger.error(f"Ошибка при регистрации: {e}", exc_info=True)
            flash(f"Ошибка при регистрации: {e}", "danger")
        return render_template('register.html')  # Возвращаемся на форму при ошибке

    return render_template('register.html')


@_flask_app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        u_password = request.form.get('password')

        if not username or not u_password:
            flash("Введите имя пользователя и пароль.", "warning")
            return render_template('login.html')

        # Проверяем хешированные пароли
        query_login = "SELECT id, username, password FROM users WHERE username = %s"

        try:
            user_data_list = execute_query(query_login, (username,))  # execute_query возвращает список
            if user_data_list:
                user_data = user_data_list[0]  # Берем первый элемент списка (кортеж)
                user_db_password_hash = user_data[2]  # Это хеш пароля из БД
                if check_password_hash(user_db_password_hash, u_password):
                    session['user_id'] = user_data[0]  # id
                    session['username'] = user_data[1]  # username
                    flash(f"Добро пожаловать, {session['username']}!", "success")

                    next_url = request.args.get('next')
                    if next_url and next_url.startswith('/'):  # Проверка безопасности next_url
                        return redirect(next_url)
                    return redirect(url_for('home'))
                else:
                    flash("Неправильный пароль.", "danger")
            else:
                flash("Пользователь с таким именем не найден.", "danger")
        except Exception as e:
            _flask_app.logger.error(f"Ошибка при входе: {e}", exc_info=True)
            flash(f"Произошла ошибка на сервере.", "danger")

        return render_template('login.html')  # При ошибке или неверных данных

    return render_template('login.html')


@_flask_app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash("Вы успешно вышли из системы.", "info")
    return redirect(url_for('home'))


@_flask_app.route('/clear_cart', methods=['POST'])  # Должен быть POST
def clear_cart():
    if 'user_id' not in session:
        flash("Необходимо войти в систему.", "warning")
        # Вместо jsonify можно просто редиректить или возвращать ошибку
        return redirect(url_for('login'))

    user_id = session['user_id']
    try:
        query_clear = "DELETE FROM cart WHERE user_id = %s"
        execute_query(query_clear, (user_id,), fetch=False)
        flash("Корзина очищена.", "success")
    except Exception as e:
        _flask_app.logger.error(f"Ошибка очистки корзины: {e}")
        flash("Не удалось очистить корзину.", "danger")
    return redirect(url_for('cart_view'))  # Перенаправляем на страницу корзины


@_flask_app.route('/inventory', methods=['GET', 'POST'])
def inventory():
    # --- НАЧАЛО ДИАГНОСТИЧЕСКОГО ЛОГИРОВАНИЯ ---
    _flask_app.logger.info("--- Entering /inventory route ---")
    _flask_app.logger.info(f"Request method: {request.method}")
    if request.method == 'POST':
        _flask_app.logger.info(f"Form data: {request.form.to_dict()}")
    else:
        _flask_app.logger.info(f"Query args: {request.args.to_dict()}")
    # --- КОНЕЦ ДИАГНОСТИЧЕСКОГО ЛОГИРОВАНИЯ ---

    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему для доступа к инвентаризации.", "warning")
        _flask_app.logger.warning("User not in session for /inventory, redirecting to login.")
        return redirect(url_for('login', next=request.url))

    manufacturers, lots = [], []
    try:
        manufacturers_raw = execute_query("SELECT DISTINCT name_pr FROM pr ORDER BY name_pr")
        manufacturers = [row[0] for row in manufacturers_raw] if manufacturers_raw else []

        lots_raw = execute_query("SELECT DISTINCT name_lot FROM lot ORDER BY name_lot")
        lots = [row[0] for row in lots_raw] if lots_raw else []
    except Exception as e:
        _flask_app.logger.error(f"Ошибка загрузки фильтров для инвентаризации: {e}", exc_info=True)
        flash("Не удалось загрузить фильтры.", "danger")

    results = []
    action = None

    if request.method == 'POST':
        selected_manufacturer_form = request.form.get('manufacturer', '')
        selected_lot_id_form = request.form.get('lot_id', '')
        selected_chip_code_filter_form = request.form.get('chip_code_filter', '').strip()
        action = request.form.get('action')
    else:  # GET
        selected_manufacturer_form = request.args.get('manufacturer', '')
        selected_lot_id_form = request.args.get('lot_id', '')
        selected_chip_code_filter_form = request.args.get('chip_code_filter', '').strip()
        action = request.args.get('action')

    _flask_app.logger.info(f"Values before perform_search_or_export check:")
    _flask_app.logger.info(f"  action = '{action}' (type: {type(action)})")
    _flask_app.logger.info(f"  selected_manufacturer_form = '{selected_manufacturer_form}'")
    _flask_app.logger.info(f"  selected_lot_id_form = '{selected_lot_id_form}'")
    _flask_app.logger.info(f"  selected_chip_code_filter_form = '{selected_chip_code_filter_form}'")

    perform_search_or_export = False
    if request.method == 'POST' and action in ['search', 'export', 'export_raw']:
        _flask_app.logger.info(f"Condition met: POST request and action is '{action}'.")
        perform_search_or_export = True

    _flask_app.logger.info(f"Final value of perform_search_or_export: {perform_search_or_export}")

    if perform_search_or_export:
        _flask_app.logger.info(f"--- Condition perform_search_or_export is TRUE, action: {action} ---")

        params_sql_filter = []
        conditions_sql_filter_list_template = []

        current_selected_manufacturer = selected_manufacturer_form if selected_manufacturer_form and selected_manufacturer_form.lower() != 'all' else ''
        current_selected_lot = selected_lot_id_form if selected_lot_id_form and selected_lot_id_form.lower() != 'all' else ''

        if current_selected_manufacturer:
            conditions_sql_filter_list_template.append("pr_alias.name_pr = %s")
            params_sql_filter.append(current_selected_manufacturer)
        if current_selected_lot:
            conditions_sql_filter_list_template.append("l_alias.name_lot = %s")
            params_sql_filter.append(current_selected_lot)
        if selected_chip_code_filter_form:
            conditions_sql_filter_list_template.append("nc_alias.n_chip ILIKE %s")
            params_sql_filter.append(f"%{selected_chip_code_filter_form}%")

        where_clause_template = ""
        if conditions_sql_filter_list_template:
            where_clause_template = " AND " + " AND ".join(conditions_sql_filter_list_template)

        if action == 'search' or action == 'export':
            where_clause_summary = where_clause_template.replace('pr_alias.', 'pr.').replace('l_alias.', 'l.').replace(
                'nc_alias.', 'nc.')

            sql_query_inventory = f"""
            WITH
            income_agg AS (
                SELECT
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    SUM(quan_w) as total_income_w,
                    SUM(quan_gp) as total_income_gp,
                    SUM(COALESCE(quan_all, quan_w + quan_gp)) as total_income_all 
                FROM invoice
                WHERE status = 1 -- Используем status, ID для 'Приход'
                GROUP BY id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
            ),
            return_agg AS (
                SELECT
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    SUM(quan_w) as total_return_w,
                    SUM(quan_gp) as total_return_gp,
                    SUM(COALESCE(quan_all, quan_w + quan_gp)) as total_return_all
                FROM invoice
                WHERE status = 3 -- Используем status, ID для 'Возврат'
                GROUP BY id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
            ),
            consumption_agg AS (
                SELECT
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    SUM(cons_w) as total_consumed_w,
                    SUM(cons_gp) as total_consumed_gp,
                    SUM(COALESCE(cons_all, cons_w + cons_gp)) as total_consumed_all
                FROM consumption
                WHERE status = 2 -- Используем status, ID для 'Расход'
                GROUP BY id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
            ),
            latest_attributes AS ( 
                SELECT DISTINCT ON (inv_la.id_start, inv_la.id_pr, inv_la.id_tech, inv_la.id_lot, inv_la.id_wafer, inv_la.id_quad, inv_la.id_in_lot, inv_la.id_n_chip)
                    inv_la.id_start, inv_la.id_pr, inv_la.id_tech, inv_la.id_lot, inv_la.id_wafer, inv_la.id_quad, inv_la.id_in_lot, inv_la.id_n_chip,
                    inv_la.note, inv_la.id_pack, inv_la.id_stor, inv_la.id_cells, inv_la.date
                FROM invoice inv_la
                WHERE inv_la.status = 1 -- Берем атрибуты только из записей ПРИХОДА
                ORDER BY inv_la.id_start, inv_la.id_pr, inv_la.id_tech, inv_la.id_lot, inv_la.id_wafer, inv_la.id_quad, inv_la.id_in_lot, inv_la.id_n_chip, inv_la.date DESC, inv_la.id DESC
            ),
            all_unique_keys_source AS (
                SELECT id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip FROM invoice
                UNION 
                SELECT id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip FROM consumption
            )
            SELECT
                COALESCE(sp.name_start, 'N/A') AS "Номер_запуска",        
                COALESCE(pr.name_pr, 'N/A') AS "Производитель",           
                COALESCE(t.name_tech, 'N/A') AS "Технологический_процесс", 
                COALESCE(l.name_lot, 'N/A') AS "Партия_Lot_ID",           
                COALESCE(w.name_wafer, 'N/A') AS "Пластина_Wafer",        
                COALESCE(q.name_quad, 'N/A') AS "Quadrant",                
                COALESCE(il.in_lot, 'N/A') AS "Внутренняя_партия",       
                COALESCE(nc.n_chip, 'N/A') AS "Шифр_кристалла",          
                COALESCE(ia.total_income_w, 0) AS "Приход_Wafer_шт",       
                COALESCE(ia.total_income_gp, 0) AS "Приход_GelPak_шт",      
                COALESCE(ia.total_income_all, 0) AS "Приход_общий_шт",     
                COALESCE(ca.total_consumed_w, 0) AS "Расход_Wafer_шт",     
                COALESCE(ca.total_consumed_gp, 0) AS "Расход_GelPak_шт",    
                COALESCE(ca.total_consumed_all, 0) AS "Расход_общий_шт",   
                COALESCE(ra.total_return_w, 0) AS "Возврат_Wafer_шт",      
                COALESCE(ra.total_return_gp, 0) AS "Возврат_GelPak_шт",     
                COALESCE(ra.total_return_all, 0) AS "Возврат_общий_шт",    
                (COALESCE(ia.total_income_all, 0) + COALESCE(ra.total_return_all, 0) - COALESCE(ca.total_consumed_all, 0)) AS "Остаток_шт", 
                COALESCE(pk.name_pack, 'N/A') AS "Упаковка",                                
                COALESCE(st.name_stor, 'N/A') AS "Место_хранения",                          
                COALESCE(ce.name_cells, 'N/A') AS "Ячейка_хранения"                         
            FROM all_unique_keys_source all_keys
            LEFT JOIN income_agg ia ON ia.id_start = all_keys.id_start AND ia.id_pr = all_keys.id_pr AND ia.id_tech = all_keys.id_tech AND ia.id_lot = all_keys.id_lot AND ia.id_wafer = all_keys.id_wafer AND ia.id_quad = all_keys.id_quad AND ia.id_in_lot = all_keys.id_in_lot AND ia.id_n_chip = all_keys.id_n_chip
            LEFT JOIN return_agg ra ON ra.id_start = all_keys.id_start AND ra.id_pr = all_keys.id_pr AND ra.id_tech = all_keys.id_tech AND ra.id_lot = all_keys.id_lot AND ra.id_wafer = all_keys.id_wafer AND ra.id_quad = all_keys.id_quad AND ra.id_in_lot = all_keys.id_in_lot AND ra.id_n_chip = all_keys.id_n_chip
            LEFT JOIN consumption_agg ca ON ca.id_start = all_keys.id_start AND ca.id_pr = all_keys.id_pr AND ca.id_tech = all_keys.id_tech AND ca.id_lot = all_keys.id_lot AND ca.id_wafer = all_keys.id_wafer AND ca.id_quad = all_keys.id_quad AND ca.id_in_lot = all_keys.id_in_lot AND ca.id_n_chip = all_keys.id_n_chip
            LEFT JOIN latest_attributes la ON la.id_start = all_keys.id_start AND la.id_pr = all_keys.id_pr AND la.id_tech = all_keys.id_tech AND la.id_lot = all_keys.id_lot AND la.id_wafer = all_keys.id_wafer AND la.id_quad = all_keys.id_quad AND la.id_in_lot = all_keys.id_in_lot AND la.id_n_chip = all_keys.id_n_chip
            LEFT JOIN start_p sp ON all_keys.id_start = sp.id
            LEFT JOIN pr pr ON all_keys.id_pr = pr.id 
            LEFT JOIN tech t ON all_keys.id_tech = t.id
            LEFT JOIN lot l ON all_keys.id_lot = l.id 
            LEFT JOIN wafer w ON all_keys.id_wafer = w.id
            LEFT JOIN quad q ON all_keys.id_quad = q.id
            LEFT JOIN in_lot il ON all_keys.id_in_lot = il.id
            LEFT JOIN n_chip nc ON all_keys.id_n_chip = nc.id 
            LEFT JOIN pack pk ON la.id_pack = pk.id
            LEFT JOIN stor st ON la.id_stor = st.id
            LEFT JOIN cells ce ON la.id_cells = ce.id
            WHERE (COALESCE(ia.total_income_all, 0) + COALESCE(ra.total_return_all, 0) - COALESCE(ca.total_consumed_all, 0)) <> 0
            {where_clause_summary}
            ORDER BY COALESCE(sp.name_start, 'N/A'), COALESCE(pr.name_pr, 'N/A'), COALESCE(l.name_lot, 'N/A'), COALESCE(nc.n_chip, 'N/A');
            """
            _flask_app.logger.info(f"Inventory Action (Summary): {action}")
            _flask_app.logger.info(
                f"SQL Query for Inventory Summary (first 300 chars):\n{sql_query_inventory[:300]}...")
            _flask_app.logger.info(f"SQL Parameters for Inventory Summary: {tuple(params_sql_filter)}")

            conn_debug_mogrify_inv_s = None
            try:
                conn_debug_mogrify_inv_s = get_db_connection()
                with conn_debug_mogrify_inv_s.cursor() as cur_debug_mogrify_inv_s:
                    mogrified_query_inv_s = cur_debug_mogrify_inv_s.mogrify(sql_query_inventory,
                                                                            tuple(params_sql_filter))
                    _flask_app.logger.info(
                        f"Mogrified SQL Query for Inventory Summary:\n{mogrified_query_inv_s.decode('utf-8', errors='replace')}")
            except Exception as e_debug_mogrify_inv_s:
                _flask_app.logger.error(f"Error mogrifying inventory summary query: {e_debug_mogrify_inv_s}",
                                        exc_info=True)
            finally:
                if conn_debug_mogrify_inv_s:
                    conn_debug_mogrify_inv_s.close()

            try:
                results = execute_query(sql_query_inventory, tuple(params_sql_filter))
                if not results and action == 'search':
                    flash("По вашему запросу для инвентаризации ничего не найдено.", "info")
            except Exception as e:
                _flask_app.logger.error(f"Ошибка выполнения запроса инвентаризации (сводка): {e}", exc_info=True)
                flash(f"Ошибка при выполнении запроса инвентаризации (сводка): {e}", "danger")
                results = []

            if action == 'export' and results:
                _flask_app.logger.info("Preparing 'Инвентаризация' Excel export...")
                excel_friendly_columns_summary = [
                    "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)",
                    "Пластина (Wafer)", "Quadrant", "Внутренняя партия", "Шифр кристалла",
                    "Приход Wafer, шт.", "Приход GelPak, шт.", "Приход общий, шт.",
                    "Расход Wafer, шт.", "Расход GelPak, шт.", "Расход общий, шт.",
                    "Возврат Wafer, шт.", "Возврат GelPak, шт.", "Возврат общий, шт.",
                    "Остаток, шт",
                    "Упаковка", "Место хранения", "Ячейка хранения"
                ]

                df = pd.DataFrame(results, columns=excel_friendly_columns_summary)

                output = BytesIO()
                try:
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Инвентаризация')
                    output.seek(0)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f'inventory_export_{timestamp}.xlsx'
                    log_user_action(
                        user_id=session.get('user_id'),
                        action_type="Экспорт инвентаризации (сводка)",
                        file_name=filename,
                        details=(
                            f"Фильтры: Производитель='{selected_manufacturer_form}', "
                            f"Партия='{selected_lot_id_form}', "
                            f"Шифр='{selected_chip_code_filter_form}'"
                        )
                    )
                    return send_file(output, as_attachment=True, download_name=filename,
                                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                except Exception as e_export_inv_file:
                    _flask_app.logger.error(
                        f"Ошибка при создании Excel файла для экспорта инвентаризации: {e_export_inv_file}",
                        exc_info=True)
                    flash("Не удалось создать файл для экспорта инвентаризации.", "danger")

        elif action == 'export_raw':
            _flask_app.logger.info("--- Preparing RAW DATA EXPORT (Invoice + Consumption Stacked) ---")
            where_clause_raw_inv = where_clause_template.replace('pr_alias.', 'pr_inv.').replace('l_alias.',
                                                                                                 'l_inv.').replace(
                'nc_alias.', 'nc_inv.')
            where_clause_raw_cons = where_clause_template.replace('pr_alias.', 'pr_cons.').replace('l_alias.',
                                                                                                   'l_cons.').replace(
                'nc_alias.', 'nc_cons.')

            sql_query_raw_data = f"""
            SELECT 
                s_inv.name AS "Статус_операции", 
                TO_CHAR(inv.date, 'YYYY-MM-DD') AS "Дата",
                COALESCE(sp_inv.name_start, 'N/A') AS "Номер_запуска",
                COALESCE(pr_inv.name_pr, 'N/A') AS "Производитель",
                COALESCE(t_inv.name_tech, 'N/A') AS "Технологический_процесс",
                COALESCE(l_inv.name_lot, 'N/A') AS "Партия_Lot_ID",
                COALESCE(w_inv.name_wafer, 'N/A') AS "Пластина_Wafer",
                COALESCE(q_inv.name_quad, 'N/A') AS "Quadrant",
                COALESCE(il_inv.in_lot, 'N/A') AS "Внутренняя_партия",
                COALESCE(ch_inv.name_chip, 'N/A') AS "Номер_кристалла",
                COALESCE(nc_inv.n_chip, 'N/A') AS "Шифр_кристалла",
                inv.quan_w AS "Количество_Wafer_ПриходВозврат",
                inv.quan_gp AS "Количество_GelPak_ПриходВозврат",
                inv.quan_all AS "Количество_Общее_ПриходВозврат",
                inv.note AS "Примечание",
                pk_inv.name_pack AS "Упаковка",
                st_inv.name_stor AS "Место_хранения",
                ce_inv.name_cells AS "Ячейка_хранения",
                cs_inv.size AS "Размер_кристалла",
                NULL AS "Количество_Wafer_Расход",
                NULL AS "Количество_GelPak_Расход",
                NULL AS "Количество_Общее_Расход",
                NULL AS "Куда_передано", 
                NULL AS "ФИО_получателя"
            FROM invoice inv
            LEFT JOIN status s_inv ON inv.status = s_inv.id 
            LEFT JOIN start_p sp_inv ON inv.id_start = sp_inv.id
            LEFT JOIN pr pr_inv ON inv.id_pr = pr_inv.id
            LEFT JOIN tech t_inv ON inv.id_tech = t_inv.id
            LEFT JOIN lot l_inv ON inv.id_lot = l_inv.id
            LEFT JOIN wafer w_inv ON inv.id_wafer = w_inv.id
            LEFT JOIN quad q_inv ON inv.id_quad = q_inv.id
            LEFT JOIN in_lot il_inv ON inv.id_in_lot = il_inv.id
            LEFT JOIN chip ch_inv ON inv.id_chip = ch_inv.id
            LEFT JOIN n_chip nc_inv ON inv.id_n_chip = nc_inv.id
            LEFT JOIN pack pk_inv ON inv.id_pack = pk_inv.id
            LEFT JOIN stor st_inv ON inv.id_stor = st_inv.id
            LEFT JOIN cells ce_inv ON inv.id_cells = ce_inv.id
            LEFT JOIN size_c cs_inv ON inv.id_size = cs_inv.id
            WHERE 1=1 {where_clause_raw_inv} 

            UNION ALL

            SELECT 
                s_cons.name AS "Статус_операции", 
                TO_CHAR(cons.date, 'YYYY-MM-DD') AS "Дата",
                COALESCE(sp_cons.name_start, 'N/A') AS "Номер_запуска",
                COALESCE(pr_cons.name_pr, 'N/A') AS "Производитель",
                COALESCE(t_cons.name_tech, 'N/A') AS "Технологический_процесс",
                COALESCE(l_cons.name_lot, 'N/A') AS "Партия_Lot_ID",
                COALESCE(w_cons.name_wafer, 'N/A') AS "Пластина_Wafer",
                COALESCE(q_cons.name_quad, 'N/A') AS "Quadrant",
                COALESCE(il_cons.in_lot, 'N/A') AS "Внутренняя_партия",
                COALESCE(ch_cons.name_chip, 'N/A') AS "Номер_кристалла",
                COALESCE(nc_cons.n_chip, 'N/A') AS "Шифр_кристалла",
                NULL AS "Количество_Wafer_ПриходВозврат",
                NULL AS "Количество_GelPak_ПриходВозврат",
                NULL AS "Количество_Общее_ПриходВозврат",
                cons.note AS "Примечание", 
                pk_cons.name_pack AS "Упаковка", -- ИЗМЕНЕНО: Упаковка для consumption
                st_cons.name_stor AS "Место_хранения",
                ce_cons.name_cells AS "Ячейка_хранения",
                NULL AS "Размер_кристалла",
                cons.cons_w AS "Количество_Wafer_Расход",
                cons.cons_gp AS "Количество_GelPak_Расход",
                cons.cons_all AS "Количество_Общее_Расход",
                cons.transf_man AS "Куда_передано",
                cons.reciver AS "ФИО_получателя"
            FROM consumption cons
            LEFT JOIN chip ch_cons ON cons.id_chip = ch_cons.id
            LEFT JOIN status s_cons ON cons.status = s_cons.id 
            LEFT JOIN start_p sp_cons ON cons.id_start = sp_cons.id
            LEFT JOIN pr pr_cons ON cons.id_pr = pr_cons.id
            LEFT JOIN tech t_cons ON cons.id_tech = t_cons.id
            LEFT JOIN lot l_cons ON cons.id_lot = l_cons.id
            LEFT JOIN wafer w_cons ON cons.id_wafer = w_cons.id
            LEFT JOIN quad q_cons ON cons.id_quad = q_cons.id
            LEFT JOIN in_lot il_cons ON cons.id_in_lot = il_cons.id
            LEFT JOIN n_chip nc_cons ON cons.id_n_chip = nc_cons.id
            LEFT JOIN pack pk_cons ON cons.id_pack = pk_cons.id -- ИЗМЕНЕНО: JOIN для упаковки из consumption
            LEFT JOIN stor st_cons ON cons.id_stor = st_cons.id
            LEFT JOIN cells ce_cons ON cons.id_cells = ce_cons.id
            WHERE 1=1 {where_clause_raw_cons}
            ORDER BY "Дата" ASC, "Номер_запуска" ASC, "Шифр_кристалла" ASC;
            """
            _flask_app.logger.info(f"Inventory Action (Raw Data Export): {action}")
            _flask_app.logger.info(f"SQL Query for Raw Data (first 300 chars):\n{sql_query_raw_data[:300]}...")
            final_params_raw = tuple(params_sql_filter + params_sql_filter)
            _flask_app.logger.info(f"SQL Parameters for Raw Data: {final_params_raw}")

            conn_debug_mogrify_raw = None
            try:
                conn_debug_mogrify_raw = get_db_connection()
                with conn_debug_mogrify_raw.cursor() as cur_debug_mogrify_raw:
                    mogrified_query_raw = cur_debug_mogrify_raw.mogrify(sql_query_raw_data, final_params_raw)
                    _flask_app.logger.info(
                        f"Mogrified SQL Query for Raw Data:\n{mogrified_query_raw.decode('utf-8', errors='replace')}")
            except Exception as e_debug_mogrify_raw:
                _flask_app.logger.error(f"Error mogrifying raw data query: {e_debug_mogrify_raw}", exc_info=True)
            finally:
                if conn_debug_mogrify_raw:
                    conn_debug_mogrify_raw.close()

            raw_data_results = []
            try:
                raw_data_results = execute_query(sql_query_raw_data, final_params_raw)
                if not raw_data_results:
                    flash("По вашему запросу для сырых данных ничего не найдено.", "info")
            except Exception as e:
                _flask_app.logger.error(f"Ошибка выполнения запроса сырых данных: {e}", exc_info=True)
                flash(f"Ошибка при выполнении запроса сырых данных: {e}", "danger")

            if raw_data_results:
                # Имена колонок должны ТОЧНО совпадать с алиасами в SQL-запросе для сырых данных
                df_raw_columns_from_sql = [
                    "Статус_операции",
                    "Дата", "Номер_запуска", "Производитель",
                    "Технологический_процесс", "Партия_Lot_ID", "Пластина_Wafer", "Quadrant",
                    "Внутренняя_партия", "Номер_кристалла", "Шифр_кристалла",
                    "Количество_Wafer_ПриходВозврат", "Количество_GelPak_ПриходВозврат",
                    "Количество_Общее_ПриходВозврат",
                    "Примечание",
                    "Упаковка",  # Общая колонка
                    "Место_хранения", "Ячейка_хранения", "Размер_кристалла",
                    "Количество_Wafer_Расход", "Количество_GelPak_Расход", "Количество_Общее_Расход",
                    "Куда_передано", "ФИО_получателя"
                ]

                # Создаем DataFrame из списка кортежей, используя имена колонок
                df_raw = pd.DataFrame(raw_data_results, columns=df_raw_columns_from_sql)

                output_raw = BytesIO()
                try:
                    with pd.ExcelWriter(output_raw, engine='openpyxl') as writer:
                        df_raw.to_excel(writer, index=False, sheet_name='Сырые_данные_стек')
                    output_raw.seek(0)
                    timestamp_raw = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename_raw = f'inventory_stacked_raw_data_{timestamp_raw}.xlsx'
                    log_user_action(
                        user_id=session.get('user_id'),
                        action_type="Экспорт сырых данных (стек)",
                        file_name=filename_raw,
                        details=(
                            f"Фильтры: Производитель='{selected_manufacturer_form}', "
                            f"Партия='{selected_lot_id_form}', "
                            f"Шифр='{selected_chip_code_filter_form}'"
                        )
                    )
                    return send_file(output_raw, as_attachment=True, download_name=filename_raw,
                                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                except Exception as e_export_raw_file:
                    _flask_app.logger.error(
                        f"Ошибка при создании Excel файла для сырых данных (стек): {e_export_raw_file}", exc_info=True)
                    flash("Не удалось создать файл c сырыми данными для экспорта.", "danger")
            elif action == 'export_raw' and not raw_data_results:
                flash("Нет сырых данных для экспорта по вашему запросу.", "info")
    else:
        _flask_app.logger.info(
            "--- Condition perform_search_or_export is FALSE or action is not for data processing, SQL query logic was SKIPPED ---")

    return render_template('inventory.html',
                           manufacturers=manufacturers,
                           lots=lots,
                           results=results,
                           selected_manufacturer=selected_manufacturer_form,
                           selected_lot_id=selected_lot_id_form,
                           selected_chip_code_filter=selected_chip_code_filter_form
                           )


# Создаем ASGI-совместимое приложение для Uvicorn.
app = WSGIMiddleware(_flask_app)

# Блок для запуска через Waitress (или встроенный сервер Flask) больше не нужен, если запускаем через Uvicorn
if __name__ == '__main__':
    # serve(_flask_app, host="0.0.0.0", port=8087) # Используем _flask_app
    _flask_app.run(debug=True, host="0.0.0.0", port=8087)  # Для локальной разработки