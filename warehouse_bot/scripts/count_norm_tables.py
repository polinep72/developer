"""
Быстрая проверка наполненности нормализованных таблиц на текущей БД.
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

for tbl in ["elements", "element_types", "invoices", "consumptions", "invoice_pp", "consumption_pp", "names_pp"]:
    cur.execute(f"select count(*) from {tbl}")
    print(f"{tbl}: {cur.fetchone()[0]}")

cur.execute("select id, code from element_types order by id")
print("element_types:", cur.fetchall())

cur.close()
conn.close()

