"""
Сервис для отправки уведомлений пользователям
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from datetime import datetime, date, time
from dotenv import load_dotenv
import os

# Загружаем .env только если переменные окружения не заданы
# Это позволяет использовать env_file из docker-compose с приоритетом
if not os.getenv("SMTP_HOST") and not os.getenv("EMAIL_HOST"):
    load_dotenv(override=False)

# Настройки SMTP из переменных окружения
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "WSB Portal")

# Флаг для включения/выключения отправки (для разработки)
ENABLE_EMAIL = os.getenv("ENABLE_EMAIL", "false").lower() == "true"


def _send_email(to_email: str, subject: str, body_html: str, body_text: str = "") -> bool:
    """
    Отправить email-уведомление.
    Возвращает True при успехе, False при ошибке.
    """
    if not ENABLE_EMAIL:
        print(f"[EMAIL DISABLED] To: {to_email}, Subject: {subject}")
        return True
    
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[EMAIL CONFIG MISSING] Cannot send email to {to_email}")
        return False
    
    if not to_email or "@" not in to_email:
        print(f"[EMAIL INVALID] Invalid email address: {to_email}")
        return False
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        
        if body_text:
            part_text = MIMEText(body_text, "plain", "utf-8")
            msg.attach(part_text)
        
        part_html = MIMEText(body_html, "html", "utf-8")
        msg.attach(part_html)
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"[EMAIL SENT] To: {to_email}, Subject: {subject}")
        return True
    except Exception as exc:
        print(f"[EMAIL ERROR] Failed to send to {to_email}: {exc}")
        return False


def send_booking_created_notification(
    user_email: str,
    user_name: str,
    equipment_name: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> bool:
    """Отправить уведомление о создании бронирования"""
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
                Это автоматическое уведомление от системы WSB Portal.
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
Это автоматическое уведомление от системы WSB Portal.
    """
    
    return _send_email(user_email, subject, body_html, body_text)


