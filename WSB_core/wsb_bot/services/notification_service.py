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

    # Сохраняем оригинальную schedule_all_notifications, если она есть
    _orig_schedule_all_notifications = getattr(_orig_mod, "schedule_all_notifications", None)

    # Реэкспортируем все публичные символы боевого notification_service
    for _name in dir(_orig_mod):
        if _name.startswith("_"):
            continue
        globals()[_name] = getattr(_orig_mod, _name)

    __all__ = [name for name in globals().keys() if not name.startswith("_")]

    # --- Интеграция с ядром WSB_core: единое расписание уведомлений ---
    try:
        # Импортируем ядро расписания и Database бота
        from database import Database
        from wsb_core.notifications_schedule import (
            rebuild_schedule_for_all_bookings,
            NotificationChannel,
        )

        def schedule_all_notifications(
            db,  # Database
            bot,
            scheduler,
            active_timers,
            scheduled_jobs_registry,
        ):
            """
            Обёртка над боевой schedule_all_notifications:
            - сначала выполняет оригинальное планирование APScheduler бота;
            - затем пересобирает единое расписание в таблице wsb_notifications_schedule
              для каналов telegram/email через ядро WSB_core.
            """
            # 1) Оригинальное планирование (ботовые уведомления), если функция доступна
            if callable(_orig_schedule_all_notifications):
                _orig_schedule_all_notifications(
                    db,
                    bot,
                    scheduler,
                    active_timers,
                    scheduled_jobs_registry,
                )

            # 2) Пересборка ядрового расписания в БД
            conn = None
            try:
                conn = Database.get_connection()
                with conn.cursor() as cur:
                    created = rebuild_schedule_for_all_bookings(
                        cur,
                        channels=(
                            NotificationChannel.TELEGRAM,
                            NotificationChannel.EMAIL,
                        ),
                    )
                    conn.commit()
                    logger.info(
                        f"[WSB_core] Расписание уведомлений пересчитано: создано {created} задач в wsb_notifications_schedule"
                    )
            except Exception as exc_inner:
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                logger.error(
                    f"[WSB_core] Ошибка пересборки расписания уведомлений: {exc_inner}",
                    exc_info=True,
                )
            finally:
                if conn is not None:
                    Database.release_connection(conn)

        # Обновляем __all__, чтобы экспортировать нашу обёртку
        if "schedule_all_notifications" not in __all__:
            __all__.append("schedule_all_notifications")

    except Exception as exc_integ:
        # При ошибке интеграции оставляем только оригинальное поведение
        logger.error(f"[WSB_core] Не удалось интегрировать ядро расписания уведомлений: {exc_integ}", exc_info=True)

except Exception as exc:  # pragma: no cover
    logger.critical(f"Не удалось загрузить боевой notification_service из {WSB_NOTIF_SERVICE_PATH}: {exc}", exc_info=True)
    __all__: list[str] = []
