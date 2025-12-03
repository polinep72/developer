import pandas as pd
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from datetime import datetime, timedelta
import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import time
import schedule
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import plotly.express as px
import io
from PIL import Image


# find the .env file and load it 
load_dotenv(find_dotenv())
# access environment variable 
token = getenv("TELEGRAM_BOT_TOKEN")

# Инициализация бота
bot = telebot.TeleBot(token)

# Создаём планировщик
scheduler = BackgroundScheduler()
# Глобальная блокировка и флаг для предотвращения одновременных запусков schedule_notifications
schedule_lock = threading.Lock()
is_scheduling = False  # Флаг выполнения функции

# Устанавливаем ID администратора
ADMIN_ID = getenv("ADMIN_ID")

# Функция Help
###################################################################################    
@bot.message_handler(commands=['help'])
def handle_message(message):
    bot.reply_to(message, "Команды бота:\n"
        "/booking - резервирование оборудования.\n"
        "/cancel - предлагает варианты для удаления резервирования. Отменить можно только резервирование в будущих периодах.\n"
        "/продлить - предлагает варианты для продления резервирования.\n"
        "/finish - окончание работы на зарезервированном оборудовании. По окончании работы на рабочем месте необходимо нажать на эту кнопку для того чтобы освободить время резервирования оборудования. \n"
        "/users - просмотр зарегистрированных пользователей.\n"
        "/allbookings  - просмотр всех резервирований оборудования.\n"
        "/mybookings  - просмотр ваших резервирований оборудования.\n"
        "/workspacebookings - просмотр резервирований по типу оборудования.\n"
        "/datebookings - просмотр всех резервирований оборудования на дату .\n"
        "/help - вывод сообщение справки.\n"
        "/view_equipment - просмотр рабочих мест и оборудования.\n"
        )
###################################################################################

###################################################################################
# Функция для подключения к базе данных и выполнения запросов
def execute_query(query, params=None):
    # find the .env file and load it 
    load_dotenv(find_dotenv())
# access environment variable 
    user = getenv("POSTGRE_USER")
    password = getenv("POSTGRE_PASSWORD")
    dbname = getenv("POSTGRE_DBNAME")
    conn = None
    result = None
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(
            user=user,
            password=password,
            dbname=dbname,
            host='192.168.1.22'
        )
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = cursor.fetchall()  # Получаем все данные из запроса
        cursor.close()
        conn.commit()  # Если нужен commit (например, при записи данных)
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Ошибка при выполнении запроса: {error}")
    finally:
        if conn is not None:
            conn.close()
    return result

def execute_query1(query, params=None, fetch_results=False):
    # find the .env file and load it 
    load_dotenv(find_dotenv())
# access environment variable 
    user = getenv("POSTGRE_USER")
    password = getenv("POSTGRE_PASSWORD")
    dbname = getenv("POSTGRE_DBNAME")
    conn = None
    result = None
    try:
        # Подключение к базе данных
        conn = psycopg2.connect(
            user=user,
            password=password,
            dbname=dbname,
            host='192.168.1.22'
        )
        cursor = conn.cursor()
        cursor.execute(query, params)
        # Если это SELECT-запрос или запрос с ожиданием результата
        if fetch_results:
            result = cursor.fetchall()  # Получаем все данные из запроса
        conn.commit()  # Коммитим транзакцию (если это добавление или изменение данных)
        cursor.close()
        
    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Ошибка при выполнении запроса: {error}")
    finally:
        if conn is not None:
            conn.close()
    return result
###################################################################################

# Оборудование  просмотр и добавление 
###################################################################################
# Просмотр списка оборудования
@bot.message_handler(commands=['view_equipment'])
def view_equipment(message):
    user_id = message.from_user.id
    # Формируем SQL-запрос для получения данных о бронированиях пользователя
    query ='SELECT e.id, e.name_equip FROM equipment e ORDER BY e.id ASC;'
    # Выполняем запрос
    bookings = execute_query(query, (user_id,))   
    if not bookings:
        bot.send_message(message.chat.id, "Нет оборудования :( !")
        return
    # Формируем ответное сообщение для пользователя
    response = "Средства измерений и вспомогательное оборудование:\n"
    for booking in bookings:
        id, name_equip = booking
        response += f"{id}. {name_equip}\n"
    # Отправляем результат пользователю
    
    bot.send_message(message.chat.id, response)
###################################################################################
# Добавление в список оборудования
@bot.message_handler(commands=['add_equipment'])
def add_equipment(message):
    bot.send_message(message.chat.id, "Введите категорию оборудования:")
    bot.register_next_step_handler(message, get_category)
def get_category(message):
    category_name = message.text
    # Проверяем, существует ли категория в таблице `cat`
    query = "SELECT id FROM cat WHERE name_cat = %s"
    params = (category_name,)
    result = execute_query(query, params)
    if result:
        # Категория найдена
        category_id = result[0][0]  # Получаем id категории
    else:
        # Если категория не найдена, добавляем её в таблицу cat
        insert_query = "INSERT INTO cat (name_cat) VALUES (%s) RETURNING id;"
        result = execute_query(insert_query, params)
        if result:
            bot.send_message(message.chat.id, f"Добавлена новая категория '{category_name}'.")
            category_id = result[0][0]
        else:
            bot.send_message(message.chat.id, "Ошибка при добавлении новой категории.")
            return
    # Переходим к запросу названия оборудования
    bot.send_message(message.chat.id, "Введите название оборудования:")
    bot.register_next_step_handler(message, get_name, category_id)
