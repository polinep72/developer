"""Единая логика уведомлений для WSB_core.

Задачи модуля:
- Централизовать константы таймингов уведомлений (до начала / до конца).
- Задать политику, когда бронь считается валидной для уведомления.
- Задать политику, когда можно предлагать продление при уведомлении о завершении.

Модуль специально не зависит от Telegram/SMTP, работает только с датами/моделями.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Optional

from .constants import (
    WORKING_HOURS_END,
    BOOKING_TIME_STEP_MINUTES,
)
from .app_config import (
    WSB_TIMEZONE,
    WSB_NOTIFICATION_BEFORE_START_MINUTES,
    WSB_NOTIFICATION_BEFORE_END_MINUTES,
)
from .models import Booking, BookingStatus


# --- Базовые константы уведомлений ---

# За сколько минут до НАЧАЛА/КОНЦА слать уведомления (читаем из app_config)
NOTIFICATION_BEFORE_START_MINUTES: int = WSB_NOTIFICATION_BEFORE_START_MINUTES
NOTIFICATION_BEFORE_END_MINUTES: int = WSB_NOTIFICATION_BEFORE_END_MINUTES

# Таймзона планировщика / уведомлений (единая)
SCHEDULER_TIMEZONE: str = WSB_TIMEZONE


@dataclass
class NotificationPolicyResult:
    """Результат проверки возможности уведомления / продления."""

    can_notify: bool
    reason: Optional[str] = None


@dataclass
class ExtensionPolicyResult:
    """Результат проверки, можно ли предлагать продление по окончании."""

    can_extend: bool
    reason: Optional[str] = None


def is_booking_valid_for_start_notification(now: datetime, booking: Booking) -> NotificationPolicyResult:
    """Проверка, имеет ли смысл слать уведомление о СКОРОМ НАЧАЛЕ.

    Правила:
    - Бронь не отменена и не завершена.
    - Время начала в будущем.
    - Разница не меньше 0 и не больше NOTIFICATION_BEFORE_START_MINUTES.
    """

    if booking.cancel or booking.status in (BookingStatus.CANCELLED, BookingStatus.FINISHED):
        return NotificationPolicyResult(False, "booking_inactive")

    if booking.time_start <= now:
        return NotificationPolicyResult(False, "already_started")

    delta = booking.time_start - now
    minutes = delta.total_seconds() / 60
    if minutes < 0:
        return NotificationPolicyResult(False, "already_started_negative")
    if minutes > NOTIFICATION_BEFORE_START_MINUTES:
        return NotificationPolicyResult(False, "too_early")

    return NotificationPolicyResult(True)


def is_booking_valid_for_end_notification(now: datetime, booking: Booking) -> NotificationPolicyResult:
    """Проверка, имеет ли смысл слать уведомление о СКОРОМ ОКОНЧАНИИ.

    Правила:
    - Бронь не отменена и не завершена.
    - Время окончания в будущем.
    - Разница не меньше 0 и не больше NOTIFICATION_BEFORE_END_MINUTES.
    """

    if booking.cancel or booking.status in (BookingStatus.CANCELLED, BookingStatus.FINISHED):
        return NotificationPolicyResult(False, "booking_inactive")

    if booking.time_end <= now:
        return NotificationPolicyResult(False, "already_ended")

    delta = booking.time_end - now
    minutes = delta.total_seconds() / 60
    if minutes < 0:
        return NotificationPolicyResult(False, "already_ended_negative")
    if minutes > NOTIFICATION_BEFORE_END_MINUTES:
        return NotificationPolicyResult(False, "too_early")

    return NotificationPolicyResult(True)


def can_offer_extension_on_end(
    *,
    booking: Booking,
    now: datetime,
    has_conflicts_in_extension_window: bool,
    extension_step_minutes: int | None = None,
) -> ExtensionPolicyResult:
    """Политика, можно ли показывать пользователю предложение продлить бронь в конце.

    Параметр has_conflicts_in_extension_window вызывающая сторона должна посчитать сама
    (например, проверкой пересечений в БД на интервале [time_end, time_end + step]).

    Правила:
    - Бронь активна (не отменена, не завершена, текущее время < time_end).
    - В пределах рабочего дня есть хотя бы один шаг продления (по BOOKING_TIME_STEP_MINUTES).
    - Нет конфликтов в ближайшем шаге продления.
    """

    if booking.cancel or booking.status in (BookingStatus.CANCELLED, BookingStatus.FINISHED):
        return ExtensionPolicyResult(False, "booking_inactive")

    if booking.time_end <= now:
        return ExtensionPolicyResult(False, "already_ended")

    step = timedelta(minutes=extension_step_minutes or BOOKING_TIME_STEP_MINUTES)
    current_end = booking.time_end
    work_end_dt = datetime.combine(current_end.date(), WORKING_HOURS_END)

    # хотя бы один шаг должен помещаться в рабочий день
    if current_end + step > work_end_dt:
        return ExtensionPolicyResult(False, "no_time_in_workday")

    if has_conflicts_in_extension_window:
        return ExtensionPolicyResult(False, "conflict_in_window")

    return ExtensionPolicyResult(True)
