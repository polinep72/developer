"""
Показывает ограничения/внешние ключи для invoices/consumptions.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    dbname=os.getenv("DB_NAME"),
)
cur = conn.cursor()

for tbl in ["invoices", "consumptions"]:
    print("\n===", tbl, "===")
    cur.execute(
        """
        select constraint_name, constraint_type
        from information_schema.table_constraints
        where table_schema='public' and table_name=%s
        order by constraint_type, constraint_name
        """,
        (tbl,),
    )
    for name, ctype in cur.fetchall():
        print(" ", ctype, name)

    cur.execute(
        """
        select kcu.constraint_name, kcu.column_name,
               ccu.table_name as foreign_table_name, ccu.column_name as foreign_column_name
        from information_schema.key_column_usage kcu
        join information_schema.constraint_column_usage ccu on ccu.constraint_name = kcu.constraint_name
        join information_schema.table_constraints tc on tc.constraint_name = kcu.constraint_name
        where tc.table_schema='public' and tc.table_name=%s and tc.constraint_type='FOREIGN KEY'
        order by kcu.constraint_name, kcu.ordinal_position
        """,
        (tbl,),
    )
    fks = cur.fetchall()
    if fks:
        print("  FK details:")
        for row in fks:
            print("   ", row)
    else:
        print("  FK details: none")

cur.close()
conn.close()

