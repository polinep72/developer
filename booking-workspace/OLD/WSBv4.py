import pandas as pd
from datetime import datetime, timedelta
import telebot
from telebot import types
import threading
import time
import schedule
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

# Инициализация бота
bot = telebot.TeleBot('YOUR_BOT_API_TOKEN') # @IPK_workplace_bot

# Создаём планировщик
scheduler = BackgroundScheduler()

# Глобальный словарь для отслеживания отправленных уведомлений (для начала и окончания работы)
sent_notifications = {
    'start': set(),  # Уникальные ключи бронирований, для которых отправлено уведомление о начале
    'end': set()     # Уникальные ключи бронирований, для которых отправлено уведомление о завершении
}

# Файлы
BOOKINGS_FILE = 'bookings.csv'
EQUIPMENT_FILE = 'equipment.csv'
REGISTERED_USERS_FILE = 'registered_users.csv'

# Загрузка необходимых файлов
# Загрузка данных о пользователях
def load_registered_users():
    try:
        users_df = pd.read_csv('registered_users.csv', encoding='utf-8')
        return users_df
    except Exception as e:
        print(f"Ошибка загрузки оборудования: {e}")
        return None
# Загрузка данных об оборудовании
def load_equipment():
    try:
        equipment_df = pd.read_csv('equipment.csv', encoding='utf-8')
        return equipment_df
    except Exception as e:
        print(f"Ошибка загрузки оборудования: {e}")
        return None

# Загрузка данных бронирований
def load_bookings():
    try:
        bookings_df = pd.read_csv('bookings.csv', encoding='utf-8')
        return bookings_df
    except Exception as e:
        print(f"Ошибка загрузки бронирований: {e}")
        return None
# Сохранение данных о пользователях
def save_registered_users(users_df):
    users_df.to_csv('registered_users.csv', index=False, encoding='utf-8')

# Сохранение бронирований
def save_booking(new_booking):
    bookings_df = load_bookings()
    # Преобразуем новый словарь в DataFrame для добавления
    new_booking_df = pd.DataFrame([new_booking])
    # Используем метод _append() для добавления
    bookings_df = bookings_df._append(new_booking_df, ignore_index=True)
    # Сохраняем обновленный DataFrame в файл
    bookings_df.to_csv('bookings.csv', index=False, encoding='utf-8')

# Загрузка объединенной таблицы (бронирования и оборудования)
def load_inf():
    bookings_df = load_bookings() # Загружаем бронирования
    equipment_df = load_equipment()  # Загружаем оборудование
    b_e_df =pd.merge(bookings_df, equipment_df, left_on='workspace_id', right_on='workspace_id', how='left')
    return b_e_df

    
# Функция Help  
@bot.message_handler(commands=['help'])
def handle_message(message):
    bot.reply_to(message, "Команды бота:\n"
        "/забронировать - резервирование оборудования.\n"
        "/отмена - предлагает варианты для удаления резервирования.\n"
        "/продлить - предлагает варианты для продления резервирования.\n"
        "/закончить - окончание работы на зарезервированном оборудовании. По окончании работы на рабочем месте необходимо нажать на эту кнопку для того чтобы освободить время резервирования РМ. \n"
        "/users - просмотр зарегистрированных пользователей.\n"
        "/моя_бронь  - просмотр ваших резервирований РМ.\n"
        "/по_оборудованию - просмотр резервирований РМ.\n"
        "/по_дате - просмотр всех резервирований РМ на дату .\n"
        "/help - вывод сообщение справки.\n"
        "/view_equipment - просмотр рабочих мест и оборудования.\n"
        )

# Начало работы START
@bot.message_handler(commands=['start'])
    
def register_user(message):
    # Клавиатура
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('/help')
    btn2 = types.KeyboardButton('/view_equipment')
        
    btn3 = types.KeyboardButton('/забронировать')
    btn4 = types.KeyboardButton('/отмена')
    btn5 = types.KeyboardButton('/закончить')
    btn6 = types.KeyboardButton('/продлить')
    
    btn7 = types.KeyboardButton('/моя_бронь')
    btn8 = types.KeyboardButton('/по_оборудованию')
    btn9 = types.KeyboardButton('/по_дате')
    
    markup.add(btn1) 
    markup.add(btn2) 
    markup.add(btn3, btn4,  btn5, btn6)
    markup.add(btn7, btn8, btn9)
    
    user_id = int(message.from_user.id)
    registered_users_df = load_registered_users()
    schedule_notifications()
    # Проверка регистрации пользователя
    if int(user_id) in registered_users_df['user_id'].values:
        first_name = registered_users_df.loc[registered_users_df['user_id']==user_id,'first_name'].item()
        
        bot.send_message(message.chat.id, f"Привет {first_name}! Я бот для резервирования оборудования.\n " 
                        "Используй /help для получения списка команд.", reply_markup=markup)
        return

    # Регистрация пользователя
    msg = bot.send_message(message.chat.id,  "Привет! Я бот для резервирования оборудования.\n " 
                            "Используй /help для получения списка команд.\n"
                            " \n"
                            "Пожалуйста, введите ваше имя и фамилию через пробел.", reply_markup=markup)
    bot.register_next_step_handler(msg, process_registration)