def get_name(message, category_id):
    equipment_name = message.text
    bot.send_message(message.chat.id, "Введите описание оборудования:")
    bot.register_next_step_handler(message, get_note, category_id, equipment_name)
def get_note(message, category_id, equipment_name):
    note = message.text
    # Добавление нового оборудования в таблицу `equipment`
    insert_query = """
    INSERT INTO equipment (category, name_equip, note)
    VALUES (%s, %s, %s)
    RETURNING id;
    """
    params = (category_id, equipment_name, note)
    # Выполняем запрос на добавление оборудования
    new_id = execute_query(insert_query, params)
    if new_id:
        bot.send_message(message.chat.id, "Оборудование успешно добавлено!")
    else:
        bot.send_message(message.chat.id, "Ошибка при добавлении оборудования.")
###################################################################################

# Просмотр бронирований
###################################################################################
# Своих
@bot.message_handler(commands=['mybookings'])
def my_bookings(message):
    user_id = message.from_user.id
    #print(user_id)
    # Формируем SQL-запрос для получения данных о бронированиях пользователя
    query ='SELECT e.name_equip, b.date, b.time_start, b.time_end FROM bookings b JOIN equipment e ON b.equip_id = e.id WHERE b.user_id = %s AND b.cancel = false AND b.finish IS NULL AND now()<=b.time_end  ORDER BY b.date, b.time_start;'
    # Выполняем запрос
    bookings = execute_query(query, (user_id,))
    if not bookings:
        bot.send_message(message.chat.id, "У вас нет активных бронирований.")
        return
    # Формируем ответное сообщение для пользователя
    response = "Ваши бронирования:\n"
    #print(bookings)
    for booking in bookings:
        equip_name, date, time_start, time_end = booking
        response += f"Оборудование: {equip_name} \n"
        response += f"Дата: {date}\nВремя: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}\n\n"
    # Отправляем результат пользователю
    bot.send_message(message.chat.id, response)
###################################################################################
# Всех бронирований
@bot.message_handler(commands=['allbookings'])
def my_bookings(message):
    user_id = message.from_user.id
    #print(user_id)
    # Формируем SQL-запрос для получения данных о бронированиях пользователя
    query ='SELECT e.name_equip, b.date, b.time_start, b.time_end,  u.fi FROM bookings b JOIN equipment e ON b.equip_id = e.id JOIN users u ON b.user_id = u.users_id WHERE b.cancel = false AND b.finish IS NULL AND now()<=b.time_end  ORDER BY b.date, b.time_start;'
    # Выполняем запрос
    bookings = execute_query(query, (user_id,))
    
    if not bookings:
        bot.send_message(message.chat.id, "Нет активных бронирований.")
        return
    # Формируем ответное сообщение для пользователя
    response = "Бронирования:\n"
    #print(bookings)
    for booking in bookings:
        equip_name, date, time_start, time_end,  users_name = booking
        response += f"Оборудование: {equip_name} \n"
        response += f"Пользователь: {users_name} \n"
        response += f"Дата: {date}\nВремя: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}\n\n"
    # Отправляем результат пользователю
    if len(response) > 4095:
            for x in range(0, len(response), 4095):
                bot.send_message(message.chat.id, text=response[x:x+4095])
    else:
            bot.send_message(message.chat.id, text=response)
###################################################################################
# по датам Работает
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
@bot.message_handler(commands=['datebookings'])
def datebookings(message):
    # Отправляем клавиатуру с выбором даты
    keyboard = generate_date_buttons()
    bot.send_message(message.chat.id, "Выберите дату для просмотра бронирований:", reply_markup=keyboard)
# Обработчик выбора даты (обработка callback_query)
@bot.callback_query_handler(func=lambda call: call.data.startswith("date_"))
def callback_date(call):
    selected_date = call.data.split("_")[1]  # Извлекаем дату из callback_data
    #print(selected_date)
    try:
        selected_datetime = datetime.strptime(selected_date, '%d-%m-%Y')
        #print(selected_datetime)
        # SQL-запрос на получение бронирований по выбранной дате
        query = """
            SELECT e.name_equip, b.time_start, b.time_end, u.fi, b.date 
            FROM bookings b 
            JOIN users u ON b.user_id = u.users_id
            JOIN equipment e ON b.equip_id = e.id
            WHERE DATE(b.date) = %s AND b.cancel = false AND b.finish IS NULL
        """
        params = (selected_datetime,)
        bookings = execute_query(query, params)
        if bookings:
            response = f"Бронирования на {selected_date}:\n"
            for booking in bookings:
                #workspace_name = equipment_dict.get(str(booking[0]), "Неизвестное оборудование")
                
                response += f"Оборудование: {booking[0]},\nВремя: {(booking[1]).strftime('%H:%M')} - {(booking[2]).strftime('%H:%M')},\nПользователь: {booking[3]}\n\n"
        else:
            response = f"Нет бронирований на {selected_date}."
        if len(response) > 4095:
            for x in range(0, len(response), 4095):
                bot.send_message(call.message.chat.id, text=response[x:x+4095])
        else:
            bot.send_message(call.message.chat.id, text=response)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка обработки данных: {e}")
