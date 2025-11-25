"""
CSRF защита для форм
"""
import secrets
import os
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

logger = logging.getLogger(__name__)

# Секретный ключ для CSRF токенов
CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", secrets.token_urlsafe(32))
CSRF_TOKEN_LENGTH = 32

# Хранилище токенов (в продакшене лучше использовать Redis)
_csrf_tokens: dict[str, str] = {}


def generate_csrf_token() -> str:
    """Генерация CSRF токена"""
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


async def validate_csrf_token(request: Request, token: Optional[str] = None) -> bool:
    """Валидация CSRF токена"""
    if not token:
        # Пытаемся получить токен из заголовка
        token = request.headers.get("X-CSRF-Token")
        if not token:
            # Пытаемся получить из формы
            try:
                form_data = await request.form()
                csrf_value = form_data.get("csrf_token")
                # Проверяем, что это строка, а не файл
                if isinstance(csrf_value, str):
                    token = csrf_value
            except Exception:
                pass
    
    if not token:
        return False
    
    # Получаем токен из сессии (в реальном приложении используйте сессии)
    session_id = request.cookies.get("session_id")
    if not session_id:
        return False
    
    expected_token = _csrf_tokens.get(session_id)
    if not expected_token:
        return False
    
    return secrets.compare_digest(token, expected_token)


def get_csrf_token(request: Request) -> str:
    """Получить или создать CSRF токен для сессии"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        # Создаем новую сессию
        session_id = secrets.token_urlsafe(16)
    
    if session_id not in _csrf_tokens:
        _csrf_tokens[session_id] = generate_csrf_token()
    
    return _csrf_tokens[session_id]


async def require_csrf_token(request: Request, token: Optional[str] = None):
    """Проверка CSRF токена (для использования в эндпоинтах)"""
    if not await validate_csrf_token(request, token):
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"CSRF token validation failed for {client_host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Неверный или отсутствующий CSRF токен"
        )