def process_registration(message):
    user_id = message.from_user.id
    try:
        first_name, last_name = message.text.split(' ')
    except ValueError:
        bot.send_message(message.chat.id, "Ошибка: необходимо ввести два слова (имя и фамилию).")
        return
    
    registered_users_df = load_registered_users()
    new_user = pd.DataFrame({
        'user_id': [user_id],
        'first_name': [first_name],
        'last_name': [last_name],
        'date': [datetime.now().strftime('%d-%m-%Y')],
        'time': [datetime.now().strftime('%H:%M:%S')]
    })
    registered_users_df = pd.concat([registered_users_df, new_user], ignore_index=True)
    save_registered_users(registered_users_df)
    bot.send_message(message.chat.id, f"Спасибо, {first_name}! Вы успешно зарегистрированы.!")

# Оборудование  просмотр и добавление 
# Просмотр списка оборудования
@bot.message_handler(commands=['view_equipment'])
def view_equipment(message):
    equipment_df = load_equipment()
    if equipment_df is not None:
        # Формируем ответ для пользователя
        response = "Список доступного оборудования:\n\n"
        for index, row in equipment_df.iterrows():
            response += f"{row['workspace_id']}. {row['name']}\n"
        
        # Отправляем сообщение с оборудованием пользователю
        bot.send_message(message.chat.id, response)
    else:
        bot.send_message(message.chat.id, "Ошибка загрузки оборудования. Попробуйте позже.")

# Добавление в список оборудования
@bot.message_handler(commands=['add_equipment'])
def add_equipment(message):
    bot.send_message(message.chat.id, "Введите категорию оборудования:")
    bot.register_next_step_handler(message, get_category)

def get_category(message):
    category = message.text
    bot.send_message(message.chat.id, "Введите название оборудования:")
    bot.register_next_step_handler(message, get_name, category)

def get_name(message, category):
    name = message.text
    bot.send_message(message.chat.id, "Введите описание оборудования:")
    bot.register_next_step_handler(message, get_note, category, name)

def get_note(message, category, name):
    note = message.text

    # Загружаем текущий список оборудования
    equipment_df = load_equipment()

    if equipment_df is not None:
        # Находим последний id и увеличиваем его на 1
        if not equipment_df.empty:
            last_id = equipment_df['workspace_id'].max() + 1
        else:
            last_id = 1
        # Добавляем новое оборудование в DataFrame
        new_data = pd.DataFrame({
            'workspace_id': [last_id],
            'category': [category],
            'name': [name],
            'note': [note]
        })
        # Объединяем старые и новые данные
        updated_df = pd.concat([equipment_df, new_data], ignore_index=True)
        # Сохраняем в файл
        try:
            updated_df.to_csv('equipment.csv', index=False, encoding='utf-8')
            bot.send_message(message.chat.id, "Оборудование успешно добавлено!")
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка сохранения оборудования: {e}")
    else:
        bot.send_message(message.chat.id, "Не удалось загрузить оборудование.")


# Просмотр бронирований
# Своих
@bot.message_handler(commands=['моя_бронь'])
def mybookings(message):
    user_id = str(message.from_user.id)
    # Загружаем файл с бронированиями
    bookings_df = load_inf()
    if bookings_df is not None:
        try:
            # Преобразуем столбец time_start в формат datetime
            bookings_df['time_start'] = pd.to_datetime(bookings_df['time_start'], format='%Y-%m-%d %H:%M:%S')
            bookings_df['time_end'] = pd.to_datetime(bookings_df['time_end'], format='%Y-%m-%d %H:%M:%S')
            # Фильтруем бронирования по user_id и будущим датам
            now = datetime.now()
            #now = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_ahead = now + timedelta(days=7)
            user_bookings = bookings_df[(bookings_df['user_id'] == int(user_id)) & 
                                        #(bookings_df['time_start'] >= now) &
                                        (bookings_df['time_end'] > now) &
                                        (bookings_df['cancel'] == 0) & 
                                        (bookings_df['finish'].isnull())]
            #print(user_bookings)
            if not user_bookings.empty:
                response = "Ваши бронирования:\n"
                for _, row in user_bookings.iterrows():
                    workspace_name = row['name']  # Получаем название оборудования
                    response += f"Оборудование: {workspace_name},\nДата: {row['date']},\nВремя: {row['time_interval']}\n\n"
            else:
                response = "У вас нет активных или будущих бронирований."
            schedule_notifications()
            bot.send_message(message.chat.id, response)
        except Exception as e:
            bot.send_message(message.chat.id, f"Ошибка обработки данных: {e}")
    else:
        bot.send_message(message.chat.id, "Ошибка загрузки бронирований или оборудования.")

