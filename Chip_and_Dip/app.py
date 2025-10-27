# app.py
import os
import threading
import time
import json
import logging
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from decouple import config as flask_config_loader

import parser_logic  # Ваш модуль с логикой парсинга

# --- Настройка Flask приложения ---
app = Flask(__name__)
# Загрузка FLASK_SECRET_KEY из .env или значение по умолчанию
app.secret_key = flask_config_loader('FLASK_SECRET_KEY', default='your_very_secret_flask_key_please_change_this')

# --- Настройка логирования (используем настроенный логгер из parser_logic) ---
# setup_logging() должен быть вызван до первого использования flask_logger
parser_logic.setup_logging(log_level_console=logging.INFO, log_level_file=logging.DEBUG)
flask_logger = parser_logic.logger  # Используем тот же экземпляр логгера

# --- Глобальные переменные для отслеживания состояния парсинга ---
parsing_active_lock = threading.Lock()  # Блокировка для безопасного доступа к parsing_active
parsing_active = False
parsing_progress_data = {
    "current": 0,
    "total": 1,  # Изначально 1, чтобы избежать деления на 0, будет обновлено
    "message": "Ожидание запуска",
    "file_path": None,  # Больше не используется для Excel, можно убрать из SSE если не нужен
    "error": None
}
parser_thread_instance = None  # Для хранения экземпляра потока
PARSER_CONFIGURATION = {}  # Словарь для хранения конфигурации парсера

# --- Загрузка конфигурации парсера при старте Flask ---
try:
    PARSER_CONFIGURATION = parser_logic.load_parser_config()
    if not PARSER_CONFIGURATION:
        # Эта ситуация возникнет, если load_parser_config вернет None или пустой словарь из-за ошибки
        flask_logger.critical(
            "Конфигурация парсера НЕ загружена! Проверьте .env файл и логи parser_logic.load_parser_config.")
    else:
        # Логируем часть конфигурации для проверки. Ключи должны быть в нижнем регистре.
        flask_logger.info(
            f"Конфигурация парсера успешно загружена: headless='{PARSER_CONFIGURATION.get('headless')}', chrome_path='{PARSER_CONFIGURATION.get('chrome_executable_path', 'Не указан')}'...")
except Exception as e:
    flask_logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА при загрузке конфигурации парсера при старте Flask: {e}", exc_info=True)
    PARSER_CONFIGURATION = {}  # В случае критической ошибки, оставляем пустым, чтобы проверки ниже сработали


# --- База данных (ЗАГЛУШКА - замените на вашу реальную логику) ---
def get_items_from_db_for_parsing():
    """Заглушка для получения элементов из БД."""
    flask_logger.info("DB MOCK: Запрос элементов для парсинга из БД...")
    # В реальном приложении здесь будет запрос к вашей БД
    # Пример данных, которые ожидает parser_logic.run_parsing_process:
    # return [
    #     {'id': 1, 'url': 'https://www.chipdip.ru/product/gr-1206s-100k-f-0.125w-1'},
    #     {'id': 2, 'url': 'https://www.chipdip.ru/product0/8003073404'},
    #     # ... другие элементы
    # ]
    # Для теста можно вернуть пустой список или несколько валидных URL
    # flask_logger.warning("DB MOCK: Возвращается ПУСТОЙ список элементов для парсинга!")
    # return []
    # Для теста с реальными данными:
    test_items = [
        {'id': 101, 'url': 'https://www.chipdip.ru/product/led-0805-smd-white'},
        {'id': 102, 'url': 'https://www.chipdip.ru/product/atmega328p-pu'},
    ]
    flask_logger.info(f"DB MOCK: Возвращено {len(test_items)} элементов для парсинга.")
    return test_items


def update_item_in_db(item_id, result_code, stock_value):
    """Заглушка для обновления элемента в БД."""
    try:
        # Здесь ваша реальная логика обновления записи в БД
        flask_logger.info(f"DB MOCK: Обновление ID {item_id} -> код: {result_code}, сток: {stock_value}")
        # Пример:
        # with get_db_connection() as conn:
        #     with conn.cursor() as cur:
        #         cur.execute("UPDATE products SET stock = %s, parse_status = %s, last_parsed_at = NOW() WHERE id = %s",
        #                     (stock_value, result_code, item_id))
        #         conn.commit()
    except Exception as e:
        flask_logger.error(f"DB MOCK: Ошибка обновления БД для ID {item_id}: {e}", exc_info=True)


