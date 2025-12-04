from __future__ import annotations

from typing import Dict, Any, Set, Tuple, Optional
from pathlib import Path
from importlib.machinery import SourceFileLoader

import telebot
from telebot.types import CallbackQuery
from apscheduler.schedulers.background import BackgroundScheduler

from database import Database
from logger import logger


# --- Грузим боевой модуль callback_handlers по прямому пути, чтобы избежать конфликтов пакетов ---
ROOT_DIR = Path(__file__).resolve().parents[2]  # C:\Soft_IPK\WSB_core
SOFT_DIR = ROOT_DIR.parent                      # C:\Soft_IPK
WSB_CALLBACKS_PATH = SOFT_DIR / "WSB" / "wsb_bot" / "handlers" / "callback_handlers.py"

try:
    _loader = SourceFileLoader("wsb_original_callback_handlers", str(WSB_CALLBACKS_PATH))
    _orig_mod = _loader.load_module()  # type: ignore[deprecated]
    _base_handle_callback_query = getattr(_orig_mod, "handle_callback_query")
    _base_user_booking_states = getattr(_orig_mod, "user_booking_states")
    _base_clear_user_state = getattr(_orig_mod, "clear_user_state")
except Exception as exc:  # pragma: no cover - защитный импорт
    logger.critical(f"Не удалось загрузить боевой callback_handlers из {WSB_CALLBACKS_PATH}: {exc}", exc_info=True)
    _base_user_booking_states: Dict[int, Dict[str, Any]] = {}

    def _base_clear_user_state(user_id: int) -> None:
        _base_user_booking_states.pop(user_id, None)

    def _base_handle_callback_query(*args: Any, **kwargs: Any) -> None:
        logger.error("handle_callback_query из боевого WSB недоступен")


# --- Публичное API для кода дубля (используется user_commands и main) ---

user_booking_states: Dict[int, Dict[str, Any]] = _base_user_booking_states


def clear_user_state(user_id: int) -> None:
    """Прокси к боевой clear_user_state, чтобы не дублировать логику FSM."""
    _base_clear_user_state(user_id)


def register_callback_handlers(
    bot: telebot.TeleBot,
    db: Database,
    scheduler: Optional[BackgroundScheduler],
    active_timers: Optional[Dict[int, Any]],
    scheduled_jobs_registry: Optional[Set[Tuple[str, int]]],
) -> None:
    """
    Регистрирует единый обработчик callback-запросов, делегируя
    всю сложную бизнес-логику в боевой модуль WSB.
    """

    @bot.callback_query_handler(func=lambda call: True)
    def main_callback_dispatcher(call: CallbackQuery) -> None:  # type: ignore[misc]
        _base_handle_callback_query(
            bot,
            db,
            scheduler,
            active_timers,
            scheduled_jobs_registry,
            call,
            source_command=None,
        )

    logger.info("Callback-хендлеры успешно зарегистрированы (через боевой модуль WSB).")
