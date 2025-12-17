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
    income_union AS (
        SELECT 'Склад кристаллов' AS wh, id_n_chip, SUM(quan_w) total_income_w, SUM(quan_gp) total_income_gp
        FROM invoice
        WHERE COALESCE(note, '') != 'возврат'
        GROUP BY 1,2
        UNION ALL
        SELECT 'Склад пластин' AS wh, id_n_chip, SUM(quan_w), SUM(quan_gp)
        FROM invoice_p
        WHERE COALESCE(note, '') != 'возврат'
        GROUP BY 1,2
        UNION ALL
        SELECT 'Дальний склад' AS wh, id_n_chip, SUM(quan_w), SUM(quan_gp)
        FROM invoice_f
        WHERE COALESCE(note, '') != 'возврат'
        GROUP BY 1,2
    ),
    return_union AS (
        SELECT 'Склад кристаллов' AS wh, id_n_chip, SUM(quan_w) total_return_w, SUM(quan_gp) total_return_gp
        FROM invoice
        WHERE note = 'возврат'
        GROUP BY 1,2
        UNION ALL
        SELECT 'Склад пластин' AS wh, id_n_chip, SUM(quan_w), SUM(quan_gp)
        FROM invoice_p
        WHERE note = 'возврат'
        GROUP BY 1,2
        UNION ALL
        SELECT 'Дальний склад' AS wh, id_n_chip, SUM(quan_w), SUM(quan_gp)
        FROM invoice_f
        WHERE note = 'возврат'
        GROUP BY 1,2
    ),
    consumption_union AS (
        SELECT 'Склад кристаллов' AS wh, id_n_chip, SUM(cons_w) total_consumed_w, SUM(cons_gp) total_consumed_gp
        FROM consumption
        GROUP BY 1,2
        UNION ALL
        SELECT 'Склад пластин' AS wh, id_n_chip, SUM(cons_w), SUM(cons_gp)
        FROM consumption_p
        GROUP BY 1,2
        UNION ALL
        SELECT 'Дальний склад' AS wh, id_n_chip, SUM(cons_w), SUM(cons_gp)
        FROM consumption_f
        GROUP BY 1,2
    ),
    all_keys AS (
        SELECT wh, id_n_chip FROM income_union
        UNION
        SELECT wh, id_n_chip FROM return_union
        UNION
        SELECT wh, id_n_chip FROM consumption_union
    )
    SELECT
        ak.wh,
        nc.n_chip AS chip_code,
        (COALESCE(inc.total_income_w, 0) + COALESCE(ret.total_return_w, 0) - COALESCE(cons.total_consumed_w, 0)) AS stock_w,
        (COALESCE(inc.total_income_gp, 0) + COALESCE(ret.total_return_gp, 0) - COALESCE(cons.total_consumed_gp, 0)) AS stock_gp
    FROM all_keys ak
    JOIN n_chip nc ON ak.id_n_chip = nc.id
    LEFT JOIN income_union inc ON inc.wh = ak.wh AND inc.id_n_chip = ak.id_n_chip
    LEFT JOIN return_union ret ON ret.wh = ak.wh AND ret.id_n_chip = ak.id_n_chip
    LEFT JOIN consumption_union cons ON cons.wh = ak.wh AND cons.id_n_chip = ak.id_n_chip
    WHERE nc.n_chip ILIKE %s
    ORDER BY ak.wh, nc.n_chip;
    """

    try:
        with closing(psycopg2.connect(user=DB_USER, password=DB_PASSWORD,
                                      dbname=DB_NAME, host=DB_HOST)) as conn:
            with conn.cursor() as cursor:
                # Добавляем символы подстановки % для частичного поиска
                cursor.execute(query, ('%' + crystal_name_filter + '%',))
                results = cursor.fetchall()

                if results:
                    warehouse_order = ["Склад кристаллов", "Склад пластин", "Дальний склад"]
                    # Структура: {chip_code: {wh: (stock_w, stock_gp)}}
                    chips = {}
                    for wh, chip_code, stock_wafer, stock_gelpak in results:
                        chip_entry = chips.setdefault(chip_code, {})
                        chip_entry[wh] = (
                            stock_wafer if stock_wafer is not None else 0,
                            stock_gelpak if stock_gelpak is not None else 0
                        )

                    response_parts = []
                    for chip_code, per_wh in chips.items():
                        for wh in warehouse_order:
                            response_parts.append(wh)
                            if wh in per_wh:
                                stock_w, stock_gp = per_wh[wh]
                                response_parts.append(f"Шифр: {chip_code}")
                                response_parts.append(f"  Остаток Wafer: {stock_w} шт.")
                                response_parts.append(f"  Остаток GelPak: {stock_gp} шт.")
                            else:
                                response_parts.append("Информация по этому кристаллу не найдена.")
                            response_parts.append("---------------")

                    if response_parts:
                        bot.reply_to(message, "\n".join(response_parts))
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