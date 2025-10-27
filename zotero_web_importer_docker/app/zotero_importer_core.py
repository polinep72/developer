# app/zotero_importer_core.py
# -*- coding: utf-8 -*-

import os
import pandas as pd
from pyzotero import zotero
import logging
import sys
import importlib.metadata
from dotenv import load_dotenv  # Для загрузки .env файла, если он есть в app/

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
# load_dotenv() # Обычно .env загружается один раз при старте приложения (в app.py или docker-compose)
# Если вы хотите, чтобы этот модуль мог работать автономно и читать свой .env из app/, раскомментируйте.
# Но при запуске через docker-compose переменные уже будут в окружении.

ZOTERO_API_KEY = os.getenv('ZOTERO_API_KEY')  # Будет взято из окружения, установленного docker-compose
ZOTERO_GROUP_ID = os.getenv('ZOTERO_GROUP_ID')
ZOTERO_LIBRARY_TYPE = os.getenv('ZOTERO_LIBRARY_TYPE', 'group')

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
# Путь к логам будет получен из переменной окружения LOG_PATH_IN_CONTAINER
# Задаем имя файла логов
LOG_FILE_NAME = "zotero_excel_importer.log"

# Получаем путь к директории для логов из переменной окружения
# Если переменная не установлена (например, при локальном запуске без Docker Compose),
# используем подпапку 'logs_core' относительно текущего файла.
DEFAULT_CORE_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs_core_local')
LOG_DIR_FROM_ENV = os.getenv('LOG_PATH_IN_CONTAINER', DEFAULT_CORE_LOG_DIR)

# Убедимся, что путь к директории логов абсолютный, если он был задан относительно
if not os.path.isabs(LOG_DIR_FROM_ENV) and LOG_DIR_FROM_ENV == DEFAULT_CORE_LOG_DIR:
    # Это уже сделано выше для DEFAULT_CORE_LOG_DIR
    pass
elif not os.path.isabs(LOG_DIR_FROM_ENV):  # Если из ENV пришел относительный путь
    # Предполагаем, что он должен быть относительно рабочей директории /app в контейнере
    LOG_DIR_FROM_ENV = os.path.join(os.getcwd(), LOG_DIR_FROM_ENV)

# Создаем папку для логов, если ее нет.
# Dockerfile уже должен был создать /app/logs, но эта проверка не помешает.
try:
    os.makedirs(LOG_DIR_FROM_ENV, exist_ok=True)
    LOG_FILE = os.path.join(LOG_DIR_FROM_ENV, LOG_FILE_NAME)
except OSError as e:
    # Если не удалось создать папку (например, из-за прав), пишем лог в текущую директорию
    print(f"Warning: Could not create log directory {LOG_DIR_FROM_ENV}. Error: {e}. Logging to current directory.")
    LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_FILE_NAME)

# Получаем логгер для этого модуля. Основная конфигурация (handlers, format) будет в app.py.
logger = logging.getLogger(__name__)
# Если хотите, чтобы этот модуль имел свою базовую конфигурацию на случай прямого запуска:
# if not logger.hasHandlers():
#     logging.basicConfig(level=logging.INFO, filename=LOG_FILE, filemode='a',
#                         format="%(asctime)s - %(levelname)s - [%(name)s:%(funcName)s:%(lineno)d] - %(message)s")


# --- КОНСТАНТЫ СТОЛБЦОВ ---
COL_FILENAME = "Наименование файла"
COL_ZOTERO_COLLECTION = "раздел Zotero"
COL_TAGS = "Метки"
COL_NOTES_CONTENT = "Соответствие пунктам ТЗ"
COL_ABSTRACT_CONTENT = "Краткое описание"
COL_BIBLIO_DESCRIPTION = "Библиографическое описание"


