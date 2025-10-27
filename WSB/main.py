"""
Тонкий лаунчер: делегирует запуск в `wsb_bot.main`.
Это необходимо для обратной совместимости при запуске `python main.py` из корня.
В продакшене Docker продолжит вызывать `wsb_bot/main.py` напрямую.
"""

import os
import sys
from logger import logger


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    wsb_dir = os.path.join(base_dir, 'wsb_bot')

    # Приоритетно подключаем `wsb_bot/` в sys.path
    if os.path.isdir(wsb_dir) and wsb_dir not in sys.path:
        sys.path.insert(0, wsb_dir)
        logger.info(f"Добавлен путь в sys.path для wsb_bot: {wsb_dir}")

    try:
        from wsb_bot.main import main as run_main
    except Exception as e:
        logger.critical(f"Ошибка импорта wsb_bot.main: {e}", exc_info=True)
        raise

    logger.info("Делегирование запуска в wsb_bot.main...")
    run_main()


if __name__ == "__main__":
    main()