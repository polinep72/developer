# app.py
from flask import Flask, render_template, request, jsonify
import os
import pandas as pd
from werkzeug.utils import secure_filename
import logging
import sys
# import shutil # Не нужен для этого подхода с PDF

import zotero_importer_core

UPLOAD_FOLDER_EXCEL = 'uploads_temp_excel'
ALLOWED_EXTENSIONS = {'xlsx'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER_EXCEL'] = UPLOAD_FOLDER_EXCEL
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER_EXCEL'], exist_ok=True)

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ (как раньше) ---
LOG_FILE = zotero_importer_core.LOG_FILE
# ... (ваша полная конфигурация logging.basicConfig) ...
for handler_to_remove in logging.root.handlers[:]:
    logging.root.removeHandler(handler_to_remove)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logging.getLogger('zotero_importer_core').setLevel(logging.INFO)


# --- КОНЕЦ КОНФИГУРАЦИИ ЛОГИРОВАНИЯ ---

def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    app.logger.info("Запрос главной страницы /")
    return render_template('index.html')


@app.route('/preview_excel', methods=['POST'])
def preview_excel():
    app.logger.info("Запрос /preview_excel (POST)")
    if 'excel_file' not in request.files:
        app.logger.warning("Файл Excel не найден в запросе.")
        return jsonify({"status": "error", "message": "Файл Excel не был отправлен."})

    excel_file = request.files['excel_file']

    if excel_file.filename == '':
        app.logger.warning("Имя файла Excel пустое.")
        return jsonify({"status": "error", "message": "Имя файла Excel не выбрано."})

    # --- ПОЛУЧЕНИЕ И ПРОВЕРКА КОРНЕВОЙ ПАПКИ ДЛЯ ПОИСКА PDF ---
    # Имя поля из HTML: name="search_root_directory_on_server"
    search_root_dir_from_input = request.form.get('search_root_directory_on_server', '').strip()
    app.logger.info(f"Получена корневая папка для поиска PDF от пользователя: '{search_root_dir_from_input}'")

    if not search_root_dir_from_input:
        app.logger.warning("Корневая папка для поиска PDF не указана пользователем.")
        return jsonify(
            {"status": "error", "message": "Пожалуйста, укажите корневую папку на сервере для поиска PDF файлов."})

    # Проверяем, существует ли указанная папка на сервере и является ли она директорией
    # НЕ НУЖНО здесь делать `secure_filename` или `os.path.join` с базовым путем,
    # так как пользователь указывает ПОЛНЫЙ АБСОЛЮТНЫЙ путь к корневой директории поиска.
    # Однако, если вы хотите ограничить поиск определенной "песочницей" на сервере,
    # то здесь нужна будет логика проверки, что `search_root_dir_from_input` находится внутри разрешенной зоны.
    # Для простоты пока предполагаем, что введенный путь можно использовать напрямую, если он существует.
    # НО ЭТО МОЖЕТ БЫТЬ НЕБЕЗОПАСНО, ЕСЛИ ПОЛЬЗОВАТЕЛИ НЕ ДОВЕРЕННЫЕ!

    # ВАЖНО ДЛЯ БЕЗОПАСНОСТИ: Если приложение доступно недоверенным пользователям,
    # НЕЛЬЗЯ позволять им указывать произвольные пути на сервере.
    # В таком случае, `search_root_dir_from_input` должно быть, например, именем подпапки
    # внутри заранее определенной БЕЗОПАСНОЙ корневой директории на сервере.
    # Сейчас я оставлю проверку на существование указанного полного пути.

    final_search_root_path = os.path.normpath(search_root_dir_from_input)  # Нормализуем путь

    search_path_message = ""
    if not os.path.isdir(final_search_root_path):
        app.logger.warning(
            f"Указанная корневая папка для поиска PDF '{final_search_root_path}' не найдена на сервере или не является директорией.")
        search_path_message = f"Ошибка: Корневая папка для поиска PDF '{final_search_root_path}' не найдена на сервере."
        return jsonify({"status": "error", "message": search_path_message})
    else:
        app.logger.info(f"Корневая папка для поиска PDF '{final_search_root_path}' найдена на сервере.")
        search_path_message = f"Корневая папка для поиска PDF на сервере: {final_search_root_path} - найдена."
    # --- КОНЕЦ ПРОВЕРКИ КОРНЕВОЙ ПАПКИ ДЛЯ ПОИСКА PDF ---

    if excel_file and allowed_file(excel_file.filename):
        excel_filename_secure = secure_filename(excel_file.filename)
        excel_file_path_on_server = os.path.join(app.config['UPLOAD_FOLDER_EXCEL'], excel_filename_secure)
        try:
            excel_file.save(excel_file_path_on_server)
            app.logger.info(f"Excel файл '{excel_filename_secure}' сохранен в '{excel_file_path_on_server}'")

            df = pd.read_excel(excel_file_path_on_server, engine='openpyxl')
            table_html = df.head(20).to_html(classes='table table-striped', escape=False, index=False, border=0)

            return jsonify({
                "status": "success",
                "table_html": table_html,
                "excel_file_path": excel_file_path_on_server,
                "search_root_path": final_search_root_path,  # Передаем проверенный путь
                "search_path_message": search_path_message
            })
        except Exception as e:
            app.logger.error(f"Ошибка при обработке Excel файла '{excel_filename_secure}': {e}", exc_info=True)
            return jsonify({"status": "error", "message": f"Ошибка обработки Excel: {e}"})
    else:
        app.logger.warning(f"Недопустимый тип Excel файла: {excel_file.filename if excel_file else 'None'}")
        return jsonify({"status": "error", "message": "Недопустимый тип файла. Разрешены только .xlsx"})


@app.route('/import_to_zotero', methods=['POST'])
def import_to_zotero_route():
    app.logger.info("Запрос /import_to_zotero (POST)")
    data = request.get_json()
    excel_file_path = data.get('excel_file_path')
    # Получаем КОРНЕВУЮ ДИРЕКТОРИЮ ДЛЯ ПОИСКА
    search_root_directory_on_server = data.get('search_root_directory')

    if not excel_file_path or not os.path.exists(excel_file_path):
        return jsonify({"status": "error", "message": "Файл Excel не найден на сервере.", "processed": 0, "skipped": 0,
                        "errors": 1})

    if not search_root_directory_on_server or not os.path.isdir(search_root_directory_on_server):
        app.logger.error(
            f"Корневая папка для поиска PDF '{search_root_directory_on_server}' недействительна или не найдена.")
        return jsonify(
            {"status": "error", "message": "Ошибка с корневой папкой для поиска PDF.", "processed": 0, "skipped": 0,
             "errors": 1})

    app.logger.info(
        f"Запуск импорта Zotero: Excel='{excel_file_path}', Корневая папка поиска PDF='{search_root_directory_on_server}'")

    try:
        # Передаем search_root_directory_on_server в качестве второго аргумента
        result = zotero_importer_core.run_zotero_import(excel_file_path, search_root_directory_on_server)
        app.logger.info(f"Результат импорта Zotero: {result}")

        # Очистка временного Excel файла ПОСЛЕ импорта
        if excel_file_path and os.path.exists(excel_file_path):
            try:
                os.remove(excel_file_path)
                app.logger.info(f"Временный Excel файл удален: {excel_file_path}")
            except Exception as e_clean_xls:
                app.logger.error(f"Ошибка удаления временного Excel {excel_file_path}: {e_clean_xls}")

        # Временную папку PDF мы не создавали и не копировали туда файлы в этом подходе, так что удалять ее не нужно.

        return jsonify(result)
    except Exception as e:
        app.logger.critical(f"Критическая ошибка при импорте в Zotero: {e}", exc_info=True)
        return jsonify(
            {"status": "error", "message": f"Критическая ошибка на сервере: {e}", "processed": 0, "skipped": 0,
             "errors": 1})


# ... (get_logs и if __name__ == '__main__': остаются такими же, КРОМЕ УДАЛЕНИЯ SERVER_BASE_PDF_COLLECTIONS_PATH из лога запуска, если он больше не нужен) ...
@app.route('/get_logs')
def get_logs():
    # ... (код get_logs) ...
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log_content = f.read()
        return log_content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except FileNotFoundError:
        return "Лог-файл не найден.", 404
    except Exception as e:
        return f"Ошибка чтения лог-файла: {e}", 500


if __name__ == '__main__':
    try:
        zotero_importer_core.check_python_version()
    except RuntimeError as e:
        logging.critical(f"Ошибка версии Python: {e}")
        sys.exit(1)

    zotero_importer_core.log_package_versions()

    app.logger.info(
        f"Запуск Flask приложения на 192.168.1.139:8086. Папка для Excel: {app.config['UPLOAD_FOLDER_EXCEL']}")
    app.run(host='0.0.0.0', port=8086, debug=True)