# по оборудованию
@bot.message_handler(commands=['по_оборудованию'])
def workspacebookings(message):
    markup = types.InlineKeyboardMarkup()
    available_workspaces = load_equipment()  # Загружаем рабочие места из файла equipment.csv
    for _, row in available_workspaces.iterrows():
        markup.add(types.InlineKeyboardButton(text=row['name'], callback_data=f"workspace_{row['workspace_id']}"))
    bot.send_message(message.chat.id, "Выберите рабочее место для просмотра бронирований:", reply_markup=markup)
# Обработка выбора рабочего места
@bot.callback_query_handler(func=lambda call: call.data.startswith("workspace_"))
def get_workspace_bookings(call):
    workspace_id = call.data.split("_")[1]  # Получаем ID выбранного рабочего места
    bookings = load_inf()
    bookings['workspace_id'] = bookings['workspace_id'].astype(int)
    #workspace_name = df[df['B'] == 3]['A'].item() bookings.loc[bookings['workspace_id'] == workspace_id, 'name']
    now = datetime.now()
    now = now.replace(hour=0, minute=0, second=0, microsecond=0)
    bookings['time_start'] = pd.to_datetime(bookings['time_start'], format='%Y-%m-%d %H:%M:%S')
    user_bookings = bookings[(bookings['workspace_id'] == int(workspace_id)) & 
                                        (bookings['time_start'] > now) &
                                        (bookings['cancel'] == 0) & 
                                        (bookings['finish'].isnull())]
    df_equip = load_equipment()
    workspace_name = df_equip.loc[df_equip['workspace_id'] == int(workspace_id)]['name'].item()
    if not user_bookings.empty:
        response = f"Бронирования для оборудования:{workspace_name},\n"
        for _, row in user_bookings.iterrows():
            workspace_name = row['name']  # Получаем название оборудования
            first_name=row['first_name']
            last_name=row['last_name']
            response += f"Пользователь: {first_name} {last_name},\nДата: {row['date']},\nВремя: {row['time_interval']}\n\n"
    else:
        response = f"Для оборудования {workspace_name} нет активных или будущих бронирований."
    schedule_notifications()
    bot.send_message(call.message.chat.id, response)

# по датам
def generate_date_buttons():
    now = datetime.now()
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    # Создаем кнопки на 7 дней вперед
    for i in range(7):
        date_str = (now + timedelta(days=i)).strftime('%d-%m-%Y')
        button = types.InlineKeyboardButton(date_str, callback_data=f"date_{date_str}")
        keyboard.add(button)
    return keyboard
# Обработчик команды /datebookings
@bot.message_handler(commands=['по_дате'])
def datebookings(message):
    # Отправляем клавиатуру с выбором даты
    keyboard = generate_date_buttons()
    bot.send_message(message.chat.id, "Выберите дату для просмотра бронирований:", reply_markup=keyboard)

# Обработчик выбора даты (обработка callback_query)
@bot.callback_query_handler(func=lambda call: call.data.startswith("date_"))
def callback_date(call):
    selected_date = call.data.split("_")[1]  # Извлекаем дату из callback_data
    bookings_df = load_bookings()
    equipment_df = load_equipment()
    equipment_dict = dict(zip(equipment_df['workspace_id'], equipment_df['name']))  # Преобразуем в словарь {id: name}
    if bookings_df is not None and equipment_dict is not None:
        try:
            # Фильтруем бронирования по выбранной дате
            bookings_df['time_start'] = pd.to_datetime(bookings_df['time_start'], format='%Y-%m-%d %H:%M:%S')
            selected_datetime = datetime.strptime(selected_date, '%d-%m-%Y')
            filtered_bookings = bookings_df[(bookings_df['time_start'].dt.date == selected_datetime.date()) & 
                                            (bookings_df['cancel'] == 0) & 
                                            (bookings_df['finish'].isnull())
                                            ]
            if not filtered_bookings.empty:
                response = f"Бронирования на {selected_date}:\n"
                for _, row in filtered_bookings.iterrows():
                    workspace_name = equipment_dict.get(int(row['workspace_id']), "Неизвестное оборудование")
                    response += f"Оборудование: {workspace_name},\nВремя: {row['time_interval']},\nПользователь: {row['first_name']} {row['last_name']}\n\n"
            else:
                response = f"Нет бронирований на {selected_date}."
            schedule_notifications()
            # Отправляем результат
            bot.send_message(call.message.chat.id, response)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка обработки данных: {e}")
    else:
        bot.send_message(call.message.chat.id, "Ошибка загрузки бронирований или оборудования.")