###################################################################################
# по оборудованию Работает
@bot.message_handler(commands=['workspacebookings'])
def workspacebookings(message):
    user_id = message.from_user.id
    # Формируем SQL-запрос для получения данных о бронированиях пользователя
    query ='SELECT e.id, e.name_equip FROM equipment e ORDER BY name_equip ASC;'
    # Выполняем запрос
    available_workspaces = execute_query(query, (user_id,))
    if not available_workspaces:
        bot.send_message(message.chat.id, "Нет оборудования :( !")
        return    
    if available_workspaces:
        markup = types.InlineKeyboardMarkup()
        for workspace in available_workspaces:
            workspace_id, workspace_name = workspace
            markup.add(types.InlineKeyboardButton(text=workspace_name, callback_data=f"workspace_{workspace_id}"))
        bot.send_message(message.chat.id, "Выберите рабочее место для просмотра бронирований:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Нет доступного оборудования для бронирования.")

# Обработка выбора рабочего места
@bot.callback_query_handler(func=lambda call: call.data.startswith("workspace_"))
def get_workspace_bookings(call):
    workspace_id = call.data.split("_")[1]  # Получаем ID выбранного рабочего места
    #workspace_name = call.data.split("_")[2] # Получаем Name выбранного рабочего места
    try:
        # Запрос для получения активных и будущих бронирований по выбранному оборудованию
        query = """
            SELECT b.date, b.time_start, b.time_end, u.fi 
            FROM bookings b
            JOIN users u ON b.user_id = u.users_id
            JOIN equipment e ON b.equip_id = e.id
            WHERE b.equip_id = %s AND b.cancel = false AND b.finish IS NULL AND b.time_start > %s
            ORDER BY b.date ASC
        """
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        params = (workspace_id, now)
        user_bookings = execute_query(query, params)
        # Получаем имя оборудования
        equip_query = "SELECT name_equip FROM equipment WHERE id = %s"
        workspace_name = execute_query(equip_query, (workspace_id,))
        workspace_name = workspace_name[0][0] if workspace_name else "Неизвестное оборудование"
        # Формируем ответ с бронированиями
        if user_bookings:
            response = f"Бронирования для оборудования: {workspace_name}\n"
            for booking in user_bookings:
                date, time_start, time_end, fi = booking
                date = date.strftime('%d-%m-%Y')
                response += f"Пользователь: {fi},\nДата: {date},\nВремя: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}\n\n"
        else:
            response = f"Для оборудования {workspace_name} нет активных или будущих бронирований."
        # Отправляем результат пользователю
        bot.send_message(call.message.chat.id, response)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при получении данных: {e}")
###################################################################################

###################################################################################
# Просмотр пользователей
@bot.message_handler(commands=['users'])
def view_users(message):
    user_id = message.from_user.id
    # Формируем SQL-запрос для получения данных о бронированиях пользователя
    query ='SELECT u.users_id, u.fi FROM users u;'
    # Выполняем запрос
    bookings = execute_query(query, (user_id,))
    if not bookings:
        bot.send_message(message.chat.id, "Нет зарегистрированных пользователей :( !")
        return
    # Формируем ответное сообщение для пользователя
    response = "Зарегистрированные пользователи:\n"
    for booking in bookings:
        user_id, fi = booking
        response += f"{fi} \n"
    # Отправляем результат пользователю
    bot.send_message(message.chat.id, response)
###################################################################################

# Начало работы START
###################################################################################
@bot.message_handler(commands=['start'])
def register_user(message):
    # Клавиатура
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton('/help')
    btn2 = types.KeyboardButton('/view_equipment')
    
    btn3 = types.KeyboardButton('/booking')
    btn4 = types.KeyboardButton('/cancel')
    btn5 = types.KeyboardButton('/finish')
    btn6 = types.KeyboardButton('/продлить')
    
    btn7 = types.KeyboardButton('/mybookings')
    btn8 = types.KeyboardButton('/workspacebookings')
    btn9 = types.KeyboardButton('/datebookings')
    
    markup.add(btn1) 
    markup.add(btn2) 
    markup.add(btn3, btn4,  btn5, btn6)
    markup.add(btn7, btn8, btn9)
# Получаем user_id и проверяем, зарегистрирован ли пользователь
    user_id = message.from_user.id

# Проверяем наличие пользователя в базе данных
    check_query = "SELECT * FROM users WHERE users_id = %s"
    user_exists = execute_query(check_query, (user_id,))
    if user_exists:
        # Пользователь уже зарегистрирован
        bot.send_message(message.chat.id, f"С возвращением, {user_exists[0][1]}! Я бот для резервирования оборудования.\n"
                        "Используй /help для получения списка команд.", reply_markup=markup)
    else:
        # Если пользователь не зарегистрирован, просим ввести имя и фамилию
        bot.send_message(message.chat.id, "Пожалуйста, представьтесь, введите своё Имя и Фамилию через пробел.", reply_markup=markup)
        bot.register_next_step_handler(message, process_name)
def register_user(message):
    user_id = message.from_user.id
    # Проверяем, зарегистрирован ли пользователь
    check_query = "SELECT * FROM users WHERE users_id = %s"
    user_exists = execute_query(check_query, (user_id,))
    if user_exists:
        # Пользователь уже зарегистрирован
        bot.send_message(message.chat.id, "С возвращением! Вы уже зарегистрированы.")
    else:
        # Если пользователь не зарегистрирован, просим ввести имя и фамилию
        bot.send_message(message.chat.id, "Пожалуйста, представьтесь, отправьте свое Имя и Фамилию.")
        bot.register_next_step_handler(message, process_name)

