import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import psycopg
from jose import jwt, JWTError
from passlib.context import CryptContext
from psycopg.rows import dict_row
from dotenv import load_dotenv
from typing import cast

# Загружаем .env только если переменные окружения не заданы
# Это позволяет использовать env_file из docker-compose с приоритетом
if not os.getenv("POSTGRE_USER") and not os.getenv("DB_USER"):
    load_dotenv(override=False)  # override=False - не перезаписывать существующие переменные

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_env(primary: str, fallback: str | None = None, default: str | None = None) -> str | None:
    value = os.getenv(primary)
    if value:
        return value
    if fallback:
        value = os.getenv(fallback)
        if value:
            return value
    return default


DB_USER = _get_env("DB_USER", "POSTGRE_USER")
DB_PASSWORD = _get_env("DB_PASSWORD", "POSTGRE_PASSWORD")
DB_NAME = _get_env("DB_NAME", "POSTGRE_DBNAME", "RM")
DB_HOST = _get_env("DB_HOST", "POSTGRE_HOST", "localhost")
DB_PORT = _get_env("DB_PORT", "POSTGRE_PORT", "5432")
DB_SSLMODE = _get_env("DB_SSLMODE", None, "prefer")

AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev-secret-key")
AUTH_ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_ACCESS_MINUTES", "720"))
RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_RESET_MINUTES", "60"))


def _connect():
    params = {
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "sslmode": DB_SSLMODE,
        "connect_timeout": 5,
        "row_factory": dict_row,
    }
    return psycopg.connect(**params)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=AUTH_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
    return cast(Dict[str, Any], payload)


def _normalize_phone(login: str) -> str:
    return "".join(ch for ch in login if ch.isdigit())


def get_user_by_login(login: str) -> Optional[Dict[str, Any]]:
    if not login:
        return None

    stripped = login.strip()
    lower_login = stripped.lower()
    normalized_phone = _normalize_phone(stripped)

    normalized = normalized_phone or ""
    params: list[Any] = [
        stripped,
        normalized,
        normalized,
        lower_login,
    ]

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                SELECT users_id, first_name, last_name, phone, email, password_hash, is_admin
                FROM users
                WHERE (phone = %s)
                   OR (%s <> '' AND regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') = %s)
                   OR (LOWER(email) = %s)
                LIMIT 1
                """,
                tuple(params),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                SELECT users_id, first_name, last_name, phone, email, password_hash, is_admin
                FROM users
                WHERE users_id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["users_id"],
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "phone": user.get("phone"),
        "email": user.get("email"),
        "is_admin": bool(user.get("is_admin")),
    }


def update_user_password(user_id: int, new_hash: str) -> None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                "UPDATE users SET password_hash = %s WHERE users_id = %s",
                (new_hash, user_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_user_profile(
    user_id: int,
    first_name: str,
    last_name: str,
    phone: Optional[str],
    email: Optional[str],
) -> Dict[str, Any]:
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    phone_value = phone.strip() if phone and phone.strip() else None
    email_value = email.strip() if email and email.strip() else None

    if not first_name or not last_name:
        return {"error": "Имя и фамилия обязательны для заполнения"}

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                UPDATE users
                SET first_name = %s,
                    last_name = %s,
                    fi = %s,
                    phone = %s,
                    email = %s
                WHERE users_id = %s
                """,
                (
                    first_name,
                    last_name,
                    f"{first_name} {last_name}".strip(),
                    phone_value,
                    email_value,
                    user_id,
                ),
            )
        conn.commit()
        return {"message": "Профиль обновлён"}
    except Exception as exc:
        conn.rollback()
        return {"error": f"Не удалось обновить профиль: {exc}"}
    finally:
        conn.close()


def create_reset_token(user_id: int) -> Dict[str, Any]:
    import secrets

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                INSERT INTO password_reset_tokens (user_id, token, expires_at, used, created_at)
                VALUES (%s, %s, %s, false, CURRENT_TIMESTAMP)
                RETURNING id, token, expires_at
                """,
                (user_id, token, expires_at),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {"token": token, "expires_at": expires_at.isoformat()}
    finally:
        conn.close()


def get_reset_token(token: str) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                SELECT id, user_id, token, expires_at, used, created_at
                FROM password_reset_tokens
                WHERE token = %s
                LIMIT 1
                """,
                (token,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def mark_reset_token_used(token_id: int):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                "UPDATE password_reset_tokens SET used = true WHERE id = %s",
                (token_id,),
            )
        conn.commit()
    finally:
        conn.close()


def register_user(
    telegram_id: int,
    first_name: str,
    last_name: str,
    phone: str,
    email: Optional[str],
    password: str,
) -> Dict[str, Any]:
    """
    Регистрация нового пользователя.
    telegram_id используется как users_id в таблице users.
    """
    if not phone or not phone.strip():
        return {"error": "Номер телефона обязателен для заполнения"}
    
    if not first_name or not last_name:
        return {"error": "Имя и фамилия обязательны для заполнения"}
    
    if not password or len(password) < 6:
        return {"error": "Пароль должен содержать минимум 6 символов"}
    
    if telegram_id <= 0:
        return {"error": "Telegram ID должен быть положительным числом"}
    
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # Проверка на существование пользователя с таким Telegram ID
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                SELECT users_id FROM users WHERE users_id = %s
                """,
                (telegram_id,),
            )
            if cur.fetchone():
                return {"error": f"Пользователь с Telegram ID {telegram_id} уже зарегистрирован"}
            
            # Проверка на существование пользователя с таким телефоном
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                SELECT users_id FROM users WHERE phone = %s
                """,
                (phone.strip(),),
            )
            if cur.fetchone():
                return {"error": "Пользователь с таким номером телефона уже зарегистрирован"}
            
            # Проверка на существование пользователя с таким email (если указан)
            if email and email.strip():
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT users_id FROM users WHERE LOWER(email) = LOWER(%s)
                    """,
                    (email.strip(),),
                )
                if cur.fetchone():
                    return {"error": "Пользователь с таким email уже зарегистрирован"}
            
            # Создание пользователя с users_id = telegram_id
            password_hash = hash_password(password)
            registration_date = datetime.now()
            full_name = f"{first_name.strip()} {last_name.strip()}".strip()
            cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                """
                INSERT INTO users (users_id, first_name, last_name, date, fi, phone, email, password_hash, is_admin, is_blocked)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, FALSE)
                """,
                (telegram_id, first_name.strip(), last_name.strip(), registration_date, full_name, phone.strip(), email.strip() if email else None, password_hash),
            )
            conn.commit()
            
            return {
                "message": "Регистрация успешна! Теперь вы можете войти в систему.",
                "data": {"user_id": telegram_id}
            }
    except Exception as exc:
        return {"error": f"Ошибка при регистрации: {exc}"}
    finally:
        conn.close()