def send_booking_cancelled_notification(
    user_email: str,
    user_name: str,
    equipment_name: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> bool:
    """Отправить уведомление об отмене бронирования"""
    subject = f"Бронирование отменено: {equipment_name}"
    
    date_str = booking_date.strftime("%d.%m.%Y")
    time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #ef4444;">Бронирование отменено</h2>
            <p>Здравствуйте, {user_name}!</p>
            <p>Ваше бронирование было отменено:</p>
            <div style="background: #fef2f2; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ef4444;">
                <p><strong>Оборудование:</strong> {equipment_name}</p>
                <p><strong>Дата:</strong> {date_str}</p>
                <p><strong>Время:</strong> {time_str}</p>
            </div>
            <p>Если вы не отменяли это бронирование, пожалуйста, свяжитесь с администратором.</p>
            <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                Это автоматическое уведомление от системы WSB Portal.
            </p>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
Бронирование отменено

Здравствуйте, {user_name}!

Ваше бронирование было отменено:

Оборудование: {equipment_name}
Дата: {date_str}
Время: {time_str}

Если вы не отменяли это бронирование, пожалуйста, свяжитесь с администратором.

---
Это автоматическое уведомление от системы WSB Portal.
    """
    
    return _send_email(user_email, subject, body_html, body_text)


def send_booking_start_notification(
    user_email: str,
    user_name: str,
    equipment_name: str,
    booking_date: date,
    start_time: time,
    end_time: time,
) -> bool:
    """Отправить уведомление о начале работы"""
    subject = f"⏰ Напоминание: начало работы с {equipment_name}"
    
    date_str = booking_date.strftime("%d.%m.%Y")
    time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #10b981;">⏰ Напоминание о начале работы</h2>
            <p>Здравствуйте, {user_name}!</p>
            <p>Напоминаем, что у вас запланирована работа с оборудованием:</p>
            <div style="background: #ecfdf5; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                <p><strong>Оборудование:</strong> {equipment_name}</p>
                <p><strong>Дата:</strong> {date_str}</p>
                <p><strong>Время:</strong> {time_str}</p>
            </div>
            <p>Удачной работы!</p>
            <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                Это автоматическое уведомление от системы WSB Portal.
            </p>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
⏰ Напоминание о начале работы

Здравствуйте, {user_name}!

Напоминаем, что у вас запланирована работа с оборудованием:

Оборудование: {equipment_name}
Дата: {date_str}
Время: {time_str}

Удачной работы!

---
Это автоматическое уведомление от системы WSB Portal.
    """
    
    return _send_email(user_email, subject, body_html, body_text)


def send_booking_start_summary(
    user_email: str,
    user_name: str,
    bookings: List[Dict[str, Any]],
) -> bool:
    """
    Отправить одно напоминание с несколькими бронированиями.
    bookings: список словарей с ключами equipment_name, date, start_time, end_time
    """
    if not bookings:
        return True

    subject = f"⏰ Напоминание: ближайшие бронирования ({len(bookings)})"

    rows_html = "".join(
        f"""
            <tr>
                <td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{item['equipment_name']}</td>
                <td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{item['date'].strftime('%d.%m.%Y')}</td>
                <td style="padding: 8px 12px; border: 1px solid #e2e8f0;">{item['start_time'].strftime('%H:%M')} – {item['end_time'].strftime('%H:%M')}</td>
            </tr>
        """
        for item in bookings
    )

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 640px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #0ea5e9;">Напоминание о начале работы</h2>
            <p>Здравствуйте, {user_name}!</p>
            <p>В ближайшее время у вас запланированы следующие бронирования:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 15px;">
                <thead>
                    <tr style="background: #f1f5f9;">
                        <th style="padding: 8px 12px; border: 1px solid #e2e8f0; text-align: left;">Оборудование</th>
                        <th style="padding: 8px 12px; border: 1px solid #e2e8f0; text-align: left;">Дата</th>
                        <th style="padding: 8px 12px; border: 1px solid #e2e8f0; text-align: left;">Интервал</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <p>Удачной работы!</p>
            <p style="color: #94a3b8; font-size: 12px; margin-top: 30px;">
                Это автоматическое уведомление от системы WSB Portal.
            </p>
        </div>
    </body>
    </html>
    """

    lines_text = "\n".join(
        f"- {item['equipment_name']}: {item['date'].strftime('%d.%m.%Y')} "
        f"{item['start_time'].strftime('%H:%M')} – {item['end_time'].strftime('%H:%M')}"
        for item in bookings
    )

    body_text = f"""
Напоминание о начале работы

Здравствуйте, {user_name}!

В ближайшее время у вас запланированы бронирования:
{lines_text}

Удачной работы!

---
Это автоматическое уведомление от системы WSB Portal.
    """

    return _send_email(user_email, subject, body_html, body_text)


def send_booking_conflict_notification(
    admin_emails: List[str],
    equipment_name: str,
    booking_date: date,
    start_time: time,
    end_time: time,
    conflicting_user: str,
    conflicting_time: str,
) -> bool:
    """Отправить уведомление администраторам о конфликте бронирования"""
    if not admin_emails:
        return False
    
    subject = f"⚠️ Конфликт бронирования: {equipment_name}"
    
    date_str = booking_date.strftime("%d.%m.%Y")
    time_str = f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
    
    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #f59e0b;">⚠️ Обнаружен конфликт бронирования</h2>
            <p>Обнаружена попытка создать бронирование, которое конфликтует с существующим:</p>
            <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                <p><strong>Оборудование:</strong> {equipment_name}</p>
                <p><strong>Дата:</strong> {date_str}</p>
                <p><strong>Запрашиваемое время:</strong> {time_str}</p>
                <p><strong>Конфликт с:</strong> {conflicting_user}</p>
                <p><strong>Время конфликта:</strong> {conflicting_time}</p>
            </div>
            <p>Пожалуйста, проверьте расписание и свяжитесь с пользователями при необходимости.</p>
            <p style="color: #64748b; font-size: 12px; margin-top: 30px;">
                Это автоматическое уведомление от системы WSB Portal.
            </p>
        </div>
    </body>
    </html>
    """
    
    body_text = f"""
⚠️ Обнаружен конфликт бронирования

Обнаружена попытка создать бронирование, которое конфликтует с существующим:

Оборудование: {equipment_name}
Дата: {date_str}
Запрашиваемое время: {time_str}
Конфликт с: {conflicting_user}
Время конфликта: {conflicting_time}

Пожалуйста, проверьте расписание и свяжитесь с пользователями при необходимости.

---
Это автоматическое уведомление от системы WSB Portal.
    """
    
    success = True
    for admin_email in admin_emails:
        if not _send_email(admin_email, subject, body_html, body_text):
            success = False
    
    return success


def get_user_notification_settings(user_id: int) -> Dict[str, bool]:
    """
    Получить настройки уведомлений пользователя.
    По умолчанию все уведомления включены.
    """
    try:
        from .auth import _connect
        from typing import cast, Optional, Dict as DictType, Any
        
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT email_notifications, sms_notifications
                    FROM notification_settings
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if row:
                    row_dict = cast(DictType[str, Any], row)
                    return {
                        "email_notifications": bool(row_dict.get("email_notifications", True)),
                        "sms_notifications": bool(row_dict.get("sms_notifications", False)),
                    }
                # Настройки по умолчанию
                return {"email_notifications": True, "sms_notifications": False}
        finally:
            conn.close()
    except Exception:
        # Если таблицы нет или ошибка - возвращаем настройки по умолчанию
        return {"email_notifications": True, "sms_notifications": False}


def should_send_email_notification(user_id: int) -> bool:
    """Проверить, нужно ли отправлять email-уведомление пользователю"""
    settings = get_user_notification_settings(user_id)
    return settings.get("email_notifications", True)


def update_user_notification_settings(user_id: int, email_notifications: bool, sms_notifications: bool = False) -> Dict[str, Any]:
    """Обновить настройки уведомлений пользователя"""
    try:
        from .auth import _connect
        from typing import cast, Optional, Dict as DictType, Any
        
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # Проверяем существование пользователя
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    "SELECT users_id FROM users WHERE users_id = %s",
                    (user_id,),
                )
                if not cur.fetchone():
                    return {"error": "Пользователь не найден"}
                
                # Обновляем или создаем настройки
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    INSERT INTO notification_settings (user_id, email_notifications, sms_notifications, updated_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        email_notifications = EXCLUDED.email_notifications,
                        sms_notifications = EXCLUDED.sms_notifications,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, email_notifications, sms_notifications),
                )
                conn.commit()
                
                return {
                    "message": "Настройки уведомлений обновлены",
                    "data": {
                        "email_notifications": email_notifications,
                        "sms_notifications": sms_notifications,
                    }
                }
        finally:
            conn.close()
    except Exception as exc:
        return {"error": f"Ошибка при обновлении настроек: {exc}"}

