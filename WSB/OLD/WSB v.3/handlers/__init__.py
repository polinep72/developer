# handlers/__init__.py

# Импортируем модули, чтобы сделать их доступными при импорте из пакета 'handlers'

from . import user_commands      # Заменили message_handlers на user_commands
from . import callback_handlers
from . import admin_commands
from . import registration       # Добавили registration

# Опционально: __all__ определяет, что будет импортировано при 'from handlers import *'
# и также может служить документацией того, что пакет предоставляет.
__all__ = [
    'user_commands',
    'callback_handlers',
    'admin_commands',
    'registration',
]