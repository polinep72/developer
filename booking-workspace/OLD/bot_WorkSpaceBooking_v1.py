import csv 
import os
from datetime import datetime, timedelta
import telebot
from telebot import types
from telegram_bot_calendar import WYearTelegramCalendar
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Создание экземпляра бота
bot = telebot.TeleBot("YOUR_BOT_API_TOKEN")

# Файлы для хранения данных
REGISTRATION_FILE = "registered_users.csv"
BOOKINGS_FILE = "bookings.csv"
CANCELLATIONS_FILE = "cancellations.csv"
FINISH_FILE = "finish.csv"

# Словари для хранения данных
registered_users = {}
bookings = {}

# Список доступных рабочих мест
available_workspaces = {
    "1": "Мощность",
    "2": "ВАЦ РШ",
    "3": "ВАЦ Микран"
}

# Временные интервалы с 8:00 до 21:00 с шагом в 1 час
time_intervals = [(datetime.strptime(f"{hour}:00", "%H:%M").time(), 
                datetime.strptime(f"{hour+1}:00", "%H:%M").time()) for hour in range(8, 21)]

# Функция для Help  
@bot.message_handler(commands=['help'])
def handle_message(message):
    bot.reply_to(message, "Команды бота:\n"
        "/регистрация - регистрация пользователя.\n "
        "/booking - резервирование рабочего места.\n"
        "/cancel - предлагает варианты для удаления резервирования РМ.\n"
        "/finish - окончание работы на зарезервированном РМ. По окончании работы на рабочем месте необходимо нажать на эту кнопку для того чтобы освободить время резервирования РМ. \n"
        "/users - просмотр зарегистрированных пользователей.\n"
        "/mybookings  - просмотр ваших резервирований РМ.\n"
        "/workspacebookings - просмотр резервирований РМ.\n"
        "/datebookings - просмотр всех резервирований РМ на дату .\n"
        "/help - вывод сообщение справки.\n"
        "\n"
        "Доступные рабочие места:\n"
        "1 - Мощность\n"
        "2 - ВАЦ Микран\n"
        "3 - ВАЦ РШ\n")

#Users
# Команда для регистрации пользователя  -   РАБОТАЕТ
@bot.message_handler(commands=['регистрация'])
def register_user(message):
    user_id = message.from_user.id
    if user_id in registered_users:
        bot.send_message(message.chat.id, "Вы уже зарегистрированы.")
    else:
        msg = bot.send_message(message.chat.id, "Введите ваше Имя:")
        bot.register_next_step_handler(msg, process_first_name_step)

# Шаг 1: Запрашиваем Имя
def process_first_name_step(message):
    user_id = message.from_user.id
    first_name = message.text
    bot.send_message(message.chat.id, "Введите вашу Фамилию:")
    bot.register_next_step_handler(message, process_last_name_step, first_name)

# Шаг 2: Запрашиваем Фамилию и сохраняем пользователя
def process_last_name_step(message, first_name):
    user_id = message.from_user.id
    last_name = message.text
    registered_users[user_id] = {'first_name': first_name, 'last_name': last_name}
    save_registered_user(user_id, first_name, last_name)
    bot.send_message(message.chat.id, f"Регистрация завершена. Добро пожаловать, {first_name} {last_name}!")

# Команда для просмотра всех зарегистрированных пользователей
@bot.message_handler(commands=['users'])
def show_registered_users(message):
    if registered_users:
        user_list = "\n".join([f"{user_info['first_name']} {user_info['last_name']}" for user_info in registered_users.values()])
        bot.send_message(message.chat.id, f"Зарегистрированные пользователи:\n{user_list}")
    else:
        bot.send_message(message.chat.id, "Нет зарегистрированных пользователей.")

# Функция для загрузки зарегистрированных пользователей из файла CSV
def load_registered_users():
    if os.path.exists(REGISTRATION_FILE):
        with open(REGISTRATION_FILE, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            for row in reader:
                if len(row) >= 3:
                    try:
                        user_id = int(row[0])
                        first_name = row[1]
                        last_name = row[2]
                        registered_users[user_id] = {'first_name': first_name, 'last_name': last_name}
                        #print(f"Загружен пользователь: {user_id} - {first_name} - {last_name}")
                    except ValueError:
                        continue
            

# Функция для сохранения пользователя в CSV файл
def save_registered_user(user_id, first_name, last_name):
    with open(REGISTRATION_FILE, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, first_name, last_name, datetime.now().strftime("%d-%m-%Y %H:%M:%S")])

