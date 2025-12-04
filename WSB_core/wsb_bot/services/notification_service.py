"""
Прокси notification_service для дубля WSB_core.

Подгружает реальную реализацию services/notification_service из боевого проекта WSB
по файловому пути, чтобы избежать конфликтов пакетов и круговых импортов.
"""

from __future__ import annotations

from pathlib import Path
from importlib.machinery import SourceFileLoader
from types import ModuleType

from logger import logger

ROOT_DIR = Path(__file__).resolve().parents[2]  # C:\Soft_IPK\WSB_core
SOFT_DIR = ROOT_DIR.parent                      # C:\Soft_IPK
WSB_NOTIF_SERVICE_PATH = SOFT_DIR / "WSB" / "wsb_bot" / "services" / "notification_service.py"

try:
    _loader = SourceFileLoader("wsb_original_notification_service", str(WSB_NOTIF_SERVICE_PATH))
    _orig_mod: ModuleType = _loader.load_module()  # type: ignore[deprecated]

    # Реэкспортируем все публичные символы боевого notification_service
    for _name in dir(_orig_mod):
        if _name.startswith("_"):
            continue
        globals()[_name] = getattr(_orig_mod, _name)

    __all__ = [name for name in globals().keys() if not name.startswith("_")]
except Exception as exc:  # pragma: no cover
    logger.critical(f"Не удалось загрузить боевой notification_service из {WSB_NOTIF_SERVICE_PATH}: {exc}", exc_info=True)
    __all__: list[str] = []
