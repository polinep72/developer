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
cur.execute(
    """
    select column_name, data_type
    from information_schema.columns
    where table_schema='public' and table_name='elements'
    order by ordinal_position
    """
)
print(cur.fetchall())
cur.close()
conn.close()

