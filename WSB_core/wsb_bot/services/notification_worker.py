"""Воркер для обработки уведомлений из единого расписания (wsb_notifications_schedule).

Воркер периодически читает задачи из таблицы wsb_notifications_schedule
со статусом 'pending' и каналом 'telegram', отправляет уведомления
и обновляет статусы.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import telebot

from database import Database
from logger import logger

try:
    from wsb_core.notifications_schedule import (
        NotificationChannel,
        NotificationEventType,
        NotificationStatus,
    )
except ImportError:
    logger.error("wsb_core.notifications_schedule недоступен, воркер не будет работать")
    NotificationChannel = None
    NotificationEventType = None
    NotificationStatus = None


def process_telegram_notifications(
    db: Database,
    bot: telebot.TeleBot,
    batch_size: int = 10,
) -> Dict[str, int]:
    """
    Обрабатывает pending уведомления для Telegram из wsb_notifications_schedule.

    Args:
        db: Объект подключения к БД
        bot: Экземпляр Telegram бота
        batch_size: Максимальное количество задач для обработки за один запуск

    Returns:
        Словарь со статистикой: {'processed': N, 'sent': M, 'failed': K}
    """
    if NotificationChannel is None or NotificationStatus is None or NotificationEventType is None:
        logger.error("wsb_core.notifications_schedule недоступен, обработка пропущена")
        return {"processed": 0, "sent": 0, "failed": 0}

    stats = {"processed": 0, "sent": 0, "failed": 0}
    now = datetime.now()

    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Получаем задачи для обработки
                cur.execute(
                    """
                    SELECT id, booking_id, event_type, run_at, payload
                    FROM wsb_notifications_schedule
                    WHERE channel = %s
                      AND status = %s
                      AND run_at <= %s
                    ORDER BY run_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                    """,
                    (
                        NotificationChannel.TELEGRAM.value,
                        NotificationStatus.PENDING.value,
                        now,
                        batch_size,
                    ),
                )
                tasks = cur.fetchall()

                if not tasks:
                    return stats

                logger.debug(f"Найдено {len(tasks)} задач для обработки Telegram уведомлений")

                for task in tasks:
                    # Проверяем формат результата (кортеж или словарь)
                    if isinstance(task, dict):
                        task_id = task.get("id")
                        booking_id = task.get("booking_id")
                        event_type_str = task.get("event_type")
                        run_at = task.get("run_at")
                        payload_json = task.get("payload")
                    else:
                        # Если кортеж
                        task_id = task[0]
                        booking_id = task[1]
                        event_type_str = task[2]
                        run_at = task[3]
                        payload_json = task[4] if len(task) > 4 else None

                    stats["processed"] += 1

                    # Помечаем задачу как обрабатываемую
                    cur.execute(
                        """
                        UPDATE wsb_notifications_schedule
                        SET status = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        """,
                        (NotificationStatus.PROCESSING.value, task_id),
                    )

                    try:
                        # Получаем информацию о бронировании
                        cur.execute(
                            """
                            SELECT b.user_id, b.time_start, b.time_end, b.cancel, b.finish,
                                   e.name_equip
                            FROM bookings b
                            JOIN equipment e ON b.equip_id = e.id
                            WHERE b.id = %s
                            """,
                            (booking_id,),
                        )
                        booking_row = cur.fetchone()

                        if not booking_row:
                            raise ValueError(f"Бронирование {booking_id} не найдено")

                        # Проверяем, что бронь еще актуальна
                        if booking_row[3] or booking_row[4]:  # cancel или finish
                            logger.info(
                                f"Бронирование {booking_id} отменено или завершено, пропускаем уведомление"
                            )
                            cur.execute(
                                """
                                UPDATE wsb_notifications_schedule
                                SET status = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                                """,
                                (NotificationStatus.DONE.value, task_id),
                            )
                            continue

                        user_id = booking_row[0]
                        equip_name = booking_row[5]

                        # Формируем сообщение в зависимости от типа события
                        event_type = NotificationEventType(event_type_str)
                        message_text = _format_notification_message(
                            event_type, equip_name, booking_row[1], booking_row[2]
                        )

                        # Отправляем уведомление
                        try:
                            bot.send_message(user_id, message_text)
                            stats["sent"] += 1
                            logger.info(
                                f"Telegram уведомление отправлено пользователю {user_id} для брони {booking_id}"
                            )

                            # Помечаем как выполненное
                            cur.execute(
                                """
                                UPDATE wsb_notifications_schedule
                                SET status = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                                """,
                                (NotificationStatus.DONE.value, task_id),
                            )

                        except telebot.apihelper.ApiTelegramException as e:
                            error_msg = f"Telegram API error: {e.error_code} - {e.description}"
                            logger.warning(
                                f"Не удалось отправить Telegram уведомление пользователю {user_id}: {error_msg}"
                            )
                            stats["failed"] += 1

                            # Помечаем как неудачное
                            cur.execute(
                                """
                                UPDATE wsb_notifications_schedule
                                SET status = %s, last_error = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                                """,
                                (NotificationStatus.FAILED.value, error_msg[:500], task_id),
                            )

                    except Exception as e:
                        error_msg = str(e)[:500]
                        logger.error(
                            f"Ошибка при обработке задачи {task_id} (бронирование {booking_id}): {e}",
                            exc_info=True,
                        )
                        stats["failed"] += 1

                        cur.execute(
                            """
                            UPDATE wsb_notifications_schedule
                            SET status = %s, last_error = %s, updated_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                            """,
                            (NotificationStatus.FAILED.value, error_msg, task_id),
                        )

                conn.commit()
                logger.debug(
                    f"Обработка Telegram уведомлений завершена: processed={stats['processed']}, "
                    f"sent={stats['sent']}, failed={stats['failed']}"
                )

    except Exception as e:
        logger.error(f"Критическая ошибка в process_telegram_notifications: {e}", exc_info=True)

    return stats


def _format_notification_message(
    event_type: Any,  # NotificationEventType, но может быть None при ошибке импорта
    equip_name: str,
    time_start: datetime,
    time_end: datetime,
) -> str:
    """Форматирует текст уведомления в зависимости от типа события."""
    if NotificationEventType is None:
        return f"🔔 Уведомление о бронировании '{equip_name}'"
    
    if event_type == NotificationEventType.START:
        time_str = time_start.strftime("%H:%M")
        return (
            f"🔔 Напоминание: Ваша работа на '{equip_name}' "
            f"начнётся в {time_str}. Приятной работы!"
        )
    elif event_type == NotificationEventType.END:
        time_str = time_end.strftime("%H:%M")
        return (
            f"🔔 Напоминание: Ваша работа на '{equip_name}' "
            f"завершится в {time_str}."
        )
    else:
        return f"🔔 Уведомление о бронировании '{equip_name}'"

