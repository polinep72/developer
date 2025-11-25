"""
Скрипт для установки временных паролей существующим пользователям.

Пароль задаётся через переменную окружения TEMP_USER_PASSWORD (по умолчанию TempPass123!).
Пароли хешируются с помощью bcrypt и записываются в таблицу users БД RM.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from passlib.context import CryptContext


def load_env() -> None:
    """Загружаем .env из корня проекта, если он существует."""
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def get_db_connection() -> psycopg.Connection:
    """Создаёт подключение к БД RM, используя переменные окружения."""
    host = os.getenv("POSTGRE_HOST") or os.getenv("DB_HOST") or "192.168.1.139"
    port = os.getenv("POSTGRE_PORT") or os.getenv("DB_PORT") or "5432"
    user = os.getenv("POSTGRE_USER") or os.getenv("DB_USER") or "postgres"
    password = os.getenv("POSTGRE_PASSWORD") or os.getenv("DB_PASSWORD") or "27915002"
    dbname = os.getenv("POSTGRE_DBNAME") or os.getenv("DB_NAME") or "RM"

    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
    )


def main() -> None:
    load_env()

    temp_password = os.getenv("TEMP_USER_PASSWORD", "TempPass123!")
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    hashed_temp_password = pwd_context.hash(temp_password)

    conn = get_db_connection()
    updated = 0

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT users_id
                FROM users
                WHERE password_hash IS NULL OR password_hash = ''
                """
            )
            rows = cur.fetchall()

            if not rows:
                print("Нет пользователей без пароля. Изменений не требуется.")
                return

            for (user_id,) in rows:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE users_id = %s",
                    (hashed_temp_password, user_id),
                )
                updated += 1

        conn.commit()
        print(
            f"Установлен временный пароль для {updated} пользовател(я/ей). "
            f"Пароль: {temp_password}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()


