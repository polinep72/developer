"""Единое расписание уведомлений для WSB_core.

Пока модуль вводится как инфраструктура:
- Описывает таблицу wsb_notifications_schedule.
- Даёт вспомогательные функции для инициализации таблицы.
- Логику фактического планирования/воркеров будем подключать отдельными шагами.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Iterable, List, Optional

from .bookings_core import CursorProtocol
from .notifications_logic import (
    NOTIFICATION_BEFORE_START_MINUTES,
    NOTIFICATION_BEFORE_END_MINUTES,
)


class NotificationChannel(str, Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"


class NotificationEventType(str, Enum):
    START = "start"
    END = "end"
    EXTEND_OFFER = "extend_offer"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# DDL для таблицы расписания
DDL_CREATE_NOTIFICATIONS_SCHEDULE_TABLE = """
CREATE TABLE IF NOT EXISTS wsb_notifications_schedule (
    id              SERIAL PRIMARY KEY,
    booking_id      INTEGER NOT NULL,
    channel         VARCHAR(32) NOT NULL,
    event_type      VARCHAR(32) NOT NULL,
    run_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    payload         JSONB,
    last_error      TEXT,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_run_at
    ON wsb_notifications_schedule (run_at);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_channel_status
    ON wsb_notifications_schedule (channel, status);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_booking
    ON wsb_notifications_schedule (booking_id);
"""


@dataclass
class NotificationScheduleEntry:
    id: Optional[int]
    booking_id: int
    channel: NotificationChannel
    event_type: NotificationEventType
    run_at: datetime
    status: NotificationStatus = NotificationStatus.PENDING
    payload: Optional[dict[str, Any]] = None
    last_error: Optional[str] = None


def ensure_notifications_schedule_table(cur: Any) -> None:
    """Гарантирует наличие таблицы расписания уведомлений.

    cur — курсор psycopg (или совместимый), как в других ядровых модулях.
    """

    cur.execute(DDL_CREATE_NOTIFICATIONS_SCHEDULE_TABLE)


def clear_schedule_for_booking(
    cur: CursorProtocol,
    booking_id: int,
    channels: Optional[Iterable[NotificationChannel]] = None,
) -> None:
    """Удалить записи расписания по брони (опционально только по указанным каналам)."""

    ensure_notifications_schedule_table(cur)
    if channels is None:
        cur.execute(
            "DELETE FROM wsb_notifications_schedule WHERE booking_id = %s",
            (booking_id,),
        )
    else:
        channel_values = tuple(str(ch) for ch in channels)
        # Защита от пустого IN (...)
        if not channel_values:
            return
        placeholders = ", ".join(["%s"] * len(channel_values))
        params: List[Any] = [booking_id, *channel_values]
        cur.execute(
            f"""
            DELETE FROM wsb_notifications_schedule
            WHERE booking_id = %s AND channel IN ({placeholders})
            """,
            tuple(params),
        )


def _is_booking_row_active(row: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    """Проверка, нужна ли вообще запись в расписании для этой брони."""

    if row.get("cancel"):
        return False
    if row.get("finish") is not None:
        return False
    status_val = row.get("status")
    if status_val in ("cancelled", "finished"):
        return False

    time_start = row.get("time_start")
    time_end = row.get("time_end")
    if not isinstance(time_start, datetime) or not isinstance(time_end, datetime):
        return False

    now = now or datetime.now()
    # Брони, которые уже полностью в прошлом, не планируем
    if time_end <= now:
        return False

    return True


def _insert_event(
    cur: CursorProtocol,
    *,
    booking_id: int,
    channel: NotificationChannel,
    event_type: NotificationEventType,
    run_at: datetime,
) -> None:
    cur.execute(
        """
        INSERT INTO wsb_notifications_schedule
            (booking_id, channel, event_type, run_at, status)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            booking_id,
            channel.value,
            event_type.value,
            run_at,
            NotificationStatus.PENDING.value,
        ),
    )


def rebuild_schedule_for_booking(
    cur: CursorProtocol,
    *,
    booking_id: int,
    channels: Optional[Iterable[NotificationChannel]] = None,
) -> int:
    """Пересчитать расписание уведомлений для одной брони.

    Возвращает количество созданных записей.
    """

    ensure_notifications_schedule_table(cur)
    if channels is None:
        channels = (NotificationChannel.TELEGRAM, NotificationChannel.EMAIL)

    # Удаляем старые записи
    clear_schedule_for_booking(cur, booking_id, channels)

    # Подтягиваем бронь
    cur.execute(
        """
        SELECT id, time_start, time_end, cancel, finish
        FROM bookings
        WHERE id = %s
        """,
        (booking_id,),
    )
    row = cur.fetchone()
    if not row:
        return 0

    # dict() на случай, если драйвер возвращает mapping-подобный объект
    if not isinstance(row, dict):
        row = dict(row)

    if not _is_booking_row_active(row):
        return 0

    time_start: datetime = row["time_start"]
    time_end: datetime = row["time_end"]
    created = 0

    # Время уведомлений
    notify_start_at = time_start - timedelta(minutes=NOTIFICATION_BEFORE_START_MINUTES)
    notify_end_at = time_end - timedelta(minutes=NOTIFICATION_BEFORE_END_MINUTES)

    # Проверяем, что время уведомлений еще не прошло
    now = datetime.now()
    
    # Создаем уведомления только если время уведомления еще не прошло
    for ch in channels:
        # Уведомление о начале - только если время уведомления еще не прошло
        if notify_start_at > now:
            _insert_event(
                cur,
                booking_id=booking_id,
                channel=ch,
                event_type=NotificationEventType.START,
                run_at=notify_start_at,
            )
            created += 1
        
        # Уведомление об окончании - только если время уведомления еще не прошло
        if notify_end_at > now:
            _insert_event(
                cur,
                booking_id=booking_id,
                channel=ch,
                event_type=NotificationEventType.END,
                run_at=notify_end_at,
            )
            created += 1

    return created


def rebuild_schedule_for_all_bookings(
    cur: CursorProtocol,
    *,
    channels: Optional[Iterable[NotificationChannel]] = None,
) -> int:
    """Полное перепланирование расписания уведомлений по всем актуальным броням.

    Используется как эквивалент команды /schedule.
    Возвращает количество созданных записей.
    """

    ensure_notifications_schedule_table(cur)
    if channels is None:
        channels = (NotificationChannel.TELEGRAM, NotificationChannel.EMAIL)

    # Полностью очищаем расписание перед пересборкой
    cur.execute("DELETE FROM wsb_notifications_schedule")

    now = datetime.now()
    cur.execute(
        """
        SELECT id, time_start, time_end, cancel, finish
        FROM bookings
        WHERE cancel = FALSE
          AND finish IS NULL
          AND time_end > %s
        """,
        (now,),
    )
    rows = cur.fetchall()

    total_created = 0
    for raw in rows:
        row = dict(raw) if not isinstance(raw, dict) else raw
        if not _is_booking_row_active(row, now=now):
            continue
        total_created += rebuild_schedule_for_booking(
            cur,
            booking_id=row["id"],
            channels=channels,
        )

    return total_created