# Бронирование рабочего места
# Начало бронирования - выбор категории оборудования
@bot.message_handler(commands=['забронировать'])
def start_booking(message):
    equipment_df = load_equipment()
    categories = equipment_df['category'].unique()
    markup = types.InlineKeyboardMarkup()
    for category in categories:
        markup.add(types.InlineKeyboardButton(text=category, callback_data=f"category1_{category}"))
    bot.send_message(message.chat.id, "Выберите категорию оборудования:", reply_markup=markup)
# Обработчик выбора категории
@bot.callback_query_handler(func=lambda call: call.data.startswith("category1_"))
def choose_equipment(call):
    category = call.data.split("_")[1]
    equipment_df = load_equipment()
    # Фильтруем оборудование по выбранной категории
    category_equipment = equipment_df[equipment_df['category'] == category]
    markup = types.InlineKeyboardMarkup()
    for _, row in category_equipment.iterrows():
        markup.add(types.InlineKeyboardButton(text=row['name'], callback_data=f"equipment1_{row['workspace_id']}"))
    bot.edit_message_text("Выберите оборудование:", call.message.chat.id, call.message.message_id, reply_markup=markup)
# Обработчик выбора оборудования
@bot.callback_query_handler(func=lambda call: call.data.startswith("equipment1_"))
def choose_date(call):
    equipment_id = call.data.split("_")[1]
    now = datetime.now()
    markup = types.InlineKeyboardMarkup()
    # Предлагаем выбор дня на неделю вперед
    for i in range(7):
        day = now + timedelta(days=i)
        day_str = day.strftime('%d-%m-%Y')
        markup.add(types.InlineKeyboardButton(text=day_str, callback_data=f"date1_{day_str}_{equipment_id}"))
    bot.edit_message_text("Выберите дату:", call.message.chat.id, call.message.message_id, reply_markup=markup)
# Обработчик выбора даты
@bot.callback_query_handler(func=lambda call: call.data.startswith("date1_"))
def choose_time(call):
    data = call.data.split("_")
    selected_date = data[1]
    equipment_id = data[2]
    markup = types.InlineKeyboardMarkup()
    # Предлагаем время с 08:00 до 20:00 с шагом 30 минут
    time = datetime.strptime('08:00', '%H:%M')
    end_time = datetime.strptime('20:00', '%H:%M')
    while time <= end_time:
        time_str = time.strftime('%H:%M')
        markup.add(types.InlineKeyboardButton(text=time_str, callback_data=f"time1_{time_str}_{selected_date}_{equipment_id}"))
        time += timedelta(minutes=30)
    bot.edit_message_text("Выберите время начала работы:", call.message.chat.id, call.message.message_id, reply_markup=markup)
# Обработчик выбора времени
@bot.callback_query_handler(func=lambda call: call.data.startswith("time1_"))
def choose_duration(call):
    data = call.data.split("_")
    start_time = data[1]
    selected_date = data[2]
    equipment_id = data[3]
    markup = types.InlineKeyboardMarkup()
    # Предлагаем выбрать длительность работы с шагом 30 минут (от 00:30 до 12:00)
    duration = timedelta(minutes=30)
    max_duration = timedelta(hours=12)
    while duration <= max_duration:
        duration_str = f"{duration.seconds//3600}:{(duration.seconds//60)%60:02}"
        markup.add(types.InlineKeyboardButton(text=duration_str, callback_data=f"duration1_{duration_str}_{start_time}_{selected_date}_{equipment_id}"))
        duration += timedelta(minutes=30)
    bot.edit_message_text("Выберите длительность работы:", call.message.chat.id, call.message.message_id, reply_markup=markup)
