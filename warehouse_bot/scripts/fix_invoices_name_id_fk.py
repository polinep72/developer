"""
Скрипт для удаления внешнего ключа name_id из таблиц invoices и consumptions.
Так как в старых данных могут быть ссылки на несуществующие записи.

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


def fix_foreign_keys():
    """Удаление внешнего ключа name_id"""
    
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
        
        log("Подключение установлено\n")
        
        # Проверка и удаление внешних ключей
        log("=== Удаление внешних ключей name_id ===")
        
        # Проверка существования FK для invoices
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
            AND table_name = 'invoices'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%name_id%'
        """)
        
        fk_invoices = cursor.fetchall()
        if fk_invoices:
            for fk in fk_invoices:
                log(f"Удаление FK {fk[0]} из таблицы invoices...")
                cursor.execute(f"ALTER TABLE invoices DROP CONSTRAINT IF EXISTS {fk[0]}")
                log(f"[OK] FK {fk[0]} удален")
        else:
            log("[OK] FK name_id в таблице invoices не найден (уже удален или не создан)")
        
        # Проверка существования FK для consumptions
        cursor.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
            AND table_name = 'consumptions'
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%name_id%'
        """)
        
        fk_consumptions = cursor.fetchall()
        if fk_consumptions:
            for fk in fk_consumptions:
                log(f"Удаление FK {fk[0]} из таблицы consumptions...")
                cursor.execute(f"ALTER TABLE consumptions DROP CONSTRAINT IF EXISTS {fk[0]}")
                log(f"[OK] FK {fk[0]} удален")
        else:
            log("[OK] FK name_id в таблице consumptions не найден (уже удален или не создан)")
        
        # Подтверждение транзакции
        conn.commit()
        log("\n[OK] Внешние ключи удалены успешно!")
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
    log("=== Удаление внешних ключей name_id ===")
    fix_foreign_keys()
    log("=== Готово ===")
