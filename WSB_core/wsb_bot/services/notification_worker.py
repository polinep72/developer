"""Воркер для обработки уведомлений из единого расписания (wsb_notifications_schedule).

Воркер периодически читает задачи из таблицы wsb_notifications_schedule
со статусом 'pending' и каналом 'telegram', отправляет уведомления
и обновляет статусы.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from datetime import timedelta

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
                # Автоотмена неподтвержденных бронирований (статус не active) при наступлении времени начала
                cur.execute(
                    """
                    SELECT id, user_id, time_start
                    FROM bookings
                    WHERE cancel = FALSE
                      AND finish IS NULL
                      AND time_start <= NOW()
                      AND time_start >= NOW() - INTERVAL '20 minutes' -- не трогаем старые периоды
                      AND (status IS NULL OR status NOT IN ('active'))
                    """
                )
                auto_cancel_rows = cur.fetchall()
                if auto_cancel_rows:
                    cancelled_ids = []
                    for row in auto_cancel_rows:
                        booking_id = row["id"]
                        user_id = row["user_id"]
                        cur.execute(
                            "UPDATE bookings SET cancel = TRUE, status = 'cancelled' WHERE id = %s AND cancel = FALSE AND finish IS NULL",
                            (booking_id,),
                        )
                        cancelled_ids.append(booking_id)
                        try:
                            bot.send_message(
                                user_id,
                                f"⚠️ Время подтверждения брони {booking_id} истекло. Бронь отменена автоматически.",
                            )
                        except Exception as e_msg:
                            logger.warning(f"Не удалось отправить сообщение об автоотмене {booking_id}: {e_msg}")
                        if cancelled_ids:
                            conn.commit()
                            logger.info(f"Автоотменены просроченные брони: {cancelled_ids}")

                # Автозавершение бронирований после окончания (если еще не завершены)
                cur.execute(
                    """
                    SELECT id, user_id, time_end
                    FROM bookings
                    WHERE cancel = FALSE
                      AND finish IS NULL
                      AND time_end <= NOW()
                      AND time_end >= NOW() - INTERVAL '20 minutes' -- не трогаем старые периоды
                    """
                )
                auto_finish_rows = cur.fetchall()
                if auto_finish_rows:
                    finished_ids = []
                    now_ts = datetime.now()
                    for row in auto_finish_rows:
                        booking_id = row["id"]
                        user_id = row["user_id"]
                        cur.execute(
                            "UPDATE bookings SET finish = %s, status = 'finished' WHERE id = %s AND cancel = FALSE AND finish IS NULL",
                            (now_ts, booking_id),
                        )
                        finished_ids.append(booking_id)
                        try:
                            bot.send_message(
                                user_id,
                                f"✅ Работа по бронированию {booking_id} завершена автоматически.",
                            )
                        except Exception as e_msg:
                            logger.warning(f"Не удалось отправить сообщение об автозавершении {booking_id}: {e_msg}")
                    if finished_ids:
                        conn.commit()
                        logger.info(f"Автозавершены брони: {finished_ids}")

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

                        # Извлекаем данные из booking_row (может быть кортеж или словарь)
                        if isinstance(booking_row, dict):
                            user_id = booking_row["user_id"]
                            time_start = booking_row["time_start"]
                            time_end = booking_row["time_end"]
                            is_cancelled = booking_row.get("cancel", False)
                            is_finished = booking_row.get("finish") is not None
                            equip_name = booking_row["name_equip"]
                        else:
                            # Если кортеж
                            user_id = booking_row[0]
                            time_start = booking_row[1]
                            time_end = booking_row[2]
                            is_cancelled = booking_row[3]
                            is_finished = booking_row[4] is not None
                            equip_name = booking_row[5]

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
                        
                        # Определяем тип события
                        event_type = NotificationEventType(event_type_str)
                        
                        # Проверяем, что время бронирования еще не прошло
                        now_check = datetime.now()
                        if event_type == NotificationEventType.START:
                            # Для уведомления о начале: проверяем, что время начала еще не прошло
                            if isinstance(time_start, datetime) and time_start <= now_check:
                                logger.info(
                                    f"Бронирование {booking_id} уже началось ({time_start} <= {now_check}), пропускаем уведомление о начале"
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
                        elif event_type == NotificationEventType.END:
                            # Для уведомления об окончании: проверяем, что время окончания еще не прошло
                            if isinstance(time_end, datetime) and time_end <= now_check:
                                logger.info(
                                    f"Бронирование {booking_id} уже закончилось ({time_end} <= {now_check}), пропускаем уведомление об окончании"
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
                        
                        # Для уведомлений о начале используем специальную логику с кнопкой подтверждения
                        if event_type == NotificationEventType.START:
                            # Используем логику из notification_service для отправки уведомления с кнопкой
                            try:
                                from utils import keyboards
                                import constants as const
                                
                                if booking_id is None:
                                    raise ValueError("booking_id is None")
                                
                                markup = keyboards.generate_start_confirmation_keyboard(booking_id)
                                start_time_str = time_start.strftime('%H:%M')
                                minutes_before = const.NOTIFICATION_BEFORE_START_MINUTES
                                timeout_minutes = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS // 60
                                message_text = (
                                    f"❗ Ваше бронирование на '{equip_name}' начинается через {minutes_before} мин ({start_time_str}).\n\n"
                                    f"Пожалуйста, **подтвердите актуальность** в течение {timeout_minutes} минут, иначе бронь будет автоматически отменена."
                                )
                                
                                sent_msg = bot.send_message(
                                    user_id,
                                    message_text,
                                    reply_markup=markup,
                                    parse_mode='Markdown'
                                )
                                stats["sent"] += 1
                                logger.info(
                                    f"Telegram уведомление с кнопкой подтверждения отправлено пользователю {user_id} для брони {booking_id} (msg_id: {sent_msg.message_id})"
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
                            except telebot.apihelper.ApiTelegramException as e_notify:
                                error_msg = f"Telegram API error: {e_notify.error_code} - {e_notify.description}"
                                logger.warning(
                                    f"Не удалось отправить Telegram уведомление пользователю {user_id}: {error_msg}"
                                )
                                stats["failed"] += 1
                                cur.execute(
                                    """
                                    UPDATE wsb_notifications_schedule
                                    SET status = %s, last_error = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = %s
                                    """,
                                    (NotificationStatus.FAILED.value, error_msg[:500], task_id),
                                )
                                continue
                            except Exception as e_notify:
                                logger.error(f"Ошибка при отправке уведомления о начале для брони {booking_id}: {e_notify}", exc_info=True)
                                stats["failed"] += 1
                                error_msg = str(e_notify)[:500]
                                cur.execute(
                                    """
                                    UPDATE wsb_notifications_schedule
                                    SET status = %s, last_error = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = %s
                                    """,
                                    (NotificationStatus.FAILED.value, error_msg, task_id),
                                )
                                continue
                        else:
                            # Для других типов уведомлений используем формат + клавиатура для окончания
                            message_text = _format_notification_message(
                                event_type, equip_name, time_start, time_end
                            )

                            markup = None
                            if event_type == NotificationEventType.END and booking_id is not None:
                                try:
                                    from utils import keyboards
                                    markup = keyboards.generate_extend_prompt_keyboard(booking_id)
                                except Exception as kb_err:
                                    logger.warning(f"Не удалось построить клавиатуру продления для брони {booking_id}: {kb_err}")

                            # Отправляем уведомление
                            try:
                                bot.send_message(user_id, message_text, reply_markup=markup)
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