def process_name(message):
    try:
        user_id = message.from_user.id
        first_name, last_name = message.text.split(" ", 1)
        date_registered = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        full_initials = f"{first_name} {last_name}"
        
        # Временное сохранение данных пользователя в базе данных
        insert_query = """
        INSERT INTO users_temp (users_id, first_name, last_name, date, fi) 
        VALUES (%s, %s, %s, %s, %s)
        """
        execute_query1(insert_query, (user_id, first_name, last_name, date_registered, full_initials))
        
        # Уведомляем администратора о новой регистрации и добавляем кнопки
        keyboard = InlineKeyboardMarkup()
        confirm_button = InlineKeyboardButton("Подтвердить", callback_data=f"confirm_{user_id}")
        decline_button = InlineKeyboardButton("Отклонить", callback_data=f"decline_{user_id}")
        keyboard.add(confirm_button, decline_button)
        
        bot.send_message(ADMIN_ID, f"Новая регистрация:\nИмя: {first_name}\nФамилия: {last_name}\nЖдет подтверждения.",
                         reply_markup=keyboard)

    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите свое имя и фамилию в правильном формате (Имя Фамилия).")
        bot.register_next_step_handler(message, process_name)

# Обработчик для нажатия кнопок подтверждения и отклонения
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_") or call.data.startswith("decline_"))
def handle_confirmation(call):
    user_id = int(call.data.split("_")[1])
    
    if call.data.startswith("confirm_"):
        # Переносим данные из временной таблицы в основную
        confirm_query = "SELECT * FROM users_temp WHERE users_id = %s"
        user_temp = execute_query(confirm_query, (user_id,))
        
        if user_temp:
            final_query = """
            INSERT INTO users (users_id, first_name, last_name, date, fi) 
            VALUES (%s, %s, %s, %s, %s)
            """
            execute_query1(final_query, (user_temp[0][0], user_temp[0][1],
                                         user_temp[0][2], user_temp[0][3], user_temp[0][4]))
            
            # Удаляем временные данные
            delete_temp_query = "DELETE FROM users_temp WHERE users_id = %s"
            execute_query1(delete_temp_query, (user_id,))
            
            bot.send_message(ADMIN_ID, f"Пользователь с ID {user_id} успешно зарегистрирован.")
            bot.send_message(user_id, f"{(user_temp[0][1])} вы успешно зарегистрировались.")
        else:
            bot.send_message(ADMIN_ID, f"Не найден временный пользователь с ID {user_id}.")
        
    elif call.data.startswith("decline_"):
        # Удаляем временные данные о пользователе
        delete_temp_query = "DELETE FROM users_temp WHERE users_id = %s"
        execute_query1(delete_temp_query, (user_id,))
        
        bot.send_message(ADMIN_ID, f"Регистрация пользователя с ID {user_id} отклонена.")

    # Уведомление о завершении обработки
    bot.answer_callback_query(call.id, "Обработка завершена.")
###################################################################################

###################################################################################
# Бронирование рабочего места
# Начало бронирования - выбор категории оборудования
@bot.message_handler(commands=['booking'])
def start_booking(message):
    user_id = message.from_user.id

    # Проверяем, зарегистрирован ли пользователь
    query_check_user = "SELECT COUNT(*) FROM users WHERE users_id = %s"
    user_exists = execute_query(query_check_user, (user_id,))[0][0]

    if not user_exists:
        # Если пользователя нет в БД, отправляем сообщение с инструкцией
        bot.send_message(
            message.chat.id,
            "Вы не зарегистрированы в системе. Пожалуйста, выполните команду /start для регистрации."
        )
        return  # Прекращаем выполнение функции

    query = "SELECT id, name_cat FROM cat ORDER BY name_cat ASC"
    categories = execute_query(query)
    markup = types.InlineKeyboardMarkup()
    for category_id, name_cat in categories:
        markup.add(types.InlineKeyboardButton(text=name_cat, callback_data=f"category1_{category_id}"))
    bot.send_message(message.chat.id, "Выберите категорию оборудования:", reply_markup=markup)
