# Интегрированный телеграм-бот в веб-приложение
# Использует общий пул подключений к БД и функции из app.py

import telebot
import os
import threading
from typing import Optional

# Импортируем функции из app.py для работы с БД
# Будем импортировать после инициализации Flask приложения
_flask_app = None
_execute_query = None
_logger = None


def init_telegram_bot(flask_app, execute_query_func):
    """
    Инициализация телеграм-бота с использованием функций из Flask приложения
    
    Args:
        flask_app: Flask приложение
        execute_query_func: Функция execute_query из app.py
    """
    global _flask_app, _execute_query, _logger
    _flask_app = flask_app
    _execute_query = execute_query_func
    _logger = flask_app.logger
    
    # Получаем токен из переменных окружения
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not telegram_token:
        _logger.warning("TELEGRAM_BOT_TOKEN не найден. Телеграм-бот не будет запущен.")
        return None
    
    try:
        bot = telebot.TeleBot(telegram_token)
        
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
            
            # Валидация длины запроса (защита от слишком длинных запросов)
            if len(crystal_name_filter) > 100:
                bot.reply_to(message, "Слишком длинный запрос. Пожалуйста, введите шифр кристалла (до 100 символов).")
                return
            
            if not crystal_name_filter:
                bot.reply_to(message, "Пожалуйста, введите шифр кристалла для поиска.")
                return
            
            # SQL-запрос для поиска остатков кристаллов по всем складам
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
                # Используем общую функцию execute_query из app.py
                # Добавляем символы подстановки % для частичного поиска
                results = _execute_query(query, ('%' + crystal_name_filter + '%',), fetch=True)
                
                if results and isinstance(results, (list, tuple)) and len(results) > 0:
                    warehouse_order = ["Склад кристаллов", "Склад пластин", "Дальний склад"]
                    # Структура: {chip_code: {wh: (stock_w, stock_gp)}}
                    chips = {}
                    for row in results:
                        if isinstance(row, (list, tuple)) and len(row) >= 4:
                            wh, chip_code, stock_wafer, stock_gelpak = row[0], row[1], row[2], row[3]
                            chip_entry = chips.setdefault(chip_code, {})
                            chip_entry[wh] = (
                                stock_wafer if stock_wafer is not None else 0,
                                stock_gelpak if stock_gelpak is not None else 0
                            )
                    
                    response_parts = []
                    chip_codes_list = list(chips.items())
                    for chip_idx, (chip_code, per_wh) in enumerate(chip_codes_list):
                        # Добавляем разделитель между кристаллами (но не перед первым)
                        if chip_idx > 0:
                            response_parts.append("")  # Пустая строка для визуального разделения
                            response_parts.append("=" * 50)  # Разделитель между кристаллами
                            response_parts.append("")  # Пустая строка для визуального разделения
                        
                        response_parts.append(f"Шифр: {chip_code}")
                        # Обрабатываем каждый склад из списка
                        for idx, wh in enumerate(warehouse_order):
                            if wh in per_wh:
                                stock_w, stock_gp = per_wh[wh]
                                response_parts.append(f"  {wh}:")
                                response_parts.append(f"    Остаток Wafer: {stock_w} шт.")
                                response_parts.append(f"    Остаток GelPak: {stock_gp} шт.")
                            else:
                                # Если информации нет, пишем "Информация отсутствует"
                                response_parts.append(f"  {wh}:")
                                response_parts.append(f"    Информация отсутствует")
                            # Добавляем разделитель между складами (но не после последнего)
                            if idx < len(warehouse_order) - 1:
                                response_parts.append("─" * 30)
                    
                    if response_parts:
                        bot.reply_to(message, "\n".join(response_parts))
                    else:
                        bot.reply_to(message, "Кристаллы найдены, но остаток по ним равен 0 (Wafer и GelPak).")
                else:
                    bot.reply_to(message, f"Кристаллы с шифром, содержащим '{crystal_name_filter}', не найдены или по ним нет операций.")
                
            except Exception as e:
                _logger.error(f"Ошибка при выполнении запроса в телеграм-боте: {e}", exc_info=True)
                bot.reply_to(message, "Произошла ошибка при поиске. Попробуйте позже или обратитесь к администратору.")
        
        _logger.info("Телеграм-бот инициализирован успешно")
        return bot
        
    except Exception as e:
        _logger.error(f"Ошибка инициализации телеграм-бота: {e}", exc_info=True)
        return None


def start_bot_polling(bot):
    """
    Запуск бота в отдельном потоке
    
    Args:
        bot: Объект TeleBot
    """
    if bot is None:
        return
    
    def run_bot():
        try:
            _logger.info("Телеграм-бот запускается...")
            bot.infinity_polling(none_stop=True, timeout=30, long_polling_timeout=5)
        except Exception as e:
            _logger.error(f"Критическая ошибка при запуске телеграм-бота: {e}", exc_info=True)
    
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True, name="TelegramBot")
    bot_thread.start()
    _logger.info("Телеграм-бот запущен в отдельном потоке")

