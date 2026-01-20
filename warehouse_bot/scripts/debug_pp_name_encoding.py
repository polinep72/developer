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

# берем одну запись из invoice_pp с остатком (quan) и печатаем соответствующее имя из names_pp
cur.execute(
    """
    select inv.id, inv.name_id, (select name from names_pp n where n.id=inv.name_id) as name
    from invoice_pp inv
    order by inv.id desc
    limit 1
    """
)
row = cur.fetchone()
print("invoice_pp sample:", row)

name = row[2] if row else None
if name:
    print("name repr:", repr(name))
    print("codepoints:", [hex(ord(ch)) for ch in name])

term = os.getenv("TERM_QUERY", "пс2у")
print("term repr:", repr(term))
print("term codepoints:", [hex(ord(ch)) for ch in term])

cur.close()
conn.close()

