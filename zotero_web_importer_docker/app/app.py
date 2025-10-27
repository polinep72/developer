# app/app.py
from flask import Flask, render_template, request, jsonify
import os
import pandas as pd
from werkzeug.utils import secure_filename
import logging  # Flask использует стандартный logging
import sys
import shutil  # Для удаления временных Excel файлов

# Импортируем наш основной модуль логики Zotero
import zotero_importer_core

# --- Конфигурация приложения Flask ---
UPLOAD_FOLDER_EXCEL = 'uploads_temp_excel'  # Временные Excel будут внутри контейнера /app/uploads_temp_excel
ALLOWED_EXTENSIONS = {'xlsx'}

app = Flask(__name__)  # Имя текущего модуля
app.config['UPLOAD_FOLDER_EXCEL'] = UPLOAD_FOLDER_EXCEL
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB для Excel файла

# --- ПОЛУЧЕНИЕ ПУТИ К БАЗОВОЙ PDF ПАПКЕ ИЗ ПЕРЕМЕННОЙ ОКРУЖЕНИЯ ---
# Этот путь будет ВНУТРИ КОНТЕЙНЕРА, смонтированный из Z:\ (или его части) на хосте.
# docker-compose.yml устанавливает SERVER_BASE_PDF_PATH_IN_CONTAINER.
DEFAULT_LOCAL_PDF_BASE_PATH_FOR_APP = os.path.join(os.getcwd(), 'local_pdf_search_base')  # Для запуска без Docker
SERVER_BASE_PDF_PATH = os.getenv('SERVER_BASE_PDF_PATH_IN_CONTAINER', DEFAULT_LOCAL_PDF_BASE_PATH_FOR_APP)
app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH'] = SERVER_BASE_PDF_PATH

# Создаем папки, если они не существуют (особенно для локального запуска)
# Dockerfile должен создать /app/uploads_temp_excel и /app/logs
os.makedirs(app.config['UPLOAD_FOLDER_EXCEL'], exist_ok=True)
if SERVER_BASE_PDF_PATH == DEFAULT_LOCAL_PDF_BASE_PATH_FOR_APP:  # Если используем путь по умолчанию
    os.makedirs(app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH'], exist_ok=True)
    # app.logger уже будет настроен ниже, используем logging напрямую для ранних сообщений
    logging.info(
        f"Создана папка по умолчанию для PDF (локальный запуск): {app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH']}")

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ (централизованная для всего приложения) ---
# Используем путь к лог-файлу, определенный в zotero_importer_core,
# который, в свою очередь, получает его из переменной окружения LOG_PATH_IN_CONTAINER.
LOG_FILE_PATH = zotero_importer_core.LOG_FILE

# Очищаем существующие обработчики корневого логгера перед новой конфигурацией
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,  # Уровень логирования по умолчанию
    format="%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, encoding='utf-8', mode='a'),  # Дозапись в файл
        logging.StreamHandler(sys.stdout)  # Вывод в консоль
    ]
)
# Устанавливаем уровень для логгера нашего модуля zotero_importer_core
logging.getLogger('zotero_importer_core').setLevel(logging.INFO)  # или DEBUG
# Логгер Flask (app.logger) автоматически будет использовать эту корневую конфигурацию.
app.logger.info(f"--- Flask приложение запущено. Логирование настроено. Файл логов: {LOG_FILE_PATH} ---")


# --- КОНЕЦ КОНФИГУРАЦИИ ЛОГИРОВАНИЯ ---


def allowed_file(filename):
    """Проверяет, имеет ли файл разрешенное расширение."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Отображает главную страницу."""
    app.logger.info(
        f"Запрос главной страницы /. Базовый путь PDF в контейнере: {app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH']}")
    # Передаем пример базового пути в шаблон для отображения пользователю
    # Это путь ВНУТРИ КОНТЕЙНЕРА, который соответствует Z:\ на хосте
    base_path_display_in_container = app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH']
    if not base_path_display_in_container.endswith(os.sep):
        base_path_display_in_container += os.sep

    # Пользователю нужно показать, как выглядит его Z:\ на хосте
    # Это значение мы не знаем наверняка, но можем предположить или попросить указать
    # Для примера, можно показать "Z:\\" или "\\\\192.168.1.10\\work\\"
    # Пока оставим подсказку в HTML более общей.
    return render_template('index.html')  # base_pdf_host_example=HOST_PATH_FOR_Z_DRIVE


