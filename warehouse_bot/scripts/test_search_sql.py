"""
Тестирует поисковый SQL (как в боте) напрямую к БД для указанного term.

Запуск:
  set TERM_QUERY=пс2у
  python scripts/test_search_sql.py
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

    # Важно: в Windows/PowerShell переменные окружения с кириллицей могут приходить битые по кодировке,
    # поэтому для диагностики используем литерал (UTF-8 в исходнике).
    term = "пс2у"
    pattern = f"%{term}%"

    conn = psycopg2.connect(host=db_host, user=db_user, password=db_password, dbname=db_name)
    cur = conn.cursor()

    try:
        log(f"DB: {db_host}/{db_name}")
        log(f"TERM_QUERY: {term}")

        cur.execute("select id from element_types where code='pp'")
        pp_type_id = cur.fetchone()[0]

        # Query (has_pp=True) аналогичный боту (упрощенный вывод)
        cur.execute(
            """
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
                e.name,
                c.chip_code,
                b.body_type,
                pp.pp_code,
                ib.balance,
                ad.date,
                i.invoice_id
            FROM item_balances ib
            LEFT JOIN elements e ON ib.name_id = e.legacy_name_id AND e.element_type_id = %s
            LEFT JOIN chips c ON ib.chip_id = c.id
            LEFT JOIN bodies b ON ib.body_id = b.id
            LEFT JOIN pp ON ib.pp_id = pp.id
            LEFT JOIN arrival_dates ad ON ib.arrival_date_id = ad.id
            LEFT JOIN invoice i ON ib.invoice_id = i.id
            WHERE (
                e.name ILIKE %s OR c.chip_code ILIKE %s
            )
            ORDER BY ad.date ASC
            """,
            (pp_type_id, pp_type_id, pp_type_id, pattern, pattern),
        )

        rows = cur.fetchall()
        log(f"rows: {len(rows)}")
        for r in rows[:5]:
            log(f"sample: {r}")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

