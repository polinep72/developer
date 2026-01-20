"""
Telegram-бот для поиска остатков товаров на складе готовой продукции.
Использует нормализованную структуру БД (таблица 'элементы' вместо names_ms/names_m/names_pp).

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
Лицензионные права: ИнноЦентр ВАО и ИПК Электрон-Маш
"""

import os
import logging
import telebot
from contextlib import closing
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Параметры подключения к БД
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'warehouse')

# Токен Telegram бота
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
    raise ValueError("TELEGRAM_BOT_TOKEN обязателен для работы бота")

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Обработка команды /start"""
    try:
        welcome_text = (
            "Добро пожаловать в бот поиска остатков на складе готовой продукции!\n\n"
            "Введите наименование товара или код кристалла для поиска остатков.\n"
            "Бот покажет остатки по всем типам продукции:\n"
            "- Микросхемы\n"
            "- Модули\n"
            "- ПП\n\n"
            "Каждая поставка отображается отдельно с остатком, датой прихода и номером накладной.\n"
            "Результаты отсортированы по дате прихода (FIFO - самые старые первыми)."
        )
        bot.reply_to(message, welcome_text)
        logger.info(f"Приветствие отправлено пользователю {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start: {e}", exc_info=True)


def validate_search_term(search_term):
    """
    Валидация поискового запроса для защиты от SQL-инъекций и атак.
    Возвращает очищенный и безопасный поисковый термин.
    """
    if not search_term:
        return ""
    
    # Ограничиваем длину запроса (защита от DoS)
    search_term = search_term.strip()[:200]
    
    # Удаляем опасные символы (хотя параметризованный запрос защищает, это дополнительная мера)
    # Убираем одиночные кавычки, точку с запятой и другие потенциально опасные символы SQL
    # Но оставляем буквы, цифры, пробелы и основные символы для поиска
    import re
    # Оставляем только безопасные символы: буквы (включая кириллицу), цифры, пробелы, дефис, точка, подчеркивание
    search_term = re.sub(r'[^\w\s\-\.а-яА-ЯёЁ]', '', search_term)
    
    return search_term.strip()


def fetch_stock_by_type(cursor, search_term, type_code, has_pp=False):
    """
    Возвращает список кортежей (item_key, остаток, дата_прихода, номер_накладной) для выбранного типа продукции.
    Использует нормализованную структуру БД: таблицы 'invoices' и 'consumptions' с фильтрацией по element_type_id.
    
    Показывает каждую поставку отдельно с её остатком, не группируя по характеристикам.
    item_key формируется как 'name | chip_code | body_type [| pp_code]' для идентификации позиции.
    Сортировка по дате прихода по возрастанию (FIFO).
    
    Безопасность: использует параметризованный запрос для защиты от SQL-инъекций.
    """
    # Базовый запрос для микросхем (без pp_id) - показывает каждую поставку отдельно
    base_query = """
        WITH invoice_sum AS (
            SELECT 
                inv.item_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                inv.arrival_date_id,
                inv.invoice_id,
                SUM(inv.quan) as total_invoice_quantity
            FROM invoices inv
            WHERE inv.element_type_id = %s
            GROUP BY inv.item_id, inv.name_id, inv.chip_id, inv.body_id, inv.arrival_date_id, inv.invoice_id
        ),
        consumption_sum AS (
            SELECT 
                cons.item_id,
                SUM(cons.quantity) as total_consumption_quantity
            FROM consumptions cons
            WHERE cons.element_type_id = %s
            GROUP BY cons.item_id
        ),
        item_balances AS (
            SELECT 
                inv.item_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                inv.arrival_date_id,
                inv.invoice_id,
                COALESCE(inv.total_invoice_quantity, 0) - COALESCE(cons.total_consumption_quantity, 0) as balance
            FROM invoice_sum inv
            LEFT JOIN consumption_sum cons ON inv.item_id = cons.item_id
            WHERE (COALESCE(inv.total_invoice_quantity, 0) - COALESCE(cons.total_consumption_quantity, 0)) > 0
        )
        SELECT 
            COALESCE(e.name, '-') || ' | ' || 
            COALESCE(c.chip_code, '-') || ' | ' || 
            COALESCE(b.body_type, '-') as item_key,
            ib.balance as total_balance,
            ad.date as arrival_date,
            i.invoice_id as invoice_number
        FROM item_balances ib
        -- name_id в invoices/consumptions хранит legacy id из names_*, поэтому джоинимся по elements.legacy_name_id
        LEFT JOIN elements e ON ib.name_id = e.legacy_name_id AND e.element_type_id = %s
        LEFT JOIN chips c ON ib.chip_id = c.id
        LEFT JOIN bodies b ON ib.body_id = b.id
        LEFT JOIN arrival_dates ad ON ib.arrival_date_id = ad.id
        LEFT JOIN invoice i ON ib.invoice_id = i.id
        WHERE (
            e.name ILIKE %s OR 
            c.chip_code ILIKE %s
        )
        ORDER BY ad.date ASC, item_key
    """
    
    # Запрос для модулей и ПП (с pp_id) - показывает каждую поставку отдельно
    query_with_pp = """
        WITH invoice_sum AS (
            SELECT 
                inv.item_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                inv.pp_id,
                inv.arrival_date_id,
                inv.invoice_id,
                SUM(inv.quan) as total_invoice_quantity
            FROM invoices inv
            WHERE inv.element_type_id = %s
            GROUP BY inv.item_id, inv.name_id, inv.chip_id, inv.body_id, inv.pp_id, inv.arrival_date_id, inv.invoice_id
        ),
        consumption_sum AS (
            SELECT 
                cons.item_id,
                SUM(cons.quantity) as total_consumption_quantity
            FROM consumptions cons
            WHERE cons.element_type_id = %s
            GROUP BY cons.item_id
        ),
        item_balances AS (
            SELECT 
                inv.item_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                inv.pp_id,
                inv.arrival_date_id,
                inv.invoice_id,
                COALESCE(inv.total_invoice_quantity, 0) - COALESCE(cons.total_consumption_quantity, 0) as balance
            FROM invoice_sum inv
            LEFT JOIN consumption_sum cons ON inv.item_id = cons.item_id
            WHERE (COALESCE(inv.total_invoice_quantity, 0) - COALESCE(cons.total_consumption_quantity, 0)) > 0
        )
        SELECT 
            COALESCE(e.name, '-') || ' | ' || 
            COALESCE(c.chip_code, '-') || ' | ' || 
            COALESCE(b.body_type, '-') || ' | ' ||
            COALESCE(pp.pp_code, '-') as item_key,
            ib.balance as total_balance,
            ad.date as arrival_date,
            i.invoice_id as invoice_number
        FROM item_balances ib
        -- name_id в invoices/consumptions хранит legacy id из names_*, поэтому джоинимся по elements.legacy_name_id
        LEFT JOIN elements e ON ib.name_id = e.legacy_name_id AND e.element_type_id = %s
        LEFT JOIN chips c ON ib.chip_id = c.id
        LEFT JOIN bodies b ON ib.body_id = b.id
        LEFT JOIN pp ON ib.pp_id = pp.id
        LEFT JOIN arrival_dates ad ON ib.arrival_date_id = ad.id
        LEFT JOIN invoice i ON ib.invoice_id = i.id
        WHERE (
            e.name ILIKE %s OR 
            c.chip_code ILIKE %s
        )
        ORDER BY ad.date ASC, item_key
    """
    
    query_template = query_with_pp if has_pp else base_query

    # Валидация входных данных (дополнительная защита)
    search_term = validate_search_term(search_term)
    if not search_term:
        return []  # Пустой результат, если запрос невалидный
    
    # Получение ID типа элемента
    cursor.execute("SELECT id FROM element_types WHERE code = %s", (type_code,))
    type_row = cursor.fetchone()
    if not type_row:
        return []  # Тип не найден
    type_id = type_row[0]
    
    # Параметризованный запрос - защита от SQL-инъекций
    # psycopg2 автоматически экранирует значения в %s
    search_pattern = f"%{search_term}%"
    
    if has_pp:
        cursor.execute(query_template, (type_id, type_id, type_id, search_pattern, search_pattern))
    else:
        cursor.execute(query_template, (type_id, type_id, type_id, search_pattern, search_pattern))
    
    # Возвращаем список кортежей (item_key, баланс, дата_прихода, номер_накладной) - каждая поставка отдельно
    return [(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]


def format_arrival_date(arrival_date):
    """Форматирует дату прихода в DD.MM.YYYY."""
    if not arrival_date:
        return None
    from datetime import datetime, date
    if isinstance(arrival_date, (datetime, date)):
        return arrival_date.strftime("%d.%m.%Y")
    elif isinstance(arrival_date, str):
        return arrival_date
    else:
        return str(arrival_date)


def build_response(search_term, stocks_ms, stocks_m, stocks_pp):
    """Формирует ответ с остатками по трем типам продукции с датой прихода."""
    if not stocks_ms and not stocks_m and not stocks_pp:
        return "К сожалению, товар не найден или остаток равен 0."

    lines = []
    separator = "---------------"
    
    def format_stock_items(items, title):
        """Форматирует поставки товаров с остатком, датой прихода и номером накладной. Показывает каждую поставку отдельно."""
        if not items:
            return []
        result = [title]
        # items уже отсортированы по дате прихода в SQL-запросе (ORDER BY ad.date ASC)
        for item_key, balance, arrival_date, invoice_id in items:
            result.append(f"Позиция: {item_key}")
            result.append(f"Остаток: {balance} шт.")
            date_str = format_arrival_date(arrival_date)
            if date_str:
                result.append(f"Дата прихода: {date_str}")
            if invoice_id:
                result.append(f"Накладная: {invoice_id}")
            result.append(separator)
        return result
    
    # Микросхемы
    lines.extend(format_stock_items(stocks_ms, "МИКРОСХЕМЫ:"))
    
    # Модули
    lines.extend(format_stock_items(stocks_m, "МОДУЛИ:"))
    
    # ПП
    lines.extend(format_stock_items(stocks_pp, "ПП:"))

    return "\n".join(lines).strip()


# Функция обработки текстовых запросов
@bot.message_handler(content_types=['text'])
def get_product_count(message):
    # Пропускаем команды (они обрабатываются отдельными хендлерами)
    if message.text and message.text.startswith('/'):
        return
    
    search_term = message.text.strip()
    
    # Валидация запроса (дополнительная защита от SQL-инъекций)
    search_term = validate_search_term(search_term)
    if not search_term:
        bot.reply_to(message, "Запрос пустой или содержит недопустимые символы. Используйте только буквы, цифры и пробелы.")
        return
    
    logger.info(f"Получен поисковый запрос '{search_term}' от пользователя {message.from_user.id}")

    try:
        with closing(
            psycopg2.connect(
                user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME, host=DB_HOST
            )
        ) as conn:
            with conn.cursor() as cursor:
                # Используем нормализованную структуру: единые таблицы 'invoices' и 'consumptions'
                # Фильтрация по типу через element_type_id
                stocks_ms = fetch_stock_by_type(cursor, search_term, "ms", has_pp=False)
                stocks_m = fetch_stock_by_type(cursor, search_term, "m", has_pp=True)
                stocks_pp = fetch_stock_by_type(cursor, search_term, "pp", has_pp=True)

                response_text = build_response(search_term, stocks_ms, stocks_m, stocks_pp)
                bot.reply_to(message, response_text)
                logger.info(f"Ответ отправлен пользователю {message.from_user.id}")
    except psycopg2.Error as e:
        error_msg = f"Ошибка подключения к БД: {e}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, f"Ошибка при подключении к базе данных. Проверьте настройки подключения.")
    except Exception as e:
        error_msg = f"Ошибка при обработке запроса '{search_term}': {type(e).__name__}: {e}"
        logger.error(error_msg, exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        bot.reply_to(message, f"Произошла ошибка при обработке запроса. Попробуйте позже.")


if __name__ == "__main__":
    logger.info(f"Запуск бота для БД {DB_NAME} на {DB_HOST}")
    logger.info("Бот использует полностью нормализованную структуру БД:")
    logger.info("  - Таблицы: elements, element_types, invoices, consumptions (английские названия)")
    logger.info("  - Все данные объединены в единые таблицы с фильтрацией по element_type_id")
    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        logger.error(f"Критическая ошибка при работе бота: {e}", exc_info=True)
