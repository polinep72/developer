# --- START OF FILE admin_service.py ---

# services/admin_service.py
from database import Database, QueryResult # Импортируем QueryResult
from logger import logger
from typing import List, Tuple, Optional, Any, Dict # Добавили Dict
from datetime import datetime, date
import io
import os
import telebot
import time
import constants as const
from services import user_service # Для получения пользователей
# Импортируем booking_service для форматтера
from services import booking_service
from telebot import apihelper # Добавим импорт apihelper

def broadcast_message_to_users(db: Database, bot: telebot.TeleBot, message_text: str, admin_chat_id: int) -> Tuple[int, int]:
    """
    Рассылает сообщение всем активным, не заблокированным пользователям.
    Возвращает кортеж (количество успешных отправок, количество ошибок).
    """
    active_users: List[Dict[str, Any]] = []
    try:
        # Получаем только активных пользователей
        active_users = user_service.get_all_users(db, include_inactive=False)
    except Exception as e_get_users:
        logger.error(f"Ошибка получения пользователей для рассылки: {e_get_users}", exc_info=True)
        try:
            bot.send_message(admin_chat_id, "Ошибка получения списка пользователей для рассылки.")
        except Exception as e_admin_notify:
            logger.error(f"Не удалось уведомить админа {admin_chat_id} об ошибке получения пользователей: {e_admin_notify}")
        return 0, 0 # Считаем как 0 успешных, 0 ошибок

    if not active_users:
        logger.info("Нет активных пользователей для рассылки.")
        try:
            bot.send_message(admin_chat_id, "В системе нет активных пользователей для рассылки.")
        except Exception as e_admin_notify:
            logger.error(f"Не удалось отправить сообщение админу {admin_chat_id}: {e_admin_notify}")
        return 0, 0

    user_ids = [user['users_id'] for user in active_users if user.get('users_id')]
    if not user_ids:
        logger.warning("Список active_users не пуст, но не содержит корректных users_id.")
        try:
            bot.send_message(admin_chat_id, "Не удалось извлечь ID пользователей для рассылки.")
        except Exception as e_admin_notify:
            logger.error(f"Не удалось отправить сообщение админу {admin_chat_id}: {e_admin_notify}")
        return 0, 0

    successful_sends = 0
    failed_sends = []
    total_users = len(user_ids)
    logger.info(f"Начало рассылки '{message_text[:30]}...' {total_users} пользователям.")

    try:
        bot.send_message(admin_chat_id, f"Начинаю рассылку сообщения {total_users} пользователям...")
    except Exception as e_admin_notify:
        logger.warning(f"Не удалось уведомить админа {admin_chat_id} о начале рассылки: {e_admin_notify}")

    for i, user_id in enumerate(user_ids):
        try:
            bot.send_message(user_id, message_text)
            successful_sends += 1
            logger.debug(f"({i+1}/{total_users}) Сообщение успешно -> {user_id}.")
            # Небольшая задержка между сообщениями для избежания флуда
            time.sleep(0.1) # 100 мс
        except apihelper.ApiTelegramException as e:
            failed_sends.append(user_id)
            # --- ИСПРАВЛЕНИЕ ЛОГИКИ ---
            if e.error_code == 403:
                logger.warning(f"({i+1}/{total_users}) Ошибка отправки {user_id}: бот заблокирован.")
                # Вызываем обработчик ТОЛЬКО для кода 403
                try:
                    user_service.handle_user_blocked_bot(db, user_id)
                except Exception as e_block:
                    logger.error(f"Ошибка при вызове handle_user_blocked_bot для {user_id}: {e_block}")
            # -------------------------
            elif e.error_code == 400 and 'chat not found' in e.description.lower():
                logger.warning(f"({i+1}/{total_users}) Ошибка отправки {user_id}: чат не найден.")
                # НЕ вызываем handle_user_blocked_bot здесь
            else:
                logger.error(f"({i+1}/{total_users}) Ошибка Telegram API для {user_id}: {e}")
            # Можно увеличить задержку при ошибке
            time.sleep(0.5)
        except Exception as e:
            failed_sends.append(user_id)
            logger.error(f"({i+1}/{total_users}) Неожиданная ошибка отправки для {user_id}: {e}", exc_info=True)
            time.sleep(1) # Большая задержка при непонятной ошибке

    # Формирование отчета для админа
    report_message = f"📢 Рассылка завершена.\n✅ Успешно: {successful_sends}\n❌ Ошибки: {len(failed_sends)}"
    if failed_sends:
        max_failed_ids = 10
        failed_ids_str = ', '.join(map(str, failed_sends[:max_failed_ids]))
        if len(failed_sends) > max_failed_ids:
            failed_ids_str += f", и еще {len(failed_sends) - max_failed_ids}"
        report_message += f"\n\nIDs с ошибками:\n{failed_ids_str}"
    try:
        bot.send_message(admin_chat_id, report_message)
    except Exception as e_admin_notify:
        logger.error(f"Не удалось отправить отчет админу {admin_chat_id}: {e_admin_notify}")

    logger.info(f"Рассылка завершена. Успешно: {successful_sends}, Ошибки: {len(failed_sends)}.")
    return successful_sends, len(failed_sends)


