"""
Ремап name_id в нормализованных таблицах invoices/consumptions:

Проблема:
- invoices.name_id и consumptions.name_id были перенесены из старых tables names_* (id bigint, отдельные sequence),
  а elements.id — новый SERIAL, поэтому JOIN на elements по id не работает.

Решение:
- Добавляем legacy_name_id (BIGINT) и сохраняем туда старые значения name_id
- Пересчитываем name_id -> elements.id по совпадению имени (names_*.name == elements.name) и типа (element_type_id)

Автор: Полин Е.П. (@PolinEP)
Соразработчик: Cursor
Лицензионные права: ИнноЦентр ВАО и ИПК Электрон-Маш
"""

from __future__ import annotations

import os
from datetime import datetime

import psycopg2
from dotenv import load_dotenv


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def main() -> None:
    load_dotenv()
    db_host = os.getenv("DB_HOST", "localhost")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "warehouse")

    conn = psycopg2.connect(host=db_host, user=db_user, password=db_password, dbname=db_name)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        log(f"DB: {db_host}/{db_name}")

        # 1) Ensure legacy columns exist
        log("Проверка/добавление legacy_name_id ...")
        cur.execute(
            """
            ALTER TABLE invoices ADD COLUMN IF NOT EXISTS legacy_name_id BIGINT;
            ALTER TABLE consumptions ADD COLUMN IF NOT EXISTS legacy_name_id BIGINT;
            """
        )

        # 2) Fill legacy columns where empty
        log("Сохранение старых name_id в legacy_name_id ...")
        cur.execute("UPDATE invoices SET legacy_name_id = name_id WHERE legacy_name_id IS NULL AND name_id IS NOT NULL;")
        inv_legacy = cur.rowcount
        cur.execute(
            "UPDATE consumptions SET legacy_name_id = name_id WHERE legacy_name_id IS NULL AND name_id IS NOT NULL;"
        )
        cons_legacy = cur.rowcount
        log(f"invoices: legacy_name_id заполнено для {inv_legacy} строк")
        log(f"consumptions: legacy_name_id заполнено для {cons_legacy} строк")

        # Helper: remap per type
        def remap_for_type(type_code: str, names_table: str) -> None:
            log(f"Ремап для типа {type_code} через {names_table} ...")

            # invoices
            cur.execute(
                f"""
                UPDATE invoices i
                SET name_id = e.id
                FROM element_types t
                JOIN {names_table} n ON TRUE
                JOIN elements e ON e.element_type_id = t.id AND e.name = n.name
                WHERE i.element_type_id = t.id
                  AND t.code = %s
                  AND i.legacy_name_id IS NOT NULL
                  AND n.id = i.legacy_name_id
                  AND (i.name_id IS DISTINCT FROM e.id)
                """,
                (type_code,),
            )
            log(f"invoices updated: {cur.rowcount}")

            # consumptions
            cur.execute(
                f"""
                UPDATE consumptions c
                SET name_id = e.id
                FROM element_types t
                JOIN {names_table} n ON TRUE
                JOIN elements e ON e.element_type_id = t.id AND e.name = n.name
                WHERE c.element_type_id = t.id
                  AND t.code = %s
                  AND c.legacy_name_id IS NOT NULL
                  AND n.id = c.legacy_name_id
                  AND (c.name_id IS DISTINCT FROM e.id)
                """,
                (type_code,),
            )
            log(f"consumptions updated: {cur.rowcount}")

            # diagnostics: how many still not mapped (legacy exists but no element match)
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM invoices i
                JOIN element_types t ON t.id = i.element_type_id
                LEFT JOIN {names_table} n ON n.id = i.legacy_name_id
                LEFT JOIN elements e ON e.element_type_id = t.id AND e.name = n.name
                WHERE t.code = %s
                  AND i.legacy_name_id IS NOT NULL
                  AND e.id IS NULL
                """,
                (type_code,),
            )
            missing_inv = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM consumptions c
                JOIN element_types t ON t.id = c.element_type_id
                LEFT JOIN {names_table} n ON n.id = c.legacy_name_id
                LEFT JOIN elements e ON e.element_type_id = t.id AND e.name = n.name
                WHERE t.code = %s
                  AND c.legacy_name_id IS NOT NULL
                  AND e.id IS NULL
                """,
                (type_code,),
            )
            missing_cons = cur.fetchone()[0]
            log(f"unmapped invoices: {missing_inv}")
            log(f"unmapped consumptions: {missing_cons}")

        remap_for_type("ms", "names_ms")
        remap_for_type("m", "names_m")
        remap_for_type("pp", "names_pp")

        conn.commit()
        log("[OK] Ремап завершен, транзакция зафиксирована")

    except Exception as e:
        conn.rollback()
        log(f"[ERROR] {type(e).__name__}: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

