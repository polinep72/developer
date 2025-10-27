from telegram import Update
from datetime import datetime, timedelta
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
from database import execute_query
from notifications import schedule_notifications

# Настраиваем логирование
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s (%(filename)s:%(lineno)d %(threadName)s) %(levelname)s - %(message)s'
)


def start_booking(bot, message, DB_CONFIG):
    user_id = message.from_user.id
    query_check_user = "SELECT COUNT(*) FROM users WHERE users_id = %s AND is_blocked = FALSE"
    user_exists = execute_query(query_check_user, (user_id,), db_config=DB_CONFIG)[0][0]
    if not user_exists:
        bot.send_message(message.chat.id,
                         "Вы не зарегистрированы в системе. Пожалуйста, выполните команду /start для регистрации.")
        return
    query = "SELECT id, name_cat FROM cat ORDER BY name_cat ASC"
    categories = execute_query(query, db_config=DB_CONFIG)
    if not categories:
        bot.send_message(message.chat.id, "Нет доступных категорий оборудования.")
        return
    markup = types.InlineKeyboardMarkup()
    for category_id, name_cat in categories:
        markup.add(types.InlineKeyboardButton(text=name_cat, callback_data=f"category1_{category_id}"))
    bot.send_message(message.chat.id, "Выберите категорию оборудования:", reply_markup=markup)


def choose_equipment(bot, call, DB_CONFIG):
    category_id = call.data.split("_")[1]
    query = "SELECT name_cat FROM cat WHERE id = %s"
    category_name = execute_query(query, (category_id,), db_config=DB_CONFIG)[0][0]
    bot.send_message(call.message.chat.id, f"Вы выбрали категорию: {category_name}")

    query = "SELECT id, name_equip FROM equipment WHERE category = %s"
    equipment = execute_query(query, (category_id,), db_config=DB_CONFIG)
    if not equipment:
        bot.send_message(call.message.chat.id, "В этой категории нет оборудования.")
        return
    markup = types.InlineKeyboardMarkup()
    for equipment_id, name_equip in equipment:
        markup.add(types.InlineKeyboardButton(text=name_equip, callback_data=f"equipment1_{equipment_id}"))
    bot.send_message(call.message.chat.id, "Выберите оборудование:", reply_markup=markup)


def choose_date(bot, call, DB_CONFIG):
    equipment_id = call.data.split("_")[1]
    query = "SELECT name_equip FROM equipment WHERE id = %s"
    equipment_name = execute_query(query, (equipment_id,), db_config=DB_CONFIG)[0][0]
    bot.send_message(call.message.chat.id, f"Вы выбрали оборудование: {equipment_name}")

    now = datetime.now()
    markup = types.InlineKeyboardMarkup()
    for i in range(7):
        day = now + timedelta(days=i)
        day_str = day.strftime('%d-%m-%Y')
        markup.add(types.InlineKeyboardButton(text=day_str, callback_data=f"date1_{day_str}_{equipment_id}"))
    bot.send_message(call.message.chat.id, "Выберите дату:", reply_markup=markup)


def choose_time(bot, call, DB_CONFIG):
    data = call.data.split("_")
    selected_date = data[1]
    equipment_id = data[2]
    bot.send_message(call.message.chat.id, f"Вы выбрали дату: {selected_date}")

    markup = types.InlineKeyboardMarkup()
    time = datetime.strptime('07:00', '%H:%M')
    end_time = datetime.strptime('20:00', '%H:%M')
    while time <= end_time:
        time_str = time.strftime('%H:%M')
        markup.add(
            types.InlineKeyboardButton(text=time_str, callback_data=f"time1_{time_str}_{selected_date}_{equipment_id}"))
        time += timedelta(minutes=30)
    bot.send_message(call.message.chat.id, "Выберите время начала работы:", reply_markup=markup)