# --- ФУНКЦИИ ---
def log_package_versions():
    packages = ["pandas", "openpyxl", "pyzotero", "python-dotenv", "Flask", "Werkzeug"]
    logger.info("--- Версии установленных пакетов ---")
    for pkg_name in packages:
        try:
            version = importlib.metadata.version(pkg_name)
            logger.info(f"{pkg_name}: {version}")
        except importlib.metadata.PackageNotFoundError:
            logger.warning(f"Пакет {pkg_name} не найден.")
        except Exception as e:
            logger.error(f"Не удалось получить версию пакета {pkg_name}: {e}")
    logger.info("------------------------------------")


def check_python_version():
    logger.info(f"Проверка версии Python: {sys.version}")
    if sys.version_info < (3, 8):  # Можно поднять минимальную версию, если нужно
        error_message = f"ОШИБКА: Этот скрипт требует Python 3.8 или выше. Вы используете Python {sys.version}."
        logger.critical(error_message)
        raise RuntimeError(error_message)
    logger.info("Версия Python соответствует требованиям.")


def find_file_path(filename, search_root_dir):
    logger.debug(f"Поиск файла '{filename}' в директории (внутри контейнера): '{search_root_dir}'")
    # Важно: search_root_dir это путь ВНУТРИ контейнера, который Docker смапил на Z:\... на хосте
    if not os.path.isdir(search_root_dir):
        logger.error(
            f"Директория для поиска '{search_root_dir}' не существует или не является директорией внутри контейнера.")
        return None

    for root, _, files in os.walk(search_root_dir):
        for f_name in files:  # Ищем без учета регистра для имен файлов, если это Windows-шара
            if f_name.lower() == filename.lower():  # Сравнение без учета регистра
                found_path = os.path.join(root, f_name)  # Используем оригинальное имя f_name для пути
                logger.info(f"Файл '{filename}' (найден как '{f_name}') по пути: {found_path}")
                return os.path.normpath(found_path)
    logger.warning(f"Файл '{filename}' НЕ найден в '{search_root_dir}' и ее поддиректориях.")
    return None


def get_or_create_hierarchical_collection(zot, full_collection_path_str, collections_cache):
    # ... (Ваша полная реализация этой функции без изменений, использует logger) ...
    normalized_path = full_collection_path_str.replace("\\", "/").strip()
    if not normalized_path:
        logger.error("Пустой или некорректный путь к коллекции предоставлен (входная строка: '%s').",
                     full_collection_path_str)
        return None
    if normalized_path in collections_cache:
        cached_id = collections_cache[normalized_path]
        logger.debug(f"Полный путь '{normalized_path}' найден в кеше (конечный ID: {cached_id}).")
        return cached_id
    path_parts = [part.strip() for part in normalized_path.split('/') if part.strip()]
    if not path_parts:
        logger.error(
            f"После обработки путь к коллекции '{full_collection_path_str}' (нормализованный: '{normalized_path}') оказался пустым.")
        return None
    current_parent_id = False
    current_processed_path_key = ""
    final_collection_id_for_path = None
    for i, part_name in enumerate(path_parts):
        if current_processed_path_key:
            current_processed_path_key += "/" + part_name
        else:
            current_processed_path_key = part_name
        if current_processed_path_key in collections_cache:
            collection_id_for_this_part = collections_cache[current_processed_path_key]
            logger.debug(
                f"Промежуточный/конечный путь '{current_processed_path_key}' найден в кеше. ID: {collection_id_for_this_part}")
            current_parent_id = collection_id_for_this_part
            final_collection_id_for_path = collection_id_for_this_part
            continue
        found_collection_this_level = False
        target_collection_id_this_level = None
        try:
            if current_parent_id:
                logger.debug(f"Запрос дочерних коллекций для родителя ID: '{current_parent_id}', ищем: '{part_name}'")
                child_collections = zot.collections(parentCollection=current_parent_id)
            else:
                logger.debug(f"Запрос коллекций верхнего уровня, ищем: '{part_name}'")
                child_collections = zot.collections(top=True)
        except Exception as e:
            logger.error(
                f"Ошибка при получении списка коллекций для '{part_name}' (родитель: {current_parent_id}): {e}",
                exc_info=True)
            return None
        for coll in child_collections:
            if coll['data']['name'] == part_name:
                target_collection_id_this_level = coll['key']
                found_collection_this_level = True
                logger.info(
                    f"Найдена существующая коллекция '{part_name}' (ID: {target_collection_id_this_level}) в '{current_parent_id if current_parent_id else 'ROOT'}'")
                break
        if found_collection_this_level:
            current_parent_id = target_collection_id_this_level
        else:
            logger.info(
                f"Коллекция '{part_name}' не найдена. Создание новой в '{current_parent_id if current_parent_id else 'ROOT'}'...")
            collection_data_to_create = {'name': part_name, 'parentCollection': current_parent_id}
            try:
                resp = zot.create_collections([collection_data_to_create])
                if resp and 'successful' in resp and resp['successful']:
                    created_item_info = list(resp['successful'].values())[0]
                    new_collection_key = created_item_info['key']
                    current_parent_id = new_collection_key
                    logger.info(f"Коллекция '{part_name}' успешно создана. ID: {current_parent_id}")
                else:
                    logger.error(f"Ошибка при создании коллекции '{part_name}'. Ответ Zotero: {resp}")
                    return None
            except Exception as e:
                logger.error(f"Исключение при создании коллекции '{part_name}': {e}", exc_info=True)
                return None
        collections_cache[current_processed_path_key] = current_parent_id
        logger.debug(f"Кеширован путь '{current_processed_path_key}' с ID: {current_parent_id}")
        final_collection_id_for_path = current_parent_id
    return final_collection_id_for_path


