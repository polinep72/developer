"""
Скрипт для применения нормализованной схемы БД.
Применяет SQL-скрипт normalized_schema.sql к БД warehouse.

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
Лицензионные права: ИнноЦентр ВАО и ИПК Электрон-Маш
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

# Параметры подключения к БД
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'warehouse')


def log(message):
    """Вывод сообщения с временной меткой"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def apply_schema():
    """Применение нормализованной схемы БД"""
    
    try:
        # Подключение к БД
        log(f"Подключение к БД {DB_NAME} на {DB_HOST}...")
        conn = psycopg2.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        conn.autocommit = False
        cursor = conn.cursor()
        
        log("Подключение установлено")
        
        # Чтение SQL-скрипта
        script_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'normalized_schema.sql')
        script_path = os.path.abspath(script_path)
        
        if not os.path.exists(script_path):
            log(f"ОШИБКА: Файл {script_path} не найден!")
            sys.exit(1)
        
        log(f"Чтение SQL-скрипта: {script_path}")
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # Разделение скрипта на отдельные команды
        # Удаляем комментарии и разделяем по точкам с запятой
        commands = []
        current_command = []
        for line in sql_script.split('\n'):
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            current_command.append(line)
            if line.endswith(';'):
                command = ' '.join(current_command)
                if command:
                    commands.append(command)
                current_command = []
        
        # Выполнение команд
        log(f"\nПрименение схемы ({len(commands)} команд)...")
        for i, command in enumerate(commands, 1):
            try:
                log(f"  [{i}/{len(commands)}] Выполнение команды...")
                cursor.execute(command)
                log(f"  [OK] Команда {i} выполнена успешно")
            except psycopg2.Error as e:
                # Некоторые ошибки можно игнорировать (например, IF NOT EXISTS)
                if 'already exists' in str(e) or 'duplicate key' in str(e):
                    log(f"  [WARN] Команда {i}: объект уже существует (пропуск)")
                else:
                    log(f"  [ERROR] ОШИБКА в команде {i}: {e}")
                    raise
        
        # Проверка созданных таблиц
        log("\n=== Проверка созданных таблиц ===")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('типы_элементов', 'элементы')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        if len(tables) == 2:
            log("[OK] Обе таблицы созданы успешно:")
            for table in tables:
                log(f"  - {table[0]}")
        else:
            log(f"[WARN] Найдено таблиц: {len(tables)} (ожидалось 2)")
            for table in tables:
                log(f"  - {table[0]}")
        
        # Проверка типов элементов
        log("\n=== Проверка типов элементов ===")
        cursor.execute("SELECT id, код, название FROM типы_элементов ORDER BY код")
        types = cursor.fetchall()
        
        if len(types) == 3:
            log("[OK] Типы элементов созданы:")
            for type_id, code, name in types:
                log(f"  - {code} ({name}): id={type_id}")
        else:
            log(f"[WARN] Найдено типов: {len(types)} (ожидалось 3)")
            for type_id, code, name in types:
                log(f"  - {code} ({name}): id={type_id}")
        
        # Подтверждение транзакции
        conn.commit()
        log("\n[OK] Схема применена успешно!")
        log("Транзакция зафиксирована")
        
    except psycopg2.Error as e:
        log(f"\n[ERROR] ОШИБКА БД: {e}")
        if conn:
            conn.rollback()
            log("Транзакция отменена")
        sys.exit(1)
    except Exception as e:
        log(f"\n[ERROR] ОШИБКА: {e}")
        if conn:
            conn.rollback()
            log("Транзакция отменена")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            log("Подключение закрыто")


if __name__ == "__main__":
    log("=== Применение нормализованной схемы БД ===")
    apply_schema()
    log("=== Готово ===")
