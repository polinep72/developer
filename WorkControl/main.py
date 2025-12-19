import requests
import schedule
import time
import datetime
import logging
import re
import docker
import os  # Для работы с переменными окружения
from dotenv import load_dotenv  # Для загрузки .env файла
import threading
import psycopg2
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Загружаем переменные из .env файла
load_dotenv()

# --- НАСТРОЙКИ из .env файла ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 5))  # Таймаут для HTTP проверок
# Автоперезапуск контейнеров, если они не запущены (true/false)
AUTO_RESTART_CONTAINERS = os.getenv("AUTO_RESTART_CONTAINERS", "false").strip().lower() == "true"
# Список сервисов (по имени в SERVICES_TO_MONITOR), которым разрешен автоперезапуск. Если пусто — разрешено всем docker-сервисам
AUTO_RESTART_ALLOW_LIST = {s.strip() for s in os.getenv("AUTO_RESTART_ALLOW_LIST", "").split(",") if s.strip()}

# Telegram бот для ручных проверок
TELEGRAM_BOT_ENABLED = os.getenv("TELEGRAM_BOT_ENABLED", "false").strip().lower() == "true"

# База данных PostgreSQL
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "monitoring")
DB_ENABLED = os.getenv("DB_ENABLED", "false").strip().lower() == "true"
# REPORT_TIME = os.getenv("REPORT_TIME", "07:30")
# CHECK_INTERVAL_HOURLY_AT = os.getenv("CHECK_INTERVAL_HOURLY_AT", ":05")
# CHECK_INTERVAL_SECONDS = os.getenv("CHECK_INTERVAL_SECONDS") # Будет None, если не задан

DOCKER_CLIENT = None
TELEGRAM_APP = None

# Функции для работы с БД
def get_db_connection():
    """Получает соединение с базой данных"""
    if not DB_ENABLED:
        return None
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

def load_services_from_db():
    """Загружает сервисы из базы данных"""
    if not DB_ENABLED:
        return []
    
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, type, check_params 
            FROM monitoring_services 
            WHERE enabled = TRUE
            ORDER BY priority, name
        """)
        
        services = []
        for name, service_type, check_params_json in cursor.fetchall():
            # check_params_json уже может быть dict или str
            if isinstance(check_params_json, dict):
                check_params = check_params_json
            elif isinstance(check_params_json, str):
                check_params = json.loads(check_params_json)
            else:
                check_params = {}
            services.append({
                "name": name,
                "type": service_type,
                "check_params": check_params
            })
        
        return services
        
    except Exception as e:
        print(f"Ошибка загрузки сервисов из БД: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

# Временно используем пустой список сервисов при старте
# Сервисы будут загружены после инициализации БД в main()
SERVICES_TO_MONITOR = []

SERVICE_STATUSES = {s["name"]: {"status": "UNKNOWN", "last_event_time": None, "last_message": "Еще не проверялся"} for s
                    in SERVICES_TO_MONITOR}


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С БАЗОЙ ДАННЫХ ---
def get_db_connection():
    """Создает подключение к PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None