def run_zotero_import(excel_file_path, search_root_directory_in_container):
    logger.info(f"НАЧАЛО ПРОЦЕССА ИМПОРТА ZOTERO")
    logger.info(f"Excel файл: {excel_file_path}")
    logger.info(f"Корневая директория для поиска PDF (внутри контейнера): {search_root_directory_in_container}")

    if not ZOTERO_API_KEY or not ZOTERO_GROUP_ID:
        msg = "КРИТИЧЕСКАЯ ОШИБКА: Переменные окружения ZOTERO_API_KEY или ZOTERO_GROUP_ID не установлены."
        logger.critical(msg)
        return {"status": "error", "message": msg, "processed": 0, "skipped": 0, "errors": 1}
    logger.info(f"Конфигурация Zotero: Group ID='{ZOTERO_GROUP_ID}', Library Type='{ZOTERO_LIBRARY_TYPE}'")

    try:
        df = pd.read_excel(excel_file_path, dtype=str, engine='openpyxl')
        logger.info(f"Успешно прочитано {len(df)} строк из Excel файла: {excel_file_path}")
    except Exception as e:
        logger.critical(f"Критическая ошибка чтения Excel файла '{excel_file_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"Ошибка чтения Excel: {e}", "processed": 0, "skipped": 0, "errors": 1}

    required_cols = [COL_FILENAME, COL_ZOTERO_COLLECTION, COL_TAGS, COL_NOTES_CONTENT, COL_ABSTRACT_CONTENT,
                     COL_BIBLIO_DESCRIPTION]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        msg = f"В Excel файле отсутствуют обязательные столбцы: {', '.join(missing_cols)}."
        logger.critical(msg)
        return {"status": "error", "message": msg, "processed": 0, "skipped": 0, "errors": 1}
    logger.info("Все необходимые столбцы найдены в Excel файле.")

    try:
        zot = zotero.Zotero(ZOTERO_GROUP_ID, ZOTERO_LIBRARY_TYPE, ZOTERO_API_KEY)
        # Проверка соединения (опционально, но полезно)
        # zot.key_info() # Этот вызов сделает запрос к API и вернет ошибку, если ключ невалидный
        logger.info(f"Успешное подключение к Zotero API для группы '{ZOTERO_GROUP_ID}'.")
    except Exception as e:
        logger.critical(f"Критическая ошибка подключения к Zotero API: {e}", exc_info=True)
        return {"status": "error", "message": f"Ошибка подключения к Zotero: {e}", "processed": 0, "skipped": 0,
                "errors": 1}

    collections_cache = {}
    processed_count = 0
    skipped_count = 0
    error_count = 0

    logger.info(f"--- НАЧАЛО ОБРАБОТКИ {len(df)} СТРОК ИЗ EXCEL ---")
    for index, row in df.iterrows():
        row_num_excel = index + 2
        logger.info(f"--- Обработка строки Excel #{row_num_excel} ---")

        filename_from_excel = str(row.get(COL_FILENAME, '')).strip()
        zotero_collection_path = str(row.get(COL_ZOTERO_COLLECTION, '')).strip()
        tags_str = str(row.get(COL_TAGS, '')).strip()
        notes_content_str = str(row.get(COL_NOTES_CONTENT, '')).strip()
        abstract_content_str = str(row.get(COL_ABSTRACT_CONTENT, '')).strip()
        biblio_description_str = str(row.get(COL_BIBLIO_DESCRIPTION, '')).strip()

        if not filename_from_excel:
            logger.warning(f"Строка {row_num_excel}: Пропущено, имя файла (в '{COL_FILENAME}') не указано.")
            skipped_count += 1
            continue

        if not zotero_collection_path:
            logger.warning(
                f"Строка {row_num_excel} (файл '{filename_from_excel}'): Пропущено, путь к коллекции Zotero (в '{COL_ZOTERO_COLLECTION}') не указан.")
            skipped_count += 1
            continue

        # Поиск файла PDF внутри контейнера (search_root_directory_in_container - это смонтированный Z:\...)
        file_path_in_container = find_file_path(filename_from_excel, search_root_directory_in_container)

        if not file_path_in_container:
            logger.error(
                f"Строка {row_num_excel}: PDF файл '{filename_from_excel}' НЕ НАЙДЕН в '{search_root_directory_in_container}' (и подпапках). Запись ПРОПУЩЕНА.")
            error_count += 1
            continue
        logger.info(f"Строка {row_num_excel}: PDF файл '{filename_from_excel}' найден: {file_path_in_container}")

        collection_id = get_or_create_hierarchical_collection(zot, zotero_collection_path, collections_cache)
        if not collection_id:
            logger.error(
                f"Строка {row_num_excel}: Не удалось получить/создать коллекцию Zotero '{zotero_collection_path}'. Запись ПРОПУЩЕНА.")
            error_count += 1
            continue
        logger.info(f"Строка {row_num_excel}: Коллекция Zotero '{zotero_collection_path}' ID: {collection_id}.")

        tags_list = []
        if tags_str:
            tags_list = [tag.strip() for tag in tags_str.replace(';', ',').split(',') if tag.strip()]
        formatted_tags = [{'tag': t} for t in tags_list]
        logger.debug(f"Строка {row_num_excel}: Метки для Zotero: {tags_list}")

        try:
            parent_template = {
                'itemType': 'document',  # Основной тип элемента
                'title': os.path.splitext(os.path.basename(file_path_in_container))[0],  # Имя файла без расширения
                'collections': [collection_id],
                'tags': formatted_tags
            }
            if abstract_content_str:
                parent_template['abstractNote'] = abstract_content_str
            if biblio_description_str:
                parent_template['extra'] = biblio_description_str

            logger.debug(f"Строка {row_num_excel}: Шаблон родительского элемента для Zotero: {parent_template}")
            parent_resp = zot.create_items([parent_template])

            if parent_resp and 'successful' in parent_resp and parent_resp['successful']:
                parent_item_info = list(parent_resp['successful'].values())[0]
                parent_item_key = parent_item_info['key']
                logger.info(
                    f"Строка {row_num_excel}: Родительский элемент Zotero для '{filename_from_excel}' создан (Item Key: {parent_item_key}).")

                # Добавление заметки, если есть контент
                if notes_content_str:
                    logger.info(f"Строка {row_num_excel}: Добавление заметки к элементу {parent_item_key}...")
                    # Замена переносов строк для HTML. Важно использовать правильный перенос для вашей ОС, если строка из Excel может их содержать.
                    # os.linesep может быть не всегда тем, что в Excel. Часто это просто \n.
                    html_note_content = f"<p>{notes_content_str.replace(chr(10), '<br />').replace(chr(13), '')}</p>"  # chr(10)=\n, chr(13)=\r
                    note_template = {
                        'itemType': 'note',
                        'parentItem': parent_item_key,
                        'note': html_note_content,
                    }
                    note_resp = zot.create_items([note_template])
                    if note_resp and 'successful' in note_resp and note_resp['successful']:
                        note_key = list(note_resp['successful'].values())[0]['key']
                        logger.info(f"Строка {row_num_excel}: Заметка успешно добавлена (Note Key: {note_key}).")
                    else:
                        logger.warning(
                            f"Строка {row_num_excel}: Не удалось добавить заметку. Ответ Zotero: {note_resp}")

                # Прикрепление файла PDF
                logger.info(
                    f"Строка {row_num_excel}: Попытка прикрепления файла '{file_path_in_container}' к элементу {parent_item_key}...")
                upload_response = zot.attachment_simple([file_path_in_container], parentid=parent_item_key)
                logger.debug(f"Строка {row_num_excel}: Ответ Zotero на прикрепление файла: {upload_response}")

                attachment_key = None
                # Логика извлечения ключа прикрепленного файла
                if upload_response:
                    if isinstance(upload_response, list) and len(upload_response) > 0 and isinstance(upload_response[0],
                                                                                                     str):  # attachment_simple может вернуть список ключей
                        attachment_key = upload_response[0]
                    elif 'successful' in upload_response and upload_response['successful']:
                        first_success_item = list(upload_response['successful'].values())[0]
                        if 'key' in first_success_item: attachment_key = first_success_item['key']
                    elif 'key' in upload_response:  # Иногда ответ - это просто словарь с ключом
                        attachment_key = upload_response['key']
                    # Добавьте другие варианты разбора ответа, если необходимо

                if attachment_key:
                    logger.info(
                        f"Строка {row_num_excel}: Файл '{filename_from_excel}' успешно прикреплен (Attachment Key: {attachment_key}).")
                    processed_count += 1
                else:
                    logger.error(
                        f"Строка {row_num_excel}: Не удалось прикрепить файл '{filename_from_excel}'. Ответ Zotero не содержал ожидаемого ключа.")
                    error_count += 1
            else:
                logger.error(
                    f"Строка {row_num_excel}: Не удалось создать родительский элемент Zotero. Ответ Zotero: {parent_resp}")
                error_count += 1
        except Exception as e_item:
            logger.error(
                f"Строка {row_num_excel}: КРИТИЧЕСКОЕ ИСКЛЮЧЕНИЕ при обработке элемента для Zotero ('{filename_from_excel}'): {e_item}",
                exc_info=True)
            error_count += 1

    summary_message = f"Процесс импорта завершен. Успешно обработано: {processed_count}, Пропущено из-за отсутствия данных: {skipped_count}, Ошибки Zotero/файлов: {error_count}."
    logger.info(summary_message)
    logger.info(f"Подробный лог находится в файле: {LOG_FILE}")

    status_code = "error"
    if processed_count > 0 and error_count == 0 and skipped_count == 0:
        status_code = "success"
    elif processed_count > 0:
        status_code = "partial_success"

    return {
        "status": status_code,
        "message": summary_message,
        "processed": processed_count,
        "skipped": skipped_count,
        "errors": error_count
    }