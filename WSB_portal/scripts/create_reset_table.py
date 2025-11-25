import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(
    host=os.getenv("POSTGRE_HOST", "192.168.1.139"),
    port=os.getenv("POSTGRE_PORT", "5432"),
    user=os.getenv("POSTGRE_USER", "postgres"),
    password=os.getenv("POSTGRE_PASSWORD", "27915002"),
    dbname=os.getenv("POSTGRE_DBNAME", "RM"),
)

with conn.cursor() as cur:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(users_id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            used BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
        """
    )
conn.commit()
conn.close()

print("password_reset_tokens table ensured.")


