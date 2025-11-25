import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

def connect():
    return psycopg.connect(
        host=os.getenv("POSTGRE_HOST", "192.168.1.139"),
        port=os.getenv("POSTGRE_PORT", "5432"),
        user=os.getenv("POSTGRE_USER", "postgres"),
        password=os.getenv("POSTGRE_PASSWORD", "27915002"),
        dbname=os.getenv("POSTGRE_DBNAME", "RM"),
        row_factory=psycopg.rows.dict_row,
    )

def show_columns():
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position
            """
        )
        print("Columns:", cur.fetchall())
    conn.close()

def find_user(phone_digits: str):
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT users_id, first_name, last_name, phone, email, password_hash, is_admin
            FROM users
            WHERE regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') = %s
            """,
            (phone_digits,),
        )
        print("Users:", cur.fetchall())
    conn.close()

if __name__ == "__main__":
    show_columns()
    find_user("79154588259")


