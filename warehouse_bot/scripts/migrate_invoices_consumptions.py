"""
Скрипт миграции данных из invoice_* и consumption_* в нормализованные таблицы invoices и consumptions.
Унифицирует формирование item_id и добавляет element_type_id.

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
Лицензионные права: ИнноЦентр ВАО и ИПК Электрон-Маш
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
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


def generate_unified_item_id(invoice_id, name_id, chip_id, body_id, pp_id, arrival_date_id):
    """
    Генерация унифицированного item_id.
    Формат: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id
    Для микросхем pp_id заменяется на '0' (вместо NULL)
    """
    pp_val = str(pp_id) if pp_id is not None else '0'
    return f"{invoice_id}-{name_id}-{chip_id}-{body_id}-{pp_val}-{arrival_date_id}"


def migrate_invoices():
    """Миграция данных из invoice_* в invoices"""
    
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
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        log("Подключение установлено\n")
        
        # 1. Проверка существования нормализованной структуры
        log("=== Проверка нормализованной структуры ===")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'invoices'
            )
        """)
        if not cursor.fetchone()['exists']:
            log("[ERROR] Таблица 'invoices' не найдена!")
            log("Сначала выполните SQL-скрипт: database/normalized_invoices_consumptions.sql")
            sys.exit(1)
        
        # 2. Получение ID типов элементов
        log("\n=== Получение ID типов элементов ===")
        cursor.execute("SELECT id, code FROM element_types")
        type_map = {row['code']: row['id'] for row in cursor.fetchall()}
        log(f"Найдены типы: {type_map}")
        
        if 'ms' not in type_map or 'm' not in type_map or 'pp' not in type_map:
            log("[ERROR] Не все типы элементов найдены в таблице element_types!")
            sys.exit(1)
        
        # 3. Миграция invoice_ms
        log("\n=== Миграция invoice_ms (Микросхемы) ===")
        cursor.execute("SELECT COUNT(*) as count FROM invoice_ms")
        ms_count = cursor.fetchone()['count']
        log(f"Найдено записей в invoice_ms: {ms_count}")
        
        cursor.execute("""
            INSERT INTO invoices (
                element_type_id, invoice_id, name_id, chip_id, body_id, pp_id,
                date, arrival_date_id, quan, defect_products, cond_suit_products,
                quantity, item_id, purpose, note, date_time_entry,
                user_entry_id, file_name_entry
            )
            SELECT 
                %s as element_type_id,
                inv.invoice_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                NULL as pp_id,  -- Для микросхем pp_id всегда NULL
                inv.date,
                inv.arrival_date_id,
                inv.quan,
                inv.defect_products,
                inv.cond_suit_products,
                inv.quantity,
                -- Генерация унифицированного item_id: invoice_id-name_id-chip_id-body_id-0-arrival_date_id
                (inv.invoice_id::text || '-' || 
                 COALESCE(inv.name_id::text, '0') || '-' || 
                 COALESCE(inv.chip_id::text, '0') || '-' || 
                 COALESCE(inv.body_id::text, '0') || '-0-' || 
                 inv.arrival_date_id::text) as item_id,
                inv.purpose,
                inv.note,
                inv.date_time_entry,
                inv.user_entry_id,
                inv.file_name_entry
            FROM invoice_ms inv
            WHERE NOT EXISTS (
                SELECT 1 FROM invoices 
                WHERE element_type_id = %s 
                AND invoice_id = inv.invoice_id
                AND name_id = inv.name_id
                AND chip_id = inv.chip_id
                AND body_id = inv.body_id
                AND pp_id IS NULL
                AND arrival_date_id = inv.arrival_date_id
            )
        """, (type_map['ms'], type_map['ms']))
        
        ms_inserted = cursor.rowcount
        log(f"Мигрировано записей из invoice_ms: {ms_inserted}")
        
        # 4. Миграция invoice_m
        log("\n=== Миграция invoice_m (Модули) ===")
        cursor.execute("SELECT COUNT(*) as count FROM invoice_m")
        m_count = cursor.fetchone()['count']
        log(f"Найдено записей в invoice_m: {m_count}")
        
        cursor.execute("""
            INSERT INTO invoices (
                element_type_id, invoice_id, name_id, chip_id, body_id, pp_id,
                date, arrival_date_id, quan, defect_products, cond_suit_products,
                quantity, item_id, purpose, note, date_time_entry,
                user_entry_id, file_name_entry
            )
            SELECT 
                %s as element_type_id,
                inv.invoice_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                inv.pp_id,
                inv.date,
                inv.arrival_date_id,
                inv.quan,
                inv.defect_products,
                inv.cond_suit_products,
                inv.quantity,
                -- Генерация унифицированного item_id: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id
                (inv.invoice_id::text || '-' || 
                 COALESCE(inv.name_id::text, '0') || '-' || 
                 COALESCE(inv.chip_id::text, '0') || '-' || 
                 COALESCE(inv.body_id::text, '0') || '-' || 
                 COALESCE(inv.pp_id::text, '0') || '-' || 
                 inv.arrival_date_id::text) as item_id,
                inv.purpose,
                inv.note,
                inv.date_time_entry,
                inv.user_entry_id,
                inv.file_name_entry
            FROM invoice_m inv
            WHERE NOT EXISTS (
                SELECT 1 FROM invoices 
                WHERE element_type_id = %s 
                AND invoice_id = inv.invoice_id
                AND COALESCE(name_id, 0) = COALESCE(inv.name_id, 0)
                AND COALESCE(chip_id, 0) = COALESCE(inv.chip_id, 0)
                AND COALESCE(body_id, 0) = COALESCE(inv.body_id, 0)
                AND COALESCE(pp_id, 0) = COALESCE(inv.pp_id, 0)
                AND arrival_date_id = inv.arrival_date_id
            )
        """, (type_map['m'], type_map['m']))
        
        m_inserted = cursor.rowcount
        log(f"Мигрировано записей из invoice_m: {m_inserted}")
        
        # 5. Миграция invoice_pp
        log("\n=== Миграция invoice_pp (ПП) ===")
        cursor.execute("SELECT COUNT(*) as count FROM invoice_pp")
        pp_count = cursor.fetchone()['count']
        log(f"Найдено записей в invoice_pp: {pp_count}")
        
        cursor.execute("""
            INSERT INTO invoices (
                element_type_id, invoice_id, name_id, chip_id, body_id, pp_id,
                date, arrival_date_id, quan, defect_products, cond_suit_products,
                quantity, item_id, purpose, note, date_time_entry,
                user_entry_id, file_name_entry
            )
            SELECT 
                %s as element_type_id,
                inv.invoice_id,
                inv.name_id,
                inv.chip_id,
                inv.body_id,
                inv.pp_id,
                inv.date,
                inv.arrival_date_id,
                inv.quan,
                inv.defect_products,
                inv.cond_suit_products,
                inv.quantity,
                -- Генерация унифицированного item_id: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id
                (inv.invoice_id::text || '-' || 
                 COALESCE(inv.name_id::text, '0') || '-' || 
                 COALESCE(inv.chip_id::text, '0') || '-' || 
                 COALESCE(inv.body_id::text, '0') || '-' || 
                 COALESCE(inv.pp_id::text, '0') || '-' || 
                 inv.arrival_date_id::text) as item_id,
                inv.purpose,
                inv.note,
                inv.date_time_entry,
                inv.user_entry_id,
                inv.file_name_entry
            FROM invoice_pp inv
            WHERE NOT EXISTS (
                SELECT 1 FROM invoices 
                WHERE element_type_id = %s 
                AND invoice_id = inv.invoice_id
                AND COALESCE(name_id, 0) = COALESCE(inv.name_id, 0)
                AND COALESCE(chip_id, 0) = COALESCE(inv.chip_id, 0)
                AND COALESCE(body_id, 0) = COALESCE(inv.body_id, 0)
                AND COALESCE(pp_id, 0) = COALESCE(inv.pp_id, 0)
                AND arrival_date_id = inv.arrival_date_id
            )
        """, (type_map['pp'], type_map['pp']))
        
        pp_inserted = cursor.rowcount
        log(f"Мигрировано записей из invoice_pp: {pp_inserted}")
        
        # 6. Миграция consumption_ms
        log("\n=== Миграция consumption_ms (Микросхемы) ===")
        cursor.execute("SELECT COUNT(*) as count FROM consumption_ms")
        ms_cons_count = cursor.fetchone()['count']
        log(f"Найдено записей в consumption_ms: {ms_cons_count}")
        
        cursor.execute("""
            INSERT INTO consumptions (
                element_type_id, invoice_id, name_id, chip_id, body_id, pp_id,
                date, arrival_date_id, quantity, item_id, consumer_name,
                purpose, note, date_time_entry, user_entry_id, file_name_entry
            )
            SELECT 
                %s as element_type_id,
                cons.invoice_id,
                cons.name_id,
                cons.chip_id,
                cons.body_id,
                NULL as pp_id,  -- Для микросхем pp_id всегда NULL
                cons.date,
                cons.arrival_date_id,
                cons.quantity,
                -- Генерация унифицированного item_id
                (cons.invoice_id::text || '-' || 
                 COALESCE(cons.name_id::text, '0') || '-' || 
                 COALESCE(cons.chip_id::text, '0') || '-' || 
                 COALESCE(cons.body_id::text, '0') || '-0-' || 
                 cons.arrival_date_id::text) as item_id,
                cons.consumer_name,
                cons.purpose,
                cons.note,
                cons.date_time_entry,
                cons.user_entry_id,
                cons.file_name_entry
            FROM consumption_ms cons
        """, (type_map['ms'],))
        
        ms_cons_inserted = cursor.rowcount
        log(f"Мигрировано записей из consumption_ms: {ms_cons_inserted}")
        
        # 7. Миграция consumption_m
        log("\n=== Миграция consumption_m (Модули) ===")
        cursor.execute("SELECT COUNT(*) as count FROM consumption_m")
        m_cons_count = cursor.fetchone()['count']
        log(f"Найдено записей в consumption_m: {m_cons_count}")
        
        cursor.execute("""
            INSERT INTO consumptions (
                element_type_id, invoice_id, name_id, chip_id, body_id, pp_id,
                date, arrival_date_id, quantity, item_id, consumer_name,
                purpose, note, date_time_entry, user_entry_id, file_name_entry
            )
            SELECT 
                %s as element_type_id,
                cons.invoice_id,
                cons.name_id,
                cons.chip_id,
                cons.body_id,
                cons.pp_id,
                cons.date,
                cons.arrival_date_id,
                cons.quantity,
                -- Генерация унифицированного item_id
                (cons.invoice_id::text || '-' || 
                 COALESCE(cons.name_id::text, '0') || '-' || 
                 COALESCE(cons.chip_id::text, '0') || '-' || 
                 COALESCE(cons.body_id::text, '0') || '-' || 
                 COALESCE(cons.pp_id::text, '0') || '-' || 
                 cons.arrival_date_id::text) as item_id,
                cons.consumer_name,
                cons.purpose,
                cons.note,
                cons.date_time_entry,
                cons.user_entry_id,
                cons.file_name_entry
            FROM consumption_m cons
        """, (type_map['m'],))
        
        m_cons_inserted = cursor.rowcount
        log(f"Мигрировано записей из consumption_m: {m_cons_inserted}")
        
        # 8. Миграция consumption_pp
        log("\n=== Миграция consumption_pp (ПП) ===")
        cursor.execute("SELECT COUNT(*) as count FROM consumption_pp")
        pp_cons_count = cursor.fetchone()['count']
        log(f"Найдено записей в consumption_pp: {pp_cons_count}")
        
        cursor.execute("""
            INSERT INTO consumptions (
                element_type_id, invoice_id, name_id, chip_id, body_id, pp_id,
                date, arrival_date_id, quantity, item_id, consumer_name,
                purpose, note, date_time_entry, user_entry_id, file_name_entry
            )
            SELECT 
                %s as element_type_id,
                cons.invoice_id,
                cons.name_id,
                cons.chip_id,
                cons.body_id,
                cons.pp_id,
                cons.date,
                cons.arrival_date_id,
                cons.quantity,
                -- Генерация унифицированного item_id
                (cons.invoice_id::text || '-' || 
                 COALESCE(cons.name_id::text, '0') || '-' || 
                 COALESCE(cons.chip_id::text, '0') || '-' || 
                 COALESCE(cons.body_id::text, '0') || '-' || 
                 COALESCE(cons.pp_id::text, '0') || '-' || 
                 cons.arrival_date_id::text) as item_id,
                cons.consumer_name,
                cons.purpose,
                cons.note,
                cons.date_time_entry,
                cons.user_entry_id,
                cons.file_name_entry
            FROM consumption_pp cons
        """, (type_map['pp'],))
        
        pp_cons_inserted = cursor.rowcount
        log(f"Мигрировано записей из consumption_pp: {pp_cons_inserted}")
        
        # 9. Проверка миграции
        log("\n=== Проверка миграции ===")
        cursor.execute("""
            SELECT 
                et.code,
                et.name,
                COUNT(inv.id) as invoice_count
            FROM element_types et
            LEFT JOIN invoices inv ON inv.element_type_id = et.id
            GROUP BY et.id, et.code, et.name
            ORDER BY et.code
        """)
        
        log("Приход по типам:")
        for row in cursor.fetchall():
            log(f"  {row['code']} ({row['name']}): {row['invoice_count']} записей")
        
        cursor.execute("""
            SELECT 
                et.code,
                et.name,
                COUNT(cons.id) as consumption_count
            FROM element_types et
            LEFT JOIN consumptions cons ON cons.element_type_id = et.id
            GROUP BY et.id, et.code, et.name
            ORDER BY et.code
        """)
        
        log("\nРасход по типам:")
        for row in cursor.fetchall():
            log(f"  {row['code']} ({row['name']}): {row['consumption_count']} записей")
        
        # 10. Сравнение количества
        log("\n=== Сравнение количества ===")
        cursor.execute("SELECT COUNT(*) as count FROM invoice_ms")
        original_ms = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM invoices WHERE element_type_id = %s", (type_map['ms'],))
        migrated_ms = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM invoice_m")
        original_m = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM invoices WHERE element_type_id = %s", (type_map['m'],))
        migrated_m = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM invoice_pp")
        original_pp = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM invoices WHERE element_type_id = %s", (type_map['pp'],))
        migrated_pp = cursor.fetchone()['count']
        
        log(f"Приход: ms={original_ms}->{migrated_ms}, m={original_m}->{migrated_m}, pp={original_pp}->{migrated_pp}")
        
        total_original = original_ms + original_m + original_pp
        total_migrated = migrated_ms + migrated_m + migrated_pp
        log(f"Всего приход: {total_original}->{total_migrated}")
        
        if total_original == total_migrated:
            log("[OK] Миграция прихода завершена успешно!")
        else:
            log("[WARN] ВНИМАНИЕ: Количество записей прихода не совпадает!")
        
        # Подтверждение транзакции
        conn.commit()
        log("\n[OK] Миграция завершена успешно!")
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
    log("=== Миграция invoice_* и consumption_* в нормализованные таблицы ===")
    migrate_invoices()
    log("=== Готово ===")
