"""
Единая конфигурация (значения читаются из .env).

Цель:
- Одинаковые имена переменных для бота и портала.
- Все значения можно контролировать через .env.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


# Загружаем .env из корня WSB_core (если есть)
ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
if load_dotenv and ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Таймзона планировщика/уведомлений
WSB_TIMEZONE: str = os.getenv("WSB_TIMEZONE", "Europe/Moscow")

# Тайминги уведомлений (минуты)
WSB_NOTIFICATION_BEFORE_START_MINUTES: int = int(
    os.getenv("WSB_NOTIFICATION_BEFORE_START_MINUTES", "10")
)
WSB_NOTIFICATION_BEFORE_END_MINUTES: int = int(
    os.getenv("WSB_NOTIFICATION_BEFORE_END_MINUTES", "10")
)

# Сетевые настройки портала
WSB_PORTAL_HOST: str = os.getenv("WSB_PORTAL_HOST", "0.0.0.0")
WSB_PORTAL_PORT: int = int(os.getenv("WSB_PORTAL_PORT", "8088"))

# Поведение бота
WSB_BOT_SKIP_PENDING: bool = (
    os.getenv("WSB_BOT_SKIP_PENDING", "true").lower() == "true"
)

# SMTP настройки для отправки email
WSB_SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
WSB_SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
WSB_SMTP_USER: str = os.getenv("SMTP_USER", "")
WSB_SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
WSB_SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", WSB_SMTP_USER)
WSB_SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "WSB System")
WSB_ENABLE_EMAIL: bool = os.getenv("ENABLE_EMAIL", "false").lower() == "true"


__all__ = [
    "WSB_TIMEZONE",
    "WSB_NOTIFICATION_BEFORE_START_MINUTES",
    "WSB_NOTIFICATION_BEFORE_END_MINUTES",
    "WSB_PORTAL_HOST",
    "WSB_PORTAL_PORT",
    "WSB_BOT_SKIP_PENDING",
    "WSB_SMTP_HOST",
    "WSB_SMTP_PORT",
    "WSB_SMTP_USER",
    "WSB_SMTP_PASSWORD",
    "WSB_SMTP_FROM_EMAIL",
    "WSB_SMTP_FROM_NAME",
    "WSB_ENABLE_EMAIL",
]

