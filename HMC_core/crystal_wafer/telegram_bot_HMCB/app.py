import telebot
import psycopg2
from contextlib import closing # Для with closing(...)
from os import getenv
from dotenv import load_dotenv, find_dotenv
import os # Уже импортирован

# Загрузка переменных окружения
load_dotenv(find_dotenv())

# Параметры подключения к БД
DB_USER = getenv("DB_USER")
DB_PASSWORD = getenv("DB_PASSWORD")
DB_NAME = getenv("DB_NAME")
DB_HOST = getenv("DB_HOST")

# Токен телеграм-бота
TELEGRAM_BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("Ошибка: TELEGRAM_BOT_TOKEN не найден в .env файле.")
    exit()
if not all([DB_USER, DB_PASSWORD, DB_NAME, DB_HOST]):
    print("Ошибка: Не все параметры подключения к БД найдены в .env файле.")
    exit()


# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "Привет! Я бот для поиска остатков кристаллов.\n"
        "Введите полный шифр кристалла (например, HJB313) или его часть (например, 313)."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(content_types=['text'])
def get_crystal_stock(message):
    crystal_name_filter = message.text.strip()

    if not crystal_name_filter:
        bot.reply_to(message, "Пожалуйста, введите шифр кристалла для поиска.")
        return

    # SQL-запрос, адаптированный из логики инвентаризации
    # Агрегируем по n_chip.n_chip
    query = """
    WITH
    income_agg AS (
        SELECT
            inv.id_n_chip,
            SUM(inv.quan_w) as total_income_w,
            SUM(inv.quan_gp) as total_income_gp
        FROM invoice inv
        WHERE COALESCE(inv.note, '') != 'возврат'
        GROUP BY inv.id_n_chip
    ),
    return_agg AS (
        SELECT
            inv.id_n_chip,
            SUM(inv.quan_w) as total_return_w,
            SUM(inv.quan_gp) as total_return_gp
        FROM invoice inv
        WHERE inv.note = 'возврат'
        GROUP BY inv.id_n_chip
    ),
    consumption_agg AS (
        SELECT
            cons.id_n_chip,
            SUM(cons.cons_w) as total_consumed_w,
            SUM(cons.cons_gp) as total_consumed_gp
        FROM consumption cons
        GROUP BY cons.id_n_chip
    ),
    all_chips_with_ops AS ( -- Собираем все id_n_chip, по которым были операции
        SELECT id_n_chip FROM invoice
        UNION
        SELECT id_n_chip FROM consumption
    )
    SELECT
        nc.n_chip AS "Шифр_кристалла",
        -- Расчет остатков Wafer
        (COALESCE(ia.total_income_w, 0) + COALESCE(ra.total_return_w, 0) - COALESCE(ca.total_consumed_w, 0)) AS "Остаток_Wafer",
        -- Расчет остатков GelPak
        (COALESCE(ia.total_income_gp, 0) + COALESCE(ra.total_return_gp, 0) - COALESCE(ca.total_consumed_gp, 0)) AS "Остаток_GelPak"
    FROM
        all_chips_with_ops acwo
    JOIN n_chip nc ON acwo.id_n_chip = nc.id -- Присоединяем n_chip для получения имени и фильтрации
    LEFT JOIN income_agg ia ON acwo.id_n_chip = ia.id_n_chip
    LEFT JOIN return_agg ra ON acwo.id_n_chip = ra.id_n_chip
    LEFT JOIN consumption_agg ca ON acwo.id_n_chip = ca.id_n_chip
    WHERE nc.n_chip ILIKE %s -- Фильтр по шифру кристалла
    ORDER BY nc.n_chip;
    """

    try:
        with closing(psycopg2.connect(user=DB_USER, password=DB_PASSWORD,
                                      dbname=DB_NAME, host=DB_HOST)) as conn:
            with conn.cursor() as cursor:
                # Добавляем символы подстановки % для частичного поиска
                cursor.execute(query, ('%' + crystal_name_filter + '%',))
                results = cursor.fetchall()

                if results:
                    response_text = ""
                    for row in results:
                        chip_code = row[0]
                        stock_wafer = row[1]
                        stock_gelpak = row[2]
                        # Показываем только если есть какой-либо остаток
                        if stock_wafer > 0 or stock_gelpak > 0:
                            response_text += f"Шифр: {chip_code}\n"
                            response_text += f"  Остаток Wafer: {stock_wafer if stock_wafer is not None else 0} шт.\n"
                            response_text += f"  Остаток GelPak: {stock_gelpak if stock_gelpak is not None else 0} шт.\n\n"
                    
                    if response_text:
                        bot.reply_to(message, response_text)
                    else:
                        bot.reply_to(message, "Кристаллы найдены, но остаток по ним равен 0 (Wafer и GelPak).")
                else:
                    bot.reply_to(message, f"Кристаллы с шифром, содержащим '{crystal_name_filter}', не найдены или по ним нет операций.")
    
    except psycopg2.Error as db_err:
        print(f"Ошибка базы данных в телеграм-боте: {db_err}")
        bot.reply_to(message, "Произошла ошибка при доступе к базе данных. Попробуйте позже.")
    except Exception as e:
        print(f"Непредвиденная ошибка в телеграм-боте: {e}")
        bot.reply_to(message, "Произошла непредвиденная ошибка. Пожалуйста, сообщите администратору.")


if __name__ == '__main__':
    print("Телеграм-бот запускается...")
    try:
        bot.infinity_polling(none_stop=True, timeout=30, long_polling_timeout=5)
    except Exception as e:
        print(f"Критическая ошибка при запуске бота: {e}")
        # Можно добавить логирование здесь