# Обработчик выбора категории
@bot.callback_query_handler(func=lambda call: call.data.startswith("category1_"))
def choose_equipment(call):
    category_id = call.data.split("_")[1]
    query = "SELECT id, name_equip FROM equipment WHERE category = %s"
    equipment = execute_query(query, (category_id,))
    markup = types.InlineKeyboardMarkup()
    for equipment_id, name_equip in equipment:
        markup.add(types.InlineKeyboardButton(text=name_equip, callback_data=f"equipment1_{equipment_id}"))
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
    time = datetime.strptime('07:00', '%H:%M')
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
    user_id = call.from_user.id
    data_booking=datetime.now()
    data = call.data.split("_")
    duration_str = data[1]
    start_time = data[2]
    selected_date = data[3]
    equipment_id = data[4]
    start_datetime = datetime.strptime(f"{selected_date} {start_time}", '%d-%m-%Y %H:%M')
    duration_hours, duration_minutes = map(int, duration_str.split(":"))
    duration_timedelta = timedelta(hours=duration_hours, minutes=duration_minutes)
    end_datetime = start_datetime + duration_timedelta
    # Проверка пересечений по времени
    query = """
        SELECT b.time_start, b.time_end, u.first_name, u.last_name
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        WHERE b.equip_id = %s AND
        b.cancel = FALSE AND
        b.time_start < %s AND
        b.time_end > %s
        AND finish  IS NULL;
    """
    conflicts = execute_query(query, (equipment_id, end_datetime, start_datetime))
    if conflicts:
        for conflict_start, conflict_end, first_name, last_name in conflicts:
            bot.send_message(
                call.message.chat.id,
                f"Пересечение по времени с бронированием пользователя {first_name} {last_name} на {conflict_start} - {conflict_end}"
            )
        return
    # Сохранение бронирования
    time_interval = f"{start_datetime.strftime('%H:%M')}-{end_datetime.strftime('%H:%M')}"
    duration = duration_timedelta.total_seconds() / 3600
    insert_query = """
        INSERT INTO bookings (user_id, equip_id, date, time_start, time_end, time_interval, duration, cancel, extension, finish, data_booking)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, NULL, %s)
    """
    execute_query1(insert_query, (user_id, equipment_id, selected_date, start_datetime, end_datetime, time_interval, duration, data_booking))
    schedule_notifications()
    bot.send_message(call.message.chat.id, "Ваше бронирование успешно сохранено.")

###################################################################################
# # Команда /cancel
@bot.message_handler(commands=['cancel'])
def cancel_booking(message):
    user_id = int(message.from_user.id)
    # Определяем текущую дату без времени для фильтрации будущих бронирований
    now = datetime.now()#.replace(hour=0, minute=0, second=0, microsecond=0)
    # Запрашиваем активные бронирования пользователя из базы данных
    query = """
    SELECT b.id, b.equip_id, b.date, b.time_start, b.time_end, e.name_equip AS name
    FROM bookings b
    JOIN equipment e ON b.equip_id = e.id
    WHERE b.user_id = %s AND b.cancel = FALSE AND b.finish IS NULL 
            AND b.time_start > %s;
    """
    user_bookings = execute_query1(query, (user_id, now), fetch_results=True)
    # Если нет активных бронирований, сообщаем об этом пользователю
    if not user_bookings:
        bot.send_message(message.chat.id, "У вас нет бронирований для отмены.")
        return
    # Создаем клавиатуру для выбора бронирования
    markup = types.InlineKeyboardMarkup()
    for booking in user_bookings:
        booking_id, workspace_id, date, time_start, time_end, equipment_name = booking
        button_text = f"{equipment_name}  Дата: {date.strftime('%d-%m-%Y')}  Время: {time_start.strftime('%H:%M')}-{time_end.strftime('%H:%M')}"
        callback_data = f"cancel_booking_{booking_id}"  # Используем ID бронирования для идентификации
        markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
    bot.send_message(message.chat.id, "Выберите бронирование для отмены:", reply_markup=markup)
# Обработка выбора бронирования для отмены
@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_booking_"))
def confirm_cancel_booking(call):
    booking_id = int(call.data.split("_")[2])
    # Проверяем, что бронирование существует и не отменено
    query_check = "SELECT cancel FROM bookings WHERE id = %s;"
    booking_status = execute_query1(query_check, (booking_id,), fetch_results=True)
    if booking_status and booking_status[0][0] is True:  # Если бронирование уже отменено
        bot.send_message(call.message.chat.id, "Это бронирование уже было отменено.")
        return
    # Обновляем статус отмены в базе данных
    query_update = "UPDATE bookings SET cancel = TRUE WHERE id = %s;"
    execute_query1(query_update, (booking_id,))
    # Перепланируем уведомления, если необходимо
    schedule_notifications()
    bot.send_message(call.message.chat.id, "Бронирование успешно отменено.")
###################################################################################

###################################################################################
# Функция для завершения работы и записи времени в столбец finish
def finish_work(booking_id, chat_id, workspace_name):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Текущее время
# Обновляем поле `finish` в базе данных
    query = """
    UPDATE bookings
    SET finish = %s
    WHERE id = %s;
    """
    execute_query1(query, (now, booking_id))
    bot.send_message(chat_id, f"Ваше бронирование оборудования {workspace_name} завершено в {now}.")

@bot.message_handler(commands=['finish'])
def finish_booking(message):
    user_id = int(message.from_user.id)
    now = datetime.now()
    # Запрос для получения активных бронирований пользователя
    query = """
    SELECT b.id, b.equip_id, b.time_start, b.time_end, e.name_equip AS workspace_name
    FROM bookings b
    JOIN equipment e ON b.equip_id = e.id
    WHERE b.user_id = %s AND b.cancel = FALSE AND b.finish IS NULL;
    """
    active_bookings = execute_query1(query, (user_id,), fetch_results=True)
    # Проверяем наличие активных бронирований
    if not active_bookings:
        bot.send_message(message.chat.id, "У вас нет активных бронирований для завершения.")
        return
    # Фильтрация бронирований по текущему времени
    ongoing_bookings = [
        booking for booking in active_bookings
        if booking[2] <= now <= booking[3]  # time_start <= now <= time_end
    ]
    # Проверяем, есть ли бронирования в текущем временном интервале
    if not ongoing_bookings:
        bot.send_message(message.chat.id, "Вы не находитесь в забронированном временном интервале.")
        return
    # Если у пользователя несколько активных бронирований, создаём клавиатуру выбора
    if len(ongoing_bookings) > 1:
        markup = types.InlineKeyboardMarkup()
        for booking in ongoing_bookings:
            booking_id, workspace_id, time_start, time_end, workspace_name = booking
            button_text = f"{workspace_name} Время: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}"
            callback_data = f"finish_{booking_id}"
            markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
        bot.send_message(message.chat.id, "Выберите рабочее место для завершения:", reply_markup=markup)
    else:
        # Если одно бронирование, завершаем работу
        booking_id, workspace_id, time_start, time_end, workspace_name = ongoing_bookings[0]
        schedule_notifications()  # Перепланируем уведомления при необходимости
        finish_work(booking_id, message.chat.id, workspace_name)

