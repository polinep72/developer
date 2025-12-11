# my_project/web_app_WebChip/app.py
"""
Веб-приложение для управления складом кристаллов и пластин
Версия: 1.2.0
"""
import logging  # <--- ДОБАВИТЬ
import logging.handlers  # Для SMTPHandler
import os
from datetime import datetime
from io import BytesIO
import pandas as pd
import psycopg2  # Убедитесь, что psycopg2 или psycopg2-binary есть в requirements.txt
from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, jsonify, session, redirect, url_for, make_response, flash
from psycopg2.extras import execute_values
# from waitress import serve
from openpyxl.styles import NamedStyle
from urllib.parse import quote

__version__ = "1.3.3"

# Импортируем WSGIMiddleware
try:
    from uvicorn.middleware.wsgi import WSGIMiddleware
except ImportError:
    from starlette.middleware.wsgi import WSGIMiddleware

# Загружаем переменные окружения
# Пробуем загрузить из текущей директории и родительской
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Настройка логирования с SMTP handler для критических ошибок
def setup_logging():
    """Настройка логирования с отправкой критических ошибок на email"""
    # Формат логов
    log_format = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Получаем настройки SMTP из переменных окружения
    # Поддерживаем оба варианта: SMTP_USERNAME и SMTP_USER для обратной совместимости
    enable_email = os.getenv('ENABLE_EMAIL', 'true').lower().strip() == 'true'
    if not enable_email:
        root_logger.warning("SMTP логирование отключено (ENABLE_EMAIL=false)")
        # Все равно настраиваем консольный handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(log_format)
        root_logger.addHandler(console_handler)
        return
    
    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER')  # Поддержка обоих вариантов
    smtp_password = os.getenv('SMTP_PASSWORD')
    admin_email = os.getenv('ADMIN_EMAIL')
    from_email = os.getenv('SMTP_FROM_EMAIL', smtp_username)
    from_name = os.getenv('SMTP_FROM_NAME', 'Crystal Wafer Management System')
    smtp_use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    
    # Консольный handler (всегда активен)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    root_logger.addHandler(console_handler)
    
    # SMTP handler для критических ошибок (только если настроен)
    if smtp_host and smtp_username and smtp_password and admin_email:
        try:
            # Создаем кастомный SMTP handler для более гибкой настройки
            class SecureSMTPHandler(logging.handlers.SMTPHandler):
                def __init__(self, mailhost, fromaddr, toaddrs, subject, credentials, use_tls=True):
                    super().__init__(mailhost, fromaddr, toaddrs, subject, credentials)
                    self.use_tls = use_tls
                    self._sending = False  # Флаг для предотвращения рекурсии
                
                def emit(self, record):
                    """Переопределяем emit для поддержки TLS"""
                    # Предотвращаем рекурсию: если уже отправляем email, не пытаемся снова
                    if self._sending:
                        return
                    
                    try:
                        self._sending = True
                        import smtplib
                        from email.utils import formatdate
                        port = self.mailport
                        if not port:
                            port = smtplib.SMTP_PORT
                        smtp = smtplib.SMTP(self.mailhost, port)
                        if self.use_tls:
                            smtp.starttls()
                        if self.username:
                            smtp.login(self.username, self.password)
                        msg = self.format(record)
                        # Используем имя отправителя, если оно указано
                        from_header = f"{self.fromname} <{self.fromaddr}>" if hasattr(self, 'fromname') and self.fromname else self.fromaddr
                        msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                            from_header,
                            ','.join(self.toaddrs),
                            self.getSubject(record),
                            formatdate(),
                            msg
                        )
                        smtp.sendmail(self.fromaddr, self.toaddrs, msg)
                        smtp.quit()
                    except smtplib.SMTPAuthenticationError as e:
                        # Ошибка аутентификации - логируем в консоль, но не пытаемся отправить email
                        import sys
                        print(f"ОШИБКА SMTP аутентификации: {e}", file=sys.stderr)
                        print("Проверьте настройки SMTP в .env файле. Для Gmail используйте 'Пароль приложения'.", file=sys.stderr)
                    except Exception as e:
                        # Другие ошибки - логируем в консоль без рекурсии
                        import sys
                        print(f"ОШИБКА отправки email: {e}", file=sys.stderr)
                    finally:
                        self._sending = False
            
            smtp_handler = SecureSMTPHandler(
                mailhost=(smtp_host, smtp_port),
                fromaddr=from_email,
                toaddrs=[admin_email],
                subject='[КРИТИЧЕСКАЯ ОШИБКА] Crystal Wafer Management System',
                credentials=(smtp_username, smtp_password),
                use_tls=smtp_use_tls
            )
            # Добавляем имя отправителя, если указано
            smtp_handler.fromname = from_name
            smtp_handler.setLevel(logging.ERROR)  # Только ERROR и CRITICAL
            smtp_handler.setFormatter(log_format)
            root_logger.addHandler(smtp_handler)
            root_logger.info(f"SMTP логирование настроено: {admin_email}")
        except Exception as e:
            root_logger.warning(f"Не удалось настроить SMTP логирование: {e}")
    else:
        root_logger.warning("SMTP логирование не настроено (отсутствуют настройки в .env)")

# Вызываем настройку логирования
setup_logging()

_flask_app = Flask(__name__)
_flask_app.secret_key = os.getenv('SECRET_KEY', 'a_default_secret_key_change_it')  # Добавим дефолтный ключ

# Настраиваем логирование Werkzeug, чтобы скрыть предупреждение о development server
logging.getLogger('werkzeug').setLevel(logging.ERROR)

if not _flask_app.debug:  # Обычно в debug режиме Flask более многословен
    # Устанавливаем уровень INFO для логгера приложения
    _flask_app.logger.setLevel(logging.INFO)

# Обработчик необработанных исключений
@_flask_app.errorhandler(Exception)
def handle_exception(e):
    """Глобальный обработчик исключений для отправки на email"""
    # Игнорируем 404 ошибки (NotFound) - это не критичные ошибки
    from werkzeug.exceptions import NotFound
    if isinstance(e, NotFound):
        # Для 404 просто возвращаем стандартный ответ Flask, не логируем как ошибку
        return "Страница не найдена", 404
    
    # Логируем только критичные ошибки (не 404)
    _flask_app.logger.error(
        f"Необработанное исключение: {type(e).__name__}: {str(e)}",
        exc_info=True
    )
    # Возвращаем стандартный ответ Flask для исключений
    return f"Внутренняя ошибка сервера: {str(e)}", 500


@_flask_app.context_processor
def inject_user():
    return {'user_logged_in': 'username' in session, 'username': session.get('username')}


# --- НАЧАЛО ОПРЕДЕЛЕНИЙ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ ---
def get_db_connection():
    # Используем DB_NAME (основная БД с таблицами users, invoice и т.д.)
    # с fallback на DB_NAME2 для обратной совместимости
    db_name = os.getenv('DB_NAME') or os.getenv('DB_NAME2')
    db_host = os.getenv('DB_HOST')
    _flask_app.logger.info(f"Подключение к БД: host={db_host}, database={db_name}")
    
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
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

# Функции для работы с разными складами
def get_warehouse_tables(warehouse_type='crystals'):
    """
    Возвращает названия таблиц в зависимости от типа склада
    warehouse_type: 'crystals' - Склад кристаллов, 'plates' - Склад пластин, 'far' - Дальний склад
    """
    if warehouse_type == 'plates':
        return {'invoice': 'invoice_p', 'consumption': 'consumption_p'}
    elif warehouse_type == 'far':
        return {'invoice': 'invoice_f', 'consumption': 'consumption_f'}
    else:  # 'crystals' по умолчанию
        return {'invoice': 'invoice', 'consumption': 'consumption'}


def get_warehouse_type_from_request():
    """Получает тип склада из запроса (query параметр или сессия)"""
    warehouse_type = request.args.get('warehouse', session.get('warehouse_type', 'crystals'))
    # Валидация
    if warehouse_type not in ['crystals', 'plates', 'far']:
        warehouse_type = 'crystals'
    session['warehouse_type'] = warehouse_type
    return warehouse_type