# Обработчик выбора длительности
@bot.callback_query_handler(func=lambda call: call.data.startswith("duration1_"))
def finalize_booking(call):
    user_id = int(call.from_user.id)
    # Загрузка зарегистрированных пользователей
    users_df = load_registered_users()
    # Извлекаем информацию о пользователе
    user_info = users_df[users_df['user_id'] == user_id]
    if user_info.empty:
        raise ValueError(f"Пользователь с user_id {user_id} не найден.")
    first_name = user_info['first_name'].values[0]
    last_name = user_info['last_name'].values[0]
    data = call.data.split("_")
    duration_str = data[1]
    start_time = data[2]
    selected_date = data[3]
    equipment_id = data[4]
    #print(duration_str,start_time,selected_date,equipment_id)
    start_datetime = datetime.strptime(f"{selected_date} {start_time}", '%d-%m-%Y %H:%M')
    duration_parts = duration_str.split(":")
    duration_timedelta = timedelta(hours=int(duration_parts[0]), minutes=int(duration_parts[1]))
    end_datetime = start_datetime + duration_timedelta
    # Проверка на пересечения по времени
    bookings_df = load_bookings()
    #print(bookings_df)
    equipment_bookings = bookings_df[
        (bookings_df['workspace_id'] == int(equipment_id)) &
        (bookings_df['cancel'] == 0) &          # Не отмененные
        (bookings_df['finish'].isna())           # Не завершенные
    ]
    #print(equipment_bookings)
    for _, booking in equipment_bookings.iterrows():
        booked_start = datetime.strptime(booking['time_start'], '%Y-%m-%d %H:%M:%S')
        booked_end = datetime.strptime(booking['time_end'], '%Y-%m-%d %H:%M:%S')
        if not (end_datetime <= booked_start or start_datetime >= booked_end):
            bot.send_message(call.message.chat.id, f"Пересечение по времени с бронированием пользователя {booking['first_name']} {booking['last_name']} на {booking['time_start']} - {booking['time_end']}")
            return
    # Сохранение бронирования
    time_interval = f"{start_datetime.strftime('%H:%M')}-{end_datetime.strftime('%H:%M')}"
    duration = duration_timedelta.total_seconds() / 3600  # Общая продолжительность в часах
    new_booking = {
        'user_id': call.from_user.id,
        'first_name': first_name,
        'last_name': last_name,
        'workspace_id': equipment_id,
        'date': selected_date,
        'time_interval': time_interval,
        'time_start': start_datetime.strftime('%Y-%m-%d %H:%M:%S'),
        'time_end': end_datetime.strftime('%Y-%m-%d %H:%M:%S'),
        'duration': f"{duration:.2f}",
        'cancel': 0,
        'extension': '',
        'finish': ''
    }
    save_booking(new_booking)
    schedule_notifications()
    bot.send_message(call.message.chat.id, "Ваше бронирование успешно сохранено.")


# Команда /cancel
@bot.message_handler(commands=['отмена'])
def cancel_booking(message):
    user_id = int(message.from_user.id)
    # Загружаем бронирования
    df = load_bookings()
    # Загружаем список оборудования
    equipment_df = load_equipment()
    equipment_dict = pd.Series(equipment_df['name'].values, index=equipment_df['workspace_id'].astype(str)).to_dict()
    now0 = datetime.now()
    now0 = now0.replace(hour=0, minute=0, second=0, microsecond=0)
    # Фильтруем активные бронирования пользователя (не отменённые, не завершённые)
    user_bookings = df[(df['user_id'] == user_id) &
                        (df['cancel'] == 0) &
                        (pd.to_datetime(df['time_start'], format='%Y-%m-%d %H:%M:%S') > now0) &
                        (df['finish'].isna())
                        ]
    if user_bookings.empty:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для отмены.")
        return
    # Создаём клавиатуру для выбора бронирования
    markup = types.InlineKeyboardMarkup()
    for index, row in user_bookings.iterrows():
        # Получаем название оборудования по workspace_id
        workspace_name = equipment_dict.get(str(row['workspace_id']), 'Неизвестное оборудование')
        button_text = f"{workspace_name} - {row['date']} - {row['time_interval']}"
        callback_data = f"cancel_booking_{index}"  # Используем индекс для идентификации бронирования
        markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
    bot.send_message(message.chat.id, "Выберите бронирование для отмены:", reply_markup=markup)
# Обработка выбора бронирования для отмены
@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_booking_"))
def confirm_cancel_booking(call):
    booking_index = int(call.data.split("_")[2])
    # Загружаем бронирования снова
    df = load_bookings()
    # Проверяем, что бронирование существует и не отменено
    if df.at[booking_index, 'cancel'] == 1:
        bot.send_message(call.message.chat.id, "Это бронирование уже было отменено.")
        return
    # Обновляем столбец cancel
    df.at[booking_index, 'cancel'] = 1
    df.to_csv('bookings.csv', index=False, encoding='utf-8')  # Сохраняем изменения
    schedule_notifications()
    bot.send_message(call.message.chat.id, "Бронирование успешно отменено.")