# --- Функция, выполняющая парсинг в отдельном потоке ---
def run_parser_in_background():
    global parsing_active, parsing_progress_data, PARSER_CONFIGURATION

    # --- ПРОВЕРКА КОНФИГУРАЦИИ ---
    if not PARSER_CONFIGURATION:
        flask_logger.error("Парсинг не может быть запущен: PARSER_CONFIGURATION не загружена (пуста).")
        with parsing_active_lock:
            parsing_progress_data["error"] = "Ошибка сервера: конфигурация парсера не инициализирована."
            parsing_progress_data["message"] = "Ошибка конфигурации сервера."
            # parsing_active должен быть сброшен здесь, если он был установлен
            parsing_active = False
        return

    # Получаем элементы для парсинга из БД
    items_to_parse = get_items_from_db_for_parsing()

    if not items_to_parse:
        flask_logger.info("Нет элементов для парсинга из БД.")
        with parsing_active_lock:
            parsing_progress_data["message"] = "Нет данных для обработки из БД."
            parsing_progress_data["error"] = None
            parsing_progress_data["total"] = 0
            parsing_progress_data["current"] = 0
            parsing_active = False  # Парсинг завершен (нечего делать)
        return

    # Обновляем total в parsing_progress_data после получения items_to_parse
    with parsing_active_lock:
        parsing_progress_data["total"] = len(items_to_parse)
        parsing_progress_data["current"] = 0  # Сбрасываем current на случай, если это повторный запуск
        parsing_progress_data["message"] = "Подготовка к парсингу..."  # Обновляем сообщение
        # parsing_active уже должен быть True из start_parsing_endpoint

    flask_logger.info(
        f"Подготовка к парсингу {len(items_to_parse)} элементов. Конфигурация: headless='{PARSER_CONFIGURATION.get('headless')}'")

    def update_progress_for_sse(current, total, message, file_path_ignored=None, error=None):
        global parsing_progress_data
        parsing_progress_data["current"] = current
        parsing_progress_data["total"] = total
        parsing_progress_data["message"] = message
        parsing_progress_data["file_path"] = None
        parsing_progress_data["error"] = error
        flask_logger.debug(f"SSE Progress Update: C:{current}/T:{total} - {message} - Err:{error}")

    try:
        flask_logger.info(f"Запуск parser_logic.run_parsing_process для {len(items_to_parse)} элементов.")

        # PARSER_CONFIGURATION передается в parser_logic.run_parsing_process
        # Он содержит ключи в нижнем регистре (headless, chrome_executable_path и т.д.)
        processed_data_list = parser_logic.run_parsing_process(
            items_to_parse,
            PARSER_CONFIGURATION,
            update_progress_for_sse,
            update_item_in_db
        )

        # Если run_parsing_process завершился без выброса исключения
        if not parsing_progress_data.get("error"):  # Проверяем, не установил ли callback ошибку
            parsing_progress_data["message"] = f"Обработка {len(items_to_parse)} элементов завершена."
            # file_path больше не используется
            flask_logger.info(
                f"Парсинг {len(items_to_parse)} элементов из БД завершен успешно (со стороны parser_logic).")

    except Exception as e:
        flask_logger.error(f"Критическая ошибка в фоновом потоке парсинга (run_parser_in_background): {e}",
                           exc_info=True)
        parsing_progress_data["error"] = f"Внутренняя ошибка сервера во время парсинга: {str(e)}"
        # Сообщение об ошибке также может быть установлено в update_progress_for_sse из parser_logic
    finally:
        with parsing_active_lock:
            parsing_active = False  # Сбрасываем флаг активности
        flask_logger.info("Фоновый поток парсинга (run_parser_in_background) завершил свою работу.")


# --- Маршруты Flask ---
@app.route('/')
def index():
    return render_template('index.html', page_title="Парсер остатков на складе ChipDip")


@app.route('/start-parsing', methods=['POST'])
def start_parsing_endpoint():
    global parsing_active, parser_thread_instance, PARSER_CONFIGURATION

    with parsing_active_lock:
        if parsing_active:
            flask_logger.warning("Попытка запуска парсинга, когда он уже активен.")
            return jsonify({"status": "error", "message": "Процесс парсинга уже запущен. Пожалуйста, подождите."}), 409

        if not PARSER_CONFIGURATION:
            flask_logger.error("Попытка запуска парсинга: PARSER_CONFIGURATION не загружена.")
            return jsonify(
                {"status": "error", "message": "Ошибка конфигурации сервера: настройки парсера не загружены."}), 500

        # Сбрасываем данные о прогрессе предыдущего запуска перед стартом нового
        parsing_progress_data["current"] = 0
        parsing_progress_data["total"] = 1  # Будет обновлено в run_parser_in_background
        parsing_progress_data["message"] = "Инициализация..."
        parsing_progress_data["file_path"] = None
        parsing_progress_data["error"] = None

        parsing_active = True  # Устанавливаем флаг, что парсинг сейчас начнется

    if parser_thread_instance and parser_thread_instance.is_alive():
        # Эта ситуация не должна возникать, если parsing_active_lock работает правильно
        flask_logger.warning("Предыдущий поток парсинга все еще активен при попытке запуска нового. Это странно.")

    parser_thread_instance = threading.Thread(target=run_parser_in_background)
    parser_thread_instance.daemon = True
    parser_thread_instance.start()
    flask_logger.info("Запрос на запуск парсинга получен, фоновый поток запущен.")

    return jsonify({"status": "success", "message": "Процесс парсинга запущен..."})


