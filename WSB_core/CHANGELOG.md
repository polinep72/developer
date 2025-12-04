# Changelog — WSB_core

Формат основан на Keep a Changelog и SemVer.

## [Unreleased]

## [0.1.0] - 2025-12-04
### Added
- Инициализация подпроекта `WSB_core` с базовыми файлами контекста и описанием целей
- Скопированы все файлы из `WSB/` (Telegram бот) в `wsb_bot/`
- Скопированы все файлы из `WSB_portal/` (веб-портал) в `wsb_portal/`
- Создана структура проекта с разделением на общее ядро (`wsb_core/`), бот (`wsb_bot/`) и портал (`wsb_portal/`)
- Боевые версии `WSB/` и `WSB_portal/` зафиксированы и больше не изменяются
- Вся дальнейшая разработка ведется только в `WSB_core/`

### Changed
- Адаптированы импорты в `wsb_bot/services/booking_service.py` для использования `wsb_core.constants`
- Обновлен `wsb_bot/constants.py` для использования констант из `wsb_core.constants`
- Обновлен `wsb_portal/app/services/bookings.py` для использования констант из `wsb_core.constants`
- Унифицированы константы времени работы: 7:00-22:00, шаг 30 минут, максимальная длительность 8 часов
- Расширен `wsb_core/slots.py` функцией `calculate_available_slots_from_bookings()` для унифицированного расчета слотов
- Адаптирован `wsb_bot/services/booking_service.py` для использования `wsb_core.slots.calculate_available_slots_from_bookings()` вместо локальной реализации
- Добавлен модуль `wsb_core/bookings_core.py` с общей бизнес-логикой (создание/отмена, проверка конфликтов, синхронизация слотов)
- `wsb_portal/app/services/bookings.py` переведен на использование `wsb_core.bookings_core` для создания и отмены бронирований
- Расширен `wsb_core/models.py`:
  - Добавлен статус `PLANNED` в `BookingStatus`
  - Расширена модель `Booking` для соответствия структуре БД (добавлены поля: cancel, finish, time_interval, duration, data_booking, user_fio, equipment_name)
  - Добавлена функция `determine_booking_status()` для определения статуса брони на основе полей БД
  - Добавлена функция `booking_from_db_row()` для создания объекта Booking из строки БД с поддержкой разных вариантов именования полей
- Обновлена документация: README.md, PROJECT_CONTEXT.md с описанием текущей структуры

