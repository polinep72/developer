from datetime import datetime, timedelta
import telebot
import logging
from database import execute_query

logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s (%(filename)s:%(lineno)d %(threadName)s) %(levelname)s - %(message)s'
)

def schedule_notifications(bot, DB_CONFIG, scheduler, sent_notifications, schedule_lock, is_scheduling):
    global is_scheduling_global
    with schedule_lock:
        if is_scheduling:
            return
        is_scheduling_global = True
    try:
        # Здесь можно добавить дополнительные уведомления, если нужно
        pass
    except Exception as e:
        logging.error(f"Ошибка в schedule_notifications: {e}")
    finally:
        with schedule_lock:
            is_scheduling_global = False

def send_notification(bot, user_id, message):
    try:
        bot.send_message(user_id, message)
        logging.info(f"Уведомление отправлено пользователю {user_id}: {message}")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")