# Стартовая страница
@_flask_app.route('/')
def home():
    # Устанавливаем тип склада по умолчанию из query параметра
    warehouse_type = request.args.get('warehouse', 'crystals')
    if warehouse_type not in ['crystals', 'plates', 'far']:
        warehouse_type = 'crystals'
    session['warehouse_type'] = warehouse_type
    return render_template('home.html', warehouse_type=warehouse_type)


# Страница поступления (inflow)
@_flask_app.route('/inflow', methods=['GET', 'POST'])
def inflow():
    # Получаем тип склада из запроса или сессии
    warehouse_type = get_warehouse_type_from_request()
    tables = get_warehouse_tables(warehouse_type)
    
    # Эта часть для GET-запроса (когда пользователь просто открывает страницу) остается без изменений
    if request.method == 'GET':
        _flask_app.logger.info(f"Route /inflow called, method: GET, warehouse: {warehouse_type}")
        return render_template('inflow.html', warehouse_type=warehouse_type)

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

        # Проверяем наличие обязательных колонок
        required_columns = ['Приход Wafer, шт.']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({"success": False, 
                          "message": f"Ошибка в файле: отсутствуют необходимые столбцы: {', '.join(missing_columns)}. Проверьте шаблон файла."}), 400

        df['Приход Wafer, шт.'] = pd.to_numeric(df['Приход Wafer, шт.'], errors='coerce').fillna(0).astype(int)
        # Колонка 'Приход GelPack, шт.' опциональна
        if 'Приход GelPack, шт.' in df.columns:
            df['Приход GelPack, шт.'] = pd.to_numeric(df['Приход GelPack, шт.'], errors='coerce').fillna(0).astype(int)
        else:
            df['Приход GelPack, шт.'] = 0  # Значение по умолчанию, если колонка отсутствует

        # Создаем одно подключение для всех операций
        conn_loop = get_db_connection()
        cur = conn_loop.cursor()
        
        # Вспомогательная функция для get_or_create_id с использованием существующего cursor
        def get_or_create_id_with_cursor(table_name, column_name, value):
            select_query = f"SELECT id FROM {table_name} WHERE {column_name} = %s"
            cur.execute(select_query, (value,))
            existing = cur.fetchone()
            if existing:
                return existing[0]
            else:
                insert_query = f"INSERT INTO {table_name} ({column_name}) VALUES (%s) RETURNING id"
                cur.execute(insert_query, (value,))
                new_id_result = cur.fetchone()
                if new_id_result:
                    return new_id_result[0]
                else:
                    raise Exception(f"Не удалось создать или получить ID для {table_name}.{column_name} = {value}")

        all_data_to_insert = []
        status_приход = 1

        for idx, row in df.iterrows():
            try:
                date_val = row['Дата прихода']
                if pd.isna(date_val):
                    raise ValueError(f"Строка {idx + 2}: Дата прихода не может быть пустой.")
                formatted_date = pd.to_datetime(date_val).strftime('%Y-%m-%d')

                # Используем оптимизированную функцию с существующим cursor
                id_start = int(get_or_create_id_with_cursor("start_p", "name_start", str(row["Номер запуска"])))
                id_pr = int(get_or_create_id_with_cursor("pr", "name_pr", str(row["Производитель"])))
                id_tech = int(get_or_create_id_with_cursor("tech", "name_tech", str(row["Технологический процесс"])))
                id_lot = int(get_or_create_id_with_cursor("lot", "name_lot", str(row['Партия (Lot ID)'])))
                id_wafer = int(get_or_create_id_with_cursor("wafer", "name_wafer", str(row['Пластина (Wafer)'])))
                id_quad = int(get_or_create_id_with_cursor("quad", "name_quad", str(row['Quadrant'])))
                id_in_lot = int(get_or_create_id_with_cursor("in_lot", "in_lot", str(row['Внутренняя партия'])))
                id_chip = int(get_or_create_id_with_cursor("chip", "name_chip", str(row['Номер кристалла'])))
                id_n_chip = int(get_or_create_id_with_cursor("n_chip", "n_chip", str(row['Шифр кристалла'])))
                id_size_val = row.get('Размер кристалла')
                id_size = get_or_create_id_with_cursor("size_c", "size",
                                           str(id_size_val).replace('х', 'x').replace('Х', 'x')) if pd.notna(
                    id_size_val) and str(id_size_val).strip() else None
                id_pack = int(get_or_create_id_with_cursor("pack", "name_pack", str(row["Упаковка"])))
                id_stor = int(get_or_create_id_with_cursor("stor", "name_stor", str(row['Место хранения'])))
                id_cells = int(get_or_create_id_with_cursor("cells", "name_cells", str(row["Ячейка хранения"])))

                # --- ИЗМЕНЕНИЕ: Добавляем user_id и file_name в кортеж ---
                all_data_to_insert.append((
                    id_start, id_tech, id_chip, id_lot, id_wafer, id_quad, id_in_lot,
                    formatted_date,  # date
                    row['Приход Wafer, шт.'],  # quan_w
                    str(row.get('Примечание', '')).strip() or None,  # note
                    id_pack, id_cells, id_n_chip,
                    id_pr, id_size,
                    row['Приход GelPack, шт.'],  # quan_gp (уже проверено/создано выше)
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
        # Используем динамическое название таблицы в зависимости от склада
        invoice_table = tables['invoice']
        insert_query = f"""
            INSERT INTO {invoice_table} (
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

        # Используем уже созданное подключение и cursor
        try:
            # Вместо execute_values используем цикл
            for record in all_data_to_insert:
                cur.execute(insert_query, record)  # psycopg2 подставит значения в %s

            conn_loop.commit()
            cur.close()

            log_user_action(
                user_id=user_id,  # Используем переменную, определенную ранее
                action_type=f'Загрузка файла: Приход (склад: {warehouse_type})',
                file_name=file_name,
                target_table=invoice_table
            )
            return jsonify({"success": True,
                            "message": f"Данные из файла '{file_name}' успешно загружены ({len(all_data_to_insert)} строк)."}), 200

        except psycopg2.Error as db_err:
            if conn_loop: 
                conn_loop.rollback()
                cur.close()
            _flask_app.logger.error(f"Inflow - psycopg2.Error: {db_err}", exc_info=True)
            return jsonify({"success": False, "message": f"Ошибка базы данных: {db_err}"}), 500
        except Exception as e:
            if conn_loop: 
                conn_loop.rollback()
                cur.close()
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
    # Получаем тип склада из запроса или сессии
    warehouse_type = get_warehouse_type_from_request()
    tables = get_warehouse_tables(warehouse_type)
    
    if request.method == 'GET':
        return render_template('outflow.html', warehouse_type=warehouse_type)

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

        # Проверяем наличие обязательных колонок
        required_columns = [
            'Расход Wafer, шт.',
            'Дата расхода',
            'Номер запуска',
            'Производитель',
            'Технологический процесс',
            'Партия (Lot ID)',
            'Пластина (Wafer)',
            'Quadrant',
            'Внутренняя партия',
            'Номер кристалла',
            'Шифр кристалла'
        ]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            missing_cols_str = ', '.join(missing_columns)
            _flask_app.logger.error(f"Outflow - Missing required columns: {missing_cols_str}")
            _flask_app.logger.error(f"Outflow - Available columns in file: {', '.join(df.columns.tolist())}")
            return jsonify({"success": False, 
                          "message": f"Ошибка в файле: отсутствуют необходимые столбцы: {missing_cols_str}. Проверьте шаблон файла."}), 400

        df['Расход Wafer, шт.'] = pd.to_numeric(df['Расход Wafer, шт.'], errors='coerce').fillna(0).astype(int)
        # Колонка 'Расход GelPack, шт.' опциональна
        if 'Расход GelPack, шт.' in df.columns:
            df['Расход GelPack, шт.'] = pd.to_numeric(df['Расход GelPack, шт.'], errors='coerce').fillna(0).astype(int)
        else:
            df['Расход GelPack, шт.'] = 0  # Значение по умолчанию, если колонка отсутствует

        # Создаем одно подключение для всех операций
        conn_loop_out = get_db_connection()
        cur = conn_loop_out.cursor()
        
        # Вспомогательная функция для get_reference_id с использованием существующего cursor
        def get_reference_id_with_cursor(table_name, column_name, value):
            if not value or (isinstance(value, str) and not value.strip()):
                return None
            select_query = f"SELECT id FROM {table_name} WHERE {column_name} = %s"
            cur.execute(select_query, (value,))
            existing = cur.fetchone()
            if existing:
                return existing[0]
            else:
                raise Exception(f"Не найдена запись в {table_name} с {column_name} = {value}")

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

                # Маппинг согласно требованиям:
                # Номер запуска -> id_start
                id_start = int(get_reference_id_with_cursor("start_p", "name_start", str(row["Номер запуска"])))
                # Производитель -> id_pr
                id_pr = int(get_reference_id_with_cursor("pr", "name_pr", str(row["Производитель"])))
                # Технологический процесс -> id_tech
                id_tech = int(get_reference_id_with_cursor("tech", "name_tech", str(row["Технологический процесс"])))
                # Партия (Lot ID) -> id_lot
                id_lot = int(get_reference_id_with_cursor("lot", "name_lot", str(row["Партия (Lot ID)"])))
                # Пластина (Wafer) -> id_wafer
                id_wafer = int(get_reference_id_with_cursor("wafer", "name_wafer", str(row["Пластина (Wafer)"])))
                # Quadrant -> id_quad
                id_quad = int(get_reference_id_with_cursor("quad", "name_quad", str(row["Quadrant"])))
                # Внутренняя партия -> id_in_lot
                id_in_lot = int(get_reference_id_with_cursor("in_lot", "in_lot", str(row["Внутренняя партия"])))
                # Номер кристалла -> id_n_chip (согласно требованиям)
                id_n_chip = int(get_reference_id_with_cursor("n_chip", "n_chip", str(row["Номер кристалла"])))
                # Шифр кристалла -> id_chip (согласно требованиям)
                id_chip = int(get_reference_id_with_cursor("chip", "name_chip", str(row["Шифр кристалла"])))
                # Упаковка -> id_pack (опционально)
                id_pack_val = row.get("Упаковка", "")
                id_pack_result = get_reference_id_with_cursor("pack", "name_pack", str(id_pack_val)) if id_pack_val and str(id_pack_val).strip() else None
                id_pack = int(id_pack_result) if id_pack_result is not None else None
                # Место хранения -> id_stor (опционально)
                id_stor_val = row.get('Место хранения', '')
                id_stor_result = get_reference_id_with_cursor("stor", "name_stor", str(id_stor_val)) if id_stor_val and str(id_stor_val).strip() else None
                id_stor = int(id_stor_result) if id_stor_result is not None else None
                # Ячейка хранения -> id_cells (опционально)
                id_cells_val = row.get("Ячейка хранения", '')
                id_cells_result = get_reference_id_with_cursor("cells", "name_cells", str(id_cells_val)) if id_cells_val and str(id_cells_val).strip() else None
                id_cells = int(id_cells_result) if id_cells_result is not None else None
                # Примечание -> note
                note = str(row.get("Примечание", "")).strip() or None

                # Порядок полей согласно требованиям
                record = (
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    id_chip, formatted_date, cons_w, cons_gp,
                    note, id_pack, id_stor, id_cells,
                    status_расход, user_id, file_name
                )
                all_data_to_insert.append(record)
            except KeyError as e_key:
                missing_column = str(e_key).replace("'", "")
                _flask_app.logger.error(f"Outflow - Missing column in row {idx + 2}: {missing_column}", exc_info=True)
                _flask_app.logger.error(f"Outflow - Available columns in DataFrame: {', '.join(df.columns.tolist())}")
                if conn_loop_out:
                    conn_loop_out.rollback()
                    cur.close()
                    conn_loop_out.close()
                return jsonify({"success": False, "message": f"Ошибка в строке {idx + 2}: отсутствует столбец '{missing_column}'. Проверьте формат файла."}), 400
            except (ValueError, Exception) as e_row:
                _flask_app.logger.error(f"Outflow - Error processing row {idx + 2}: {e_row}", exc_info=True)
                if conn_loop_out:
                    conn_loop_out.rollback()
                    cur.close()
                    conn_loop_out.close()
                return jsonify({"success": False, "message": f"Ошибка в строке {idx + 2}: {str(e_row)}"}), 400

        if not all_data_to_insert:
            if conn_loop_out:
                cur.close()
                conn_loop_out.close()
            return jsonify({"success": False, "message": "Нет корректных данных для импорта в файле."}), 400

        # SQL запрос согласно требованиям
        consumption_table = tables['consumption']
        query_consumption = f"""
            INSERT INTO {consumption_table} (
                id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                id_chip, date, cons_w, cons_gp,
                note, id_pack, id_stor, id_cells,
                status, user_entry_id, file_name_entry, date_time_entry
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            );
        """

        try:
            _flask_app.logger.info(f"Outflow - Начинаем вставку {len(all_data_to_insert)} записей в таблицу {consumption_table}")
            for record_idx, record in enumerate(all_data_to_insert, 1):
                try:
                    cur.execute(query_consumption, record)
                except Exception as exec_err:
                    _flask_app.logger.error(f"Outflow - Ошибка при вставке записи {record_idx}: {exec_err}")
                    _flask_app.logger.error(f"Outflow - Параметры записи: {record}")
                    raise
            conn_loop_out.commit()
            cur.close()

            log_user_action(
                user_id=user_id,
                action_type=f'Загрузка файла: Расход (склад: {warehouse_type})',
                file_name=file_name,
                target_table=consumption_table
            )
            return jsonify({"success": True,
                            "message": f"Данные расхода из файла '{file_name}' успешно загружены ({len(all_data_to_insert)} строк)."}), 200

        except psycopg2.Error as db_err:
            if conn_loop_out: 
                conn_loop_out.rollback()
                cur.close()
            _flask_app.logger.error(f"Ошибка БД при обработке файла расхода: {db_err}", exc_info=True)
            _flask_app.logger.error(f"Таблица: {consumption_table}, warehouse_type: {warehouse_type}")
            error_msg = str(db_err)
            return jsonify({"success": False, "message": f"Ошибка базы данных: {error_msg}"}), 500
        except Exception as e:
            if conn_loop_out: 
                conn_loop_out.rollback()
                cur.close()
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
    # Получаем тип склада из запроса или сессии
    warehouse_type = get_warehouse_type_from_request()
    tables = get_warehouse_tables(warehouse_type)
    
    if request.method == 'GET':
        return render_template('refund.html', warehouse_type=warehouse_type)

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

        # Проверяем наличие обязательных колонок
        required_columns = ['Возврат Wafer, шт.']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({"success": False, 
                          "message": f"Ошибка в файле: отсутствуют необходимые столбцы: {', '.join(missing_columns)}. Проверьте шаблон файла."}), 400

        df['Возврат Wafer, шт.'] = pd.to_numeric(df['Возврат Wafer, шт.'], errors='coerce').fillna(0).astype(int)
        # Колонка 'Возврат GelPack, шт.' опциональна
        if 'Возврат GelPack, шт.' in df.columns:
            df['Возврат GelPack, шт.'] = pd.to_numeric(df['Возврат GelPack, шт.'], errors='coerce').fillna(0).astype(int)
        else:
            df['Возврат GelPack, шт.'] = 0  # Значение по умолчанию, если колонка отсутствует

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

        # --- ИЗМЕНЕНИЕ ЗДЕСЬ: в SQL запросе id_cells и динамическое название таблицы ---
        invoice_table = tables['invoice']
        query_refund_insert = f"""
            INSERT INTO {invoice_table} (
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
                action_type=f'Загрузка файла: Возврат (склад: {warehouse_type})',
                file_name=file_name,
                target_table=invoice_table
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
    # Получаем тип склада из запроса или сессии
    warehouse_type = get_warehouse_type_from_request()
    session['warehouse_type'] = warehouse_type  # Сохраняем в сессию для использования в add_to_cart
    tables = get_warehouse_tables(warehouse_type)
    invoice_table = tables['invoice']
    consumption_table = tables['consumption']
    
    manufacturers = []
    lots = []
    try:
        manufacturers_query = "SELECT DISTINCT name_pr FROM pr ORDER BY name_pr"
        manufacturers_raw = execute_query(manufacturers_query)
        if manufacturers_raw:
            manufacturers = [row[0] for row in manufacturers_raw]
        
        # Загружаем список партий только для склада кристаллов
        # Фильтруем партии по выбранному производителю, если он указан
        if warehouse_type == 'crystals':
            # Получаем значение производителя из формы или аргументов
            selected_manufacturer_for_lots = request.form.get('manufacturer') or request.args.get('manufacturer', 'all')
            
            if selected_manufacturer_for_lots and selected_manufacturer_for_lots != 'all':
                # Фильтруем партии по производителю через invoice таблицу
                lots_query = f"""
                    SELECT DISTINCT l.name_lot 
                    FROM lot l
                    INNER JOIN {invoice_table} inv ON inv.id_lot = l.id
                    INNER JOIN pr p ON inv.id_pr = p.id
                    WHERE p.name_pr = %s
                    ORDER BY l.name_lot
                """
                lots_raw = execute_query(lots_query, (selected_manufacturer_for_lots,))
                if lots_raw:
                    lots = [row[0] for row in lots_raw]
            else:
                # Если производитель не выбран, показываем все партии
                lots_query = "SELECT DISTINCT name_lot FROM lot ORDER BY name_lot"
                lots_raw = execute_query(lots_query)
                if lots_raw:
                    lots = [row[0] for row in lots_raw]
    except Exception as e:
        flash(f"Ошибка загрузки списка производителей: {e}", "danger")
        _flask_app.logger.error(f"Ошибка загрузки списка производителей: {e}")

    results = []
    chip_name_form = ''
    manufacturer_filter_form = 'all'
    lot_filter_form = 'all'

    if request.method == 'POST':
        if 'user_id' not in session:
            flash("Пожалуйста, войдите в систему для выполнения поиска.", "warning")
            return redirect(url_for('login', next=request.url))
        
        chip_name_form = request.form.get('chip_name', '').strip()
        manufacturer_filter_form = request.form.get('manufacturer', 'all')
        lot_filter_form = request.form.get('lot_filter', 'all')
    else:  # GET request
        chip_name_form = request.args.get('chip_name', '').strip()
        manufacturer_filter_form = request.args.get('manufacturer', 'all')
        lot_filter_form = request.args.get('lot_filter', 'all')

    # Строим SQL-запрос для поиска (для обоих методов - POST и GET)
    # Логика: группируем БЕЗ note, чтобы получить общий остаток по позиции
    query_search = f"""
        WITH 
        income_sum_by_item AS (
            SELECT
                item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                id_stor AS latest_id_stor, id_cells AS latest_id_cells,
                MAX(note) FILTER (WHERE note IS NOT NULL AND note != '' AND LOWER(note) != 'nan') AS latest_note,
                SUM(quan_w) as total_received_w, SUM(quan_gp) as total_received_gp
            FROM {invoice_table}
            WHERE status = 1  -- Только приход (status=1)
            GROUP BY item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells
        ),
        return_sum_by_item AS (
            SELECT
                item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                id_stor AS latest_id_stor, id_cells AS latest_id_cells,
                MAX(note) FILTER (WHERE note IS NOT NULL AND note != '' AND LOWER(note) != 'nan') AS latest_note,
                SUM(quan_w) as total_return_w, SUM(quan_gp) as total_return_gp
            FROM {invoice_table}
            WHERE status = 3  -- Только возврат (status=3)
            GROUP BY item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells
        ),
        consumption_sum_by_item AS (
            SELECT
                item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                id_stor AS latest_id_stor,
                id_cells AS latest_id_cells,
                MAX(note) FILTER (WHERE note IS NOT NULL AND note != '' AND LOWER(note) != 'nan') AS latest_note,
                SUM(cons_w) as total_consumed_w, SUM(cons_gp) as total_consumed_gp
            FROM {consumption_table}
            GROUP BY item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells
        ),
        combined_invoice_sum AS (
            SELECT
                COALESCE(inc.item_id, ret.item_id) AS item_id,
                COALESCE(inc.latest_note, ret.latest_note) AS note,
                COALESCE(inc.id_start, ret.id_start) AS id_start,
                COALESCE(inc.id_pr, ret.id_pr) AS id_pr,
                COALESCE(inc.id_tech, ret.id_tech) AS id_tech,
                COALESCE(inc.id_lot, ret.id_lot) AS id_lot,
                COALESCE(inc.id_wafer, ret.id_wafer) AS id_wafer,
                COALESCE(inc.id_quad, ret.id_quad) AS id_quad,
                COALESCE(inc.id_in_lot, ret.id_in_lot) AS id_in_lot,
                COALESCE(inc.id_n_chip, ret.id_n_chip) AS id_n_chip,
                COALESCE(inc.latest_id_stor, ret.latest_id_stor) AS latest_id_stor,
                COALESCE(inc.latest_id_cells, ret.latest_id_cells) AS latest_id_cells,
                COALESCE(inc.total_received_w, 0) AS total_received_w,
                COALESCE(inc.total_received_gp, 0) AS total_received_gp,
                COALESCE(ret.total_return_w, 0) AS total_return_w,
                COALESCE(ret.total_return_gp, 0) AS total_return_gp
            FROM income_sum_by_item inc
            FULL OUTER JOIN return_sum_by_item ret
                ON inc.item_id = ret.item_id 
                AND inc.id_start = ret.id_start AND inc.id_pr = ret.id_pr AND inc.id_tech = ret.id_tech 
                AND inc.id_lot = ret.id_lot AND inc.id_wafer = ret.id_wafer AND inc.id_quad = ret.id_quad
                AND inc.id_in_lot = ret.id_in_lot AND inc.id_n_chip = ret.id_n_chip
                AND COALESCE(inc.latest_id_stor, -1) = COALESCE(ret.latest_id_stor, -1)
                AND COALESCE(inc.latest_id_cells, -1) = COALESCE(ret.latest_id_cells, -1)
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
            (COALESCE(inv.total_received_w, 0) + COALESCE(inv.total_return_w, 0) - COALESCE(cons.total_consumed_w, 0)) AS ostatok_w,     -- 10
            (COALESCE(inv.total_received_gp, 0) + COALESCE(inv.total_return_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) AS ostatok_gp,   -- 11
            COALESCE(inv.note, cons.latest_note, '') AS display_note,     -- 12
            st.name_stor,                                                 -- 13
            c.name_cells,                                                 -- 14
            COALESCE(inv.id_pr, cons.id_pr) AS actual_id_pr,              -- 15
            COALESCE(inv.id_tech, cons.id_tech) AS actual_id_tech,        -- 16
            COALESCE(inv.id_lot, cons.id_lot) AS actual_id_lot,            -- 17
            COALESCE(inv.id_wafer, cons.id_wafer) AS actual_id_wafer,      -- 18
            COALESCE(inv.id_quad, cons.id_quad) AS actual_id_quad,        -- 19
            COALESCE(inv.id_in_lot, cons.id_in_lot) AS actual_id_in_lot,   -- 20
            COALESCE(inv.id_n_chip, cons.id_n_chip) AS actual_id_n_chip    -- 21
        FROM combined_invoice_sum inv
        FULL OUTER JOIN consumption_sum_by_item cons 
            ON inv.item_id = cons.item_id 
            AND inv.id_start = cons.id_start AND inv.id_pr = cons.id_pr AND inv.id_tech = cons.id_tech 
            AND inv.id_lot = cons.id_lot AND inv.id_wafer = cons.id_wafer AND inv.id_quad = cons.id_quad
            AND inv.id_in_lot = cons.id_in_lot AND inv.id_n_chip = cons.id_n_chip
            AND COALESCE(inv.latest_id_stor, -1) = COALESCE(cons.latest_id_stor, -1)
            AND COALESCE(inv.latest_id_cells, -1) = COALESCE(cons.latest_id_cells, -1)
        LEFT JOIN start_p s ON s.id = COALESCE(inv.id_start, cons.id_start)
        LEFT JOIN pr p ON p.id = COALESCE(inv.id_pr, cons.id_pr)
        LEFT JOIN tech t ON t.id = COALESCE(inv.id_tech, cons.id_tech)
        LEFT JOIN wafer w ON w.id = COALESCE(inv.id_wafer, cons.id_wafer)
        LEFT JOIN quad q ON q.id = COALESCE(inv.id_quad, cons.id_quad)
        LEFT JOIN lot l ON l.id = COALESCE(inv.id_lot, cons.id_lot)
        LEFT JOIN in_lot il ON il.id = COALESCE(inv.id_in_lot, cons.id_in_lot)
        LEFT JOIN n_chip nc ON nc.id = COALESCE(inv.id_n_chip, cons.id_n_chip)
        LEFT JOIN stor st ON st.id = COALESCE(inv.latest_id_stor, cons.latest_id_stor)
        LEFT JOIN cells c ON c.id = COALESCE(inv.latest_id_cells, cons.latest_id_cells)
        WHERE 
            ( (COALESCE(inv.total_received_gp, 0) + COALESCE(inv.total_return_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) != 0 OR
              (COALESCE(inv.total_received_w, 0) + COALESCE(inv.total_return_w, 0) - COALESCE(cons.total_consumed_w, 0)) != 0 OR
              COALESCE(inv.total_received_gp, 0) != 0 OR COALESCE(inv.total_received_w, 0) != 0 OR
              COALESCE(inv.total_return_gp, 0) != 0 OR COALESCE(inv.total_return_w, 0) != 0 OR
              COALESCE(cons.total_consumed_gp, 0) != 0 OR COALESCE(cons.total_consumed_w, 0) != 0 )
        """
    
    params_search = []
    filter_conditions = []
    
    # Для складов "Склад пластин" и "Дальний склад" добавляем фильтр: скрываем строки где оба остатка = 0
    if warehouse_type in ('plates', 'far'):
        filter_conditions.append(
            "NOT ((COALESCE(inv.total_received_w, 0) + COALESCE(inv.total_return_w, 0) - COALESCE(cons.total_consumed_w, 0)) = 0 "
            "AND (COALESCE(inv.total_received_gp, 0) + COALESCE(inv.total_return_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) = 0)"
        )
    
    # Фильтр по шифру кристалла (необязательный) - добавляем только если есть непустое значение
    if chip_name_form and chip_name_form.strip():
        filter_conditions.append("nc.n_chip ILIKE %s")
        params_search.append(f"%{chip_name_form.strip()}%")
    
    # Фильтр по производителю
    if manufacturer_filter_form and manufacturer_filter_form != "all":
        filter_conditions.append("p.name_pr = %s")
        params_search.append(manufacturer_filter_form)
    
    # Добавляем фильтр по партии только для склада кристаллов
    if warehouse_type == 'crystals' and lot_filter_form and lot_filter_form != "all":
        filter_conditions.append("l.name_lot = %s")
        params_search.append(lot_filter_form)

    if filter_conditions:
        query_search += " AND " + " AND ".join(filter_conditions)
    
    query_search += " ORDER BY display_item_id;"

    # Выполняем поиск только если это POST запрос (при нажатии кнопки "Найти")
    if request.method == 'POST':
        try:
            results = execute_query(query_search, tuple(params_search))
            if not results:
                flash("По вашему запросу ничего не найдено.", "info")
        except Exception as e:
            flash(f"Ошибка при выполнении поиска: {e}", "danger")
            _flask_app.logger.error(f"Ошибка поиска: {e}", exc_info=True)
            _flask_app.logger.error(f"SQL запрос: {query_search}")
            _flask_app.logger.error(f"Параметры: {params_search}")
            results = []

    return render_template('search.html',
                           results=results,
                           manufacturers=manufacturers,
                           lots=lots if warehouse_type == 'crystals' else [],
                           chip_name=chip_name_form,
                           manufacturer_filter=manufacturer_filter_form,
                           lot_filter=lot_filter_form,
                           warehouse_type=warehouse_type
                           )


@_flask_app.route('/api/get_lots', methods=['GET'])
def get_lots():
    """API endpoint для получения списка партий по выбранному производителю"""
    warehouse_type = request.args.get('warehouse', 'crystals')
    
    if warehouse_type != 'crystals':
        return jsonify({"lots": []})
    
    manufacturer = request.args.get('manufacturer', 'all')
    
    tables = get_warehouse_tables(warehouse_type)
    invoice_table = tables['invoice']
    
    try:
        if manufacturer and manufacturer != 'all':
            # Фильтруем партии по производителю
            lots_query = f"""
                SELECT DISTINCT l.name_lot 
                FROM lot l
                INNER JOIN {invoice_table} inv ON inv.id_lot = l.id
                INNER JOIN pr p ON inv.id_pr = p.id
                WHERE p.name_pr = %s
                ORDER BY l.name_lot
            """
            lots_raw = execute_query(lots_query, (manufacturer,))
        else:
            # Все партии
            lots_query = "SELECT DISTINCT name_lot FROM lot ORDER BY name_lot"
            lots_raw = execute_query(lots_query)
        
        lots = [row[0] for row in lots_raw] if lots_raw else []
        return jsonify({"lots": lots})
    except Exception as e:
        _flask_app.logger.error(f"Ошибка загрузки партий: {e}", exc_info=True)
        return jsonify({"lots": [], "error": str(e)}), 500


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

    # Получаем тип склада из сессии или запроса
    warehouse_type = session.get('warehouse_type', 'crystals')
    tables = get_warehouse_tables(warehouse_type)
    invoice_table = tables['invoice']
    consumption_table = tables['consumption']

    try:
        date_added = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Специальная логика для складов "Склад пластин" и "Дальний склад"
        if warehouse_type in ('plates', 'far'):
            if not item_id:
                return jsonify({'success': False, 'message': 'Некорректные данные для добавления (ID)'}), 400

            # Извлекаем префикс item_id (без последней части - кода кристалла)
            # item_id имеет вид "8-26-8-10-8-8-9-66", где последняя часть - код кристалла
            item_id_parts = str(item_id).split('-')
            if len(item_id_parts) < 2:
                return jsonify({'success': False, 'message': 'Некорректный формат item_id'}), 400
            
            # Формируем префикс без последней части (кода кристалла)
            item_id_prefix = '-'.join(item_id_parts[:-1])  # "8-26-8-10-8-8-9"
            
            # Находим все строки с таким префиксом item_id в invoice таблице
            # Используем запрос, аналогичный поиску, чтобы получить остатки
            query_find_all_items = f"""
            WITH 
            income_sum_by_item AS (
                SELECT
                    item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    id_stor AS latest_id_stor, id_cells AS latest_id_cells,
                    MAX(id_chip) AS latest_id_chip, MAX(id_pack) AS latest_id_pack,
                    MAX(note) FILTER (WHERE note IS NOT NULL AND note != '' AND LOWER(note) != 'nan') AS latest_note,
                    SUM(quan_w) as total_received_w, SUM(quan_gp) as total_received_gp
                FROM {invoice_table}
                WHERE item_id LIKE %s AND status = 1  -- Только приход (status=1)
                GROUP BY item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells
            ),
            return_sum_by_item AS (
                SELECT
                    item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    id_stor AS latest_id_stor, id_cells AS latest_id_cells,
                    MAX(note) FILTER (WHERE note IS NOT NULL AND note != '' AND LOWER(note) != 'nan') AS latest_note,
                    SUM(quan_w) as total_return_w, SUM(quan_gp) as total_return_gp
                FROM {invoice_table}
                WHERE item_id LIKE %s AND status = 3  -- Только возврат (status=3)
                GROUP BY item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells
            ),
            consumption_sum_by_item AS (
                SELECT
                    item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    id_stor AS latest_id_stor,
                    id_cells AS latest_id_cells,
                    MAX(note) FILTER (WHERE note IS NOT NULL AND note != '' AND LOWER(note) != 'nan') AS latest_note,
                    SUM(cons_w) as total_consumed_w, SUM(cons_gp) as total_consumed_gp
                FROM {consumption_table}
                WHERE item_id LIKE %s
                GROUP BY item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells
            ),
            combined_invoice_sum AS (
                SELECT
                    COALESCE(inc.item_id, ret.item_id) AS item_id,
                    COALESCE(inc.latest_note, ret.latest_note) AS note,
                    COALESCE(inc.id_start, ret.id_start) AS id_start,
                    COALESCE(inc.id_pr, ret.id_pr) AS id_pr,
                    COALESCE(inc.id_tech, ret.id_tech) AS id_tech,
                    COALESCE(inc.id_lot, ret.id_lot) AS id_lot,
                    COALESCE(inc.id_wafer, ret.id_wafer) AS id_wafer,
                    COALESCE(inc.id_quad, ret.id_quad) AS id_quad,
                    COALESCE(inc.id_in_lot, ret.id_in_lot) AS id_in_lot,
                    COALESCE(inc.id_n_chip, ret.id_n_chip) AS id_n_chip,
                    COALESCE(inc.latest_id_stor, ret.latest_id_stor) AS latest_id_stor,
                    COALESCE(inc.latest_id_cells, ret.latest_id_cells) AS latest_id_cells,
                    inc.latest_id_chip,
                    inc.latest_id_pack,
                    COALESCE(inc.total_received_w, 0) AS total_received_w,
                    COALESCE(inc.total_received_gp, 0) AS total_received_gp,
                    COALESCE(ret.total_return_w, 0) AS total_return_w,
                    COALESCE(ret.total_return_gp, 0) AS total_return_gp
                FROM income_sum_by_item inc
                FULL OUTER JOIN return_sum_by_item ret
                    ON inc.item_id = ret.item_id 
                    AND inc.id_start = ret.id_start AND inc.id_pr = ret.id_pr AND inc.id_tech = ret.id_tech 
                    AND inc.id_lot = ret.id_lot AND inc.id_wafer = ret.id_wafer AND inc.id_quad = ret.id_quad
                    AND inc.id_in_lot = ret.id_in_lot AND inc.id_n_chip = ret.id_n_chip
                    AND COALESCE(inc.latest_id_stor, -1) = COALESCE(ret.latest_id_stor, -1)
                    AND COALESCE(inc.latest_id_cells, -1) = COALESCE(ret.latest_id_cells, -1)
            )
            SELECT 
                COALESCE(inv.item_id, cons.item_id) AS display_item_id,
                COALESCE(inv.id_start, cons.id_start) AS actual_id_start,
                s.name_start,
                p.name_pr,
                t.name_tech,
                w.name_wafer,
                q.name_quad,
                l.name_lot,
                il.in_lot,
                nc.n_chip,
                (COALESCE(inv.total_received_w, 0) + COALESCE(inv.total_return_w, 0) - COALESCE(cons.total_consumed_w, 0)) AS ostatok_w,
                (COALESCE(inv.total_received_gp, 0) + COALESCE(inv.total_return_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) AS ostatok_gp,
                COALESCE(inv.note, cons.latest_note, '') AS display_note,
                st.name_stor,
                c.name_cells,
                inv.latest_id_chip,
                inv.latest_id_pack
            FROM combined_invoice_sum inv
            FULL OUTER JOIN consumption_sum_by_item cons 
                ON inv.item_id = cons.item_id 
                AND inv.id_start = cons.id_start AND inv.id_pr = cons.id_pr AND inv.id_tech = cons.id_tech 
                AND inv.id_lot = cons.id_lot AND inv.id_wafer = cons.id_wafer AND inv.id_quad = cons.id_quad
                AND inv.id_in_lot = cons.id_in_lot AND inv.id_n_chip = cons.id_n_chip
                AND COALESCE(inv.latest_id_stor, -1) = COALESCE(cons.latest_id_stor, -1)
                AND COALESCE(inv.latest_id_cells, -1) = COALESCE(cons.latest_id_cells, -1)
            LEFT JOIN start_p s ON s.id = COALESCE(inv.id_start, cons.id_start)
            LEFT JOIN pr p ON p.id = COALESCE(inv.id_pr, cons.id_pr)
            LEFT JOIN tech t ON t.id = COALESCE(inv.id_tech, cons.id_tech)
            LEFT JOIN wafer w ON w.id = COALESCE(inv.id_wafer, cons.id_wafer)
            LEFT JOIN quad q ON q.id = COALESCE(inv.id_quad, cons.id_quad)
            LEFT JOIN lot l ON l.id = COALESCE(inv.id_lot, cons.id_lot)
            LEFT JOIN in_lot il ON il.id = COALESCE(inv.id_in_lot, cons.id_in_lot)
            LEFT JOIN n_chip nc ON nc.id = COALESCE(inv.id_n_chip, cons.id_n_chip)
            LEFT JOIN stor st ON st.id = COALESCE(inv.latest_id_stor, cons.latest_id_stor)
            LEFT JOIN cells c ON c.id = COALESCE(inv.latest_id_cells, cons.latest_id_cells)
            WHERE 
                (COALESCE(inv.total_received_w, 0) + COALESCE(inv.total_return_w, 0) - COALESCE(cons.total_consumed_w, 0)) > 0
            ORDER BY display_item_id
            """
            
            # Ищем все item_id, начинающиеся с префикса (например, "8-26-8-10-8-8-9-%")
            search_pattern = f"{item_id_prefix}-%"
            all_items = execute_query(query_find_all_items, (search_pattern, search_pattern, search_pattern), fetch=True)
            
            if not all_items:
                return jsonify({'success': False, 'message': 'Не найдено кристаллов для добавления'}), 400

            # Добавляем каждую найденную строку в корзину с количеством ostatok_w
            added_count = 0
            for row in all_items:
                row_item_id = row[0]
                ostatok_w = int(row[10]) if row[10] else 0
                
                if ostatok_w <= 0:
                    continue  # Пропускаем строки с нулевым остатком
                
                # Получаем id_chip и id_pack для текущего item_id
                id_chip_val = row[15] if len(row) > 15 else None
                id_pack_val = row[16] if len(row) > 16 else None
                
                query_insert_cart = """
                    INSERT INTO cart (
                        user_id, item_id, 
                        cons_w, cons_gp, 
                        start, manufacturer, technology, lot, wafer, quadrant, internal_lot, chip_code, 
                        note, stor, cells, 
                        id_chip, id_pack,
                        warehouse_type,
                        date_added
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, item_id, warehouse_type) 
                    DO UPDATE SET 
                        cons_w = EXCLUDED.cons_w,
                        cons_gp = EXCLUDED.cons_gp,
                        date_added = EXCLUDED.date_added; 
                """
                params_cart = (
                    user_id, row_item_id,
                    ostatok_w, 0,  # quantity_w = ostatok_w, quantity_gp = 0
                    row[2], row[3], row[4], row[7],  # start, manufacturer, technology, lot
                    row[5], row[6], row[8], row[9],  # wafer, quadrant, internal_lot, chip_code
                    row[12], row[13], row[14],  # note, stor, cells
                    id_chip_val, id_pack_val,
                    warehouse_type,  # Добавляем тип склада
                    date_added
                )
                
                execute_query(query_insert_cart, params_cart, fetch=False)
                added_count += 1

            return jsonify({'success': True, 'message': f'Добавлено кристаллов в корзину: {added_count}'})
        
        else:
            # Обычная логика для склада кристаллов
            if not item_id or (quantity_w <= 0 and quantity_gp <= 0):
                return jsonify({'success': False, 'message': 'Некорректные данные для добавления (ID или количество)'}), 400

            # Получаем id_chip и id_pack из invoice по item_id
            id_chip_val = None
            id_pack_val = None
            if item_id:
                invoice_data = execute_query(f"SELECT id_chip, id_pack FROM {invoice_table} WHERE item_id = %s LIMIT 1", (item_id,), fetch=True)
                if invoice_data:
                    id_chip_val = invoice_data[0][0]
                    id_pack_val = invoice_data[0][1]

            # Обновляем запрос на вставку в корзину
            query_insert_cart = """
                INSERT INTO cart (
                    user_id, item_id, 
                    cons_w, cons_gp, 
                    start, manufacturer, technology, lot, wafer, quadrant, internal_lot, chip_code, 
                    note, stor, cells, 
                    id_chip, id_pack,
                    warehouse_type,
                    date_added
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, item_id, warehouse_type) 
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
                id_chip_val, id_pack_val,
                warehouse_type,  # Добавляем тип склада
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
    # Получаем тип склада из сессии или запроса
    warehouse_type = get_warehouse_type_from_request()
    session['warehouse_type'] = warehouse_type  # Сохраняем в сессию
    
    # Запрос для отображения корзины. Имена столбцов должны соответствовать вашей таблице cart.
    query_get_cart = """
    SELECT 
        item_id, user_id,
        start, manufacturer, technology, wafer, quadrant, lot, internal_lot, chip_code,
        note, stor, cells, date_added, cons_w, cons_gp
    FROM cart
    WHERE user_id = %s AND warehouse_type = %s
    ORDER BY date_added DESC
    """
    try:
        cart_items = execute_query(query_get_cart, (user_id, warehouse_type))
    except Exception as e:
        _flask_app.logger.error(f"Ошибка загрузки корзины: {e}")
        flash("Не удалось загрузить корзину.", "danger")
        cart_items = []

    return render_template('cart.html', results=cart_items if cart_items else [], warehouse_type=warehouse_type)


@_flask_app.route('/remove_from_cart', methods=['POST'])
def remove_from_cart():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Пользователь не авторизован'}), 401

    user_id = session['user_id']
    warehouse_type = session.get('warehouse_type', 'crystals')
    data = request.get_json()
    item_id = data.get('item_id')  # ID товара (row[0] из search.html)

    if not item_id:
        return jsonify({'success': False, 'message': 'Неверный ID товара'}), 400

    query_delete_cart = "DELETE FROM cart WHERE item_id = %s AND user_id = %s AND warehouse_type = %s"
    try:
        rows_deleted = execute_query(query_delete_cart, (item_id, user_id, warehouse_type), fetch=False)
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
    warehouse_type = session.get('warehouse_type', 'crystals')
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
            query_delete = "DELETE FROM cart WHERE item_id = %s AND user_id = %s AND warehouse_type = %s"
            execute_query(query_delete, (item_id, user_id, warehouse_type), fetch=False)
            return jsonify({"success": True, "removed": True, "message": "Товар удален (количество 0)"})
        else:
            query_update = "UPDATE cart SET cons_w = %s, cons_gp = %s WHERE item_id = %s AND user_id = %s AND warehouse_type = %s"
            rows_updated = execute_query(query_update, (cons_w, cons_gp, item_id, user_id, warehouse_type), fetch=False)
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
    warehouse_type = session.get('warehouse_type', 'crystals')
    
    # Для складов "Склад пластин" и "Дальний склад" используем другой формат экспорта
    if warehouse_type in ('plates', 'far'):
        # Получаем данные из invoice таблиц через item_id для точного соответствия
        tables_warehouse = get_warehouse_tables(warehouse_type)
        invoice_table = tables_warehouse['invoice']
        query_export = f"""
        SELECT DISTINCT ON (c.item_id)
            s.name_start AS "Номер запуска",
            p.name_pr AS "Производитель",
            t.name_tech AS "Технологический процесс",
            l.name_lot AS "Партия (Lot ID)",
            w.name_wafer AS "Пластина (Wafer)",
            q.name_quad AS "Quadrant",
            il.in_lot AS "Внутренняя партия",
            nc.n_chip AS "Номер кристалла",
            ch.name_chip AS "Шифр кристалла",
            COALESCE(sc.size::text, '') AS "Размер кристалла",
            TO_CHAR(c.date_added, 'YYYY-MM-DD') AS "Дата расхода",
            c.cons_w AS "Расход Wafer, шт.",
            c.cons_gp AS "Расход GelPak, шт.",
            (c.cons_w + COALESCE(c.cons_gp, 0)) AS "Расход общий, шт.",
            c.note AS "Примечание",
            pack.name_pack AS "Упаковка",
            st.name_stor AS "Место хранения",
            cells.name_cells AS "Ячейка хранения"
        FROM cart c
        LEFT JOIN {invoice_table} inv ON c.item_id = inv.item_id
        LEFT JOIN start_p s ON inv.id_start = s.id
        LEFT JOIN pr p ON inv.id_pr = p.id
        LEFT JOIN tech t ON inv.id_tech = t.id
        LEFT JOIN lot l ON inv.id_lot = l.id
        LEFT JOIN wafer w ON inv.id_wafer = w.id
        LEFT JOIN quad q ON inv.id_quad = q.id
        LEFT JOIN in_lot il ON inv.id_in_lot = il.id
        LEFT JOIN n_chip nc ON inv.id_n_chip = nc.id
        LEFT JOIN chip ch ON inv.id_chip = ch.id
        LEFT JOIN pack ON inv.id_pack = pack.id
        LEFT JOIN size_c sc ON inv.id_size = sc.id
        LEFT JOIN stor st ON inv.id_stor = st.id
        LEFT JOIN cells ON inv.id_cells = cells.id
        WHERE c.user_id = %s AND c.warehouse_type = %s
        ORDER BY c.item_id, inv.id DESC
        """
        
        try:
            results = execute_query(query_export, (user_id, warehouse_type))
        except Exception as e:
            _flask_app.logger.error(f"Ошибка при экспорте корзины (SQL): {e}")
            flash("Не удалось подготовить данные для экспорта.", "danger")
            return redirect(url_for('cart_view'))

        if not results:
            flash("Корзина пуста. Нет данных для экспорта.", "info")
            return redirect(url_for('cart_view'))

        # Столбцы согласно требованиям для складов plates/far
        filled_columns = [
            "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)", "Пластина (Wafer)",
            "Quadrant", "Внутренняя партия", "Номер кристалла", "Шифр кристалла", "Размер кристалла",
            "Дата расхода", "Расход Wafer, шт.", "Расход GelPak, шт.", "Расход общий, шт.",
            "Примечание", "Упаковка", "Место хранения", "Ячейка хранения"
        ]
        df_from_db = pd.DataFrame(results, columns=filled_columns)
        
        # Для этих складов используем те же столбцы что и получены из БД
        final_excel_columns = filled_columns
        df_export = df_from_db.copy()
        
    else:
        # Обычный экспорт для склада кристаллов
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
            c.stor AS "Место хранения",
            c.cells AS "Ячейка хранения",
            c.note AS "Примечание",
            TO_CHAR(c.date_added, 'YYYY-MM-DD') AS "Дата расхода",
            c.cons_w AS "Расход Wafer, шт.",
            c.cons_gp AS "Расход GelPack, шт."
        FROM cart c
        LEFT JOIN chip ON c.id_chip = chip.id
        LEFT JOIN pack ON c.id_pack = pack.id
        WHERE c.user_id = %s AND c.warehouse_type = %s
        ORDER BY c.date_added DESC
        """
        try:
            results = execute_query(query_export, (user_id, warehouse_type))
        except Exception as e:
            _flask_app.logger.error(f"Ошибка при экспорте корзины (SQL): {e}")
            flash("Не удалось подготовить данные для экспорта.", "danger")
            return redirect(url_for('cart_view'))

        if not results:
            flash("Корзина пуста. Нет данных для экспорта.", "info")
            return redirect(url_for('cart_view'))

        filled_columns = [
            "Номер запуска", "Производитель", "Технологический процесс", "Партия (Lot ID)", "Пластина (Wafer)",
            "Quadrant", "Внутренняя партия", "Номер кристалла", "Шифр кристалла", "Упаковка",
            "Место хранения", "Ячейка хранения", "Примечание",
            "Дата расхода", "Расход Wafer, шт.", "Расход GelPack, шт."
        ]
        df_from_db = pd.DataFrame(results, columns=filled_columns)

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
        df_export["Расход общий, шт."] = df_export["Расход Wafer, шт."].fillna(0) + df_export["Расход GelPack, шт."].fillna(0)

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

        # ВАЖНО: Хешируйте пароли в реальном приложении!
        # from werkzeug.security import generate_password_hash
        # hashed_password = generate_password_hash(u_password)

        try:
            # Проверка, существует ли пользователь
            existing_user = execute_query("SELECT id FROM public.users WHERE username = %s", (username,))
            if existing_user:
                flash("Пользователь с таким именем уже существует.", "warning")
                return render_template('register.html')

            # query_register = "INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id"
            # params_register = (username, hashed_password) # Используйте hashed_password

            # НЕБЕЗОПАСНО: сохранение пароля как есть
            query_register = "INSERT INTO public.users (username, password) VALUES (%s, %s) RETURNING id"
            params_register = (username, u_password)

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

        # ВАЖНО: Сравнивайте хешированные пароли!
        # from werkzeug.security import check_password_hash
        # query_login = "SELECT id, username, password FROM users WHERE username = %s"

        # НЕБЕЗОПАСНО: прямое сравнение паролей
        # Пробуем разные варианты: с указанием схемы и без
        query_login = "SELECT id, username, password FROM public.users WHERE username = %s"

        try:
            _flask_app.logger.info(f"Попытка входа пользователя: {username}")
            user_data_list = execute_query(query_login, (username,))  # execute_query возвращает список
            _flask_app.logger.info(f"Результат запроса: найдено записей = {len(user_data_list) if user_data_list else 0}")
            
            if user_data_list:
                user_data = user_data_list[0]  # Берем первый элемент списка (кортеж)
                _flask_app.logger.info(f"Данные пользователя: id={user_data[0]}, username={user_data[1]}, пароль в БД (первые 3 символа)={user_data[2][:3] if user_data[2] else 'None'}...")
                
                # user_db_password = user_data[2] # Это пароль из БД (в реальном приложении - хеш)
                # if check_password_hash(user_db_password, u_password):
                db_password = user_data[2]
                _flask_app.logger.info(f"Сравнение паролей: введенный пароль (длина)={len(u_password)}, пароль в БД (длина)={len(db_password) if db_password else 0}")
                
                if db_password == u_password:  # Прямое сравнение (НЕБЕЗОПАСНО)
                    session['user_id'] = user_data[0]  # id
                    session['username'] = user_data[1]  # username
                    _flask_app.logger.info(f"Сессия установлена: user_id={session.get('user_id')}, username={session.get('username')}")
                    flash(f"Добро пожаловать, {session['username']}!", "success")

                    next_url = request.args.get('next')
                    if next_url and next_url.startswith('/'):  # Проверка безопасности next_url
                        _flask_app.logger.info(f"Редирект на next_url: {next_url}")
                        return redirect(next_url)
                    _flask_app.logger.info("Редирект на главную страницу")
                    return redirect(url_for('home'))
                else:
                    _flask_app.logger.warning(f"Неверный пароль для пользователя: {username}")
                    flash("Неправильный пароль.", "danger")
            else:
                _flask_app.logger.warning(f"Пользователь не найден: {username}")
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
    warehouse_type = session.get('warehouse_type', 'crystals')
    try:
        query_clear = "DELETE FROM cart WHERE user_id = %s AND warehouse_type = %s"
        execute_query(query_clear, (user_id, warehouse_type), fetch=False)
        flash("Корзина очищена.", "success")
    except Exception as e:
        _flask_app.logger.error(f"Ошибка очистки корзины: {e}")
        flash("Не удалось очистить корзину.", "danger")
    return redirect(url_for('cart_view'))  # Перенаправляем на страницу корзины


@_flask_app.route('/inventory', methods=['GET', 'POST'])
def inventory():
    # Получаем тип склада из запроса или сессии
    warehouse_type = get_warehouse_type_from_request()
    tables = get_warehouse_tables(warehouse_type)
    invoice_table = tables['invoice']
    consumption_table = tables['consumption']
    
    # --- НАЧАЛО ДИАГНОСТИЧЕСКОГО ЛОГИРОВАНИЯ ---
    _flask_app.logger.info(f"--- Entering /inventory route (warehouse: {warehouse_type}) ---")
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
                FROM {invoice_table}
                WHERE status = 1 -- Используем status, ID для 'Приход'
                GROUP BY id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
            ),
            return_agg AS (
                SELECT
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    SUM(quan_w) as total_return_w,
                    SUM(quan_gp) as total_return_gp,
                    SUM(COALESCE(quan_all, quan_w + quan_gp)) as total_return_all
                FROM {invoice_table}
                WHERE status = 3 -- Используем status, ID для 'Возврат'
                GROUP BY id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
            ),
            consumption_agg AS (
                SELECT
                    id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip,
                    SUM(cons_w) as total_consumed_w,
                    SUM(cons_gp) as total_consumed_gp,
                    SUM(COALESCE(cons_all, cons_w + cons_gp)) as total_consumed_all
                FROM {consumption_table}
                WHERE status = 2 -- Используем status, ID для 'Расход'
                GROUP BY id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip
            ),
            latest_attributes AS ( 
                SELECT DISTINCT ON (inv_la.id_start, inv_la.id_pr, inv_la.id_tech, inv_la.id_lot, inv_la.id_wafer, inv_la.id_quad, inv_la.id_in_lot, inv_la.id_n_chip)
                    inv_la.id_start, inv_la.id_pr, inv_la.id_tech, inv_la.id_lot, inv_la.id_wafer, inv_la.id_quad, inv_la.id_in_lot, inv_la.id_n_chip,
                    inv_la.note, inv_la.id_pack, inv_la.id_stor, inv_la.id_cells, inv_la.date
                FROM {invoice_table} inv_la
                WHERE inv_la.status = 1 -- Берем атрибуты только из записей ПРИХОДА
                ORDER BY inv_la.id_start, inv_la.id_pr, inv_la.id_tech, inv_la.id_lot, inv_la.id_wafer, inv_la.id_quad, inv_la.id_in_lot, inv_la.id_n_chip, inv_la.date DESC, inv_la.id DESC
            ),
            all_unique_keys_source AS (
                SELECT id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip FROM {invoice_table}
                UNION 
                SELECT id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip FROM {consumption_table}
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
                COALESCE(la.note, '') AS "Примечание",
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
                    "Примечание",
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
            FROM {invoice_table} inv
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
            FROM {consumption_table} cons
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
                           selected_chip_code_filter=selected_chip_code_filter_form,
                           warehouse_type=warehouse_type
                           )


# Создаем ASGI-совместимое приложение для Uvicorn.
app = WSGIMiddleware(_flask_app)

# Блок для запуска приложения
if __name__ == '__main__':
    import sys
    
    # Проверяем режим запуска из переменных окружения
    mode = os.getenv('MODE', 'development').lower()
    is_production = mode == 'production'
    
    if is_production:
        # Production режим: используем Waitress (кроссплатформенный WSGI сервер)
        try:
            from waitress import serve
            print("=" * 60)
            print("Запуск в PRODUCTION режиме через Waitress WSGI сервер")
            print("=" * 60)
            serve(_flask_app, host="0.0.0.0", port=8089, threads=4)
        except ImportError:
            print("ОШИБКА: Waitress не установлен. Установите: pip install waitress")
            print("Запуск в режиме разработки...")
            _flask_app.run(debug=False, host="0.0.0.0", port=8089)
    else:
        # Development режим: используем встроенный сервер Flask (только для разработки)
        print("=" * 60)
        print("ВНИМАНИЕ: Запуск в режиме РАЗРАБОТКИ")
        print("Для production установите MODE=production в .env")
        print("=" * 60)
        _flask_app.run(debug=True, host="0.0.0.0", port=8089)