def choose_duration(bot, call, DB_CONFIG):
    data = call.data.split("_")
    start_time = data[1]
    selected_date = data[2]
    equipment_id = data[3]
    bot.send_message(call.message.chat.id, f"Вы выбрали время начала: {start_time}")

    markup = types.InlineKeyboardMarkup()
    duration = timedelta(minutes=30)
    max_duration = timedelta(hours=12)
    while duration <= max_duration:
        duration_str = f"{duration.seconds // 3600}:{(duration.seconds // 60) % 60:02}"
        markup.add(types.InlineKeyboardButton(text=duration_str,
                                              callback_data=f"duration1_{duration_str}_{start_time}_{selected_date}_{equipment_id}"))
        duration += timedelta(minutes=30)
    bot.send_message(call.message.chat.id, "Выберите длительность работы:", reply_markup=markup)


def notify_user_about_booking(bot, booking_id, user_id, chat_id, equip_name, start_time):
    """Оповещение пользователя о начале работы с кнопкой подтверждения"""
    markup = InlineKeyboardMarkup()
    confirm_button = InlineKeyboardButton("Подтвердить актуальность", callback_data=f"book_confirm_{booking_id}")
    markup.add(confirm_button)

    message = f"Ваше бронирование на оборудование '{equip_name}' начинается в {start_time.strftime('%H:%M')}\nПодтвердите актуальность бронирования в течение 5 минут."
    try:
        bot.send_message(chat_id, message, reply_markup=markup)
        logging.info(f"Уведомление о подтверждении бронирования {booking_id} отправлено пользователю {user_id}")
    except Exception as e:
        logging.error(
            f"Ошибка при отправке уведомления о подтверждении бронирования {booking_id} пользователю {user_id}: {e}")


def notify_user_about_end(bot, booking_id, user_id, chat_id, equip_id, equip_name, end_time, DB_CONFIG):
    """Оповещение пользователя об окончании работы с предложением продления"""
    # Проверяем, свободно ли время после окончания
    query = """
        SELECT COUNT(*)
        FROM bookings
        WHERE equip_id = %s
        AND cancel = FALSE
        AND finish IS NULL
        AND time_start <= %s
        AND time_end > %s
    """
    next_time = end_time + timedelta(minutes=30)  # Проверяем ближайший слот
    conflicts = execute_query(query, (equip_id, next_time, end_time), db_config=DB_CONFIG)[0][0]

    markup = InlineKeyboardMarkup()
    if conflicts == 0:  # Если время свободно, предлагаем продлить
        markup.add(
            InlineKeyboardButton("Продлить", callback_data=f"extend_{booking_id}"),
            InlineKeyboardButton("Отказаться", callback_data=f"finish_{booking_id}")
        )
        message = f"Ваше бронирование на оборудование '{equip_name}' заканчивается в {end_time.strftime('%H:%M')}.\nХотите продлить работу?"
    else:  # Если время занято, только уведомляем
        message = f"Ваше бронирование на оборудование '{equip_name}' заканчивается в {end_time.strftime('%H:%M')}.\nСледующее время занято."

    try:
        bot.send_message(chat_id, message, reply_markup=markup if conflicts == 0 else None)
        logging.info(f"Уведомление об окончании бронирования {booking_id} отправлено пользователю {user_id}")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления об окончании бронирования {booking_id}: {e}")


def auto_cancel_booking(bot, booking_id, chat_id, DB_CONFIG, schedule_notifications_func, scheduler, sent_notifications,
                        schedule_lock, is_scheduling):
    """Автоматическая отмена бронирования, если нет подтверждения"""
    query = "SELECT cancel FROM bookings WHERE id = %s"
    result = execute_query(query, (booking_id,), db_config=DB_CONFIG)

    if not result:
        logging.error(f"Бронирование с ID {booking_id} не найдено")
        return

    if result[0][0] == False:  # Если бронирование уже подтверждено
        return

    update_query = "UPDATE bookings SET cancel = TRUE WHERE id = %s"
    execute_query1(update_query, (booking_id,), db_config=DB_CONFIG)

    schedule_notifications_func(bot, DB_CONFIG, scheduler, sent_notifications, schedule_lock, is_scheduling)
    try:
        bot.send_message(chat_id,
                         f"Ваше бронирование с ID {booking_id} было автоматически отменено из-за отсутствия подтверждения.")
        logging.info(f"Бронирование {booking_id} автоматически отменено")
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения об отмене бронирования {booking_id}: {e}")