# Функция для завершения работы и записи времени в столбец finish
def finish_work(booking, chat_id):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Текущее время в нужном формате
    #print(f"Завершаем бронирование: {booking}")
        # Загружаем оборудование с помощью pandas
    equipment_df = load_equipment()
    equipment_dict = pd.Series(equipment_df['name'].values, index=equipment_df['workspace_id'].astype(str)).to_dict()
    # Загружаем бронирования
    bookings_df = load_bookings()
    # Преобразуем столбцы time_start и finish к формату datetime для корректного сравнения
    bookings_df['time_start'] = pd.to_datetime(bookings_df['time_start'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    bookings_df['finish'] = pd.to_datetime(bookings_df['finish'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    # Логика для обновления времени завершения работы
    bookings_df.loc[
        (bookings_df['workspace_id'] == booking['workspace_id']) & 
        (bookings_df['user_id'] == booking['user_id']) & 
        (bookings_df['date'] == booking['date']) & 
        (bookings_df['time_start'] == booking['time_start']),
        'finish'
    ] = now  # Записываем текущее время
    # Сохраняем обновленные данные
    bookings_df.to_csv('bookings.csv', index=False)
    schedule_notifications()
    bot.send_message(chat_id, f"Ваше бронирование оборудования {booking['workspace_id']} завершено в {now}.")


# Функция для завершения работы
@bot.message_handler(commands=['закончить'])
def finish_booking(message):
    user_id = int(message.from_user.id)
    now = datetime.now()
    # Загружаем оборудование с помощью pandas
    equipment_df = load_equipment()
    equipment_dict = pd.Series(equipment_df['name'].values, index=equipment_df['workspace_id'].astype(str)).to_dict()
    # Загружаем бронирования с помощью pandas
    bookings_df = load_inf()
    # Фильтруем активные бронирования пользователя
    active_bookings = bookings_df[
        (bookings_df['user_id'] == user_id) & 
        (bookings_df['cancel'] == 0) & 
        (bookings_df['finish'].isnull())
    ]
    if active_bookings.empty:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для завершения.")
        return
    # Проверяем, находится ли пользователь в забронированном временном интервале
    ongoing_bookings = active_bookings[
        (pd.to_datetime(active_bookings['time_start'], format='%Y-%m-%d %H:%M:%S') < now) & 
        (pd.to_datetime(active_bookings['time_end'], format='%Y-%m-%d %H:%M:%S') > now)
    ]
    if ongoing_bookings.empty:
        bot.send_message(message.chat.id, "Вы не находитесь в забронированном временном интервале.")
        return
    # Если у пользователя несколько активных бронирований, предлагаем выбрать рабочее место
    if len(ongoing_bookings) > 1:
        # Создаем клавиатуру для выбора бронирования
        markup = types.InlineKeyboardMarkup()
        for idx, booking in ongoing_bookings.iterrows():
            workspace_name = equipment_dict.get(str(booking['workspace_id']), 'Неизвестное оборудование')
            button_text = f"{workspace_name} ({booking['time_interval']})"
            callback_data = f"finish_{booking['workspace_id']}_{booking['date']}_{booking['time_start']}_{booking['time_end']}"
            markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
        bot.send_message(message.chat.id, "Выберите рабочее место для завершения:", reply_markup=markup)
    else:
        # Если одно бронирование, сразу завершаем работу
        finish_work(ongoing_bookings.iloc[0], message.chat.id)
# Обработка выбора рабочего места для завершения работы
@bot.callback_query_handler(func=lambda call: call.data.startswith("finish_"))
def finish_selected_booking(call):
    _, workspace_id, date, time_start, time_end = call.data.split("_")
    user_id = str(call.from_user.id)
    # Загружаем бронирования с помощью pandas
    bookings_df = load_inf()
    # Преобразуем время для корректного сравнения
    bookings_df['time_start'] = pd.to_datetime(bookings_df['time_start'], format='%Y-%m-%d %H:%M:%S')
    bookings_df['time_end'] = pd.to_datetime(bookings_df['time_end'], format='%Y-%m-%d %H:%M:%S')
    # Находим текущее активное бронирование для этого рабочего места
    current_booking = bookings_df[
        (bookings_df['user_id'] == int(user_id)) & 
        (bookings_df['workspace_id'] == int(workspace_id)) & 
        (bookings_df['date'] == date) & 
        (bookings_df['time_start'] == time_start) & 
        (bookings_df['time_end'] == time_end) & 
        (bookings_df['cancel'] == 0) & 
        (bookings_df['finish'].isnull())
    ]
    #print(user_id, workspace_id, date, time_start, time_end)
    #print(bookings_df.info())
    #print(current_booking)
    if current_booking.empty:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено.")
        return
    schedule_notifications()
    finish_work(current_booking.iloc[0], call.message.chat.id)


# Функция для продления бронирования
@bot.message_handler(commands=['продлить'])
def extend_booking(message):
    user_id = message.from_user.id
    now = datetime.now()
    # Загружаем бронирования
    bookings_df = load_bookings()
    # Проверяем активные бронирования пользователя
    active_bookings = bookings_df[
        (bookings_df['user_id'] == user_id) &
        (bookings_df['cancel'] == 0) &
        (bookings_df['finish'].isnull())
    ]
    if active_bookings.empty:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для продления.")
        return
    # Фильтруем бронирования, которые сейчас в активном временном интервале
    ongoing_bookings = active_bookings[
        (pd.to_datetime(active_bookings['time_start'], format='%Y-%m-%d %H:%M:%S') < now) &
        (pd.to_datetime(active_bookings['time_end'], format='%Y-%m-%d %H:%M:%S') > now)
    ]
    # Загружаем оборудование с помощью pandas
    equipment_df = load_equipment()
    equipment_dict = pd.Series(equipment_df['name'].values, index=equipment_df['workspace_id'].astype(str)).to_dict()
    if ongoing_bookings.empty:
        bot.send_message(message.chat.id, "Вы не находитесь в активном рабочем времени для продления.")
        return
    # Если несколько активных бронирований, предлагаем выбрать рабочее место
    if len(ongoing_bookings) > 1:
        markup = types.InlineKeyboardMarkup()
        for idx, booking in ongoing_bookings.iterrows():
            workspace_name = equipment_dict.get(str(booking['workspace_id']), 'Неизвестное оборудование')
            button_text = f"{workspace_name} ({booking['time_interval']})"
            callback_data = f"extend_{booking['workspace_id']}_{booking['date']}_{booking['time_start']}_{booking['time_end']}"
            markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
        bot.send_message(message.chat.id, "Выберите рабочее место для продления:", reply_markup=markup)
    else:
        extend_booking_for_workspace(ongoing_bookings.iloc[0], message.chat.id)
# Обработка выбора рабочего места для продления
@bot.callback_query_handler(func=lambda call: call.data.startswith("extend_"))
def extend_selected_booking(call):
    _, workspace_id, date, time_start, time_end = call.data.split("_")
    workspace_id = int(workspace_id)
    # Найти бронирование
    bookings_df = load_bookings()
    current_booking = bookings_df[
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['date'] == date) &
        (bookings_df['time_start'] == time_start) &
        (bookings_df['time_end'] == time_end) &
        (bookings_df['cancel'] == 0)
    ]
    if current_booking.empty:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено.")
        return
    extend_booking_for_workspace(current_booking.iloc[0], call.message.chat.id)
# Функция продления для выбранного рабочего места
def extend_booking_for_workspace(booking, chat_id):
    # Генерация времени продления от 00:30 до 08:00 с шагом 0:30
    markup = types.InlineKeyboardMarkup()
    time_intervals = [(i * 30) for i in range(1, 17)]  # от 00:30 до 08:00 с шагом 30 минут
    for minutes in time_intervals:
        # Создаем строковое представление времени в формате ЧЧ:ММ
        hours, mins = divmod(minutes, 60)
        extension = f"{hours:02d}:{mins:02d}"
        callback_data = f"confirm_extend_{booking['workspace_id']}_{booking['date']}_{booking['time_start']}_{extension}"
        markup.add(types.InlineKeyboardButton(text=f"{extension}", callback_data=callback_data))
    bot.send_message(chat_id, "Выберите время для продления:", reply_markup=markup)
# Обработка подтверждения продления
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_extend_"))
def confirm_extension(call):
    #print(call.data)
    confirm, extend, workspace_id, date, time_start, extension = call.data.split("_")
    workspace_id = int(workspace_id)
    user_id = call.from_user.id
    now = datetime.now()
    # Загружаем данные о бронированиях
    bookings_df = load_bookings()
    # Находим бронирование, которое пользователь хочет продлить
    booking = bookings_df[
        (bookings_df['user_id'] == user_id) &
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['date'] == date) &
        (bookings_df['time_start'] == time_start) &
        (bookings_df['cancel'] == 0)
    ].iloc[0]
    # Проверяем возможность продления
    time_end = pd.to_datetime(booking['time_end'], format='%Y-%m-%d %H:%M:%S')
    hours, minutes = map(int, extension.split(":"))
    new_end_time = time_end + timedelta(hours=hours, minutes=minutes)
    bookings_df['time_start'] = pd.to_datetime(bookings_df['time_start'], format='%Y-%m-%d %H:%M:%S')
    bookings_df['time_end'] = pd.to_datetime(bookings_df['time_end'], format='%Y-%m-%d %H:%M:%S')
    # Проверка на пересечение с другими пользователями
    overlapping_bookings = bookings_df[
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['time_start'] < new_end_time) &
        (bookings_df['time_end'] > booking['time_end']) &
        (bookings_df['user_id'] != user_id) &
        (bookings_df['cancel'] == 0)
    ]
    if not overlapping_bookings.empty:
        bot.send_message(call.message.chat.id, "Время пересекается с другим пользователем. Пожалуйста, согласуйте работу.")
        return
    # Продление: Если пересекается с собственным временем, отменяем старое бронирование
    own_overlapping = bookings_df[
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['time_start'] < new_end_time) &
        (bookings_df['time_end'] > booking['time_end']) &
        (bookings_df['user_id'] == user_id) &
        (bookings_df['cancel'] == 0)
    ]
    if not own_overlapping.empty:
        # Отмечаем старое бронирование как отмененное
        bookings_df.loc[own_overlapping.index, 'cancel'] = 1
    # Обновляем бронирование
    bookings_df.loc[
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['user_id'] == user_id) &
        (bookings_df['date'] == date) &
        (bookings_df['time_start'] == time_start),
        'time_end'
    ] = new_end_time
    bookings_df.loc[
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['user_id'] == user_id) &
        (bookings_df['date'] == date) &
        (bookings_df['time_start'] == time_start),
        'extension'
    ] = extension
    bookings_df['time_interval']=bookings_df['time_interval'].astype(str)
    time_start = pd.to_datetime(booking['time_start'], format='%Y-%m-%d %H:%M:%S')
    time_end = pd.to_datetime(booking['time_end'], format='%Y-%m-%d %H:%M:%S')
    time_interval = f"{time_start.strftime('%H:%M')}-{new_end_time.strftime('%H:%M')}"
    bookings_df.loc[
        (bookings_df['workspace_id'] == workspace_id) &
        (bookings_df['user_id'] == user_id) &
        (bookings_df['date'] == date) &
        (bookings_df['time_start'] == time_start),
        'time_interval'
    ] = time_interval
    # Сохраняем данные
    bookings_df.to_csv('bookings.csv', index=False)
    schedule_notifications()
    bot.send_message(call.message.chat.id, f"Ваше бронирование продлено до {new_end_time}.")


