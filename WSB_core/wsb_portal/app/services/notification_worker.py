"""Воркер для обработки email-уведомлений из единого расписания (wsb_notifications_schedule).

Воркер периодически читает задачи из таблицы wsb_notifications_schedule
со статусом 'pending' и каналом 'email', отправляет уведомления
и обновляет статусы.
"""

import logging
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)

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

from .notifications import (
    send_booking_start_notification,
    should_send_email_notification,
    _send_email,
)
from .auth import _connect


def process_email_notifications(
    batch_size: int = 10,
) -> Dict[str, int]:
    """
    Обрабатывает pending уведомления для Email из wsb_notifications_schedule.

    Args:
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
        conn = _connect()
        try:
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
                        NotificationChannel.EMAIL.value,
                        NotificationStatus.PENDING.value,
                        now,
                        batch_size,
                    ),
                )
                tasks = cur.fetchall()

                if not tasks:
                    return stats

                logger.debug(f"Найдено {len(tasks)} задач для обработки Email уведомлений")

                for task in tasks:
                    # psycopg с dict_row возвращает объекты, которые можно использовать как словари
                    try:
                        # Используем доступ по ключу (dict_row возвращает объекты с доступом по ключу)
                        task_id = task["id"]
                        booking_id = task["booking_id"]
                        event_type_str = task["event_type"]
                        run_at = task["run_at"]
                        payload_json = task.get("payload") if hasattr(task, 'get') else (task["payload"] if "payload" in task else None)
                    except (KeyError, TypeError, AttributeError) as e:
                        logger.error(f"Ошибка при разборе задачи из БД: {e}, тип: {type(task)}, значение: {task}")
                        continue

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
                        # Получаем информацию о бронировании и пользователе
                        cur.execute(
                            """
                            SELECT b.user_id, b.time_start, b.time_end, b.cancel, b.finish,
                                   e.name_equip,
                                   u.email, u.first_name, u.last_name
                            FROM bookings b
                            JOIN equipment e ON b.equip_id = e.id
                            JOIN users u ON b.user_id = u.users_id
                            WHERE b.id = %s
                            """,
                            (booking_id,),
                        )
                        booking_row = cur.fetchone()

                        if not booking_row:
                            raise ValueError(f"Бронирование {booking_id} не найдено")

                        # Извлекаем данные из booking_row (dict_row возвращает словари)
                        user_id = booking_row["user_id"]
                        time_start = booking_row["time_start"]
                        time_end = booking_row["time_end"]
                        is_cancelled = booking_row.get("cancel", False) if isinstance(booking_row, dict) else booking_row[3]
                        is_finished = booking_row.get("finish") is not None if isinstance(booking_row, dict) else (booking_row[4] is not None)
                        equip_name = booking_row["name_equip"]
                        user_email = booking_row["email"]
                        user_first_name = booking_row.get("first_name") or "" if isinstance(booking_row, dict) else (booking_row[7] or "")
                        user_last_name = booking_row.get("last_name") or "" if isinstance(booking_row, dict) else (booking_row[8] or "")

                        # Проверяем, что бронь еще актуальна
                        if is_cancelled or is_finished:
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

                        user_name = f"{user_first_name} {user_last_name}".strip() or "Пользователь"

                        # Проверяем настройки уведомлений пользователя
                        if not should_send_email_notification(user_id):
                            logger.info(
                                f"Пользователь {user_id} отключил email-уведомления, пропускаем"
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

                        if not user_email:
                            logger.warning(
                                f"У пользователя {user_id} не указан email, пропускаем уведомление"
                            )
                            cur.execute(
                                """
                                UPDATE wsb_notifications_schedule
                                SET status = %s, last_error = %s, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                                """,
                                (
                                    NotificationStatus.FAILED.value,
                                    "Email пользователя не указан",
                                    task_id,
                                ),
                            )
                            stats["failed"] += 1
                            continue

                        # Отправляем уведомление в зависимости от типа события
                        event_type = NotificationEventType(event_type_str)
                        success = False

                        if event_type == NotificationEventType.START:
                            # Используем существующую функцию отправки
                            success = send_booking_start_notification(
                                user_email=user_email,
                                user_name=user_name,
                                equipment_name=equip_name,
                                booking_date=time_start.date(),
                                start_time=time_start.time(),
                                end_time=time_end.time(),
                            )
                        elif event_type == NotificationEventType.END:
                            # Для уведомления об окончании создаем простое сообщение
                            subject = f"⏰ Напоминание: окончание работы с {equip_name}"
                            time_str = time_end.strftime("%H:%M")
                            body_html = f"""
                            <html>
                            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                                    <h2 style="color: #f59e0b;">⏰ Напоминание об окончании работы</h2>
                                    <p>Здравствуйте, {user_name}!</p>
                                    <p>Напоминаем, что ваша работа с оборудованием завершится в {time_str}:</p>
                                    <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                                        <p><strong>Оборудование:</strong> {equip_name}</p>
                                        <p><strong>Время окончания:</strong> {time_str}</p>
                                    </div>
                                    <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                                        Это автоматическое уведомление от системы WSB Portal.
                                    </p>
                                </div>
                            </body>
                            </html>
                            """
                            body_text = f"""
⏰ Напоминание об окончании работы

Здравствуйте, {user_name}!

Напоминаем, что ваша работа с оборудованием завершится в {time_str}:

Оборудование: {equip_name}
Время окончания: {time_str}

---
Это автоматическое уведомление от системы WSB Portal.
                            """
                            success = _send_email(user_email, subject, body_html, body_text)
                        else:
                            logger.warning(f"Неизвестный тип события: {event_type_str}")
                            success = False

                        if success:
                            stats["sent"] += 1
                            logger.info(
                                f"Email уведомление отправлено пользователю {user_id} ({user_email}) для брони {booking_id}"
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
                        else:
                            error_msg = "Не удалось отправить email"
                            logger.warning(
                                f"Не удалось отправить Email уведомление пользователю {user_id}: {error_msg}"
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
                    f"Обработка Email уведомлений завершена: processed={stats['processed']}, "
                    f"sent={stats['sent']}, failed={stats['failed']}"
                )

        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Критическая ошибка в process_email_notifications: {e}", exc_info=True)

    return stats

