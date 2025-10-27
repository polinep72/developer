# services/equipment_service.py
from database import Database, QueryResult # Импортируем QueryResult для типизации
from logger import logger
from typing import List, Tuple, Optional, Union, Dict, Any # Уточняем импорты
import logging # Импорт для уровней логирования
import constants as const # Для сообщений

# Ожидаемый тип результата от DictCursor
EquipmentRow = Dict[str, Any]
CategoryRow = Dict[str, Any]

# --- Функции получения данных ---
def get_all_categories(db: Database) -> List[CategoryRow]:
    """Получает все категории в виде списка словарей."""
    query = "SELECT id, name_cat FROM cat ORDER BY name_cat ASC;"
    result: QueryResult = db.execute_query(query, fetch_results=True)
    # Убедимся, что результат - это список словарей
    return result if isinstance(result, list) else []

def get_equipment_by_category(db: Database, category_id: int) -> List[EquipmentRow]:
    """Получает оборудование по ID категории в виде списка словарей."""
    query = "SELECT id, name_equip FROM equipment WHERE category = %s ORDER BY name_equip ASC;"
    result: QueryResult = db.execute_query(query, (category_id,), fetch_results=True)
    return result if isinstance(result, list) else []

def get_all_equipment(db: Database) -> List[EquipmentRow]:
     """Получает все оборудование в виде списка словарей."""
     query = "SELECT id, name_equip FROM equipment ORDER BY name_equip ASC;"
     result: QueryResult = db.execute_query(query, fetch_results=True)
     return result if isinstance(result, list) else []

def get_equipment_info_by_id(db: Database, equipment_id: int) -> Optional[EquipmentRow]:
     """Получает информацию об оборудовании (включая ID категории) по его ID."""
     query = "SELECT id, name_equip, category, note FROM equipment WHERE id = %s;"
     result: QueryResult = db.execute_query(query, (equipment_id,), fetch_results=True)
     # execute_query возвращает список, берем первый элемент, если он есть
     return result[0] if result and isinstance(result, list) else None

def get_equipment_name_by_id(db: Database, equipment_id: int) -> Optional[str]:
    """Получает только имя оборудования по его ID."""
    info = get_equipment_info_by_id(db, equipment_id)
    # Используем доступ по ключу, так как ожидаем словарь от DictCursor
    return info['name_equip'] if info else None


# --- Функции проверки ---
def check_equipment_exists(db: Database, category_id: int, name: str) -> bool:
    """Проверяет, существует ли оборудование с таким именем в указанной категории."""
    logger.debug(f"Начало проверки существования оборудования '{name}' в категории {category_id}")
    # Используем LOWER для регистронезависимой проверки, если это нужно
    # query = "SELECT 1 FROM equipment WHERE category = %s AND LOWER(name_equip) = LOWER(%s) LIMIT 1;"
    # params = (category_id, name.lower())
    # Иначе, если регистр важен:
    query = "SELECT 1 FROM equipment WHERE category = %s AND name_equip = %s LIMIT 1;"
    params = (category_id, name)
    try:
        # Для SELECT commit=False (по умолчанию)
        result: QueryResult = db.execute_query(query, params, fetch_results=True)
        exists = bool(result) # Если список не пустой, значит существует
        logger.debug(f"Запрос на проверку существования выполнен. Результат: {exists}")
        return exists
    except Exception as e:
        # Лог ошибки уже будет в execute_query, если он пробросит исключение
        logger.error(f"Ошибка при проверке существования оборудования '{name}' в кат {category_id}: {e}", exc_info=True)
        # Пробрасываем исключение, чтобы администратор увидел ошибку
        raise e


# --- Функции добавления ---
def find_or_create_category(db: Database, category_name: str) -> Optional[int]:
    """Находит категорию по имени или создает новую, возвращает ID категории."""
    if not category_name:
        logger.warning("Пустое имя категории.")
        return None
    query_find = "SELECT id FROM cat WHERE name_cat = %s;"
    try:
        # Для SELECT commit=False (по умолчанию)
        result_find: QueryResult = db.execute_query(query_find, (category_name,), fetch_results=True)
        if result_find and isinstance(result_find, list):
            category_id = result_find[0]['id'] # Доступ по ключу
            logger.debug(f"Найдена кат '{category_name}' ID {category_id}.")
            return category_id
        else:
            logger.info(f"Кат '{category_name}' не найдена, создаем...")
            query_insert = "INSERT INTO cat (name_cat) VALUES (%s) RETURNING id;"
            # Для INSERT используем commit=True
            result_insert: QueryResult = db.execute_query(query_insert, (category_name,), fetch_results=True, commit=True)
            if result_insert and isinstance(result_insert, list):
                new_category_id = result_insert[0]['id'] # Доступ по ключу
                logger.info(f"Создана кат '{category_name}' ID {new_category_id}.")
                return new_category_id
            else:
                # Эта ветка маловероятна при RETURNING, но возможна при ошибке коммита
                logger.error(f"Не удалось создать кат '{category_name}', INSERT не вернул ID или произошла ошибка коммита.")
                return None
    except Exception as e:
        # Лог ошибки уже будет в execute_query, если он пробросит исключение
        logger.error(f"Исключение при поиске/создании категории '{category_name}': {e}", exc_info=True)
        return None # Возвращаем None при любой ошибке