# Обработка выбора рабочего места для завершения работы
@bot.callback_query_handler(func=lambda call: call.data.startswith("finish_"))
def finish_selected_booking(call):
    booking_id = int(call.data.split("_")[1])
    # Проверяем существование бронирования и его статус
    query = """
    SELECT b.equip_id, e.name_equip AS workspace_name
    FROM bookings b
    JOIN equipment e ON b.equip_id = e.id
    WHERE b.id = %s AND b.cancel = FALSE AND b.finish IS NULL;
    """
    booking_info = execute_query1(query, (booking_id,), fetch_results=True)
    if not booking_info:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено или уже завершено.")
        return
    # Завершаем бронирование
    workspace_id, workspace_name = booking_info[0]
    schedule_notifications()  # Перепланируем уведомления при необходимости
    finish_work(booking_id, call.message.chat.id, workspace_name)

###################################################################################
# Функция для продления бронирования
@bot.message_handler(commands=['продлить'])
def extend_booking(message):
    user_id = message.from_user.id
    now = datetime.now()
    # Запрос для получения активных бронирований пользователя
    query = """
    SELECT b.id, b.equip_id, b.time_start, b.time_end, e.name_equip AS workspace_name
    FROM bookings b
    JOIN equipment e ON b.equip_id = e.id
    WHERE b.user_id = %s AND b.cancel = FALSE AND b.finish IS NULL AND time_start <= now() AND now() <= time_end;
    """
    active_bookings = execute_query1(query, (user_id,), fetch_results=True)
    if not active_bookings:
        bot.send_message(message.chat.id, "Вы не находитесь в активном рабочем времени для продления.")
        return

    # Если несколько активных бронирований, предлагаем выбрать рабочее место
    if len(active_bookings) > 1:
        markup = types.InlineKeyboardMarkup()
        for booking in active_bookings:
            booking_id, workspace_id, time_start, time_end, workspace_name = booking
            button_text = f"{workspace_name} Время: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}"
            callback_data = f"extend_{booking_id}"
            markup.add(types.InlineKeyboardButton(text=button_text, callback_data=callback_data))
        bot.send_message(message.chat.id, "Выберите рабочее место для продления:", reply_markup=markup)
    else:
        # Если одно бронирование, сразу предлагаем продление
        booking_id, workspace_id, time_start, time_end, workspace_name = active_bookings[0]
        extend_booking_for_workspace(booking_id, message.chat.id)

# Обработка выбора рабочего места для продления
@bot.callback_query_handler(func=lambda call: call.data.startswith("extend_"))
def extend_selected_booking(call):
    booking_id = int(call.data.split("_")[1])
    extend_booking_for_workspace(booking_id, call.message.chat.id)
# Функция для выбора времени продления
def extend_booking_for_workspace(booking_id, chat_id):
    markup = types.InlineKeyboardMarkup()
    time_intervals = [(i * 30) for i in range(1, 17)]  # 00:30 до 08:00 с шагом 30 минут
    for minutes in time_intervals:
        hours, mins = divmod(minutes, 60)
        extension = f"{hours:02d}:{mins:02d}"
        callback_data = f"confirm_extend_{booking_id}_{extension}"
        markup.add(types.InlineKeyboardButton(text=f"{extension}", callback_data=callback_data))
    bot.send_message(chat_id, "Выберите время для продления:", reply_markup=markup)
# Обработка подтверждения продления
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_extend_"))
def confirm_extension(call):
    booking_id = int(call.data.split("_")[2])
    extension = call.data.split("_")[3]
    #_, _, booking_id, extension = call.data.split("_")
    booking_id = int(booking_id)
    user_id = call.from_user.id

    # Извлекаем бронирование, которое нужно продлить
    query = """
    SELECT time_end, equip_id FROM bookings
    WHERE id = %s AND user_id = %s AND cancel = FALSE AND finish IS NULL;
    """
    result = execute_query1(query, (booking_id, user_id), fetch_results=True)

    if not result:
        bot.send_message(call.message.chat.id, "Ошибка: бронирование не найдено или уже завершено.")
        return

    time_end, workspace_id = result[0]
    hours, minutes = map(int, extension.split(":"))
    new_end_time = time_end + timedelta(hours=hours, minutes=minutes)

        # Проверка пересечений по времени
    query = """
        SELECT b.time_start, b.time_end, u.first_name, u.last_name
        FROM bookings b
        JOIN users u ON b.user_id = u.users_id
        WHERE b.equip_id = %s 
        AND b.cancel = FALSE 
        AND b.time_start < %s
        AND b.time_end > %s
        AND finish IS NULL;
    """
    conflicts = execute_query(query, (workspace_id, new_end_time, time_end))
    if conflicts:
        for conflict_start, conflict_end, first_name, last_name in conflicts:
            response = "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! \n"
            response += f"Пересечение по времени с бронированием пользователя {first_name} {last_name} на {conflict_start} - {conflict_end}"
        return bot.send_message(call.message.chat.id, response)
    # Обновление времени окончания в бронировании
    update_query = """
    UPDATE bookings
    SET time_end = %s 
    WHERE id = %s;
    """
    execute_query1(update_query, (new_end_time, booking_id))