@app.route('/preview_excel', methods=['POST'])
def preview_excel():
    """
    Обрабатывает загрузку Excel-файла и имени подпапки PDF.
    Проверяет пути и возвращает HTML-таблицу для предпросмотра.
    """
    app.logger.info("Получен POST-запрос на /preview_excel")
    if 'excel_file' not in request.files:
        app.logger.warning("Файл Excel не найден в данных запроса.")
        return jsonify({"status": "error", "message": "Файл Excel не был отправлен."})

    excel_file = request.files['excel_file']

    if excel_file.filename == '':
        app.logger.warning("Имя файла Excel в запросе пустое.")
        return jsonify({"status": "error", "message": "Имя файла Excel не выбрано."})

    # Пользователь вводит имя подпапки ОТНОСИТЕЛЬНО базового пути (смонтированного Z:\)
    # Имя поля в HTML: name="pdf_subfolder_name" (как в последнем index.html)
    # или name="search_root_directory_on_server" если вы его так назвали в HTML
    pdf_subfolder_name_from_user = request.form.get('pdf_subfolder_name', '').strip()  # Используем 'pdf_subfolder_name'
    if not pdf_subfolder_name_from_user:  # Если это поле не пришло, пробуем старое имя
        pdf_subfolder_name_from_user = request.form.get('search_root_directory_on_server', '').strip()

    app.logger.info(f"Получено имя подпапки PDF от пользователя: '{pdf_subfolder_name_from_user}'")

    if not pdf_subfolder_name_from_user:
        app.logger.warning("Имя подпапки PDF не указано пользователем.")
        return jsonify({"status": "error",
                        "message": "Пожалуйста, укажите имя Вашей папки с PDF файлами (относительно общего ресурса)."})

    # Очистка имени подпапки от потенциально опасных конструкций
    # Заменяем обратные слеши на прямые для унификации и удаляем начальные/конечные
    clean_relative_subfolder_path = pdf_subfolder_name_from_user.replace('\\', '/').strip('/')

    # Предотвращаем выход наверх ('../')
    # Разбираем путь на компоненты и проверяем каждый
    path_components = clean_relative_subfolder_path.split('/')
    if '..' in path_components or '.' in path_components:  # Также запрещаем просто '.'
        app.logger.warning(
            f"Недопустимый относительный путь к подпапке PDF (содержит '.' или '..'): '{pdf_subfolder_name_from_user}' -> '{clean_relative_subfolder_path}'")
        return jsonify({"status": "error",
                        "message": "Имя подпапки PDF не должно содержать '.' или '..' и должно быть корректным именем папки."})

    # secure_filename не очень подходит для путей, он больше для имен файлов.
    # Мы будем использовать clean_relative_subfolder_path после базовых проверок.
    # Если после очистки путь пустой (например, был только '/')
    if not clean_relative_subfolder_path:
        app.logger.warning(f"Имя подпапки PDF стало пустым после очистки: '{pdf_subfolder_name_from_user}'")
        return jsonify({"status": "error", "message": "Некорректное имя подпапки PDF."})

    # Конструируем полный путь к папке поиска ВНУТРИ КОНТЕЙНЕРА
    # app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH'] это, например, /mnt/shared_z_drive
    full_search_root_in_container = os.path.join(app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH'],
                                                 clean_relative_subfolder_path)
    full_search_root_in_container = os.path.normpath(
        full_search_root_in_container)  # Нормализуем путь (убирает ./, // и т.д.)

    app.logger.info(f"Сконструирован полный путь для поиска PDF внутри контейнера: '{full_search_root_in_container}'")

    # Проверка безопасности: убедимся, что сконструированный путь не выходит за пределы базового пути
    normalized_base_path = os.path.normpath(app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH'])
    if not full_search_root_in_container.startswith(normalized_base_path):
        app.logger.error(
            f"Попытка выхода за пределы базовой директории PDF! База: '{normalized_base_path}', Результат: '{full_search_root_in_container}'")
        return jsonify({"status": "error", "message": "Ошибка безопасности: недопустимый путь к папке PDF."})

    search_path_validation_message = ""
    # Проверяем существование этой директории ВНУТРИ КОНТЕЙНЕРА
    if not os.path.isdir(full_search_root_in_container):
        app.logger.warning(f"Папка для поиска PDF '{full_search_root_in_container}' не найдена ВНУТРИ КОНТЕЙНЕРА.")
        search_path_validation_message = f"Ошибка: Указанная папка PDF ('{pdf_subfolder_name_from_user}' на общем ресурсе) не найдена или не доступна по пути '{full_search_root_in_container}' внутри системы. Проверьте имя папки и настройки монтирования Docker."
        # Важно не возвращать ошибку здесь сразу, если zotero_importer_core.find_file_path
        # сам может корректно обработать несуществующую search_root_dir (он вернет None для file_path).
        # Но для пользователя лучше дать знать сразу.
        return jsonify({"status": "error", "message": search_path_validation_message})
    else:
        app.logger.info(
            f"Папка для поиска PDF '{full_search_root_in_container}' (внутри контейнера) найдена и является директорией.")
        search_path_validation_message = f"Папка для поиска PDF (на общем ресурсе, подпапка '{pdf_subfolder_name_from_user}') найдена. Внутренний путь: {full_search_root_in_container}"

    # Сохраняем Excel файл во временную папку внутри контейнера
    if excel_file and allowed_file(excel_file.filename):
        excel_filename_secure = secure_filename(excel_file.filename)
        # Путь для сохранения Excel внутри контейнера
        excel_file_path_in_container = os.path.join(app.config['UPLOAD_FOLDER_EXCEL'], excel_filename_secure)
        try:
            excel_file.save(excel_file_path_in_container)
            app.logger.info(
                f"Excel файл '{excel_filename_secure}' сохранен в '{excel_file_path_in_container}' (внутри контейнера).")

            df = pd.read_excel(excel_file_path_in_container, engine='openpyxl')
            # Ограничиваем количество строк для предпросмотра
            table_html = df.head(20).to_html(classes='table table-striped', escape=False, index=False, border=0)

            return jsonify({
                "status": "success",
                "table_html": table_html,
                "excel_file_path": excel_file_path_in_container,  # Путь к Excel ВНУТРИ контейнера
                "search_root_path": full_search_root_in_container,  # Полный путь к папке поиска PDF ВНУТРИ контейнера
                "search_path_message": search_path_validation_message
            })
        except Exception as e:
            app.logger.error(f"Ошибка при обработке или сохранении Excel файла '{excel_filename_secure}': {e}",
                             exc_info=True)
            return jsonify({"status": "error", "message": f"Ошибка обработки Excel: {e}"})
    else:
        app.logger.warning(
            f"Недопустимый тип Excel файла: {excel_file.filename if excel_file else 'Файл не предоставлен'}")
        return jsonify({"status": "error", "message": "Недопустимый тип файла Excel. Разрешены только .xlsx"})


@app.route('/import_to_zotero', methods=['POST'])
def import_to_zotero_route():
    """Запускает основной процесс импорта в Zotero."""
    app.logger.info("Получен POST-запрос на /import_to_zotero")
    data = request.get_json()
    if not data:
        app.logger.error("Пустые JSON данные в запросе на /import_to_zotero.")
        return jsonify(
            {"status": "error", "message": "Нет данных в запросе.", "processed": 0, "skipped": 0, "errors": 1})

    excel_file_path_in_container = data.get('excel_file_path')
    # Это ПОЛНЫЙ ПУТЬ к подпапке PDF ВНУТРИ КОНТЕЙНЕРА
    search_root_directory_in_container = data.get('search_root_directory')

    if not excel_file_path_in_container or not os.path.exists(
            excel_file_path_in_container):  # Проверяем путь ВНУТРИ контейнера
        app.logger.error(f"Файл Excel '{excel_file_path_in_container}' не найден ВНУТРИ КОНТЕЙНЕРА.")
        return jsonify({"status": "error", "message": "Файл Excel не найден на сервере.", "processed": 0, "skipped": 0,
                        "errors": 1})

    if not search_root_directory_in_container or not os.path.isdir(
            search_root_directory_in_container):  # Проверяем путь ВНУТРИ контейнера
        app.logger.error(
            f"Корневая папка для поиска PDF '{search_root_directory_in_container}' недействительна или не найдена ВНУТРИ КОНТЕЙНЕРА.")
        return jsonify(
            {"status": "error", "message": "Ошибка с путем к папке для поиска PDF на сервере.", "processed": 0,
             "skipped": 0, "errors": 1})

    app.logger.info(
        f"Запуск импорта в Zotero: Excel='{excel_file_path_in_container}', Корень поиска PDF='{search_root_directory_in_container}' (пути внутри контейнера)")

    try:
        # Вызываем основную логику импорта
        result = zotero_importer_core.run_zotero_import(excel_file_path_in_container,
                                                        search_root_directory_in_container)
        app.logger.info(f"Результат импорта от zotero_importer_core: {result}")

        # Очистка временного Excel файла ПОСЛЕ импорта
        if excel_file_path_in_container and os.path.exists(excel_file_path_in_container):
            try:
                os.remove(excel_file_path_in_container)
                app.logger.info(f"Временный Excel файл удален: {excel_file_path_in_container}")
            except Exception as e_clean_xls:
                app.logger.error(
                    f"Ошибка удаления временного Excel файла {excel_file_path_in_container}: {e_clean_xls}")

        # Временную папку PDF мы не создавали специально для этой сессии (используем смонтированную),
        # поэтому и удалять ее здесь не нужно.

        return jsonify(result)
    except Exception as e:
        app.logger.critical(f"Критическая ошибка во время выполнения zotero_importer_core.run_zotero_import: {e}",
                            exc_info=True)
        return jsonify(
            {"status": "error", "message": f"Критическая ошибка на сервере во время импорта: {e}", "processed": 0,
             "skipped": 0, "errors": 1})


@app.route('/get_logs')
def get_logs():
    """Возвращает содержимое лог-файла."""
    try:
        with open(zotero_importer_core.LOG_FILE, 'r', encoding='utf-8') as f:
            log_content = f.read()
        return log_content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except FileNotFoundError:
        app.logger.warning(f"Лог-файл {zotero_importer_core.LOG_FILE} не найден при запросе /get_logs.")
        return "Лог-файл не найден.", 404
    except Exception as e:
        app.logger.error(f"Ошибка чтения лог-файла {zotero_importer_core.LOG_FILE}: {e}", exc_info=True)
        return f"Ошибка чтения лог-файла: {e}", 500


if __name__ == '__main__':
    try:
        zotero_importer_core.check_python_version()
    except RuntimeError as e:
        # Используем logging напрямую, так как app.logger может быть еще не полностью инициализирован
        logging.critical(f"КРИТИЧЕСКАЯ ОШИБКА ВЕРСИИ PYTHON: {e}. Приложение не будет запущено.")
        sys.exit(1)  # Важно завершить работу, если версия Python не подходит

    zotero_importer_core.log_package_versions()  # Логируем версии пакетов

    app.logger.info(f"--- Запуск Flask приложения (app.py) ---")
    app.logger.info(f"Flask будет слушать на хосте 0.0.0.0 и порту 8086 (для Docker).")
    app.logger.info(
        f"Базовый путь для поиска PDF (внутри контейнера, из ENV): {app.config['SERVER_BASE_PDF_PATH_FOR_SEARCH']}")
    app.logger.info(f"Папка для временных Excel файлов (внутри контейнера): {app.config['UPLOAD_FOLDER_EXCEL']}")
    app.logger.info(
        f"Путь к файлу логов (внутри контейнера, из ENV zotero_importer_core): {zotero_importer_core.LOG_FILE}")

    # При запуске через `docker-compose up`, эта команда `app.run` будет выполнена,
    # так как CMD в Dockerfile ["python", "-u", "app.py"].
    # `host='0.0.0.0'` важно, чтобы Flask был доступен извне контейнера.
    app.run(host='0.0.0.0', port=8086, debug=True)  # debug=True для разработки