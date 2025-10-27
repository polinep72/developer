# zotero_importer_core.py
# -*- coding: utf-8 -*-

import os
import pandas as pd
from pyzotero import zotero
# import tkinter as tk # УДАЛЯЕМ tkinter
# from tkinter import filedialog # УДАЛЯЕМ filedialog
import logging
import sys
import importlib.metadata
from dotenv import load_dotenv

# import mimetypes # Пока не используется, можно оставить или убрать

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
load_dotenv()

ZOTERO_API_KEY = os.getenv('ZOTERO_API_KEY')
ZOTERO_GROUP_ID = os.getenv('ZOTERO_GROUP_ID')
ZOTERO_LIBRARY_TYPE = os.getenv('ZOTERO_LIBRARY_TYPE', 'group')

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
# Эту часть можно оставить здесь, Flask будет использовать этот же логгер, если имя модуля одинаковое
# или мы настроим Flask логгер на тот же файл.
LOG_FILE = "zotero_excel_importer.log"
# Очистка существующих обработчиков, чтобы избежать дублирования при многократном импорте модуля (если такое случится)
# Лучше это делать один раз при старте приложения Flask
# for handler_to_remove in logging.root.handlers[:]:
#     logging.root.removeHandler(handler_to_remove)
# logging.basicConfig( # Эту конфигурацию можно сделать в app.py для всего приложения
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
#     handlers=[
#         logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'), # 'a' для дозаписи
#         logging.StreamHandler(sys.stdout)
#     ]
# )

# Получаем логгер для этого модуля. Flask может настроить root логгер или свой.
logger = logging.getLogger(__name__)  # Используем логгер модуля

COL_FILENAME = "Наименование файла"
COL_ZOTERO_COLLECTION = "раздел Zotero"
COL_TAGS = "Метки"
COL_NOTES_CONTENT = "Соответствие пунктам ТЗ"
COL_ABSTRACT_CONTENT = "Краткое описание"
COL_BIBLIO_DESCRIPTION = "Библиографическое описание"


def log_package_versions():
    packages = ["pandas", "openpyxl", "pyzotero", "python-dotenv", "Flask"]  # Добавил Flask
    for pkg_name in packages:
        try:
            version = importlib.metadata.version(pkg_name)
            logger.info(f"Версия пакета {pkg_name}: {version}")
        except importlib.metadata.PackageNotFoundError:
            logger.warning(f"Пакет {pkg_name} не найден.")
        except Exception as e:
            logger.error(f"Не удалось получить версию пакета {pkg_name}: {e}")
    try:
        version = importlib.metadata.version("xlrd")
        logger.info(f"Версия пакета xlrd: {version} (Этот пакет больше не должен использоваться для .xlsx)")
    except importlib.metadata.PackageNotFoundError:
        logger.info("Пакет xlrd не найден (это ожидаемо для работы с .xlsx через openpyxl).")


def check_python_version():
    if sys.version_info < (3, 6):  # Минимальная версия Python
        error_message = f"ОШИБКА: Этот скрипт требует Python 3.6 или выше. Вы используете Python {sys.version}."
        logger.critical(error_message)
        # Вместо sys.exit(1) будем возвращать ошибку или выбрасывать исключение
        raise RuntimeError(error_message)
    logger.info(f"Версия Python: {sys.version} - проверка пройдена.")


def find_file_path(filename, search_root_dir):
    logger.debug(f"Поиск файла '{filename}' в директории '{search_root_dir}' и ее поддиректориях...")
    for root, _, files in os.walk(search_root_dir):
        if filename in files:
            found_path = os.path.join(root, filename)
            found_path = os.path.normpath(found_path)
            logger.info(f"Файл '{filename}' найден по пути: {found_path}")
            return found_path
    logger.warning(f"Файл '{filename}' НЕ найден в '{search_root_dir}' и ее поддиректориях.")
    return None


def get_or_create_hierarchical_collection(zot, full_collection_path_str, collections_cache):
    # Ваша полная реализация этой функции остается здесь
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