# Внесение данных о продлении в бронирование
    update_query = """
    UPDATE bookings
    SET extension=%s 
    WHERE id = %s;
    """
    execute_query1(update_query, (extension, booking_id))   
    # Обновляем задачу завершения бронирования
    schedule_notifications()
    bot.send_message(call.message.chat.id, f"Ваше бронирование продлено до {new_end_time.strftime('%H:%M')}.")
###################################################################################

###################################################################################
# Функция для отправки уведомления
def send_notification(user_id, message_text):
    bot.send_message(user_id, message_text)

# Функция планирования уведомлений на основе данных из БД
def schedule_notifications():
    # Очищаем все задачи в планировщике
    scheduler.remove_all_jobs()
    # Очистка отслеживания отправленных уведомлений
    sent_notifications['start'].clear()
    sent_notifications['end'].clear()
    clean_up_notifications()
    now = datetime.now()
    # Запрос бронирований с учетом времени продления
    query = """SELECT b.id, b.user_id, b.equip_id, b.date, b.time_start, b.time_end, b.extension, e.name_equip AS equipment_name FROM bookings b JOIN equipment e ON b.equip_id = e.id WHERE b.cancel = false AND b.finish IS NULL AND b.date >= now()::date - interval '1h'"""
    bookings_df = execute_query1(query, fetch_results=True)
    bookings_df=pd.DataFrame(list(bookings_df))
    bookings_df = bookings_df.rename(columns={0:'id', 1:'user_id', 2:'workspace_id', 3:'date', 4:'time_start', 5:'time_end', 6:'extension', 7:'name'})
    for index, booking in bookings_df.iterrows():
        #if booking['cancel'] == 0 and pd.isna(booking['finish']):
            start_time = pd.to_datetime(booking['time_start'], format='%Y-%m-%d %H:%M:%S')
            end_time = pd.to_datetime(booking['time_end'], format='%Y-%m-%d %H:%M:%S')
            #Преобразуем extension в timedelta, если оно не пустое
            extension = pd.to_datetime(booking['extension'], format='%H:%M:%S')
            extension = timedelta(
                hours=extension.hour, 
                minutes=extension.minute, 
                seconds=extension.second
            ) if extension else timedelta(0)
            # Добавляем продление к времени окончания
            end_time = end_time + extension
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

# Функция очистки уведомлений для завершенных, отмененных и просроченных бронирований
def clean_up_notifications():
    now = datetime.now()
    # Получаем список завершенных, отмененных или просроченных бронирований
    query = """
    SELECT id FROM bookings 
    WHERE cancel = TRUE OR finish IS NOT NULL OR time_start < %s
    """
    completed_bookings = execute_query1(query, (now,), fetch_results=True)
    for booking in completed_bookings:
        booking_id = booking[0]
        # Проверяем наличие и удаляем задачи начала
        start_job_id = f"start_{booking_id}"
        if scheduler.get_job(start_job_id):
            scheduler.remove_job(start_job_id)
            sent_notifications['start'].discard(start_job_id)
            print(f"Удалено уведомление о начале: {start_job_id}")
    
    query = """
    SELECT id FROM bookings 
    WHERE cancel = TRUE OR finish IS NOT NULL OR time_end < %s
    """
    completed_bookings = execute_query1(query, (now,), fetch_results=True)
    for booking in completed_bookings:
        booking_id = booking[0]
        # Проверяем наличие и удаляем задачи окончания
        end_job_id = f"end_{booking_id}"
        if scheduler.get_job(end_job_id):
            scheduler.remove_job(end_job_id)
            sent_notifications['end'].discard(end_job_id)
            print(f"Удалено уведомление о завершении: {end_job_id}")

###################################################################################
# Просмотр пользователей
@bot.message_handler(commands=['schedule'])
def view_users(message):
    schedule_notifications()
    print(scheduler.get_jobs, sent_notifications)
    bot.send_message(message.chat.id, "График обновлен")
###################################################################################

###################################################################################
# Обработчик команды для просмотра всех бронирований
@bot.message_handler(commands=['all'])
def all_bookings(message):
    # Создаем кнопки для выбора параметра фильтрации
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Пользователи", callback_data="filter_users"))
    markup.add(InlineKeyboardButton("Оборудование", callback_data="filter_equipment"))
    markup.add(InlineKeyboardButton("Даты (месяц)", callback_data="filter_dates"))

    # Сообщение с кнопками
    bot.send_message(message.chat.id, "Выберите параметр для фильтрации бронирований:", reply_markup=markup)