def init_database():
    """Инициализирует базу данных и создает таблицы"""
    if not DB_ENABLED:
        return
    
    conn = get_db_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для инициализации")
        return
    
    try:
        cursor = conn.cursor()
        
        # Создаем таблицу для конфигурации сервисов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_services (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                type VARCHAR(50) NOT NULL,
                check_params JSONB,
                enabled BOOLEAN DEFAULT TRUE,
                priority INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Создаем таблицу для результатов проверок
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS service_checks (
                id SERIAL PRIMARY KEY,
                service_name VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                message TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Создаем таблицу для новых записей (для мониторинга)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS new_records (
                id SERIAL PRIMARY KEY,
                table_name VARCHAR(255) NOT NULL,
                record_id INTEGER,
                data JSONB,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Создаем индексы для быстрого поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_service_checks_service_name ON service_checks(service_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_service_checks_checked_at ON service_checks(checked_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_new_records_detected_at ON new_records(detected_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_new_records_processed ON new_records(processed)")
        
        # Миграция сервисов из .env в БД (если таблица пуста)
        cursor.execute("SELECT COUNT(*) FROM monitoring_services")
        if cursor.fetchone()[0] == 0:
            logger.info("Мигрирую сервисы из .env в БД...")
            
            # Docker контейнеры
            for key, value in os.environ.items():
                if key.startswith("CONTAINER_NAME_") and value:
                    service_name = f"Telegram Бот: {key.replace('CONTAINER_NAME_', '').replace('_', ' ')}"
                    check_params = json.dumps({"container_name": value})
                    cursor.execute("""
                        INSERT INTO monitoring_services (name, type, check_params) 
                        VALUES (%s, %s, %s)
                    """, (service_name, "docker_container_status", check_params))
            
            # WEB сервисы
            for key, value in os.environ.items():
                if key.startswith("URL_WEB_") and value:
                    service_name = f"WEB: {key.replace('URL_WEB_', '').replace('_', ' ')}"
                    check_params = json.dumps({
                        "url": value, 
                        "expected_status": 200, 
                        "timeout": HTTP_TIMEOUT
                    })
                    cursor.execute("""
                        INSERT INTO monitoring_services (name, type, check_params) 
                        VALUES (%s, %s, %s)
                    """, (service_name, "http", check_params))
        
        conn.commit()
        logger.info("База данных инициализирована успешно")
        
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def save_service_check(service_name, status, message):
    """Сохраняет результат проверки сервиса в БД"""
    if not DB_ENABLED:
        return
    
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO service_checks (service_name, status, message)
            VALUES (%s, %s, %s)
        """, (service_name, status, message))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения в БД: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def check_new_records():
    """Проверяет новые записи в БД за последние 12 часов"""
    if not DB_ENABLED:
        return []
    
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        # Ищем новые записи за последние 12 часов
        cursor.execute("""
            SELECT table_name, COUNT(*) as new_count, MAX(detected_at) as latest_time
            FROM new_records 
            WHERE detected_at >= NOW() - INTERVAL '12 hours'
            AND processed = FALSE
            GROUP BY table_name
            ORDER BY latest_time DESC
        """)
        
        results = cursor.fetchall()
        new_records = []
        
        for table_name, count, latest_time in results:
            new_records.append({
                'table': table_name,
                'count': count,
                'latest': latest_time
            })
        
        # Помечаем записи как обработанные
        cursor.execute("""
            UPDATE new_records 
            SET processed = TRUE 
            WHERE detected_at >= NOW() - INTERVAL '12 hours'
            AND processed = FALSE
        """)
        conn.commit()
        
        return new_records
        
    except Exception as e:
        logger.error(f"Ошибка проверки новых записей: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def generate_db_report():
    """Генерирует отчет о новых записях в БД"""
    new_records = check_new_records()
    
    if not new_records:
        return "📊 *Отчет по базе данных*\n\n✅ Новых записей за последние 12 часов не обнаружено."
    
    report_lines = ["📊 *Отчет по базе данных* (последние 12 часов):\n"]
    
    for record in new_records:
        report_lines.append(f"📋 *{record['table']}*: {record['count']} новых записей")
        report_lines.append(f"   Последняя: {record['latest'].strftime('%H:%M:%S')}")
    
    return "\n".join(report_lines)


# ... (остальной код logging, escape_markdown_v2, send_telegram_message, check_http_endpoint, check_docker_container_status, check_service, perform_hourly_checks, generate_daily_report - без изменений)
# ... Скопируйте их из предыдущей полной версии кода ...

# --- ФУНКЦИЯ ЭКРАНИРОВАНИЯ MARKDOWN ---
def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


# --- МОДУЛЬ УВЕДОМЛЕНИЙ ---
def send_telegram_message(message_text: str, use_markdown: bool = True):
    logger.debug(f"Попытка отправки сообщения в Telegram: {message_text[:100]}...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text}
    if use_markdown: payload["parse_mode"] = "MarkdownV2"

    try:
        response = requests.post(url, data=payload, timeout=10)
        logger.debug(f"Ответ от Telegram API: {response.status_code}, {response.text[:200]}")
        response.raise_for_status()
        logger.info(f"Сообщение успешно отправлено в Telegram: {message_text[:50]}...")
    except requests.exceptions.RequestException as e:
        err_text = e.response.text if e.response is not None else "Нет ответа"
        logger.error(f"Ошибка отправки сообщения в Telegram: {e}. Ответ сервера: {err_text}")
        if use_markdown and e.response is not None and e.response.status_code == 400 and "can't parse entities" in err_text.lower():
            logger.warning("Ошибка парсинга Markdown, пробую отправить как простой текст...")
            send_telegram_message(payload["text"], use_markdown=False)


# --- МОДУЛИ ПРОВЕРКИ ---
def check_http_endpoint(url, expected_status=200, timeout=10):
    # ... (код без изменений)
    logger.debug(f"HTTP Check: Начало проверки URL {url} с таймаутом {timeout}s")
    try:
        response = requests.get(url, timeout=timeout)
        logger.debug(f"HTTP Check: URL {url}, Статус: {response.status_code}, Ожидаемый: {expected_status}")
        if response.status_code == expected_status:
            return True, f"URL {url} доступен (статус: {response.status_code})."
        else:
            ct = response.text[:200].replace('\n', ' ').strip() if response.text else "Нет тела"
            logger.warning(
                f"HTTP Check: URL {url} статус {response.status_code} (ожидался {expected_status}). Контент: '{ct}'")
            return False, f"URL {url} статус {response.status_code} (ожидался {expected_status}). Ответ: {ct}"
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP Check: RequestException для URL {url}: {type(e).__name__} - {str(e)[:200]}", exc_info=False)
        if isinstance(e, requests.exceptions.ConnectTimeout):
            msg = f"Тайм-аут соединения с URL {url}."
        elif isinstance(e, requests.exceptions.ReadTimeout):
            msg = f"Тайм-аут чтения от URL {url}."
        elif isinstance(e, requests.exceptions.ConnectionError):
            msg = f"Ошибка соединения с URL {url}."
        else:
            msg = f"Общая ошибка сети для URL {url}: {type(e).__name__}."
        return False, msg
    except Exception as e:
        logger.error(f"HTTP Check: НЕПРЕДВИДЕННАЯ ошибка для URL {url}: {type(e).__name__} - {e}", exc_info=True)
        return False, f"Непредвиденная ошибка для URL {url}: {e}"


def _is_restart_allowed(service_name: str) -> bool:
    if not AUTO_RESTART_CONTAINERS:
        return False
    if not AUTO_RESTART_ALLOW_LIST:
        return True
    return service_name in AUTO_RESTART_ALLOW_LIST


def _attempt_restart_container(container_name: str):
    try:
        container = DOCKER_CLIENT.containers.get(container_name)
        try:
            container.start()
        except docker.errors.APIError as e:
            return False, f"Не удалось запустить контейнер '{container_name}': {e}"
        # Обновляем состояние и перепроверяем
        try:
            container.reload()
        except Exception:
            pass
        status_after = container.status
        if status_after == "running":
            health = container.attrs.get('State', {}).get('Health', {}).get('Status')
            if health and health != "healthy":
                return True, f"Контейнер '{container_name}' перезапущен, но health='{health}'."
            return True, f"Контейнер '{container_name}' успешно перезапущен."
        return False, f"Контейнер '{container_name}' не запущен после попытки старта (status='{status_after}')."
    except docker.errors.NotFound:
        return False, f"Контейнер '{container_name}' не найден, перезапуск невозможен."
    except Exception as e:
        return False, f"Ошибка при попытке перезапуска контейнера '{container_name}': {e}"


def get_monitored_containers():
    """Получает список всех Docker-контейнеров из мониторинга"""
    containers = []
    for service in SERVICES_TO_MONITOR:
        if service["type"] == "docker_container_status":
            container_name = service["check_params"].get("container_name")
            if container_name:
                containers.append({
                    "name": service["name"],
                    "container_name": container_name
                })
    return containers


def restart_container(container_name: str):
    """Перезапускает Docker-контейнер (публичная функция для бота)"""
    global DOCKER_CLIENT
    if DOCKER_CLIENT is None or DOCKER_CLIENT == "init_failed":
        try:
            DOCKER_CLIENT = docker.from_env()
            DOCKER_CLIENT.ping()
        except Exception as e:
            return False, f"Ошибка подключения к Docker: {e}"
    
    try:
        container = DOCKER_CLIENT.containers.get(container_name)
        current_status = container.status
        
        # Если контейнер запущен, сначала останавливаем
        if current_status == "running":
            try:
                container.restart(timeout=10)
            except docker.errors.APIError as e:
                return False, f"Не удалось перезапустить контейнер '{container_name}': {e}"
        else:
            # Если контейнер остановлен, просто запускаем
            try:
                container.start()
            except docker.errors.APIError as e:
                return False, f"Не удалось запустить контейнер '{container_name}': {e}"
        
        # Обновляем состояние
        try:
            container.reload()
        except Exception:
            pass
        
        status_after = container.status
        if status_after == "running":
            return True, f"Контейнер '{container_name}' успешно перезапущен."
        return False, f"Контейнер '{container_name}' не запущен после перезапуска (status='{status_after}')."
    except docker.errors.NotFound:
        return False, f"Контейнер '{container_name}' не найден."
    except Exception as e:
        return False, f"Ошибка при перезапуске контейнера '{container_name}': {e}"


def check_docker_container_status(container_name):
    # ... (код без изменений)
    global DOCKER_CLIENT
    if DOCKER_CLIENT is None:
        try:
            DOCKER_CLIENT = docker.from_env()
            DOCKER_CLIENT.ping()
            logger.info("Docker клиент успешно инициализирован.")
        except docker.errors.DockerException as e:
            logger.error(f"Ошибка инициализации Docker клиента: {e}. Проверки Docker будут недоступны.")
            DOCKER_CLIENT = "init_failed"
            return False, f"Ошибка Docker API: {e}"
        except Exception as e:
            logger.error(f"Непредвиденная ошибка при инициализации Docker клиента: {e}")
            DOCKER_CLIENT = "init_failed"
            return False, f"Ошибка инициализации Docker: {e}"

    if DOCKER_CLIENT == "init_failed":
        # Повторная попытка инициализации при следующих проверках (например, после старта Docker после перезагрузки)
        try:
            DOCKER_CLIENT = docker.from_env()
            DOCKER_CLIENT.ping()
            logger.info("Docker клиент успешно переинициализирован.")
        except Exception as e:
            logger.error(f"Не удалось переинициализировать Docker клиент: {e}")
            return False, "Docker клиент не инициализирован, проверка невозможна."

    logger.debug(f"Docker Check: Проверка контейнера '{container_name}'")
    try:
        container = DOCKER_CLIENT.containers.get(container_name)
        logger.debug(f"Docker Check: Контейнер '{container_name}', Статус: {container.status}")
        if container.status == "running":
            health = container.attrs.get('State', {}).get('Health', {}).get('Status')
            if health:
                logger.debug(f"Docker Check: Контейнер '{container_name}', Health: {health}")
                if health == "healthy":
                    return True, f"Контейнер '{container_name}' запущен и здоров (status: {container.status}, health: {health})."
                else:
                    return False, f"Контейнер '{container_name}' запущен, но не здоров (status: {container.status}, health: {health})."
            return True, f"Контейнер '{container_name}' запущен (status: {container.status})."
        else:
            # Контейнер не запущен — при необходимости пробуем перезапустить
            return False, f"Контейнер '{container_name}' не запущен (status: {container.status})."
    except docker.errors.NotFound:
        logger.warning(f"Docker Check: Контейнер '{container_name}' не найден.")
        return False, f"Контейнер '{container_name}' не найден."
    except docker.errors.APIError as e:
        logger.error(f"Docker Check: Ошибка API Docker при проверке '{container_name}': {e}")
        return False, f"Ошибка API Docker при проверке '{container_name}': {e}"
    except Exception as e:
        logger.error(f"Docker Check: Непредвиденная ошибка при проверке '{container_name}': {e}", exc_info=True)
        return False, f"Непредвиденная ошибка при проверке Docker контейнера '{container_name}': {e}"


def check_service(service_config):
    # ... (код без изменений)
    name = service_config["name"];
    check_type = service_config["type"];
    params = service_config["check_params"]
    is_ok, details_message = False, "Тип проверки не поддерживается/настроен"
    logger.info(f"Проверка: {name} ({check_type})")

    if check_type == "http":
        is_ok, details_message = check_http_endpoint(params["url"], params.get("expected_status", 200),
                                                     params.get("timeout", HTTP_TIMEOUT))  # Используем HTTP_TIMEOUT
    elif check_type == "docker_container_status":
        is_ok, details_message = check_docker_container_status(params["container_name"])
        # Если контейнер не запущен — пробуем автоперезапуск по политике и оперативно переоценим статус
        if not is_ok and _is_restart_allowed(name):
            logger.warning(f"Автоперезапуск: '{name}' (контейнер '{params['container_name']}') не запущен — пробую перезапустить...")
            restarted, restart_msg = _attempt_restart_container(params["container_name"])
            logger.warning(restart_msg)
            if restarted:
                # После успешного перезапуска считаем проверку успешной, чтобы не слать ложную тревогу
                is_ok, details_message = True, f"Автоперезапуск выполнен: {restart_msg}"

    logger.debug(f"Результат для '{name}': is_ok={is_ok}, details='{details_message}'")
    now = datetime.datetime.now();
    prev_status_info = SERVICE_STATUSES[name];
    prev_status = prev_status_info["status"]
    status_changed = False

    if is_ok:
        SERVICE_STATUSES[name]["status"] = "OK"
        if prev_status == "FAIL":
            raw_msg = f"✅ ВОССТАНОВЛЕНИЕ: '{name}' снова работает.\nДетали: {details_message}"
            send_telegram_message(escape_markdown_v2(raw_msg))
            status_changed = True
    else:
        SERVICE_STATUSES[name]["status"] = "FAIL"
        logger.warning(f"Проблема с '{name}': {details_message}")
        if prev_status != "FAIL":
            raw_msg = f"🚨 ПРОБЛЕМА: '{name}' не отвечает/некорректно!\nДетали: {details_message}"
            send_telegram_message(escape_markdown_v2(raw_msg))
            status_changed = True

    SERVICE_STATUSES[name]["last_message"] = details_message
    if status_changed or prev_status_info["last_event_time"] is None or prev_status == "UNKNOWN":
        SERVICE_STATUSES[name]["last_event_time"] = now
    
    # Сохраняем результат в БД
    save_service_check(name, SERVICE_STATUSES[name]["status"], details_message)
    
    logger.debug(f"Новый статус для '{name}': {SERVICE_STATUSES[name]['status']}")
    return is_ok, details_message


def perform_hourly_checks():
    # ... (код без изменений)
    logger.info("--- Ежечасная проверка ---");
    total = len(SERVICES_TO_MONITOR);
    ok_count = 0
    if not SERVICES_TO_MONITOR:
        logger.warning("Список сервисов для мониторинга пуст. Проверьте конфигурацию .env")
        return
    for conf in SERVICES_TO_MONITOR:
        if check_service(conf)[0]: ok_count += 1
    if ok_count == total:
        logger.info(f"Все {total} сервисов OK.")
    else:
        logger.warning(f"Проблемы: {total - ok_count} из {total} сервисов не OK.")
    logger.info("--- Ежечасная проверка завершена ---")


def generate_daily_report():
    # ... (код с исправлением SyntaxWarning, без других изменений)
    logger.info("--- Ежедневный отчет ---")
    report_lines = []
    report_header = f"📅 Ежедневный отчет о состоянии сервисов на {datetime.datetime.now():%Y-%m-%d %H:%M:%S}:\n"
    report_lines.append(report_header)

    all_systems_nominal = True
    if not SERVICES_TO_MONITOR:
        report_lines.append(escape_markdown_v2("Список сервисов для мониторинга пуст."))
    else:
        for service_name, data in SERVICE_STATUSES.items():
            status_emoji = "✅" if data['status'] == "OK" else ("❓" if data['status'] == "UNKNOWN" else "🚨")
            escaped_service_name = escape_markdown_v2(service_name)
            details_for_report = ""
            if data['status'] != "OK" and data['last_message']:
                msg_for_report = data['last_message']
                for pat in [
                    r"URL http://[^ ]+", r"URL https://[^ ]+",
                    r"\(сервис недоступен или отверг запрос\)\.",
                    r"\(status: [a-zA-Z0-9_-]+\)",
                    r"\(health: [a-zA-Z0-9_-]+\)\.",
                    r"Контейнер '[^']+' (не найден|не запущен|запущен, но не здоров)\.",
                    r"Ошибка API Docker при проверке '[^']+':.*",
                    r"\(timeout=\d+s\)\."
                ]:
                    try:
                        msg_for_report = re.sub(pat, "", msg_for_report, flags=re.IGNORECASE).strip()
                    except Exception as e_re:
                        logger.error(f"Ошибка re.sub: {e_re} для '{pat}' и '{msg_for_report}'")

                if len(msg_for_report) > 100:
                    msg_for_report = (msg_for_report.split('.')[0] if '.' in msg_for_report[:100] else msg_for_report[
                                                                                                       :100]) + "..."
                details_for_report = f" ({escape_markdown_v2(msg_for_report.strip())})" if msg_for_report.strip() else ""

            report_lines.append(f"{status_emoji} *{escaped_service_name}*: {data['status']}{details_for_report}")
            if data['status'] != "OK": all_systems_nominal = False

    summary_message = "\n" + (
        "👍 Все системы работают в штатном режиме." if all_systems_nominal else "⚠️ Обнаружены проблемы с некоторыми сервисами.")
    report_lines.append(escape_markdown_v2(summary_message))

    full_report_text = "\n".join(report_lines)
    send_telegram_message(full_report_text, use_markdown=True)
    logger.info("Ежедневный отчет отправлен.")


# --- TELEGRAM БОТ ДЛЯ РУЧНЫХ ПРОВЕРОК ---
def generate_status_report():
    """Генерирует отчет о состоянии сервисов для Telegram бота"""
    report_lines = []
    report_header = f"🔍 *Проверка сервисов* на {datetime.datetime.now():%H:%M:%S}:\n"
    report_lines.append(report_header)

    all_systems_nominal = True
    if not SERVICES_TO_MONITOR:
        report_lines.append("Список сервисов для мониторинга пуст.")
    else:
        for service_name, data in SERVICE_STATUSES.items():
            status_emoji = "✅" if data['status'] == "OK" else ("❓" if data['status'] == "UNKNOWN" else "🚨")
            escaped_service_name = escape_markdown_v2(service_name)
            details_for_report = ""
            if data['status'] != "OK" and data['last_message']:
                msg_for_report = data['last_message']
                # Упрощенная очистка сообщения для бота
                for pat in [r"URL http://[^ ]+", r"URL https://[^ ]+", r"\(status: [a-zA-Z0-9_-]+\)", r"\(health: [a-zA-Z0-9_-]+\)\."]:
                    try:
                        msg_for_report = re.sub(pat, "", msg_for_report, flags=re.IGNORECASE).strip()
                    except Exception:
                        pass
                if len(msg_for_report) > 50:
                    msg_for_report = msg_for_report[:50] + "..."
                details_for_report = f" ({escape_markdown_v2(msg_for_report.strip())})" if msg_for_report.strip() else ""

            report_lines.append(f"{status_emoji} *{escaped_service_name}*: {data['status']}{details_for_report}")
            if data['status'] != "OK": all_systems_nominal = False

    summary_message = "\n" + (
        "👍 Все системы работают в штатном режиме." if all_systems_nominal else "⚠️ Обнаружены проблемы с некоторыми сервисами.")
    report_lines.append(escape_markdown_v2(summary_message))

    return "\n".join(report_lines)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [
        [InlineKeyboardButton("🔍 Проверить сервисы", callback_data="check_services")],
        [InlineKeyboardButton("📊 Статус", callback_data="get_status")],
        [InlineKeyboardButton("🔄 Перезапустить контейнер", callback_data="restart_menu")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 *Мониторинг сервисов*\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /status"""
    report = generate_status_report()
    await update.message.reply_text(report, parse_mode='Markdown')


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /check - выполняет полную проверку"""
    await update.message.reply_text("🔄 Выполняю проверку сервисов...")
    
    # Выполняем проверку
    perform_hourly_checks()
    
    # Отправляем результат
    report = generate_status_report()
    await update.message.reply_text(report, parse_mode='Markdown')


async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reload - перезагружает конфигурацию"""
    await update.message.reply_text("🔄 Перезагружаю конфигурацию...")
    
    # Перезагружаем переменные окружения
    load_dotenv()
    
    # Обновляем список сервисов из БД
    global SERVICES_TO_MONITOR, SERVICE_STATUSES
    SERVICES_TO_MONITOR = load_services_from_db()
    SERVICE_STATUSES = {s["name"]: {"status": "UNKNOWN", "last_event_time": None, "last_message": "Еще не проверялся"} for s in SERVICES_TO_MONITOR}
    
    await update.message.reply_text(f"✅ Конфигурация перезагружена! Загружено {len(SERVICES_TO_MONITOR)} сервисов из БД.")


async def db_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /db - проверяет новые записи в БД"""
    if not DB_ENABLED:
        await update.message.reply_text("❌ Мониторинг БД отключен (DB_ENABLED=false)")
        return
    
    await update.message.reply_text("🔄 Проверяю новые записи в базе данных...")
    
    report = generate_db_report()
    await update.message.reply_text(report, parse_mode='Markdown')


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /restart - показывает меню выбора контейнера для перезапуска"""
    containers = get_monitored_containers()
    
    if not containers:
        await update.message.reply_text("❌ Нет Docker-контейнеров в мониторинге.")
        return
    
    keyboard = []
    for container_info in containers:
        service_name = escape_markdown_v2(container_info["name"])
        container_name = container_info["container_name"]
        # Используем короткое имя сервиса для кнопки, полное имя в callback_data
        button_text = f"🔄 {container_info['name']}"
        callback_data = f"restart_{container_name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="refresh")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔄 *Перезапуск контейнеров*\n\n"
        "Выберите контейнер для перезапуска:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help - показывает список всех команд с описанием"""
    help_text = """📖 *Справка по командам бота*

*Основные команды:*

/start \\- Главное меню с кнопками быстрого доступа

/status \\- Показать текущий статус всех сервисов

/check \\- Выполнить полную проверку всех сервисов

/restart \\- Перезапустить Docker\\-контейнер
   Выберите контейнер из списка для перезапуска

/reload \\- Перезагрузить конфигурацию из базы данных
   Обновляет список сервисов для мониторинга

/db \\- Проверить новые записи в базе данных
   Показывает статистику за последние 12 часов

/help \\- Показать эту справку

*Кнопки в меню:*

🔍 *Проверить сервисы* \\- Выполнить проверку всех сервисов

📊 *Статус* \\- Показать текущий статус

🔄 *Перезапустить контейнер* \\- Меню выбора контейнера для перезапуска

🔄 *Обновить* \\- Вернуться в главное меню"""
    
    await update.message.reply_text(help_text, parse_mode='MarkdownV2')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_services":
        await query.edit_message_text("🔄 Выполняю проверку сервисов...")
        perform_hourly_checks()
        report = generate_status_report()
        await query.edit_message_text(report, parse_mode='Markdown')
        
    elif query.data == "get_status":
        report = generate_status_report()
        await query.edit_message_text(report, parse_mode='Markdown')
        
    elif query.data == "restart_menu":
        containers = get_monitored_containers()
        
        if not containers:
            await query.edit_message_text("❌ Нет Docker-контейнеров в мониторинге.")
            return
        
        keyboard = []
        for container_info in containers:
            container_name = container_info["container_name"]
            button_text = f"🔄 {container_info['name']}"
            callback_data = f"restart_{container_name}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="refresh")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔄 *Перезапуск контейнеров*\n\n"
            "Выберите контейнер для перезапуска:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith("restart_"):
        container_name = query.data.replace("restart_", "")
        
        # Находим имя сервиса по container_name
        service_name = None
        for service in SERVICES_TO_MONITOR:
            if service["type"] == "docker_container_status":
                if service["check_params"].get("container_name") == container_name:
                    service_name = service["name"]
                    break
        
        display_name = service_name if service_name else container_name
        
        await query.edit_message_text(f"🔄 Перезапускаю контейнер '{escape_markdown_v2(display_name)}'...")
        
        success, message = restart_container(container_name)
        
        if success:
            result_text = f"✅ *Успешно*\n\n{escape_markdown_v2(message)}"
            # Обновляем статус сервиса после перезапуска
            if service_name:
                check_service(next(s for s in SERVICES_TO_MONITOR if s["name"] == service_name))
        else:
            result_text = f"❌ *Ошибка*\n\n{escape_markdown_v2(message)}"
        
        keyboard = [
            [InlineKeyboardButton("◀️ Назад к меню", callback_data="refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(result_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif query.data == "refresh":
        keyboard = [
            [InlineKeyboardButton("🔍 Проверить сервисы", callback_data="check_services")],
            [InlineKeyboardButton("📊 Статус", callback_data="get_status")],
            [InlineKeyboardButton("🔄 Перезапустить контейнер", callback_data="restart_menu")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 *Мониторинг сервисов*\n\n"
            "Выберите действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def start_telegram_bot():
    """Запуск Telegram бота"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не настроен, бот не запущен")
        return
    
    global TELEGRAM_APP
    TELEGRAM_APP = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчики
    TELEGRAM_APP.add_handler(CommandHandler("start", start_command))
    TELEGRAM_APP.add_handler(CommandHandler("status", status_command))
    TELEGRAM_APP.add_handler(CommandHandler("check", check_command))
    TELEGRAM_APP.add_handler(CommandHandler("reload", reload_command))
    TELEGRAM_APP.add_handler(CommandHandler("db", db_command))
    TELEGRAM_APP.add_handler(CommandHandler("restart", restart_command))
    TELEGRAM_APP.add_handler(CommandHandler("help", help_command))
    TELEGRAM_APP.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    await TELEGRAM_APP.initialize()
    await TELEGRAM_APP.start()
    await TELEGRAM_APP.updater.start_polling()
    logger.info("Telegram бот запущен и ожидает сообщения")


# --- ЗАПУСК ---
if __name__ == "__main__":
    # Инициализация логгера и базовых настроек
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(),
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)  # Переопределяем logger после basicConfig с уровнем из env

    # Проверка обязательных переменных окружения
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.critical("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не настроены в .env!")
        exit(1)

    if not SERVICES_TO_MONITOR:
        logger.warning("ВНИМАНИЕ: Не определено ни одного сервиса для мониторинга. Система будет работать в режиме ожидания.")
        # Не выходим из программы, продолжаем работу
    else:
        logger.info(f"Загружено {len(SERVICES_TO_MONITOR)} сервисов для мониторинга.")

    # Настройка расписания из .env или по умолчанию
    report_time_str = os.getenv("REPORT_TIME", "07:30")
    hourly_check_at_minute_str = os.getenv("CHECK_INTERVAL_HOURLY_AT", ":05")
    check_interval_seconds_str = os.getenv("CHECK_INTERVAL_SECONDS")

    # Инициализация базы данных
    if DB_ENABLED:
        init_database()
        
        # Загружаем сервисы из БД после инициализации
        SERVICES_TO_MONITOR = load_services_from_db()
        # Фильтруем сервисы, для которых не заданы параметры
        SERVICES_TO_MONITOR = [
            s for s in SERVICES_TO_MONITOR
            if (s["type"] == "http" and s["check_params"].get("url")) or \
               (s["type"] == "docker_container_status" and s["check_params"].get("container_name"))
        ]
        SERVICE_STATUSES = {s["name"]: {"status": "UNKNOWN", "last_event_time": None, "last_message": "Еще не проверялся"} for s in SERVICES_TO_MONITOR}
        
        logger.info(f"Загружено {len(SERVICES_TO_MONITOR)} сервисов из БД")
    else:
        logger.info("Мониторинг БД отключен (DB_ENABLED=false)")

    logger.info("Программа мониторинга запущена.")
    send_telegram_message("🚀 Мониторинг запущен!", use_markdown=False)

    logger.info("Первоначальная проверка...")
    perform_hourly_checks()
    logger.info("Проверка завершена.")

    if check_interval_seconds_str:
        try:
            interval = int(check_interval_seconds_str)
            schedule.every(interval).seconds.do(perform_hourly_checks)
            logger.info(f"Расписание: проверка каждые {interval} секунд (для отладки).")
        except ValueError:
            logger.error(
                f"Неверное значение для CHECK_INTERVAL_SECONDS: {check_interval_seconds_str}. Используется ежечасная проверка.")
            schedule.every().hour.at(hourly_check_at_minute_str).do(perform_hourly_checks)
            logger.info(f"Расписание: ежечасно в XX{hourly_check_at_minute_str}.")
    else:
        schedule.every().hour.at(hourly_check_at_minute_str).do(perform_hourly_checks)
        logger.info(f"Расписание: ежечасно в XX{hourly_check_at_minute_str}.")

    schedule.every().day.at(report_time_str).do(generate_daily_report)
    logger.info(f"Ежедневный отчет в {report_time_str}.")
    
    # Проверка новых записей в БД каждые 12 часов
    if DB_ENABLED:
        schedule.every(12).hours.do(lambda: send_telegram_message(generate_db_report(), use_markdown=True))
        logger.info("Проверка новых записей в БД каждые 12 часов.")

    # Запуск Telegram бота в отдельном потоке
    if TELEGRAM_BOT_ENABLED:
        def run_bot():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(start_telegram_bot())
            loop.run_forever()  # Держим бота активным
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logger.info("Telegram бот запущен в отдельном потоке")
    else:
        logger.info("Telegram бот отключен (TELEGRAM_BOT_ENABLED=false)")

    print("Мониторинг работает. Ctrl+C для выхода.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        send_telegram_message(escape_markdown_v2("🛑 Мониторинг остановлен."), use_markdown=True)
        logger.info("Остановлено вручную.")
        if TELEGRAM_APP:
            import asyncio
            asyncio.run(TELEGRAM_APP.stop())
    except Exception as e:
        raw_msg = f"🆘 КРИТИЧЕСКАЯ ОШИБКА МОНИТОРИНГА: {type(e).__name__} - {e}"
        logger.critical(raw_msg, exc_info=True)
        try:
            send_telegram_message(escape_markdown_v2(raw_msg), use_markdown=True)
        except Exception as te:
            logger.error(f"Не удалось отправить крит. ошибку в TG: {te}")