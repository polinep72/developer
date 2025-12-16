"""Модуль для отслеживания новых бронирований в БД и отправки email-уведомлений.

Модуль отслеживает новые бронирования (созданные через бот) и автоматически
отправляет email-уведомления без дублей, используя механизм отслеживания
последнего обработанного ID.
"""

import logging
from datetime import datetime, date, time
from typing import Dict, Any, Optional, Tuple
from threading import Lock

from .email_service import send_booking_created_notification
from .bookings_core import CursorProtocol

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения последнего обработанного ID
_last_processed_booking_id: Optional[int] = None
_lock = Lock()


def get_last_processed_booking_id() -> Optional[int]:
    """Получить последний обработанный ID бронирования."""
    with _lock:
        return _last_processed_booking_id


def set_last_processed_booking_id(booking_id: int) -> None:
    """Установить последний обработанный ID бронирования."""
    global _last_processed_booking_id
    with _lock:
        _last_processed_booking_id = booking_id


def initialize_last_processed_id(cur: CursorProtocol) -> None:
    """Инициализировать последний обработанный ID из БД (максимальный существующий ID)."""
    try:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM bookings")
        result = cur.fetchone()
        max_id = result[0] if result else 0
        set_last_processed_booking_id(max_id)
        logger.info(f"Инициализирован последний обработанный ID бронирования: {max_id}")
    except Exception as e:
        logger.error(f"Ошибка при инициализации последнего обработанного ID: {e}", exc_info=True)
        set_last_processed_booking_id(0)


def process_new_bookings(
    cur: CursorProtocol,
    batch_size: int = 50,
) -> Dict[str, int]:
    """
    Обрабатывает новые бронирования и отправляет email-уведомления.

    Args:
        cur: Курсор БД для выполнения запросов
        batch_size: Максимальное количество новых бронирований для обработки за один запуск

    Returns:
        Словарь со статистикой: {'processed': N, 'sent': M, 'failed': K, 'skipped': L}
    """
    stats = {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}

    try:
        # Инициализируем последний ID при первом запуске
        if get_last_processed_booking_id() is None:
            try:
                initialize_last_processed_id(cur)
            except Exception as init_err:
                logger.error(f"Ошибка инициализации последнего ID: {init_err}", exc_info=True)
                return stats

        last_id = get_last_processed_booking_id() or 0

        # Получаем новые бронирования (ID > last_id)
        # Исключаем отмененные и завершенные
        try:
            cur.execute(
                """
                SELECT 
                    b.id, b.user_id, b.equip_id, b.date, b.time_start, b.time_end,
                    b.time_interval, b.data_booking,
                    e.name_equip,
                    u.email, u.first_name, u.last_name
                FROM bookings b
                JOIN equipment e ON b.equip_id = e.id
                JOIN users u ON b.user_id = u.users_id
                WHERE b.id > %s
                  AND b.cancel = FALSE
                  AND b.finish IS NULL
                ORDER BY b.id ASC
                LIMIT %s
                """,
                (last_id, batch_size),
            )
            new_bookings = cur.fetchall()
        except Exception as query_err:
            logger.error(f"Ошибка выполнения запроса новых бронирований: {query_err}", exc_info=True)
            return stats

        if not new_bookings:
            return stats

        logger.debug(f"Найдено {len(new_bookings)} новых бронирований для обработки (после ID {last_id})")

        max_processed_id = last_id

        for booking_row in new_bookings:
            try:
                # Извлекаем данные из booking_row (dict_row возвращает объекты с доступом по ключу)
                booking_id = booking_row["id"]  # type: ignore[index]
                user_id = booking_row["user_id"]  # type: ignore[index]
                booking_date = booking_row["date"]  # type: ignore[index]
                time_start = booking_row["time_start"]  # type: ignore[index]
                time_end = booking_row["time_end"]  # type: ignore[index]
                equipment_name = booking_row["name_equip"]  # type: ignore[index]
                user_email = booking_row.get("email") if hasattr(booking_row, 'get') else booking_row["email"]  # type: ignore[index]
                user_first_name = (booking_row.get("first_name") if hasattr(booking_row, 'get') else booking_row["first_name"]) or ""  # type: ignore[index]
                user_last_name = (booking_row.get("last_name") if hasattr(booking_row, 'get') else booking_row["last_name"]) or ""  # type: ignore[index]

                stats["processed"] += 1
                max_processed_id = max(max_processed_id, booking_id)

                # Проверяем наличие email
                if not user_email:
                    stats["skipped"] += 1
                    logger.debug(f"Пропущено уведомление для брони {booking_id} (нет email у пользователя {user_id})")
                    continue

                # Преобразуем время
                start_time_obj: time
                end_time_obj: time

                if isinstance(time_start, datetime):
                    start_time_obj = time_start.time()
                elif isinstance(time_start, time):
                    start_time_obj = time_start
                else:
                    logger.warning(f"Неожиданный тип time_start для брони {booking_id}: {type(time_start)}")
                    stats["failed"] += 1
                    continue

                if isinstance(time_end, datetime):
                    end_time_obj = time_end.time()
                elif isinstance(time_end, time):
                    end_time_obj = time_end
                else:
                    logger.warning(f"Неожиданный тип time_end для брони {booking_id}: {type(time_end)}")
                    stats["failed"] += 1
                    continue

                # Формируем имя пользователя
                user_name = f"{user_first_name} {user_last_name}".strip() or "Пользователь"

                # Отправляем email
                success = send_booking_created_notification(
                    user_email=user_email,
                    user_name=user_name,
                    equipment_name=equipment_name,
                    booking_date=booking_date,
                    start_time=start_time_obj,
                    end_time=end_time_obj,
                )

                if success:
                    stats["sent"] += 1
                    logger.info(f"Отправлено email-уведомление о создании брони {booking_id} пользователю {user_id} ({user_email})")
                else:
                    stats["failed"] += 1
                    logger.warning(f"Не удалось отправить email-уведомление для брони {booking_id} пользователю {user_id}")

            except (KeyError, TypeError, AttributeError) as e:
                logger.error(f"Ошибка при обработке бронирования: {e}, тип: {type(booking_row)}, значение: {booking_row}", exc_info=True)
                stats["failed"] += 1
                continue
            except Exception as e:
                logger.error(f"Неожиданная ошибка при обработке бронирования: {e}", exc_info=True)
                stats["failed"] += 1
                continue

        # Обновляем последний обработанный ID
        if max_processed_id > last_id:
            set_last_processed_booking_id(max_processed_id)
            logger.debug(f"Обновлен последний обработанный ID: {max_processed_id}")

    except Exception as e:
        # Логируем ошибку, но не прерываем выполнение - вернем статистику
        error_str = str(e).lower()
        if "server closed the connection" in error_str or "connection" in error_str:
            logger.warning(f"Ошибка соединения с БД в process_new_bookings (последний ID не обновлен): {e}")
        else:
            logger.error(f"Критическая ошибка в process_new_bookings: {e}", exc_info=True)

    return stats