# Обработчик нажатий на кнопки фильтрации
@bot.callback_query_handler(func=lambda call: call.data.startswith("filter_"))
def filter_selection(call):
    selection = call.data.split("_")[1]

    # В зависимости от выбора пользователя предлагаем варианты
    if selection == "users":
        query = "SELECT DISTINCT u.fi, u.users_id FROM users u JOIN bookings b ON u.users_id = b.user_id"
        options = execute_query(query)
        markup = InlineKeyboardMarkup()
        for user_name, user_id in options:
            markup.add(InlineKeyboardButton(user_name, callback_data=f"user2_{user_id}"))
        bot.send_message(call.message.chat.id, "Выберите пользователя:", reply_markup=markup)

    elif selection == "equipment":
        query = "SELECT DISTINCT name_equip, id FROM equipment"
        options = execute_query(query)
        markup = InlineKeyboardMarkup()
        for equip_name, equip_id in options:
            markup.add(InlineKeyboardButton(equip_name, callback_data=f"equipment2_{equip_id}"))
        bot.send_message(call.message.chat.id, "Выберите оборудование:", reply_markup=markup)

    elif selection == "dates":
        query = "SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month FROM bookings ORDER BY month DESC"
        options = execute_query(query)
        markup = InlineKeyboardMarkup()
        for (month,) in options:
            markup.add(InlineKeyboardButton(month, callback_data=f"date2_{month}"))
        bot.send_message(call.message.chat.id, "Выберите месяц:", reply_markup=markup)

# Обработчик нажатия на выбранный параметр
@bot.callback_query_handler(func=lambda call: call.data.startswith(("user2_", "equipment2_", "date2_")))
def show_filtered_bookings(call):
    filter_type, filter_value = call.data.split("_")
    user_id = call.from_user.id

    # Формирование SQL-запроса в зависимости от выбранного параметра фильтрации
    if filter_type == "user2":
        query = '''
            SELECT e.name_equip, b.date, b.time_start, b.time_end, u.fi 
            FROM bookings b 
            JOIN equipment e ON b.equip_id = e.id 
            JOIN users u ON b.user_id = u.users_id 
            WHERE u.users_id = %s 
            ORDER BY b.date, b.time_start;
        '''
        params = (filter_value,)

    elif filter_type == "equipment2":
        query = '''
            SELECT e.name_equip, b.date, b.time_start, b.time_end, u.fi 
            FROM bookings b 
            JOIN equipment e ON b.equip_id = e.id 
            JOIN users u ON b.user_id = u.users_id 
            WHERE e.id = %s 
            ORDER BY b.date, b.time_start;
        '''
        params = (filter_value,)

    elif filter_type == "date2":
        query = "SELECT e.name_equip, b.date, b.time_start, b.time_end, u.fi FROM bookings b JOIN equipment e ON b.equip_id = e.id JOIN users u ON b.user_id = u.users_id WHERE TO_CHAR(b.date, 'YYYY-MM') = '" + filter_value + "'ORDER BY b.date, b.time_start;"
        params = (filter_value,)

    # Выполнение запроса
    bookings = execute_query(query, params)
    # Проверка наличия бронирований
    if not bookings:
        bot.send_message(call.message.chat.id, "Нет бронирований по выбранному фильтру.")
        return

    # Формирование строки для записи в текстовый файл
    file_content = "Бронирования:\n"
    for booking in bookings:
        equip_name, date, time_start, time_end, user_name = booking
        date_formatted = date.strftime('%d-%m-%Y') if isinstance(date, datetime) else date
        file_content += f"Оборудование: {equip_name}\n"
        file_content += f"Пользователь: {user_name}\n"
        file_content += f"Дата: {date_formatted}\n"
        file_content += f"Время: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}\n\n"

    # Сохранение данных в текстовый файл
    file_path = "bookings.txt"
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(file_content)
    response = "Файл подготовлен:\n"
    bot.send_message(call.message.chat.id, text=response)
    # Отправка текстового файла пользователю
    with open(file_path, "rb") as file:
        bot.send_document(call.message.chat.id, file)
    
    # Удаление файла после отправки
    os.remove(file_path)

    # response = "Бронирования:\n"
    # for booking in bookings:
    #     equip_name, date, time_start, time_end, user_name = booking
    #     # Преобразование даты из строки в нужный формат
    #     date_formatted = date.strftime('%d-%m-%Y') if isinstance(date, datetime) else date
    #     response += f"Оборудование: {equip_name}\n"
    #     response += f"Пользователь: {user_name}\n"
    #     response += f"Дата: {date_formatted}\nВремя: {time_start.strftime('%H:%M')} - {time_end.strftime('%H:%M')}\n\n"

    # # Отправляем результат пользователю
    # if len(response) > 4095:
    #     for x in range(0, len(response), 4095):
    #         bot.send_message(call.message.chat.id, text=response[x:x+4095])
    # else:
    #     bot.send_message(call.message.chat.id, text=response)
###################################################################################

# Запуск бота
def main():
    try:
        # Запускаем проверку уведомлений при запуске программы
        schedule_notifications()
        bot.infinity_polling(none_stop=True, timeout=15, long_polling_timeout=5)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        time.sleep(5)  # Ждем перед перезапуском

if __name__ == '__main__':
    # Глобальный словарь для отслеживания отправленных уведомлений
    sent_notifications = {
        'start': set(),  # Уникальные ключи для уведомлений о начале
        'end': set()      # Уникальные ключи для уведомлений о завершении
    }
    # Запускаем планировщик
    scheduler.start()
    main()