# Просмотр пользователей
@bot.message_handler(commands=['users'])
def view_users(message):
    users_df = load_registered_users()
    if users_df.empty:
        bot.send_message(message.chat.id, "Нет зарегистрированных пользователей.")
        return
    users_df['Name'] = users_df['first_name'].map(str) + ' ' + users_df['last_name'].map(str)
    schedule_notifications()
    bot.send_message(message.chat.id, f"Зарегистрированные пользователи:\n{users_df['Name'].to_string(index=False)}")


# Функция для отправки уведомления
def send_notification(user_id, message_text):
    bot.send_message(user_id, message_text)

# Проверка и планирование уведомлений для каждого бронирования
def schedule_notifications():
    now = datetime.now()
    bookings_df = load_inf()
    
    for index, booking in bookings_df.iterrows():
        if booking['cancel'] == 0 and pd.isna(booking['finish']):
            start_time = pd.to_datetime(booking['time_start'], format='%Y-%m-%d %H:%M:%S')
            end_time = pd.to_datetime(booking['time_end'], format='%Y-%m-%d %H:%M:%S')

                        # Генерируем уникальный ключ для бронирования
            booking_key = (booking['user_id'], booking['workspace_id'], booking['date'], booking['time_start'], booking['time_end'])
            
            # Проверяем и планируем уведомление за 10 минут до начала работы
            if booking_key not in sent_notifications['start']:
                notification_time_start = start_time - timedelta(minutes=10)
                if notification_time_start > now:
                    scheduler.add_job(send_notification, DateTrigger(run_date=notification_time_start),
                                        args=[booking['user_id'], f"Напоминание: Ваша работа на оборудовании {booking['name']} начнется через 10 минут ({booking['time_start']})"])
                    # Помечаем, что уведомление о начале было запланировано
                    sent_notifications['start'].add(booking_key)

            # Проверяем и планируем уведомление за 10 минут до завершения работы
            if booking_key not in sent_notifications['end']:
                notification_time_end = end_time - timedelta(minutes=10)
                if notification_time_end > now:
                    scheduler.add_job(send_notification, DateTrigger(run_date=notification_time_end),
                                        args=[booking['user_id'], f"Напоминание: Ваша работа на оборудовании {booking['name']} завершится через 10 минут ({booking['time_end']})"])
                    # Помечаем, что уведомление о завершении было запланировано
                    sent_notifications['end'].add(booking_key)

            
# Запуск бота
def main():
    # # Создаём поток для schedule
    # schedule_thread = threading.Thread(target=run_schedule)
    # schedule_thread.start()
    try:
        # Запускаем проверку уведомлений при запуске программы
        schedule_notifications()
        bot.infinity_polling(none_stop=True, timeout=15, long_polling_timeout = 5)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
    
if __name__ == '__main__':
    # Запускаем планировщик
    scheduler.start()
    main()
