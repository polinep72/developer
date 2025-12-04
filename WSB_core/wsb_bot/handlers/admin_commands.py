from __future__ import annotations

from pathlib import Path
from importlib.machinery import SourceFileLoader

import telebot
from database import Database
from logger import logger

ROOT_DIR = Path(__file__).resolve().parents[2]  # C:\Soft_IPK\WSB_core
SOFT_DIR = ROOT_DIR.parent
WSB_ADMIN_PATH = SOFT_DIR / "WSB" / "wsb_bot" / "handlers" / "admin_commands.py"

try:
    _loader = SourceFileLoader("wsb_original_admin_commands", str(WSB_ADMIN_PATH))
    _orig_mod = _loader.load_module()  # type: ignore[deprecated]
    _base_register_admin_command_handlers = getattr(
        _orig_mod, "register_admin_command_handlers"
    )
except Exception as exc:  # pragma: no cover
    logger.critical(f"Не удалось загрузить боевой admin_commands из {WSB_ADMIN_PATH}: {exc}", exc_info=True)

    def _base_register_admin_command_handlers(bot: telebot.TeleBot, db: Database) -> None:  # type: ignore[override]
        logger.error("register_admin_command_handlers из боевого WSB недоступен")


def register_admin_command_handlers(bot: telebot.TeleBot, db: Database) -> None:
    """
    Прокси к боевой функции регистрации админских хендлеров.
    """
    _base_register_admin_command_handlers(bot, db)