@app.route('/progress-stream')
def progress_stream_endpoint():
    def generate_progress():
        global parsing_active, parsing_progress_data
        flask_logger.info("SSE: Клиент подключился к /progress-stream.")
        last_sent_data_json = None
        connection_active = True

        try:
            while connection_active:
                with parsing_active_lock:
                    current_parsing_active = parsing_active

                data_to_send = {
                    "running": current_parsing_active,
                    "progress": parsing_progress_data.get("current", 0),
                    "total": parsing_progress_data.get("total", 1),
                    "message": parsing_progress_data.get("message", ""),
                    "file_path": None,
                    "error": parsing_progress_data.get("error")
                }
                current_data_json = json.dumps(data_to_send)

                if current_data_json != last_sent_data_json:
                    try:
                        yield f"data: {current_data_json}\n\n"
                        last_sent_data_json = current_data_json
                        flask_logger.debug(f"SSE Sent: {current_data_json}")
                    except Exception as e_yield:
                        flask_logger.error(f"SSE: Ошибка при yield data: {e_yield}")
                        connection_active = False
                        break

                # Условие выхода из цикла для сервера
                # Парсинг не активен И (есть ошибка ИЛИ (есть общее число И текущий >= общего И сообщение не начальное))
                # Добавил проверку, что current >= total, если total > 0, чтобы не выйти преждевременно, если total еще 0 или 1
                is_finished_locally = False
                if not current_parsing_active:
                    if parsing_progress_data.get("error"):
                        is_finished_locally = True
                    else:
                        current_prog = parsing_progress_data.get("current", 0)
                        total_prog = parsing_progress_data.get("total", 0)  # Используем 0 если нет total
                        if total_prog > 0 and current_prog >= total_prog:
                            # Дополнительно проверяем, что сообщение не указывает на инициализацию
                            initial_messages = ["Ожидание запуска", "Инициализация...", "Подготовка к парсингу...",
                                                "Запуск процесса парсинга..."]
                            if parsing_progress_data.get("message") not in initial_messages:
                                is_finished_locally = True
                        elif total_prog == 0 and parsing_progress_data.get(
                                "message") == "Нет данных для обработки из БД.":  # Случай без данных
                            is_finished_locally = True

                if is_finished_locally:
                    flask_logger.info(
                        f"SSE: Условие завершения парсинга (is_finished_locally=True) выполнено на сервере. current_parsing_active={current_parsing_active}, data_to_send={data_to_send}. Закрытие потока.")
                    connection_active = False
                    # Отправим финальное состояние еще раз
                    final_data_json = json.dumps(data_to_send)  # data_to_send уже содержит финальное состояние
                    if final_data_json != last_sent_data_json:  # Если оно не было отправлено последним
                        try:
                            yield f"data: {final_data_json}\n\n"
                            flask_logger.debug(f"SSE Sent (Final on Finish): {final_data_json}")
                        except:
                            pass
                    break

                time.sleep(0.5)

        except GeneratorExit:
            flask_logger.info("SSE: Клиент отключился (GeneratorExit).")
            connection_active = False
        except Exception as e_main_loop:
            flask_logger.error(f"SSE: Ошибка в основном цикле generate_progress: {e_main_loop}", exc_info=True)
            connection_active = False
        finally:
            flask_logger.info("SSE: Цикл generate_progress завершен.")

    # Используем Response без stream_with_context, как было в предыдущем тесте
    return Response(generate_progress(), mimetype='text/event-stream')


if __name__ == '__main__':
    flask_logger.info(f"Запуск Flask веб-приложения для ChipDip парсера...")
    # При локальном запуске .env файл должен быть в той же директории, что и app.py
    # или доступен через стандартные пути поиска python-decouple.
    app.run(host='0.0.0.0', port=8085, debug=True, threaded=True, use_reloader=True)