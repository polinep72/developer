import telebot
import pandas as pd
import psycopg2
from contextlib import closing
from os import getenv
from dotenv import load_dotenv, find_dotenv
import os

# find the .env file and load it 
load_dotenv(find_dotenv())
# Получить параметры подключения из переменных окружения
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")
db_host = os.getenv("DB_HOST")

# access environment variable 
token = getenv("TELEGRAM_BOT_TOKEN")

# Инициализация бота
bot = telebot.TeleBot(token)


# Функция для обработки команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "Привет! Я бот для поиска кристаллов.\n"
        "Введите полное название кристалла 'W0.130.0' или частичное '130'"
    )
    bot.reply_to(message, welcome_text)
# Функция обработки SQL
@bot.message_handler(content_types=['text'])
def get_crystal_count(message):
    crystal_name = message.text.strip()
    
    with closing(psycopg2.connect(user=db_user, password=db_password, 
                    dbname=db_name, host=db_host)) as conn:
        with conn.cursor() as cursor:
            # Изменённый запрос с использованием LIKE и подстановочных символов
            query = """
                SELECT name_chip, SUM(ostatok)
                FROM (
                    SELECT * 
                    FROM (
                        SELECT * 
                        FROM (
                            SELECT c.name_chip, 
                                (COALESCE(i.quantity, 0) - COALESCE(SUM(cm.consumption), 0)) AS ostatok
                            FROM invoice i
                            LEFT OUTER JOIN consumption cm ON cm.item_id = i.item_id
                            LEFT JOIN start_p s ON s.id = i.id_start
                            LEFT JOIN tech t ON t.id = i.id_tech
                            LEFT JOIN chip c ON c.id = i.id_chip
                            LEFT JOIN lot l ON l.id = i.id_lot
                            LEFT JOIN wafer w ON w.id = i.id_wafer
                            LEFT JOIN pr p ON p.id = i.id_pr
                            LEFT JOIN quad q ON q.id = i.id_quad
                            LEFT JOIN n_chip nc ON nc.id = i.id_n_chip
                            LEFT JOIN pack pk ON pk.id = i.id_pack
                            LEFT JOIN cells cs ON cs.id = i.id_cells
                            LEFT JOIN in_lot il ON il.id = i.id_in_lot
                            GROUP BY s.name_start, t.name_tech, c.name_chip, l.name_lot, w.name_wafer, i.quantity, p.name_pr, q.name_quad, il.in_lot, c.name_chip, pk.name_pack, cs.name_cells
                        ) AS t
                        WHERE ostatok > 0
                    ) AS C 
                    WHERE c.name_chip LIKE %s
                ) AS P 
                GROUP BY name_chip
            """
            # Добавляем символы подстановки % для частичного поиска
            cursor.execute(query, ('%' + crystal_name + '%',))
            result = cursor.fetchall()

            if result:
                response_text = ""
                for row in result:
                    response_text += f"Кристалл: {row[0]}, Остаток: {row[1]}\n"
                bot.reply_to(message, response_text)
            else:
                bot.reply_to(message, "К сожалению, кристалл не найден или остаток равен 0.")

# Запуск бота
bot.infinity_polling(none_stop=True, timeout=10, long_polling_timeout = 5)