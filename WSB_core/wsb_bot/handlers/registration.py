from __future__ import annotations

from pathlib import Path
from importlib.machinery import SourceFileLoader

import telebot
from database import Database
from logger import logger

ROOT_DIR = Path(__file__).resolve().parents[2]  # C:\Soft_IPK\WSB_core
SOFT_DIR = ROOT_DIR.parent
WSB_REG_PATH = SOFT_DIR / "WSB" / "wsb_bot" / "handlers" / "registration.py"

try:
    _loader = SourceFileLoader("wsb_original_registration", str(WSB_REG_PATH))
    _orig_mod = _loader.load_module()  # type: ignore[deprecated]
    _base_register_reg_handlers = getattr(_orig_mod, "register_reg_handlers")
except Exception as exc:  # pragma: no cover
    logger.critical(f"Не удалось загрузить боевой registration из {WSB_REG_PATH}: {exc}", exc_info=True)

    def _base_register_reg_handlers(bot: telebot.TeleBot, db: Database) -> None:  # type: ignore[override]
        logger.error("register_reg_handlers из боевого WSB недоступен")


def register_reg_handlers(bot: telebot.TeleBot, db: Database) -> None:
    """
    Прокси к боевой функции регистрации хендлеров регистрации пользователей.
    """
    _base_register_reg_handlers(bot, db)