def get_filtered_bookings(db: Database, filter_type: str, filter_value: Any) -> List[Dict[str, Any]]:
    """
    Получает бронирования по заданному фильтру для команды /all.
    Возвращает список словарей.
    """
    if filter_type not in ["users", "equipment", "dates"]:
        logger.warning(f"Неизвестный тип фильтра: {filter_type}")
        return []

    query = """
        SELECT
            b.id as booking_id, b.user_id, b.equip_id, b.date,
            b.time_interval, b.time_start, b.time_end, b.duration,
            b.cancel, b.extension, b.finish, b.data_booking,
            e.name_equip,
            u.fi as user_fi, u.first_name as user_first_name, u.last_name as user_last_name
        FROM bookings b
        JOIN equipment e ON b.equip_id = e.id
        JOIN users u ON b.user_id = u.users_id
    """
    params: Optional[Tuple[Any, ...]] = None
    where_clause = ""

    try:
        if filter_type == "users":
            where_clause = " WHERE u.users_id = %s"
            params = (int(filter_value),)
        elif filter_type == "equipment":
            where_clause = " WHERE e.id = %s"
            params = (int(filter_value),)
        elif filter_type == "dates":
            datetime.strptime(str(filter_value), '%Y-%m')
            where_clause = " WHERE TO_CHAR(b.date, 'YYYY-MM') = %s"
            params = (str(filter_value),)
    except ValueError as e:
        logger.error(f"Некорректное значение фильтра '{filter_value}' для типа '{filter_type}': {e}")
        return []
    except Exception as e:
         logger.error(f"Ошибка при подготовке параметров фильтра: {e}", exc_info=True)
         return []

    query += where_clause + " ORDER BY b.date DESC, b.time_start DESC;"

    try:
        results: Optional[QueryResult] = db.execute_query(query, params, fetch_results=True)
        return results if results else []
    except Exception as e:
        logger.error(f"Ошибка при выполнении запроса get_filtered_bookings: {e}", exc_info=True)
        return []


def format_bookings_to_file_content(bookings: List[Dict[str, Any]], filter_details: str) -> str:
     """ Форматирует список бронирований (словари) в строку для записи в файл. """
     header = f"Отчет по бронированиям\n"
     header += f"Фильтр: {filter_details}\n"
     header += f"Сформирован: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
     header += "=" * 50 + "\n\n"

     if not bookings:
         return header + "Нет бронирований по выбранному фильтру."

     file_content = header
     for booking in bookings:
         equip_name = booking.get('name_equip', '???')
         date_val = booking.get('date')
         time_start = booking.get('time_start')
         time_end = booking.get('time_end')
         user_name = booking.get('user_fi', '???')
         is_cancelled = booking.get('cancel', False)
         is_finished = booking.get('finish') is not None # Проверяем, что не NULL
         status = ""
         if is_cancelled: status = " [ОТМЕНЕНО]"
         elif is_finished: status = " [ЗАВЕРШЕНО]"

         try:
             formatted_line = booking_service.format_booking_info(
                 equip_name, date_val, time_start, time_end, user_name
             )
             file_content += formatted_line + status + "\n"
         except Exception as e_format:
              logger.error(f"Ошибка форматирования строки для booking_id {booking.get('booking_id')}: {e_format}")
              file_content += f"Ошибка форматирования: ID={booking.get('booking_id')}, User={user_name}\n"

     return file_content

def create_bookings_report_file(
    bookings: List[Dict[str, Any]],
    filter_details: str,
    filename_prefix: str = "bookings_report"
    ) -> Optional[str]:
    """
    Создает текстовый файл с отчетом и возвращает путь к нему.
    """
    content = ""
    filename = "" # Инициализируем
    file_path = None # Инициализируем
    try:
        content = format_bookings_to_file_content(bookings, filter_details)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.txt"
        file_path = os.path.abspath(filename)

        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
        logger.info(f"Отчет по бронированиям сохранен в файл: {file_path}")
        return file_path
    except IOError as e_io:
        logger.error(f"Ошибка записи отчета в файл {filename}: {e_io}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при создании файла отчета: {e}", exc_info=True)
        # Пытаемся удалить частично созданный файл, если он есть
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e_remove:
                 logger.error(f"Ошибка при удалении файла отчета после ошибки создания: {e_remove}")
        return None

# --- END OF FILE admin_service.py ---