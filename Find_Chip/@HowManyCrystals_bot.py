import telebot
import pandas as pd
import psycopg2
from psycopg2 import sql
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
def fetch_stock(cursor, crystal_name, invoice_table, consumption_table):
    """Возвращает словарь {name_chip: остаток} для выбранного склада."""
    query = sql.SQL(
        """
        SELECT name_chip, SUM(ostatok) AS total_ostatok
        FROM (
            SELECT c.name_chip,
                   (COALESCE(i.quantity, 0) - COALESCE(SUM(cm.consumption), 0)) AS ostatok
            FROM {invoice} i
            LEFT OUTER JOIN {consumption} cm ON cm.item_id = i.item_id
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
            GROUP BY s.name_start, t.name_tech, c.name_chip, l.name_lot, w.name_wafer, i.quantity, p.name_pr, q.name_quad, il.in_lot, pk.name_pack, cs.name_cells
        ) AS stock
        WHERE stock.ostatok > 0 AND stock.name_chip LIKE %s
        GROUP BY stock.name_chip
        """
    ).format(
        invoice=sql.Identifier(invoice_table),
        consumption=sql.Identifier(consumption_table),
    )

    cursor.execute(query, (f"%{crystal_name}%",))
    return {row[0]: row[1] for row in cursor.fetchall()}


def build_response(crystal_name, stocks_main, stocks_plate, stocks_far):
    names = set(stocks_main.keys()) | set(stocks_plate.keys()) | set(stocks_far.keys())
    if not names:
        return "К сожалению, кристалл не найден или остаток равен 0."

    lines = []
    separator = "---------------"
    for name in names:
        lines.append(f"Кристалл: {name}")
        lines.append("На складе.")
        lines.append(f"Остаток: {stocks_main.get(name, 0)} шт.")
        lines.append(separator)
        lines.append("На складе в пластинах неразделенных.")
        lines.append(f"Остаток: {stocks_plate.get(name, 0)} шт.")
        lines.append(separator)
        lines.append("На дальнем складе.")
        lines.append(f"Остаток: {stocks_far.get(name, 0)} шт.")
        lines.append("")  # разделяем записи по кристаллам пустой строкой

    return "\n".join(lines).strip()


# Функция обработки SQL
@bot.message_handler(content_types=['text'])
def get_crystal_count(message):
    crystal_name = message.text.strip()

    with closing(
        psycopg2.connect(
            user=db_user, password=db_password, dbname=db_name, host=db_host
        )
    ) as conn:
        with conn.cursor() as cursor:
            stocks_main = fetch_stock(cursor, crystal_name, "invoice", "consumption")
            stocks_plate = fetch_stock(cursor, crystal_name, "invoice_p", "consumption_p")
            stocks_far = fetch_stock(cursor, crystal_name, "invoice_f", "consumption_f")

            response_text = build_response(crystal_name, stocks_main, stocks_plate, stocks_far)
            bot.reply_to(message, response_text)

# Запуск бота
bot.infinity_polling(none_stop=True, timeout=30, long_polling_timeout = 5)