# БРОНИРОВАНИЕ РМ    
# Команда для бронирования рабочего места
@bot.message_handler(commands=['booking'])
def start_booking(message):
    markup = InlineKeyboardMarkup()
    # Предлагаем выбрать рабочее место
    for workspace_id, workspace_name in available_workspaces.items():
        markup.add(InlineKeyboardButton(text=workspace_name, callback_data=f"select_workspace_{workspace_id}"))
    bot.send_message(message.chat.id, "Выберите рабочее место:", reply_markup=markup)

# Обработка выбора рабочего места
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_workspace_"))
def select_workspace(call):
    workspace_id = call.data.split("_")[2]
    bot.send_message(call.message.chat.id, f"Вы выбрали рабочее место: {available_workspaces[workspace_id]}")

    # Предлагаем выбрать дату (неделя вперед)
    markup = InlineKeyboardMarkup()
    today = datetime.now()
    for i in range(7):
        date = (today + timedelta(days=i)).strftime('%d-%m-%Y')
        markup.add(InlineKeyboardButton(text=date, callback_data=f"select_date_{workspace_id}_{date}"))

    bot.send_message(call.message.chat.id, "Выберите дату для бронирования:", reply_markup=markup)

# Обработка выбора даты
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_date_"))
def select_date(call):
    workspace_id, date = call.data.split("_")[2], call.data.split("_")[3]
    bot.send_message(call.message.chat.id, f"Вы выбрали дату: {date}")

    # Предлагаем выбрать время начала работы (с 08:00 до 20:00)
    markup = InlineKeyboardMarkup()
    for hour in range(8, 21):  # Время с 08:00 до 20:00
        time_start = f"{hour:02d}:00"
        markup.add(InlineKeyboardButton(text=time_start, callback_data=f"select_time_start_{workspace_id}_{date}_{time_start}"))

    bot.send_message(call.message.chat.id, "Выберите время начала работы:", reply_markup=markup)

# Обработка выбора времени начала работы
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_time_start_"))
def select_time_start(call):
    workspace_id, date, time_start = call.data.split("_")[3], call.data.split("_")[4], call.data.split("_")[5]
    bot.send_message(call.message.chat.id, f"Вы выбрали время начала: {time_start}")

    # Предлагаем выбрать продолжительность работы (от 00:30 до 08:00 с шагом 30 минут)
    markup = InlineKeyboardMarkup()
    durations = [(0, 30), (1, 0), (1, 30), (2, 0), (2, 30), (3, 0), (3, 30), (4, 0), (4, 30), (5, 0), (5, 30), (6, 0), (6, 30), (7, 0), (7, 30), (8, 0)]
    
    for hours, minutes in durations:
        duration = f"{hours:02d}:{minutes:02d}"
        markup.add(InlineKeyboardButton(text=duration, callback_data=f"select_duration_{workspace_id}_{date}_{time_start}_{duration}"))

    bot.send_message(call.message.chat.id, "Выберите продолжительность работы:", reply_markup=markup)

# Обработка выбора продолжительности работы
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_duration_"))
def select_duration(call):
    workspace_id, date, time_start, duration = call.data.split("_")[2], call.data.split("_")[3], call.data.split("_")[4], call.data.split("_")[5]
    
    bot.send_message(call.message.chat.id, f"Вы выбрали продолжительность работы: {duration}")
    
    # Конвертация времени начала и продолжительности в объекты datetime
    time_start_dt = datetime.strptime(time_start, '%H:%M')
    hours, minutes = map(int, duration.split(":"))
    time_end_dt = time_start_dt + timedelta(hours=hours, minutes=minutes)
    time_end = datetime.strftime(time_end_dt, '%H:%M')
    
    # Получаем интервал рабочего времени
    user_id = str(call.from_user.id)
    time_interval = f"{time_start}-{time_end}"
    first_name = call.from_user.first_name
    last_name = call.from_user.last_name

    # Проверяем, доступно ли рабочее место на это время
    if any(b_date == date and ws_id == workspace_id and 
        (time_start < t_interval.split('-')[1] and time_end > t_interval.split('-')[0]) for (uid, f_name, l_name, b_date, t_interval), ws_id in bookings.items()):
        bot.send_message(call.message.chat.id, "Это время уже занято. Попробуйте выбрать другое время.")
    else:
        # Сохраняем новое бронирование в CSV и словарь
        bookings[(user_id, first_name, last_name, date, time_interval)] = workspace_id
        save_booking(user_id, first_name, last_name, workspace_id, date, time_interval)
        bot.send_message(call.message.chat.id, f"Ваше бронирование на рабочее место '{available_workspaces[workspace_id]}' подтверждено.")