def run_zotero_import(excel_file_path, files_root_directory):
    """
    Основная функция для запуска импорта.
    Принимает пути к файлам, возвращает словарь со статистикой.
    """
    logger.info(
        f"================ ЗАПУСК ИМПОРТА В ZOTERO (excel: {excel_file_path}, pdf_dir: {files_root_directory}) ================")

    # Проверки переменных окружения
    if not ZOTERO_API_KEY:
        msg = "КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения ZOTERO_API_KEY не установлена или пуста."
        logger.critical(msg)
        return {"status": "error", "message": msg, "processed": 0, "skipped": 0, "errors": 1}
    if not ZOTERO_GROUP_ID:
        msg = "КРИТИЧЕСКАЯ ОШИБКА: Переменная окружения ZOTERO_GROUP_ID не установлена или пуста."
        logger.critical(msg)
        return {"status": "error", "message": msg, "processed": 0, "skipped": 0, "errors": 1}

    logger.info(f"Конфигурация Zotero: Group ID='{ZOTERO_GROUP_ID}', Library Type='{ZOTERO_LIBRARY_TYPE}'")

    try:
        logger.info(f"Чтение Excel файла: {excel_file_path}")
        df = pd.read_excel(excel_file_path, dtype=str, engine='openpyxl')
        logger.info(f"Успешно прочитано {len(df)} строк из Excel.")
    except Exception as e:
        logger.critical(f"Ошибка чтения Excel файла '{excel_file_path}': {e}", exc_info=True)
        return {"status": "error", "message": f"Ошибка чтения Excel: {e}", "processed": 0, "skipped": 0, "errors": 1}

    required_cols = [COL_FILENAME, COL_ZOTERO_COLLECTION, COL_TAGS, COL_NOTES_CONTENT, COL_ABSTRACT_CONTENT,
                     COL_BIBLIO_DESCRIPTION]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        msg = f"В Excel файле отсутствуют столбцы: {', '.join(missing_cols)}."
        logger.critical(msg)
        return {"status": "error", "message": msg, "processed": 0, "skipped": 0, "errors": 1}
    logger.info("Все необходимые столбцы найдены в Excel.")

    try:
        zot = zotero.Zotero(ZOTERO_GROUP_ID, ZOTERO_LIBRARY_TYPE, ZOTERO_API_KEY)
        logger.info(f"Успешное подключение к Zotero API (группа '{ZOTERO_GROUP_ID}').")
    except Exception as e:
        logger.critical(f"Ошибка подключения к Zotero API: {e}", exc_info=True)
        return {"status": "error", "message": f"Ошибка подключения к Zotero: {e}", "processed": 0, "skipped": 0,
                "errors": 1}

    collections_cache = {}
    processed_count = 0
    skipped_count = 0
    error_count = 0

    logger.info(f"--- НАЧАЛО ОБРАБОТКИ {len(df)} СТРОК EXCEL ---")
    for index, row in df.iterrows():
        row_num_excel = index + 2
        logger.info(f"--- Обработка строки {row_num_excel} ---")

        filename_from_excel = str(row.get(COL_FILENAME, '')).strip()
        zotero_collection_path = str(row.get(COL_ZOTERO_COLLECTION, '')).strip()
        tags_str = str(row.get(COL_TAGS, '')).strip()
        notes_content_str = str(row.get(COL_NOTES_CONTENT, '')).strip()
        abstract_content_str = str(row.get(COL_ABSTRACT_CONTENT, '')).strip()
        biblio_description_str = str(row.get(COL_BIBLIO_DESCRIPTION, '')).strip()

        if not filename_from_excel:
            logger.warning(f"Строка {row_num_excel}: Пропущено, имя файла не указано.")
            skipped_count += 1
            continue

        if not zotero_collection_path:
            logger.warning(
                f"Строка {row_num_excel} (файл '{filename_from_excel}'): Пропущено, путь к коллекции не указан.")
            skipped_count += 1
            continue

        file_path = find_file_path(filename_from_excel, files_root_directory)
        if not file_path:
            logger.error(
                f"Строка {row_num_excel}: Файл '{filename_from_excel}' не найден в '{files_root_directory}'. Запись ПРОПУЩЕНА.")
            error_count += 1
            continue

        collection_id = get_or_create_hierarchical_collection(zot, zotero_collection_path, collections_cache)
        if not collection_id:
            logger.error(
                f"Строка {row_num_excel}: Не удалось получить/создать коллекцию '{zotero_collection_path}'. Запись ПРОПУЩЕНА.")
            error_count += 1
            continue

        tags_list = []
        if tags_str:
            tags_list = [tag.strip() for tag in tags_str.replace(';', ',').split(',') if tag.strip()]
        formatted_tags = [{'tag': t} for t in tags_list]

        try:
            parent_template = {
                'itemType': 'document',
                'title': os.path.splitext(os.path.basename(file_path))[0],
                'collections': [collection_id],
                'tags': formatted_tags
            }
            if abstract_content_str:
                parent_template['abstractNote'] = abstract_content_str
            if biblio_description_str:
                parent_template['extra'] = biblio_description_str

            logger.debug(f"Строка {row_num_excel}: Шаблон родительского элемента: {parent_template}")
            parent_resp = zot.create_items([parent_template])

            if parent_resp and 'successful' in parent_resp and parent_resp['successful']:
                parent_item_info = list(parent_resp['successful'].values())[0]
                parent_item_key = parent_item_info['key']
                logger.info(
                    f"Строка {row_num_excel}: Родительский элемент для '{filename_from_excel}' создан (Key: {parent_item_key}).")

                if notes_content_str:
                    html_note_content = f"<p>{notes_content_str.replace(os.linesep, '<br />').replace('\n', '<br />')}</p>"
                    note_template = {'itemType': 'note', 'parentItem': parent_item_key, 'note': html_note_content}
                    note_resp = zot.create_items([note_template])
                    if note_resp and 'successful' in note_resp and note_resp['successful']:
                        logger.info(f"Строка {row_num_excel}: Заметка добавлена.")
                    else:
                        logger.warning(f"Строка {row_num_excel}: Не удалось добавить заметку. Ответ: {note_resp}")

                upload_response = zot.attachment_simple([file_path], parentid=parent_item_key)
                attachment_key = None
                if upload_response:
                    if 'successful' in upload_response and upload_response['successful']:
                        first_success_item = list(upload_response['successful'].values())[0]
                        if 'key' in first_success_item: attachment_key = first_success_item['key']
                    elif 'success' in upload_response and upload_response['success']:
                        if isinstance(upload_response['success'], list) and len(
                            upload_response['success']) > 0: attachment_key = upload_response['success'][0]
                    elif 'unchanged' in upload_response and upload_response['unchanged']:
                        if isinstance(upload_response['unchanged'], list) and len(upload_response['unchanged']) > 0:
                            first_unchanged_item = upload_response['unchanged'][0]
                            if isinstance(first_unchanged_item,
                                          dict) and 'key' in first_unchanged_item: attachment_key = \
                            first_unchanged_item['key']

                if attachment_key:
                    logger.info(
                        f"Строка {row_num_excel}: Файл '{filename_from_excel}' прикреплен (Key: {attachment_key}).")
                    processed_count += 1
                else:
                    logger.error(
                        f"Строка {row_num_excel}: Не удалось прикрепить файл '{filename_from_excel}'. Ответ: {upload_response}")
                    error_count += 1
            else:
                logger.error(f"Строка {row_num_excel}: Не удалось создать родительский элемент. Ответ: {parent_resp}")
                error_count += 1
        except Exception as e:
            logger.error(f"Строка {row_num_excel}: Исключение при обработке '{filename_from_excel}': {e}",
                         exc_info=True)
            error_count += 1

    summary_message = f"Импорт завершен. Успешно: {processed_count}, Пропущено: {skipped_count}, Ошибки: {error_count}."
    logger.info(summary_message)
    logger.info(f"Подробный лог в файле: {LOG_FILE}")

    return {
        "status": "success" if error_count == 0 and processed_count > 0 else (
            "partial_success" if processed_count > 0 else "error"),
        "message": summary_message,
        "processed": processed_count,
        "skipped": skipped_count,
        "errors": error_count
    }

# if __name__ == "__main__":
#    # Эта часть больше не нужна, так как запуск будет из app.py
#    # main() был заменен на run_zotero_import()