def add_equipment(db: Database, category_id: int, name: str, note: str) -> bool:
    """Добавляет новое оборудование в базу данных."""
    if not name:
        logger.warning("Пустое имя оборудования.")
        return False
    insert_query = "INSERT INTO equipment (category, name_equip, note) VALUES (%s, %s, %s) RETURNING id;"
    try:
        # Для INSERT используем commit=True
        result: QueryResult = db.execute_query(insert_query, (category_id, name, note), fetch_results=True, commit=True)
        # Проверяем, что результат не None и не пустой список
        if result and isinstance(result, list):
            new_id = result[0]['id'] # Доступ по ключу
            logger.info(f"Оборудование '{name}' (ID:{new_id}) добавлено в кат {category_id}.")
            return True
        else:
            logger.error(f"Не добавить '{name}', INSERT не вернул ID или произошла ошибка выполнения/коммита.")
            return False
    except Exception as e:
        # Лог ошибки уже будет в execute_query
        logger.error(f"Исключение при добавлении оборудования '{name}': {e}", exc_info=True)
        return False

# --- Функции удаления ---
def check_equipment_usage(db: Database, equipment_id: int) -> bool:
    """Проверяет, есть ли записи в bookings для данного equip_id."""
    query = "SELECT 1 FROM bookings WHERE equip_id = %s LIMIT 1;"
    try:
        # Для SELECT commit=False (по умолчанию)
        result: QueryResult = db.execute_query(query, (equipment_id,), fetch_results=True)
        usage_found = bool(result)
        log_level = logging.WARNING if usage_found else logging.INFO
        logger.log(log_level, f"Проверка использования equip_id={equipment_id}: {'ДА (используется)' if usage_found else 'НЕТ (не используется)'}")
        return usage_found
    except Exception as e:
        logger.error(f"Ошибка при проверке использования оборудования ID {equipment_id}: {e}", exc_info=True)
        # В случае ошибки безопаснее считать, что оно используется, чтобы не удалить случайно
        return True # Возвращаем True при ошибке


