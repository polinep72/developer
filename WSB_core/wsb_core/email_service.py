"""Сервис для отправки email-уведомлений в wsb_core.

Модуль предоставляет базовую функциональность отправки email
для использования в боте и других компонентах системы.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import date, time

from .app_config import (
    WSB_SMTP_HOST,
    WSB_SMTP_PORT,
    WSB_SMTP_USER,
    WSB_SMTP_PASSWORD,
    WSB_SMTP_FROM_EMAIL,
    WSB_SMTP_FROM_NAME,
    WSB_ENABLE_EMAIL,
)

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    body_text: str = "",
) -> bool:
    """
    Отправить email-уведомление.

    Args:
        to_email: Email получателя
        subject: Тема письма
        body_html: HTML-тело письма
        body_text: Текстовое тело письма (опционально)

    Returns:
        True при успехе, False при ошибке
    """
    if not WSB_ENABLE_EMAIL:
        logger.debug(f"[EMAIL DISABLED] To: {to_email}, Subject: {subject}")
        return True

    if not WSB_SMTP_USER or not WSB_SMTP_PASSWORD:
        logger.warning(f"[EMAIL CONFIG MISSING] Cannot send email to {to_email}")
        return False

    if not to_email or "@" not in to_email:
        logger.warning(f"[EMAIL INVALID] Invalid email address: {to_email}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{WSB_SMTP_FROM_NAME} <{WSB_SMTP_FROM_EMAIL}>"
        msg["To"] = to_email

        if body_text:
            part_text = MIMEText(body_text, "plain", "utf-8")
            msg.attach(part_text)

        part_html = MIMEText(body_html, "html", "utf-8")
        msg.attach(part_html)

        with smtplib.SMTP(WSB_SMTP_HOST, WSB_SMTP_PORT) as server:
            server.starttls()
            server.login(WSB_SMTP_USER, WSB_SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"[EMAIL SENT] To: {to_email}, Subject: {subject}")
        return True
    except Exception as exc:
        logger.error(f"[EMAIL ERROR] Failed to send to {to_email}: {exc}", exc_info=True)
        return False


def send_booking_created_notification(
    user_email: str,
    user_name: str,
    equipment_name: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> bool:
    """
    Отправить уведомление о создании бронирования.

    Args:
        user_email: Email пользователя
        user_name: Имя пользователя
        equipment_name: Название оборудования
        booking_date: Дата бронирования
        start_time: Время начала
        end_time: Время окончания

    Returns:
        True при успехе, False при ошибке
    """
    subject = f"Бронирование создано: {equipment_name}"

    date_str = booking_date.strftime("%d.%m.%Y")
    time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #3b82f6;">Бронирование успешно создано</h2>
            <p>Здравствуйте, {user_name}!</p>
            <p>Ваше бронирование было успешно создано:</p>
            <div style="background: #f8fafc; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <p><strong>Оборудование:</strong> {equipment_name}</p>
                <p><strong>Дата:</strong> {date_str}</p>
                <p><strong>Время:</strong> {time_str}</p>
            </div>
            <p>Не забудьте о своем бронировании!</p>
            <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                Это автоматическое уведомление от системы WSB.
            </p>
        </div>
    </body>
    </html>
    """

    body_text = f"""
Бронирование успешно создано

Здравствуйте, {user_name}!

Ваше бронирование было успешно создано:

Оборудование: {equipment_name}
Дата: {date_str}
Время: {time_str}

Не забудьте о своем бронировании!

---
Это автоматическое уведомление от системы WSB.
    """

    return send_email(user_email, subject, body_html, body_text)

