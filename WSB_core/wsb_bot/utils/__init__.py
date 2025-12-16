"""
Прокси-пакет utils: реэкспортирует публичные объекты из wsb_bot.utils.
"""

# Всегда используем относительный импорт, т.к. запускаем из wsb_bot/
from . import keyboards  # noqa: F401,F403
try:
    from . import formatters  # noqa: F401,F403
except ImportError:
    pass
try:
    from . import message_utils  # noqa: F401,F403
except ImportError:
    pass
try:
    from . import time_utils  # noqa: F401,F403
except ImportError:
    pass