def delete_equipment_if_unused(db: Database, equipment_id: int) -> Tuple[bool, str]:
    """
    Удаляет оборудование, если оно не используется в bookings.
    Если это было последнее оборудование в категории, удаляет и категорию.
    Возвращает (Успех, Сообщение).
    """
    logger.info(f"Запрос на удаление оборудования ID {equipment_id}")

    try:
        # 1. ПРОВЕРКА ИСПОЛЬЗОВАНИЯ
        if check_equipment_usage(db, equipment_id):  # Предполагаем, что эта функция существует
            equip_name = get_equipment_name_by_id(db,
                                                  equipment_id) or f"ID {equipment_id}"  # Предполагаем, что эта функция существует
            # Используем константу MSG_ADMIN_EQUIP_DELETE_FAIL_HAS_HISTORY (или аналогичную)
            # и метод .format() для корректной подстановки
            # Пример: return False, const.MSG_ADMIN_EQUIP_DELETE_FAIL_HAS_HISTORY.format(name_equip=equip_name)
            # Оставляю ваш .replace, но убедитесь, что плейсхолдер в константе такой же
            return False, const.MSG_ADMIN_EQUIP_DELETE_FAIL_HAS_HISTORY.replace('{name_equip}',
                                                                                f"'{equip_name}'")  # ЗАМЕНИТЕ КОНСТАНТУ И ПЛЕЙСХОЛДЕР НА ПРАВИЛЬНЫЕ

        # 2. Получаем имя и ID категории перед удалением
        equip_info = get_equipment_info_by_id(db,
                                              equipment_id)  # Предполагаем, что эта функция существует и возвращает dict
        if not equip_info:
            logger.warning(f"Оборудование ID {equipment_id} не найдено для удаления.")
            # Используем const.MSG_ADMIN_EQUIP_DELETE_FAIL_NOT_FOUND
            return False, const.MSG_ADMIN_EQUIP_DELETE_FAIL_NOT_FOUND

        equip_name = equip_info['name_equip']
        category_id = equip_info.get(
            'category')  # Используем .get для безопасности, если 'category' может отсутствовать

        # <<< НАЧАЛО ИЗМЕНЕНИЯ: Получение имени категории >>>
        category_name = "N/A"  # Значение по умолчанию
        if category_id:
            cat_info_query = "SELECT name_cat FROM cat WHERE id = %s;"
            # Предполагаем, что execute_query с fetch_results=True возвращает список словарей
            cat_data_list = db.execute_query(cat_info_query, (category_id,), fetch_results=True)
            if cat_data_list:  # Если список не пустой
                cat_data = cat_data_list[0]  # Берем первый (и единственный) элемент
                category_name = cat_data.get('name_cat', "N/A")  # .get для безопасности
            else:
                logger.warning(f"Имя категории для ID {category_id} не найдено.")
        # <<< КОНЕЦ ИЗМЕНЕНИЯ >>>

        # 3. Удаление оборудования
        query_delete_equip = "DELETE FROM equipment WHERE id = %s;"
        db.execute_query(query_delete_equip, (equipment_id,), commit=True)  # Предполагаем, что это работает для DELETE
        logger.info(f"Запись об оборудовании '{equip_name}' (ID: {equipment_id}) удалена.")

        # 4. Проверка и удаление категории, если она стала пустой
        category_operation_msg_part = ""  # Переименовал для ясности
        if category_id is not None:
            query_check_other = "SELECT 1 FROM equipment WHERE category = %s LIMIT 1;"
            # Предполагаем, что execute_query с fetch_results=True возвращает список
            other_equip_list = db.execute_query(query_check_other, (category_id,), fetch_results=True)
            # Если other_equip_list пустой, значит, в категории нет другого оборудования
            if not other_equip_list:
                current_category_name_for_msg = category_name  # Используем уже полученное имя категории
                logger.info(
                    f"Оборудование '{equip_name}' было последним в категории {category_id} ('{current_category_name_for_msg}'). Удаляем категорию...")
                query_delete_cat = "DELETE FROM cat WHERE id = %s;"
                try:
                    db.execute_query(query_delete_cat, (category_id,), commit=True)
                    logger.info(f"Категория ID {category_id} ('{current_category_name_for_msg}') успешно удалена.")
                    # const.MSG_ADMIN_CAT_AUTO_DELETE_SUCCESS = "✅ Категория '{name_cat}' была пуста и автоматически удалена."
                    category_operation_msg_part = " " + const.MSG_ADMIN_CAT_AUTO_DELETE_SUCCESS.format(
                        name_cat=current_category_name_for_msg)
                except Exception as e_cat:
                    logger.error(
                        f"Ошибка при удалении пустой категории ID {category_id} ('{current_category_name_for_msg}'): {e_cat}",
                        exc_info=True)
                    # const.MSG_ADMIN_CAT_AUTO_DELETE_FAIL = "⚠️ Не удалось автоматически удалить пустую категорию '{name_cat}' после удаления оборудования."
                    category_operation_msg_part = " " + const.MSG_ADMIN_CAT_AUTO_DELETE_FAIL.format(
                        name_cat=current_category_name_for_msg)
            else:
                logger.debug(f"В категории {category_id} ('{category_name}') осталось другое оборудование.")

        # 5. Формирование финального сообщения
        # <<< ИЗМЕНЕНИЕ: Используем .format() и подставляем оба значения >>>
        # const.MSG_ADMIN_EQUIP_DELETE_SUCCESS = "✅ Оборудование '{name_equip}' (категория: '{name_cat}') удалено."
        base_success_msg = const.MSG_ADMIN_EQUIP_DELETE_SUCCESS.format(name_equip=equip_name, name_cat=category_name)

        final_success_msg = base_success_msg + category_operation_msg_part  # Добавляем часть про операцию с категорией

        return True, final_success_msg

    except Exception as e:
        logger.error(f"Исключение при обработке удаления оборудования ID {equipment_id}: {e}", exc_info=True)
        # Убедитесь, что const.MSG_ADMIN_EQUIP_DELETE_FAIL_DB определена
        return False, const.MSG_ADMIN_EQUIP_DELETE_FAIL_DB


def get_category_by_id(db: Database, category_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о категории оборудования по ее ID.
    Возвращает словарь с данными категории или None, если категория не найдена.
    """
    query = "SELECT id, name_cat FROM cat WHERE id = %s;"
    try:
        # Используем fetch_results=True, так как мы ожидаем результат SELECT
        query_result: QueryResult = db.execute_query(query, (category_id,), fetch_results=True)

        # query_result будет списком словарей или None
        if query_result and isinstance(query_result, list) and len(query_result) > 0:
            return query_result[0] # Возвращаем первый (и единственный ожидаемый) элемент списка
        else:
            # Это также обработает случай, когда query_result равен None или пустой список
            logger.warning(f"Категория с ID {category_id} не найдена в базе данных.")
            return None
    except Exception as e:
        # Логгер из вашего database.py уже должен был залогировать ошибку выполнения запроса.
        # Этот лог для дополнительной информации на уровне сервиса.
        logger.error(f"Исключение в get_category_by_id при получении категории ID {category_id}: {e}", exc_info=True)
        return None

# Убедитесь, что у вас есть функция get_equipment_name_by_id, если она еще не реализована:
def get_equipment_name_by_id(db: Database, equipment_id: int) -> Optional[str]:
    """Получает имя оборудования по его ID."""
    query = "SELECT name_equip FROM equipment WHERE id = %s;"
    try:
        result: QueryResult = db.execute_query(query, (equipment_id,), fetch_results=True)
        if result and isinstance(result, list) and len(result) > 0 and 'name_equip' in result[0]:
            return result[0]['name_equip']
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении имени оборудования по ID {equipment_id}: {e}", exc_info=True)
        return None