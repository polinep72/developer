"""
Сервис для управления пользователями (только для администраторов)
"""
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from typing import cast

from .auth import _connect, hash_password, verify_password

load_dotenv()


def get_all_users() -> Dict[str, Any]:
    """Получить список всех пользователей"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT users_id, first_name, last_name, phone, email, is_admin, is_blocked
                    FROM users
                    ORDER BY last_name, first_name
                    """
                )
                rows = cur.fetchall()
                users = []
                for row in rows:
                    row_dict = cast(Dict[str, Any], row)
                    users.append({
                        "id": row_dict.get("users_id"),
                        "first_name": row_dict.get("first_name") or "",
                        "last_name": row_dict.get("last_name") or "",
                        "phone": row_dict.get("phone") or "",
                        "email": row_dict.get("email") or "",
                        "is_admin": bool(row_dict.get("is_admin")),
                        "is_blocked": bool(row_dict.get("is_blocked")),
                    })
                return {"data": users}
        finally:
            conn.close()
    except Exception as exc:
        return {"error": f"Ошибка при получении списка пользователей: {exc}"}


def get_user_by_id(user_id: int) -> Dict[str, Any]:
    """Получить пользователя по ID"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT users_id, first_name, last_name, phone, email, is_admin, is_blocked
                    FROM users
                    WHERE users_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return {"error": "Пользователь не найден"}
                
                row_dict = cast(Dict[str, Any], row)
                return {
                    "data": {
                        "id": row_dict.get("users_id"),
                        "first_name": row_dict.get("first_name") or "",
                        "last_name": row_dict.get("last_name") or "",
                        "phone": row_dict.get("phone") or "",
                        "email": row_dict.get("email") or "",
                        "is_admin": bool(row_dict.get("is_admin")),
                        "is_blocked": bool(row_dict.get("is_blocked")),
                    }
                }
        finally:
            conn.close()
    except Exception as exc:
        return {"error": f"Ошибка при получении пользователя: {exc}"}


def create_user(
    first_name: str,
    last_name: str,
    phone: Optional[str],
    email: Optional[str],
    password: str,
    is_admin: bool = False,
) -> Dict[str, Any]:
    """Создать нового пользователя"""
    if not first_name or not last_name:
        return {"error": "Имя и фамилия обязательны"}
    
    if not phone and not email:
        return {"error": "Необходимо указать телефон или email"}
    
    if not password or len(password) < 6:
        return {"error": "Пароль должен содержать минимум 6 символов"}
    
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # Проверка на существование пользователя с таким телефоном или email
                if phone:
                    cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                        """
                        SELECT users_id FROM users WHERE phone = %s
                        """,
                        (phone,),
                    )
                    if cur.fetchone():
                        return {"error": "Пользователь с таким телефоном уже существует"}
                
                if email:
                    cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                        """
                        SELECT users_id FROM users WHERE LOWER(email) = LOWER(%s)
                        """,
                        (email,),
                    )
                    if cur.fetchone():
                        return {"error": "Пользователь с таким email уже существует"}
                
                # Создание пользователя
                password_hash = hash_password(password)
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    INSERT INTO users (first_name, last_name, phone, email, password_hash, is_admin, is_blocked)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                    RETURNING users_id
                    """,
                    (first_name, last_name, phone, email, password_hash, is_admin),
                )
                new_user_row = cur.fetchone()
                if not new_user_row:
                    return {"error": "Не удалось получить ID созданного пользователя"}
                new_user_id = cast(Dict[str, Any], new_user_row).get("users_id")
                conn.commit()
                
                return {
                    "message": "Пользователь успешно создан",
                    "data": {"id": new_user_id}
                }
        finally:
            conn.close()
    except Exception as exc:
        return {"error": f"Ошибка при создании пользователя: {exc}"}


def update_user(
    user_id: int,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    is_admin: Optional[bool] = None,
    is_blocked: Optional[bool] = None,
) -> Dict[str, Any]:
    """Обновить данные пользователя"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # Проверка существования пользователя
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT users_id FROM users WHERE users_id = %s
                    """,
                    (user_id,),
                )
                if not cur.fetchone():
                    return {"error": "Пользователь не найден"}
                
                # Формирование запроса обновления
                updates = []
                params = []
                
                if first_name is not None:
                    updates.append("first_name = %s")
                    params.append(first_name)
                
                if last_name is not None:
                    updates.append("last_name = %s")
                    params.append(last_name)
                
                if phone is not None:
                    # Проверка на дубликат телефона
                    cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                        """
                        SELECT users_id FROM users WHERE phone = %s AND users_id != %s
                        """,
                        (phone, user_id),
                    )
                    if cur.fetchone():
                        return {"error": "Пользователь с таким телефоном уже существует"}
                    updates.append("phone = %s")
                    params.append(phone)
                
                if email is not None:
                    # Проверка на дубликат email
                    cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                        """
                        SELECT users_id FROM users WHERE LOWER(email) = LOWER(%s) AND users_id != %s
                        """,
                        (email, user_id),
                    )
                    if cur.fetchone():
                        return {"error": "Пользователь с таким email уже существует"}
                    updates.append("email = %s")
                    params.append(email)
                
                if is_admin is not None:
                    updates.append("is_admin = %s")
                    params.append(is_admin)
                
                if is_blocked is not None:
                    updates.append("is_blocked = %s")
                    params.append(is_blocked)
                
                if not updates:
                    return {"error": "Нет данных для обновления"}
                
                params.append(user_id)
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    f"""
                    UPDATE users
                    SET {', '.join(updates)}
                    WHERE users_id = %s
                    """,
                    tuple(params),
                )
                conn.commit()
                
                return {"message": "Пользователь успешно обновлен"}
        finally:
            conn.close()
    except Exception as exc:
        return {"error": f"Ошибка при обновлении пользователя: {exc}"}


def reset_user_password(user_id: int, new_password: str) -> Dict[str, Any]:
    """Сбросить пароль пользователя (только для админов)"""
    if not new_password or len(new_password) < 6:
        return {"error": "Пароль должен содержать минимум 6 символов"}
    
    try:
        from .auth import update_user_password
        password_hash = hash_password(new_password)
        update_user_password(user_id, password_hash)
        return {"message": "Пароль успешно изменен"}
    except Exception as exc:
        return {"error": f"Ошибка при изменении пароля: {exc}"}


def delete_user(user_id: int) -> Dict[str, Any]:
    """Удалить пользователя (только для админов)"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                # Проверка существования пользователя
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT users_id FROM users WHERE users_id = %s
                    """,
                    (user_id,),
                )
                if not cur.fetchone():
                    return {"error": "Пользователь не найден"}
                
                # Проверка на активные бронирования
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    SELECT COUNT(*) as count
                    FROM bookings
                    WHERE user_id = %s
                      AND cancel = FALSE
                      AND finish = FALSE
                      AND time_start > NOW()
                    """,
                    (user_id,),
                )
                bookings_row = cur.fetchone()
                if not bookings_row:
                    active_bookings = 0
                else:
                    active_bookings = cast(Dict[str, Any], bookings_row).get("count", 0)
                if active_bookings > 0:
                    return {"error": f"Нельзя удалить пользователя с активными бронированиями ({active_bookings})"}
                
                # Удаление пользователя
                cur.execute(  # pyright: ignore[reportGeneralTypeIssues]
                    """
                    DELETE FROM users WHERE users_id = %s
                    """,
                    (user_id,),
                )
                conn.commit()
                
                return {"message": "Пользователь успешно удален"}
        finally:
            conn.close()
    except Exception as exc:
        return {"error": f"Ошибка при удалении пользователя: {exc}"}