def finalize_booking(bot, call, DB_CONFIG, schedule_notifications_func, scheduler, sent_notifications, schedule_lock,
                     is_scheduling):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data_booking = datetime.now()
    data = call.data.split("_")
    duration_str = data[1]
    start_time = data[2]
    selected_date = data[3]
    equipment_id = data[4]

    start_datetime = datetime.strptime(f"{selected_date} {start_time}", '%d-%m-%Y %H:%M')
    duration_hours, duration_minutes = map(int, duration_str.split(":"))
    duration_timedelta = timedelta(hours=duration_hours, minutes=duration_minutes)
    end_datetime = start_datetime + duration_timedelta

    bot.send_message(chat_id, f"Вы выбрали длительность: {duration_str}")

    query = """
        SELECT b.time_start, b.time_end, u.first_name, u.last_name
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        WHERE b.equip_id = %s AND
        b.cancel = FALSE AND
        b.time_start < %s AND
        b.time_end > %s
        AND finish IS NULL
    """
    conflicts = execute_query(query, (equipment_id, end_datetime, start_datetime), db_config=DB_CONFIG)
    if conflicts:
        for conflict_start, conflict_end, first_name, last_name in conflicts:
            bot.send_message(chat_id,
                             f"Пересечение по времени с бронированием пользователя {first_name} {last_name} на {conflict_start} - {conflict_end}")
        return

    time_interval = f"{start_datetime.strftime('%H:%M')}-{end_datetime.strftime('%H:%M')}"
    duration = duration_timedelta.total_seconds() / 3600
    insert_query = """
        INSERT INTO bookings (user_id, equip_id, date, time_start, time_end, time_interval, duration, cancel, extension, finish, data_booking)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, NULL, %s)
        RETURNING id
    """
    booking_id = execute_query1(insert_query, (
    user_id, equipment_id, selected_date, start_datetime, end_datetime, time_interval, duration, data_booking),
                                fetch_results=True, db_config=DB_CONFIG)[0][0]

    equip_query = "SELECT name_equip FROM equipment WHERE id = %s"
    equip_name = execute_query(equip_query, (equipment_id,), db_config=DB_CONFIG)[0][0]

    # Уведомление за 10 минут до начала
    notification_time_start = start_datetime - timedelta(minutes=10)
    if notification_time_start > datetime.now():
        scheduler.add_job(
            notify_user_about_booking,
            'date',
            run_date=notification_time_start,
            args=[bot, booking_id, user_id, chat_id, equip_name, start_datetime]
        )
        logging.info(f"Уведомление о начале бронирования {booking_id} запланировано на {notification_time_start}")

        # Автоматическая отмена через 5 минут после уведомления
        cancel_time = notification_time_start + timedelta(minutes=5)
        if cancel_time > datetime.now():
            scheduler.add_job(
                auto_cancel_booking,
                'date',
                run_date=cancel_time,
                args=[bot, booking_id, chat_id, DB_CONFIG, schedule_notifications_func, scheduler, sent_notifications,
                      schedule_lock, is_scheduling]
            )
            logging.info(f"Автоматическая отмена бронирования {booking_id} запланирована на {cancel_time}")

    # Уведомление за 10 минут до конца
    notification_time_end = end_datetime - timedelta(minutes=10)
    if notification_time_end > datetime.now():
        scheduler.add_job(
            notify_user_about_end,
            'date',
            run_date=notification_time_end,
            args=[bot, booking_id, user_id, chat_id, equipment_id, equip_name, end_datetime, DB_CONFIG]
        )
        logging.info(f"Уведомление об окончании бронирования {booking_id} запланировано на {notification_time_end}")

    schedule_notifications_func(bot, DB_CONFIG, scheduler, sent_notifications, schedule_lock, is_scheduling)
    bot.send_message(chat_id, "Ваше бронирование успешно сохранено.")