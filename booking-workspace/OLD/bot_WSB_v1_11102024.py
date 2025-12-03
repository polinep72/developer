import csv 
import os
from datetime import datetime, timedelta
from telebot import types
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import chardet  # Для определения кодировки файла


bot = telebot.TeleBot('*****************************')

# Файлы для хранения данных
REGISTRATION_FILE = "registered_users.csv"
BOOKINGS_FILE = "bookings.csv"
EQUIPMENT_FILE = "equipment.csv"

register_users={}

# Запись нового пользователя
def register_user(user_id, first_name, last_name):
    with open('registered_users.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, first_name, last_name, datetime.now().strftime('%d-%m-%Y'), datetime.now().strftime('%H:%M')])

# Загрузка списка доступных рабочих мест из файла
def load_available_workspaces():
    workspaces = []
    with open('equipment.csv', newline='', encoding='ANSI') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            workspaces.append(row)
    return workspaces

# Запись нового рабочего места
def add_equipment(equipment_data):
    with open('equipment.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(equipment_data)

# Загрузка бронирований
def load_bookings():
    bookings = []
    with open('bookings.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            bookings.append(row)
    return bookings

# Запись нового бронирования
def save_booking(user_id, first_name, last_name, workspace_id, date, time_interval, time_start, time_end, duration):
    with open('bookings.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, first_name, last_name, workspace_id, date, time_interval, time_start, time_end, duration, "0", "", ""])

# Обновление записи о завершении бронирования
def update_finish_time(user_id, booking_id, finish_time):
    rows = []
    with open('bookings.csv', 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if row[0] == user_id and row[10] == booking_id:
                row[10] = finish_time
            rows.append(row)
    with open('bookings.csv', 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(rows)

#    Работает!!!!!!
# Команда бронирования
@bot.message_handler(commands=['booking'])
def start_booking(message):
    user_id = str(message.from_user.id)
    users = load_registered_users()
    available_workspaces = load_available_workspaces()
    if user_id not in users:
        bot.send_message(message.chat.id, "Вы не зарегистрированы. Пожалуйста, используйте команду /регистрация.")
        return
    markup = types.InlineKeyboardMarkup()
    categories = set([workspace['category'] for workspace in available_workspaces])
    for category in categories:
        markup.add(types.InlineKeyboardButton(text=category, callback_data=f"select_category_{category}"))
    bot.send_message(message.chat.id, "Выберите категорию рабочего места:", reply_markup=markup)

# Обработка выбора категории
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_category_"))
def select_category(call):
    available_workspaces = load_available_workspaces()
    category = call.data.split("_")[2]
    bot.send_message(call.message.chat.id, f"Вы выбрали категорию: {category}")
    markup = types.InlineKeyboardMarkup()
    workspaces_in_category = [ws for ws in available_workspaces if ws['category'] == category]
    for workspace in workspaces_in_category:
        markup.add(types.InlineKeyboardButton(text=workspace['name'], callback_data=f"select_workspace_{workspace['id']}"))
    bot.send_message(call.message.chat.id, "Выберите рабочее место:", reply_markup=markup)

# Обработка выбора рабочего места
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_workspace_"))
def select_workspace(call):
    workspace_id = call.data.split("_")[2]
    available_workspaces = load_available_workspaces()
    selected_workspace = next(ws for ws in available_workspaces if ws['id'] == workspace_id)
    bot.send_message(call.message.chat.id, f"Вы выбрали рабочее место: {selected_workspace['name']}")

# Предлагаем выбрать дату
    markup = types.InlineKeyboardMarkup()
    today = datetime.now()
    for i in range(7):
        date = (today + timedelta(days=i)).strftime('%d-%m-%Y')
        markup.add(types.InlineKeyboardButton(text=date, callback_data=f"select_date_{workspace_id}_{date}"))
    bot.send_message(call.message.chat.id, "Выберите дату для бронирования:", reply_markup=markup)

# Обработка выбора даты
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_date_"))
def select_date(call):
    workspace_id, date = call.data.split("_")[2], call.data.split("_")[3]
    bot.send_message(call.message.chat.id, f"Вы выбрали дату: {date}")
# Предлагаем выбрать время начала
    markup = types.InlineKeyboardMarkup()
    time_start_pred = [(8, 0), (8, 30), (9, 0), (9, 30), (10, 0), (10, 30), (11, 0), (11, 30), (12, 0), (12, 30), (13, 0), (13, 30), (14, 0), (14, 30), (15, 0), (15, 30), (16, 0), (16, 30), (17, 0), (17, 30), (18, 0), (18, 30), (19, 0), (19, 30)]
    for hours, minutes in time_start_pred:
        time_start = f"{hours:02d}:{minutes:02d}"
    
    # for hour in range(8, 2):
    #     time_start = f"{hour:02d}:00"
        markup.add(types.InlineKeyboardButton(text=time_start, callback_data=f"select_time_start_{workspace_id}_{date}_{time_start}"))
    
    bot.send_message(call.message.chat.id, "Выберите время начала работы:", reply_markup=markup)

# Обработка выбора времени начала
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_time_start_"))
def select_time_start(call):
    workspace_id, date, time_start = call.data.split("_")[3], call.data.split("_")[4], call.data.split("_")[5]
    bot.send_message(call.message.chat.id, f"Вы выбрали время начала: {time_start}")
    
    # Предлагаем выбрать продолжительность
    markup = types.InlineKeyboardMarkup()
    durations = [(0, 30), (1, 0), (1, 30), (2, 0), (2, 30), (3, 0), (3, 30), (4, 0), (4, 30), (5, 0), (5, 30), (6, 0), (6, 30), (7, 0), (7, 30), (8, 0) ]
    for hours, minutes in durations:
        duration = f"{hours:02d}:{minutes:02d}"
        markup.add(types.InlineKeyboardButton(text=duration, callback_data=f"select_duration_{workspace_id}_{date}_{time_start}_{duration}"))
        
    bot.send_message(call.message.chat.id, "Выберите продолжительность работы:", reply_markup=markup)

# Обработка выбора продолжительности работы
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_duration_"))
def select_duration(call):
    
    workspace_id, date, time_start, duration = call.data.split("_")[2], call.data.split("_")[3], call.data.split("_")[4], call.data.split("_")[5]
    bot.send_message(call.message.chat.id, f"Вы выбрали продолжительность работы: {duration}")
    
    # Конвертируем время в datetime и сохраняем бронирование
    time_start_dt = datetime.strptime(time_start, '%H:%M')
    hours, minutes = map(int, duration.split(":"))
    time_end_dt = time_start_dt + timedelta(hours=hours, minutes=minutes)
    time_end = datetime.strftime(time_end_dt, '%H:%M')
    
    # Проверка доступности временного окна
    if not is_time_slot_available(workspace_id, date, time_start, time_end):
        bot.send_message(call.message.chat.id, "К сожалению, выбранный временной интервал уже занят. Пожалуйста, выберите другое время.")
        #select_date(call)  # Возврат к выбору времени начала, чтобы пользователь мог попробовать снова
        return
    
    time_interval = f"{time_start}-{time_end}"
    user_id = str(call.from_user.id)
    users = load_registered_users()
    first_name = users[user_id]['first_name']
    last_name = users[user_id]['last_name']

    save_booking(user_id, first_name, last_name, workspace_id, date, time_interval, time_start, time_end, duration)
    bot.send_message(call.message.chat.id, f"Ваше бронирование подтверждено: {time_interval} на оборудовании {workspace_id}")

# Функция для проверки пересечения временных интервалов
def is_time_slot_available(workspace_id, booking_date, new_time_start, new_time_end):
    bookings = load_bookings()  # Загружаем все бронирования
    existing_bookings = [b for b in bookings if b['workspace_id'] == workspace_id and b['date'] == booking_date and b['cancel'] == '0' and b['finish'] == '']
    new_time_start_dt = datetime.strptime(new_time_start, '%H:%M')
    new_time_end_dt = datetime.strptime(new_time_end, '%H:%M')

    for booking in existing_bookings:
        booked_start = datetime.strptime(booking['time_start'], '%H:%M')
        booked_end = datetime.strptime(booking['time_end'], '%H:%M')

        # Проверка на пересечение временных интервалов
        if (new_time_start_dt < booked_end and new_time_end_dt > booked_start):
            return False  # Время занято
    return True  # Время свободно

#    Работает!!!!!!
# Просмотр бронирований пользователя
@bot.message_handler(commands=['mybookings'])
def mybookings(message):
    user_id = str(message.from_user.id)
    bookings = load_bookings()  # Загружаем все бронирования
    available_workspaces = load_available_workspaces()  # Загружаем рабочие места для отображения названий

    user_bookings = [b for b in bookings if b['user_id'] == user_id and b['cancel'] == '0' and b['finish'] == '']
    
    if user_bookings:
        response = "Ваши активные бронирования:\n"
        for booking in user_bookings:
            workspace_name = next((ws['name'] for ws in available_workspaces if ws['id'] == booking['workspace_id']), "Неизвестное РМ")
            response += f"{workspace_name}," + f"\nДата: {booking['date']}, Время: {booking['time_interval']}\n"
    else:
        response = "У вас нет активных бронирований."

    bot.send_message(message.chat.id, response)

#    Работает!!!!!!
# Просмотр всех бронирований для рабочего места
@bot.message_handler(commands=['workspacebookings'])
def workspacebookings(message):
    markup = types.InlineKeyboardMarkup()
    available_workspaces = load_available_workspaces()  # Загружаем рабочие места из файла equipment.csv
    
    for workspace in available_workspaces:
        markup.add(types.InlineKeyboardButton(text=workspace['name'], callback_data=f"workspace_{workspace['id']}"))
    
    bot.send_message(message.chat.id, "Выберите рабочее место для просмотра бронирований:", reply_markup=markup)

# Обработка выбора рабочего места
@bot.callback_query_handler(func=lambda call: call.data.startswith("workspace_"))
def get_workspace_bookings(call):
    workspace_id = call.data.split("_")[1]  # Получаем ID выбранного рабочего места
    bookings = load_bookings()
    response = f"Бронирования оборудования {workspace_id}:\n"
    
    for booking in bookings:
        if booking['workspace_id'] == workspace_id and booking['cancel'] == "0" and booking['finish'] == "":
            response += f"Пользователь: {booking['first_name']} {booking['last_name']},\nДата: {booking['date']}, Время: {booking['time_interval']}\n"
    
    if response == f"Бронирования для рабочего места {workspace_id}:\n":
        response = "Нет активных бронирований для этого рабочего места."
    
    bot.send_message(call.message.chat.id, response)

#    Работает!!!!!!
# Команда для просмотра бронирований на конкретную дату
@bot.message_handler(commands=['datebookings'])
def datebookings(message):
    markup = InlineKeyboardMarkup()
    today = datetime.now()
    
    # Генерируем кнопки для дат на неделю вперед
    for i in range(7):
        date = (today + timedelta(days=i)).strftime('%d-%m-%Y')
        markup.add(InlineKeyboardButton(text=date, callback_data=f"select1_date_{date}"))
    
    bot.send_message(message.chat.id, "Выберите дату для просмотра бронирований:", reply_markup=markup)

# Обработка выбора даты для просмотра бронирований
@bot.callback_query_handler(func=lambda call: call.data.startswith("select1_date_"))
def select_date(call):
    selected_date = call.data.split("_")[2]
    bookings = load_bookings()  # Загружаем все бронирования
    available_workspaces = load_available_workspaces()  # Загружаем список рабочих мест для отображения названий
    
    # Фильтруем бронирования по выбранной дате
    date_bookings = [b for b in bookings if b['date'] == selected_date and b['cancel'] == '0' and b['finish'] == '']
    
    if date_bookings:
        response = f"Бронирования на {selected_date}:\n"
        for booking in date_bookings:
            workspace_name = next((ws['name'] for ws in available_workspaces if ws['id'] == booking['workspace_id']), "Неизвестное РМ")
            response += f"{booking['first_name']} {booking['last_name']} зарезервировал оборудование:\n{workspace_name},\nВремя: {booking['time_interval']}\n"
    else:
        response = f"На {selected_date} бронирований нет."

    bot.send_message(call.message.chat.id, response)

#    Работает!!!!!!
# Команда для добавления нового оборудования
@bot.message_handler(commands=['add_equipment'])
def add_equipment(message):
    # Загружаем список оборудования и находим последний id
    workspaces = load_available_workspaces()
    
    if workspaces:
        last_id = int(workspaces[-1]['id'])  # Последний номер id
    else:
        last_id = 0  # Если список пуст, начинаем с 1

    new_id = last_id + 1

    # Запрашиваем категорию
    msg = bot.send_message(message.chat.id, f"Введите категорию для нового оборудования (например, Анализаторы или Осцилографы):")
    bot.register_next_step_handler(msg, process_category_step, new_id)

# Шаг 1: Получаем категорию
def process_category_step(message, new_id):
    category = message.text

    # Запрашиваем имя оборудования
    msg = bot.send_message(message.chat.id, "Введите имя оборудования:")
    bot.register_next_step_handler(msg, process_name_step, new_id, category)

# Шаг 2: Получаем имя оборудования
def process_name_step(message, new_id, category):
    name = message.text

    # Запрашиваем примечание (note)
    msg = bot.send_message(message.chat.id, "Введите примечание (note) для оборудования (например, расположение или доп. информация):")
    bot.register_next_step_handler(msg, process_note_step, new_id, category, name)

# Шаг 3: Получаем примечание и сохраняем оборудование
def process_note_step(message, new_id, category, name):
    note = message.text

    # Добавляем новое оборудование в файл equipment.csv с кодировкой ANSI
    new_equipment = {
        'id': new_id,
        'category': category,
        'name': name,
        'note': note
    }
    save_equipment(new_equipment)

    bot.send_message(message.chat.id, f"Новое оборудование добавлено:\nID: {new_id}\nКатегория: {category}\nНазвание: {name}\nПримечание: {note}")

# Функция для сохранения нового оборудования в файл equipment.csv с кодировкой ANSI
def save_equipment(new_equipment):
    # Сначала загружаем существующее оборудование
    workspaces = load_available_workspaces()

    # Добавляем новое оборудование в список
    workspaces.append(new_equipment)

    # Сохраняем все оборудование обратно в файл
    with open('equipment.csv', mode='w', newline='', encoding='ansi') as file:
        fieldnames = ['id', 'category', 'name', 'note']
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(workspaces)

#    Работает!!!!!!
# Просмотр списка оборудования
@bot.message_handler(commands=['view_equipment'])
def view_equipment(message):
    equipment = load_available_workspaces()
    response = "Доступное оборудование:\n"
    
    for eq in equipment:
        response += f"{eq['id']}, {eq['category']}, {eq['name']}, {eq['note']}\n"
    
    bot.send_message(message.chat.id, response)

#    Работает!!!!!!
# Команда для отмены бронирования     
@bot.message_handler(commands=['cancel'])
def cancel_booking(message):
    user_id = str(message.from_user.id)
    bookings = load_bookings()  # Загружаем все бронирования
    active_bookings = [b for b in bookings if b['user_id'] == user_id and b['cancel'] == '0' and b['finish'] == '']
    
    if not active_bookings:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для отмены.")
        return

    # Создаем клавиатуру с кнопками для выбора бронирования
    markup = InlineKeyboardMarkup()
    for i, booking in enumerate(active_bookings):
        workspace_name = next((ws['name'] for ws in load_available_workspaces() if ws['id'] == booking['workspace_id']), "Неизвестное РМ")
        date = booking['date']
        time_interval = booking['time_interval']
        button_text = f"{workspace_name} на {date} с {time_interval}"
        markup.add(InlineKeyboardButton(text=button_text, callback_data=f"cancel_{i}"))

    bot.send_message(message.chat.id, "Выберите бронирование для отмены:", reply_markup=markup)

# Обработка выбора бронирования для отмены
@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_booking_confirm(call):
    booking_index = int(call.data.split("_")[1])
    user_id = str(call.from_user.id)
    
    # Загружаем бронирования снова, чтобы быть уверенными, что они актуальны
    bookings = load_bookings()

    # Находим нужное бронирование
    active_bookings = [b for b in bookings if b['user_id'] == user_id and b['cancel'] == '0' and b['finish'] == '']
    
    if booking_index < len(active_bookings):
        selected_booking = active_bookings[booking_index]
        selected_booking['cancel'] = '1'  # Помечаем как отмененное
        save_bookings(bookings)  # Сохраняем изменения
        
        bot.send_message(call.message.chat.id, f"Ваше бронирование на {selected_booking['date']} с {selected_booking['time_interval']} отменено.")
    else:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено.")

# Функция для загрузки бронирований из файла bookings.csv
def load_bookings():
    bookings = []
    with open('bookings.csv', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            bookings.append(row)
    return bookings

# Функция для сохранения бронирований в файл bookings.csv
def save_bookings(bookings):
    with open('bookings.csv', mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['user_id', 'first_name', 'last_name', 'workspace_id', 'date', 'time_interval', 'time_start', 'time_end', 'duration', 'cancel', 'extension', 'finish'])
        writer.writeheader()
        writer.writerows(bookings)

#    Работает!!!!!!
# Команда для продления времени бронирования   
@bot.message_handler(commands=['продлить'])
def extend_booking(message):
    user_id = str(message.from_user.id)
    now = datetime.now()

    # Загружаем бронирования пользователя
    bookings = load_bookings()
    active_bookings = [b for b in bookings if b['user_id'] == user_id and b['cancel'] == '0' and b['finish'] == '']

    if not active_bookings:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для продления.")
        return

    # Проверяем, находится ли пользователь в забронированном временном интервале
    current_booking = None
    for booking in active_bookings:
        time_start = datetime.strptime(f"{booking['date']} {booking['time_start']}", "%d-%m-%Y %H:%M")
        time_end = datetime.strptime(f"{booking['date']} {booking['time_end']}", "%d-%m-%Y %H:%M")
        
        if time_start <= now <= time_end:
            current_booking = booking
            break

    if not current_booking:
        bot.send_message(message.chat.id, "Вы не находитесь в забронированном временном интервале.")
        return

    # Если пользователь находится в интервале бронирования, предлагаем продлить время
    markup = InlineKeyboardMarkup()
    workspace_name = next((ws['name'] for ws in load_available_workspaces() if ws['id'] == current_booking['workspace_id']), "Неизвестное РМ")
    button_text = f"{workspace_name} ({current_booking['time_interval']})"
    callback_data = f"extend_{current_booking['workspace_id']}_{current_booking['date']}_{current_booking['time_start']}"  # Привязка к конкретному бронированию
    markup.add(InlineKeyboardButton(text=button_text, callback_data=callback_data))

    bot.send_message(message.chat.id, "Выберите рабочее место для продления:", reply_markup=markup)

# Обработка выбора рабочего места для продления
@bot.callback_query_handler(func=lambda call: call.data.startswith("extend_"))
def extend_time_selection(call):
    _, workspace_id, date, time_start = call.data.split("_")

    # Предлагаем выбрать время продления (от 00:30 до 06:00 с шагом 30 минут)
    markup = InlineKeyboardMarkup()
    durations = [(0, 30), (1, 0), (1, 30), (2, 0), (2, 30), (3, 0), (3, 30), (4, 0), (4, 30), (5, 0), (5, 30), (6, 0)]
    
    for hours, minutes in durations:
        duration = f"{hours:02d}:{minutes:02d}"
        callback_data = f"select_duration1_{workspace_id}_{date}_{time_start}_{duration}"  # Привязка к конкретному бронированию
        markup.add(InlineKeyboardButton(text=duration, callback_data=callback_data))

    bot.send_message(call.message.chat.id, "Выберите время для продления:", reply_markup=markup)

# Обработка выбора времени продления
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_duration1_"))
def extend_time_confirm(call):
    workspace_id, date, time_start, duration = call.data.split("_")[2:]
    user_id = str(call.from_user.id)
    bookings = load_bookings()

    # Находим текущее активное бронирование для этого рабочего места по дате и времени
    current_booking = next((b for b in bookings if b['workspace_id'] == workspace_id and b['user_id'] == user_id 
                            and b['date'] == date and b['time_start'] == time_start and b['cancel'] == '0' and b['finish'] == ''), None)
    
    if not current_booking:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено.")
        return

    # Проверяем возможность продления
    time_end = datetime.strptime(f"{current_booking['date']} {current_booking['time_end']}", "%d-%m-%Y %H:%M")
    hours, minutes = map(int, duration.split(":"))
    new_time_end = time_end + timedelta(hours=hours, minutes=minutes)

    # Проверка на занятость рабочего места в выбранный временной интервал
    conflicting_booking = next((b for b in bookings if b['workspace_id'] == workspace_id and b['date'] == current_booking['date'] 
                                and b['cancel'] == '0' and b['finish'] == '0' 
                                and datetime.strptime(b['time_start'], '%H:%M') < new_time_end <= datetime.strptime(b['time_end'], '%H:%M')), None)
    
    if conflicting_booking:
        bot.send_message(call.message.chat.id, f"Данное время занято. Согласуйте временной интервал с {conflicting_booking['first_name']} {conflicting_booking['last_name']}.")
    else:
        # Продление времени
        current_booking['time_end'] = new_time_end.strftime("%H:%M")
        current_booking['time_interval'] = f"{current_booking['time_interval'].split('-')[0]}-{current_booking['time_end']}"
        current_booking['extension'] = duration
        save_bookings(bookings)  # Сохраняем изменения

        bot.send_message(call.message.chat.id, f"Ваше бронирование на рабочее место {current_booking['workspace_id']} продлено до {current_booking['time_end']}.")

#    Работает!!!!!!!
# Команда для завершения работы на рабочем месте    
@bot.message_handler(commands=['finish'])
def finish_booking(message):
    user_id = str(message.from_user.id)
    now = datetime.now()

    # Загружаем бронирования пользователя
    bookings = load_bookings()
    active_bookings = [b for b in bookings if b['user_id'] == user_id and b['cancel'] == '0' and b['finish'] == '']

    if not active_bookings:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для завершения.")
        return

    # Проверяем, находится ли пользователь в забронированном временном интервале
    current_bookings = []
    for booking in active_bookings:
        time_start = datetime.strptime(f"{booking['date']} {booking['time_start']}", "%d-%m-%Y %H:%M")
        time_end = datetime.strptime(f"{booking['date']} {booking['time_end']}", "%d-%m-%Y %H:%M")

        if time_start <= now <= time_end:
            current_bookings.append(booking)

    if not current_bookings:
        bot.send_message(message.chat.id, "Вы не находитесь в забронированном временном интервале.")
        return

    # Если есть активные бронирования в данный момент, предлагаем выбрать рабочее место для завершения
    markup = InlineKeyboardMarkup()
    for booking in current_bookings:
        workspace_name = next((ws['name'] for ws in load_available_workspaces() if ws['id'] == booking['workspace_id']), "Неизвестное РМ")
        button_text = f"{workspace_name} ({booking['time_interval']})"
        callback_data = f"finish_{booking['workspace_id']}_{booking['date']}_{booking['time_start']}"  # Привязка к конкретному бронированию
        markup.add(InlineKeyboardButton(text=button_text, callback_data=callback_data))

    bot.send_message(message.chat.id, "Выберите рабочее место для завершения работы:", reply_markup=markup)

# Обработка завершения работы на выбранном рабочем месте
@bot.callback_query_handler(func=lambda call: call.data.startswith("finish_"))
def finish_booking_confirm(call):
    _, workspace_id, date, time_start = call.data.split("_")
    user_id = str(call.from_user.id)
    bookings = load_bookings()

    # Находим текущее активное бронирование для этого рабочего места
    current_booking = next((b for b in bookings if b['workspace_id'] == workspace_id and b['user_id'] == user_id 
                            and b['date'] == date and b['time_start'] == time_start and b['cancel'] == '0' and b['finish'] == ''), None)
    
    if not current_booking:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено.")
        return

    # Завершаем работу: записываем текущее время в столбец finish
    current_booking['finish'] = datetime.now().strftime("%H:%M")
    save_bookings(bookings)  # Сохраняем изменения

    bot.send_message(call.message.chat.id, f"Ваше бронирование на рабочее место {current_booking['workspace_id']} завершено.")

#    Работает!!!!!!!    
# Функция для Help  
@bot.message_handler(commands=['help'])
def handle_message(message):
    bot.reply_to(message, "Команды бота:\n"
        "/регистрация - регистрация пользователя.\n "
        "/booking - резервирование оборудования.\n"
        "/cancel - предлагает варианты для удаления резервирования.\n"
        "/продлить - предлагает варианты для продления резервирования.\n"
        "/finish - окончание работы на зарезервированном оборудовании. По окончании работы на рабочем месте необходимо нажать на эту кнопку для того чтобы освободить время резервирования РМ. \n"
        "/users - просмотр зарегистрированных пользователей.\n"
        "/mybookings  - просмотр ваших резервирований РМ.\n"
        "/workspacebookings - просмотр резервирований РМ.\n"
        "/datebookings - просмотр всех резервирований РМ на дату .\n"
        "/help - вывод сообщение справки.\n"
        "/view_equipment - просмотр рабочих мест и оборудования.\n"
        )
#    Работает!!!!!!!  
# Клавиатура
# Добавляем кнопки управления
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    btn1 = types.KeyboardButton('/help')
    #btn2 = types.KeyboardButton('/регистрация')
        
    btn3 = types.KeyboardButton('/booking')
    btn4 = types.KeyboardButton('/cancel')
    btn5 = types.KeyboardButton('/finish')
    btn6 = types.KeyboardButton('/продлить')
    
    btn7 = types.KeyboardButton('/mybookings')
    btn8 = types.KeyboardButton('/workspacebookings')
    btn9 = types.KeyboardButton('/datebookings')
    
    markup.add(btn1) #, btn2
    markup.add(btn3, btn4,  btn5, btn6)
    markup.add(btn7, btn8, btn9)
    
    # Приветствие
    user_id = str(message.from_user.id)
    user_id_to_check = user_id
    register_users = load_registered_users()
    if check_user_exists(user_id_to_check):
        first_name = register_users[user_id]['first_name']
        #last_name = registered_users[user_id]['last_name']
        bot.send_message(message.chat.id, f"Привет {first_name}! Я бот для резервирования оборудования.\n " 
                        "Используй /help для получения списка команд.", reply_markup=markup)
    else:
        # Если пользователь не найден, запрашиваем имя и фамилию
        msg = bot.send_message(message.chat.id, "Привет! Я бот для резервирования оборудования.\n " 
                            "Используй /help для получения списка команд.\n"
                            " \n"
                            "Пожалуйста, введите ваше имя.", reply_markup=markup)
        bot.register_next_step_handler(msg, get_first_name)

# Проверка наличия пользователя по user_id
def check_user_exists(user_id):
    users = load_registered_users()  # Загружаем всех пользователей
    return user_id in users  # Проверяем наличие user_id в словаре
    
# Обработка ввода имени
def get_first_name(message):
    first_name = message.text
    msg = bot.send_message(message.chat.id, "Пожалуйста, введите вашу фамилию.")
    bot.register_next_step_handler(msg, get_last_name, first_name)

# Обработка ввода фамилии
def get_last_name(message, first_name):
    last_name = message.text
    user_id = int(message.from_user.id)

# Сохраняем нового пользователя в registered_users.csv
    save_registered_user(user_id, first_name, last_name)
    bot.send_message(message.chat.id, f"Спасибо, {first_name} {last_name}! Вы успешно зарегистрированы.")

#    Работает!!!!!!!  
# Загрузка зарегистрированных пользователей
def load_registered_users():
    users = {}
    with open('registered_users.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            users[row['user_id']] = {'first_name': row['first_name'], 'last_name': row['last_name']}
    return users


#    Работает!!!!!!!  
# Функция для добавления нового пользователя в файл registered_users.csv
def save_registered_user(user_id, first_name, last_name):
    reg_date = datetime.now().strftime('%d-%m-%Y')
    reg_time = datetime.now().strftime('%H:%M:%S')
    with open('registered_users.csv', mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([user_id, first_name, last_name, reg_date, reg_time])

#    Работает!!!!!!!  
# Команда для просмотра всех зарегистрированных пользователей
@bot.message_handler(commands=['users'])
def show_registered_users(message):
    registered_users = load_registered_users()
    print(registered_users)
    if registered_users:
        user_list = "\n".join([f"{user_info['first_name']} {user_info['last_name']}" for user_info in registered_users.values()])
        bot.send_message(message.chat.id, f"Зарегистрированные пользователи:\n{user_list}")
    else:
        bot.send_message(message.chat.id, "Нет зарегистрированных пользователей.")

# Запуск бота
if __name__ == "__main__":
    load_registered_users()

bot.infinity_polling(none_stop=True, timeout=15, long_polling_timeout = 5)