# Функция для сохранения бронирований в CSV
def save_booking(user_id, first_name, last_name, workspace_id, date, time_interval):
    with open('bookings.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, first_name, last_name, workspace_id, date, time_interval])

# Функция для загрузки бронирований из CSV
def load_bookings():
    bookings = {}
    with open('bookings.csv', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            user_id, first_name, last_name, workspace_id, date, time_interval = row
            bookings[(user_id, first_name, last_name, date, time_interval)] = workspace_id
    return bookings

# Пример загрузки бронирований
bookings = load_bookings()

#Cancel 
# Команда для отмены бронирования
@bot.message_handler(commands=['cancel'])
def cancel_booking(message):
    user_id = str(message.from_user.id)
    
    # Загружаем бронирования пользователя из файла bookings.csv
    user_bookings = []
    today = datetime.now().date()
    one_week_ahead = today + timedelta(days=7)
    
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            booking_date = datetime.strptime(row['date'], '%d-%m-%Y').date()
            if row['user_id'] == user_id and today <= booking_date <= one_week_ahead:
                user_bookings.append(row)
    
    if user_bookings:
        # Если есть бронирования, предлагаем пользователю выбрать одно из них для отмены
        markup = InlineKeyboardMarkup()
        for booking in user_bookings:
            workspace = available_workspaces[booking['workspace_id']]
            date = booking['date']
            time_interval = booking['time_interval']
            booking_str = f"{workspace}, {date}, {time_interval}"
            callback_data = f"cancel_{booking['workspace_id']}_{date}_{time_interval}"
            markup.add(InlineKeyboardButton(booking_str, callback_data=callback_data))
        
        bot.send_message(message.chat.id, "Выберите бронирование, которое хотите отменить:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "У вас нет бронирований для отмены в течение следующей недели.")

# Обработка выбора бронирования для отмены
@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def handle_cancel_booking(call):
    user_id = str(call.from_user.id)
    data = call.data.split('_')
    workspace_id = data[1]
    date = data[2]
    time_interval = data[3]  # Формат времени с тире, напр. 10:30-12:00
    
    booking_to_cancel = None
    bookings = []
    today = datetime.now().date()

    booking_date = datetime.strptime(date, '%d-%m-%Y').date()
    
    if booking_date < today:
        bot.send_message(call.message.chat.id, "Вы не можете отменить бронирование на прошедшую дату.")
        return
    
    # Загружаем все бронирования из bookings.csv
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            bookings.append(row)
            if (row['user_id'] == user_id and row['workspace_id'] == workspace_id and 
                row['date'] == date and row['time_interval'] == time_interval):
                booking_to_cancel = row
    
    if booking_to_cancel:
        # Удаляем отмененное бронирование из списка
        bookings.remove(booking_to_cancel)
        
        # Сохраняем обновленный список бронирований в bookings.csv
        with open('bookings.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['user_id', 'first_name', 'last_name', 'workspace_id', 'date', 'time_interval'])
            writer.writeheader()
            writer.writerows(bookings)
        
        # Переносим отмененное бронирование в файл cancellations.csv
        with open('cancellations.csv', 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([booking_to_cancel['user_id'], booking_to_cancel['first_name'], booking_to_cancel['last_name'],
                            booking_to_cancel['workspace_id'], booking_to_cancel['date'], booking_to_cancel['time_interval']])
        
        bot.send_message(call.message.chat.id, f"Ваше бронирование рабочего места {available_workspaces[workspace_id]} на {date} с {time_interval} было успешно отменено.")
    
    else:
        bot.send_message(call.message.chat.id, "Не удалось найти бронирование для отмены.")

#окончание работы   
# Команда для завершения бронирования
@bot.message_handler(commands=['finish'])
def finish_booking(message):
    user_id = str(message.from_user.id)
    current_time = datetime.now().strftime('%H:%M')  # Текущее время
    current_date = datetime.now().strftime('%d-%m-%Y')  # Текущая дата
    
    # Загружаем бронирования пользователя из файла bookings.csv
    user_bookings = []
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['user_id'] == user_id and row['date'] == current_date:
                # Проверяем, попадает ли текущее время в диапазон time_interval
                time_start, time_end = row['time_interval'].split('-')
                if time_start <= current_time <= time_end:  # Проверка нахождения в интервале
                    user_bookings.append(row)

    if user_bookings:
        # Если есть бронирования в текущем интервале времени, предлагаем завершить их
        markup = InlineKeyboardMarkup()
        for booking in user_bookings:
            workspace = available_workspaces[booking['workspace_id']]
            date = booking['date']
            time_interval = booking['time_interval']
            booking_str = f"{workspace}, {date}, {time_interval}"
            callback_data = f"finish_{booking['workspace_id']}_{date}_{time_interval}"
            markup.add(InlineKeyboardButton(booking_str, callback_data=callback_data))
        
        bot.send_message(message.chat.id, "Выберите бронирование для завершения:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "У вас нет активных бронирований, которые можно завершить в данное время.")

# Обработка выбора бронирования для завершения
@bot.callback_query_handler(func=lambda call: call.data.startswith('finish_'))
def handle_finish_booking(call):
    user_id = str(call.from_user.id)
    data = call.data.split('_')
    workspace_id = data[1]
    date = data[2]
    time_interval = data[3]  # Формат времени, напр. 10:30-12:00
    
    # Разделяем time_interval на начало и конец
    time_start, time_end = time_interval.split('-')
    current_time = datetime.now().strftime('%H:%M')  # Текущее время для завершения
    
    booking_to_finish = None
    bookings = []
    
    # Загружаем все бронирования из bookings.csv
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            bookings.append(row)
            if (row['user_id'] == user_id and row['workspace_id'] == workspace_id and 
                row['date'] == date and row['time_interval'] == time_interval):
                booking_to_finish = row
    
    if booking_to_finish:
        # Обновляем время окончания работы на текущее
        updated_time_interval = f"{time_start}-{current_time}"
        booking_to_finish['time_interval'] = updated_time_interval
        
        # Обновляем файл bookings.csv с измененным временным интервалом
        with open('bookings.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=['user_id', 'first_name', 'last_name', 'workspace_id', 'date', 'time_interval'])
            writer.writeheader()
            writer.writerows(bookings)
        
        # Переносим завершенное бронирование в файл finish.csv
        with open('finish.csv', 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([booking_to_finish['user_id'], booking_to_finish['first_name'], booking_to_finish['last_name'],
                            booking_to_finish['workspace_id'], booking_to_finish['date'], updated_time_interval])
        
        bot.send_message(call.message.chat.id, f"Ваше бронирование рабочего места {available_workspaces[workspace_id]} на {date} было завершено. Время окончания: {current_time}.")
    
    else:
        bot.send_message(call.message.chat.id, "Не удалось найти бронирование для завершения.")

# продление бронирования   -  РАБОТАЕТ
# Команда для продления бронирования
@bot.message_handler(commands=['продлить'])
def extend_booking(message):
    user_id = str(message.from_user.id)
    
    # Открываем файл bookings.csv и ищем текущее бронирование пользователя
    user_booking = None
    current_time = datetime.now().strftime("%H:%M")
    today_date = datetime.now().strftime('%d-%m-%Y')
    
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['user_id'] == user_id and row['date'] == today_date:
                booking_start_time, booking_end_time = row['time_interval'].split('-')
                # Проверяем, что текущее время находится в пределах бронирования
                if booking_start_time <= current_time <= booking_end_time:
                    user_booking = row
                    break
    
    if user_booking:
        workspace_id = user_booking['workspace_id']
        booking_end_time = user_booking['time_interval'].split('-')[1]
        
        # Преобразуем время окончания бронирования в объект datetime
        end_time = datetime.strptime(booking_end_time, "%H:%M")
        
        # Если пользователь находится в пределах текущего бронирования, предлагаем продление
        bot.send_message(message.chat.id, f"Ваше бронирование рабочего места {available_workspaces[workspace_id]} активно до {booking_end_time}. Выберите время продления.")
        show_extend_time_keyboard(message.chat.id, workspace_id, end_time)

    else:
        bot.send_message(message.chat.id, "Вы не можете продлить бронирование, так как в данный момент не находитесь в активном бронировании.")

# Функция для показа клавиатуры выбора времени для продления бронирования
def show_extend_time_keyboard(chat_id, workspace_id, end_time):
    markup = InlineKeyboardMarkup()
    # Добавляем кнопки для продления времени с 00:30 до 05:00 с шагом в 30 минут
    times = [("00:30", 30), ("01:00", 60), ("01:30", 90), ("02:00", 120), ("02:30", 150),
            ("03:00", 180), ("03:30", 210), ("04:00", 240), ("04:30", 270), ("05:00", 300)]
    
    for time_label, delta in times:
        new_end_time = end_time + timedelta(minutes=delta)
        new_time_interval = f"{end_time.strftime('%H:%M')}-{new_end_time.strftime('%H:%M')}"
        markup.add(InlineKeyboardButton(time_label, callback_data=f"extend_{workspace_id}_{new_time_interval}"))

    bot.send_message(chat_id, "Выберите время продления:", reply_markup=markup)

# Обработка выбора времени продления
@bot.callback_query_handler(func=lambda call: call.data.startswith('extend_'))
def handle_extend_time(call):
    # Получаем workspace_id и новый временной интервал из callback_data
    data = call.data.split('_')
    workspace_id = data[1]
    new_time_interval = data[2]
    
    user_id = str(call.from_user.id)
    
    # Проверяем, занято ли новое время на рабочем месте
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['workspace_id'] == workspace_id and row['date'] == datetime.now().strftime('%d-%m-%Y'):
                existing_start, existing_end = row['time_interval'].split('-')
                new_start, new_end = new_time_interval.split('-')
                
                # Проверяем пересекаются ли интервалы бронирования
                if (new_start < existing_end and new_end > existing_start):
                    other_user_first_name = row['first_name']
                    other_user_last_name = row['last_name']
                    bot.send_message(call.message.chat.id, 
                                    f"Данное время забронировал (забронировала) {other_user_first_name} {other_user_last_name}. "
                                    f"Согласуйте время работы с ним (ней).")
                    return
    
    # Если время свободно, продлеваем бронирование
    with open('bookings.csv', 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, call.from_user.first_name, call.from_user.last_name, workspace_id, datetime.now().strftime('%d-%m-%Y'), new_time_interval])
    
    bot.send_message(call.message.chat.id, f"Ваше бронирование успешно продлено до {new_time_interval.split('-')[1]}.")

#просмотр бронирований   -   РАБОТАЕТ
# Команда для просмотра своих бронирований
@bot.message_handler(commands=['mybookings'])
def view_my_bookings(message):
    user_id = str(message.from_user.id)

    # Открываем файл bookings.csv и загружаем бронирования пользователя
    user_bookings = []
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        # Выводим заголовки для отладки
        headers = reader.fieldnames
        #print(f"Заголовки файла: {headers}")  # Для отладки, можно закомментировать после тестирования

        if 'user_id' not in headers:
            bot.send_message(message.chat.id, "Ошибка: Не найден столбец 'user_id' в файле bookings.csv")
            return
        
        # Чтение записей
        for row in reader:
            if row['user_id'] == user_id:
                # Добавляем в список записи для данного пользователя
                user_bookings.append({
                    "first_name": row['first_name'],
                    "last_name": row['last_name'],
                    "workspace_id": row['workspace_id'],
                    "date": row['date'],
                    "time_interval": row['time_interval']
                })

    if user_bookings:
        # Формируем список бронирований
        booking_list = "\n".join([f"Рабочее место: {available_workspaces[row['workspace_id']]} на {row['date']} с {row['time_interval']}" 
                                for row in user_bookings])
        bot.send_message(message.chat.id, f"Ваши бронирования:\n{booking_list}")
    else:
        bot.send_message(message.chat.id, "У вас нет активных бронирований.")

# Функция для загрузки бронирований по дате
def get_date_bookings(date):
    date_bookings = [(date, workspace_id, time_interval, registered_users[uid]) for (date_b, workspace_id, time_interval), uid in bookings.items() if date_b == date]
    return date_bookings

#workspacebookings    -   РАБОТАЕТ
# Команда для просмотра всех бронирований по рабочему месту
@bot.message_handler(commands=['workspacebookings'])
def choose_workspaceb(message):
    # Создаем клавиатуру
    markup = InlineKeyboardMarkup()

    # Добавляем кнопки для каждого рабочего места
    for workspace_id, workspace_name in available_workspaces.items():
        markup.add(InlineKeyboardButton(workspace_name, callback_data=f"workspaceb_{workspace_id}"))

    bot.send_message(message.chat.id, "Выберите рабочее место:", reply_markup=markup)

# Обработка нажатия на кнопки выбора рабочего места
@bot.callback_query_handler(func=lambda call: call.data.startswith('workspaceb_'))
def view_workspace_bookings(call):
    # Получаем идентификатор выбранного рабочего места
    workspace_id = call.data.split("_")[1]
    
    # Получаем текущую дату
    current_date = datetime.now()
    current_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
        # Дата через неделю
    end_date = current_date + timedelta(days=7)

    # Открываем файл bookings.csv и загружаем бронирования для выбранного рабочего места на ближайшие 7 дней
    workspace_bookings = []
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Преобразуем дату из строки в объект datetime
            booking_date = datetime.strptime(row['date'], "%d-%m-%Y")
            # Фильтруем записи по рабочему месту и дате (только ближайшие 7 дней)
            if row['workspace_id'] == workspace_id and current_date <= booking_date <= end_date:
                workspace_bookings.append({
                    "first_name": row['first_name'],
                    "last_name": row['last_name'],
                    "date": row['date'],
                    "time_interval": row['time_interval']
                })

    # Проверяем, есть ли бронирования для выбранного рабочего места на ближайшую неделю
    if workspace_bookings:
        response = f"Бронирования для рабочего места {available_workspaces[workspace_id]} на ближайшую неделю:\n"
        # Формируем список бронирований
        for booking in workspace_bookings:
            response += f"{booking['first_name']} {booking['last_name']} - {booking['date']} с {booking['time_interval']}\n"
        bot.send_message(call.message.chat.id, response)
    else:
        bot.send_message(call.message.chat.id, f"На рабочем месте {available_workspaces[workspace_id]} нет активных бронирований на ближайшую неделю.")


# datebookings     -   РАБОТАЕТ
# Команда для просмотра бронирований на конкретную дату
@bot.message_handler(commands=['datebookings'])
def choose_date(message):
    # Создаем клавиатуру
    markup = InlineKeyboardMarkup()
    
    # Текущая дата
    current_date = datetime.now()
    
    # Генерируем кнопки для дат на неделю вперед
    for i in range(7):
        date_str = (current_date + timedelta(days=i)).strftime("%d-%m-%Y")
        markup.add(InlineKeyboardButton(date_str, callback_data=f"date_{date_str}"))
    
    bot.send_message(message.chat.id, "Выберите дату:", reply_markup=markup)

# Обработка нажатия на кнопки выбора даты
@bot.callback_query_handler(func=lambda call: call.data.startswith('date_'))
def view_bookings_by_date(call):
    # Получаем выбранную дату
    selected_date = call.data.split("_")[1]
    
    # Открываем файл bookings.csv и загружаем все бронирования на выбранную дату
    bookings_by_date = []
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['date'] == selected_date:
                bookings_by_date.append({
                    "workspace_id": row['workspace_id'],
                    "first_name": row['first_name'],
                    "last_name": row['last_name'],
                    "time_interval": row['time_interval']
                })

    # Проверяем, есть ли бронирования на выбранную дату
    if bookings_by_date:
        response = f"Бронирования на {selected_date}:\n"
        # Формируем список бронирований для всех рабочих мест
        for booking in bookings_by_date:
            response += f"{booking['first_name']} {booking['last_name']} - Рабочее место {available_workspaces[booking['workspace_id']]} с {booking['time_interval']}\n"
        bot.send_message(call.message.chat.id, response)
    else:
        bot.send_message(call.message.chat.id, f"На {selected_date} нет активных бронирований.")

# Клавиатура
# Добавляем кнопки управления
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    btn1 = types.KeyboardButton('/help')
    btn2 = types.KeyboardButton('/регистрация')
        
    btn3 = types.KeyboardButton('/booking')
    btn4 = types.KeyboardButton('/cancel')
    btn5 = types.KeyboardButton('/finish')
    btn6 = types.KeyboardButton('/продлить')
    
    btn7 = types.KeyboardButton('/mybookings')
    btn8 = types.KeyboardButton('/workspacebookings')
    btn9 = types.KeyboardButton('/datebookings')
    
    markup.add(btn1, btn2)
    markup.add(btn3, btn4,  btn5, btn6)
    markup.add(btn7, btn8, btn9)
    

    # Приветствие
    bot.send_message(message.chat.id, "Привет! Я бот для резервирования рабочих мест (РМ). Используй /help для получения списка команд.", reply_markup=markup)


# Запуск бота
if __name__ == "__main__":
    load_registered_users()
    load_bookings()
    bot.infinity_polling(none_stop=True, timeout=10, long_polling_timeout = 5)
