"""
Сервис для отправки напоминаний о начале работы
"""
import logging
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def _ensure_date_obj(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return datetime.strptime(str(value), "%Y-%m-%d").date()


def _ensure_time_obj(value: Any) -> time:
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    try:
        return datetime.fromisoformat(str(value)).time()
    except Exception:
        return datetime.strptime(str(value), "%H:%M:%S").time()


def get_bookings_starting_soon(
    minutes_before: int = 15,
    max_minutes_before: int = 16
) -> List[Dict[str, Any]]:
    """
    Получить список бронирований, которые начинаются в ближайшее время.
    
    Args:
        minutes_before: За сколько минут до начала отправлять напоминание (по умолчанию 15)
        max_minutes_before: Максимальное время до начала (чтобы не отправлять повторно)
    
    Returns:
        Список словарей с данными бронирований
    """
    try:
        from .auth import _connect
        from typing import cast, Dict as DictType, Any
        
        now = datetime.now()
        start_window = now + timedelta(minutes=minutes_before)
        end_window = now + timedelta(minutes=max_minutes_before)
        
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # Создаем таблицу для отслеживания отправленных напоминаний, если её нет
                try:
                    cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                        """
                        CREATE TABLE IF NOT EXISTS booking_reminders_sent (
                            id SERIAL PRIMARY KEY,
                            booking_id INTEGER NOT NULL,
                            reminder_type VARCHAR(20) NOT NULL DEFAULT 'start',
                            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(booking_id, reminder_type)
                        )
                        """
                    )
                    conn.commit()
                except Exception:
                    pass  # Таблица уже существует или ошибка создания
                
                # Проверяем существование таблицы перед использованием в запросе
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'booking_reminders_sent'
                    ) AS exists
                    """
                )
                table_row = cur.fetchone()
                if table_row:
                    table_row_dict = cast(DictType[str, Any], table_row)
                    table_exists = bool(table_row_dict.get("exists", False))
                else:
                    table_exists = False
                
                # Формируем запрос с учетом существования таблицы
                if table_exists:
                    reminder_check = """
                        AND NOT EXISTS (
                            SELECT 1 FROM booking_reminders_sent brs 
                            WHERE brs.booking_id = b.id 
                            AND brs.reminder_type = 'start'
                        )
                    """
                else:
                    reminder_check = ""
                
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    f"""
                    SELECT 
                        b.id,
                        b.user_id,
                        b.date,
                        b.time_start,
                        b.time_end,
                        b.cancel,
                        b.finish,
                        u.email,
                        u.first_name,
                        u.last_name,
                        e.name_equip
                    FROM bookings b
                    JOIN users u ON b.user_id = u.users_id
                    JOIN equipment e ON b.equip_id = e.id
                    WHERE 
                        b.cancel IS NOT TRUE
                        AND b.finish IS NULL
                        AND b.time_start >= %s
                        AND b.time_start <= %s
                        AND u.email IS NOT NULL
                        AND u.email != ''
                        {reminder_check}
                    ORDER BY b.time_start
                    """,
                    (start_window, end_window),
                )
                rows = cur.fetchall()
                
                bookings = []
                for row in rows:
                    row_dict = cast(DictType[str, Any], row)
                    bookings.append({
                        "booking_id": row_dict["id"],
                        "user_id": row_dict["user_id"],
                        "date": row_dict["date"],
                        "time_start": row_dict["time_start"],
                        "time_end": row_dict["time_end"],
                        "user_email": row_dict["email"],
                        "user_name": f"{row_dict.get('first_name', '')} {row_dict.get('last_name', '')}".strip() or "Пользователь",
                        "equipment_name": row_dict.get("name_equip", "Оборудование"),
                    })
                
                return bookings
        finally:
            conn.close()
    except Exception as exc:
        logger.error(f"Ошибка при получении бронирований для напоминаний: {exc}")
        return []


def send_booking_start_reminders(minutes_before: int = 15) -> Dict[str, Any]:
    """
    Отправить напоминания о начале работы для всех бронирований, которые начинаются в ближайшее время.
    
    Args:
        minutes_before: За сколько минут до начала отправлять напоминание
    
    Returns:
        Словарь с результатами отправки
    """
    try:
        from .notifications import send_booking_start_summary, should_send_email_notification
        
        bookings = get_bookings_starting_soon(minutes_before, minutes_before + 1)
        
        if not bookings:
            return {
                "message": "Нет бронирований для напоминаний",
                "sent": 0,
                "failed": 0,
            }
        
        user_payloads: Dict[int, Dict[str, Any]] = {}
        skipped_users: set[int] = set()
        
        for booking in bookings:
            user_id = booking["user_id"]
            
            if user_id in skipped_users:
                continue
            
            if user_id not in user_payloads:
                if not should_send_email_notification(user_id):
                    skipped_users.add(user_id)
                    logger.info(f"Пользователь {user_id} отключил email-уведомления, пропускаем")
                    continue
                user_payloads[user_id] = {
                    "user_email": booking["user_email"],
                    "user_name": booking["user_name"],
                    "items": [],
                    "booking_ids": [],
                }
            
            booking_date = _ensure_date_obj(booking["date"])
            if isinstance(booking["time_start"], datetime):
                booking_date = booking["time_start"].date()
            
            start_time = _ensure_time_obj(booking["time_start"])
            end_time = _ensure_time_obj(booking["time_end"])
            
            user_payloads[user_id]["items"].append(
                {
                    "equipment_name": booking["equipment_name"],
                    "date": booking_date,
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )
            user_payloads[user_id]["booking_ids"].append(booking["booking_id"])
        
        sent = 0
        failed = 0
        
        for user_id, payload in user_payloads.items():
            try:
                success = send_booking_start_summary(
                    user_email=payload["user_email"],
                    user_name=payload["user_name"],
                    bookings=payload["items"],
                )
                if success:
                    _mark_bookings_as_notified(payload["booking_ids"])
                    sent += 1
                    logger.info(f"Групповое напоминание отправлено пользователю {user_id}")
                else:
                    failed += 1
                    logger.warning(f"Не удалось отправить напоминание пользователю {user_id}")
            except Exception as exc:
                failed += 1
                logger.error(f"Ошибка при отправке напоминания пользователю {user_id}: {exc}")
        
        return {
            "message": f"Отправлено напоминаний: {sent}, ошибок: {failed}",
            "sent": sent,
            "failed": failed,
            "total": len(user_payloads),
        }
    except Exception as exc:
        logger.error(f"Ошибка при отправке напоминаний: {exc}")
        return {
            "error": f"Ошибка при отправке напоминаний: {exc}",
            "sent": 0,
            "failed": 0,
        }


def _mark_bookings_as_notified(booking_ids: List[int]) -> None:
    if not booking_ids:
        return
    try:
        from .auth import _connect
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    CREATE TABLE IF NOT EXISTS booking_reminders_sent (
                        id SERIAL PRIMARY KEY,
                        booking_id INTEGER NOT NULL,
                        reminder_type VARCHAR(20) NOT NULL DEFAULT 'start',
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(booking_id, reminder_type)
                    )
                    """
                )
                for booking_id in booking_ids:
                    cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                        """
                        INSERT INTO booking_reminders_sent (booking_id, reminder_type)
                        VALUES (%s, 'start')
                        ON CONFLICT (booking_id, reminder_type) DO NOTHING
                        """,
                        (booking_id,),
                    )
                conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"Не удалось сохранить факт отправки напоминания: {exc}")

