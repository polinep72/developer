# WSB_core

Единое ядро логики бронирования для стека WSB (бот + портал).

## Цели
- Убрать дублирование кода между Telegram‑ботом (`WSB/`) и порталом (`WSB_portal/`).
- Хранить в одном месте бизнес‑правила бронирований и уведомлений.
- Облегчить сопровождение и развитие (одно место для изменений, два клиента — бот и портал).
- **Безопасность боевых систем**: все изменения происходят только в `WSB_core/`, боевые версии не затрагиваются.

## Текущая структура

```text
WSB_core/
├── wsb_core/              # Общее ядро логики
│   ├── models.py         # Общие модели (User, Equipment, Booking, TimeSlot)
│   ├── constants.py       # Общие константы (WORKING_HOURS_START, BOOKING_TIME_STEP_MINUTES)
│   ├── slots.py           # Генерация слотов, работа с wsb_time_slots
│   └── bookings_core.py   # Общая бизнес-логика бронирований (создание/отмена)
├── wsb_bot/              # Копия Telegram бота (из WSB/)
│   ├── main.py
│   ├── bot_app.py
│   ├── config.py
│   ├── constants.py      # Использует wsb_core.constants
│   ├── database.py
│   ├── handlers/         # Обработчики команд и callback'ов
│   ├── services/         # Бизнес-логика (booking_service, equipment_service, notification_service)
│   └── utils/            # Утилиты (keyboards, message_utils, time_utils)
├── wsb_portal/           # Копия веб-портала (из WSB_portal/)
│   ├── app/
│   │   ├── main.py       # FastAPI приложение
│   │   ├── services/     # Бизнес-логика (bookings, heatmap, dashboard, equipment)
│   │   ├── static/       # CSS, JS, изображения
│   │   └── templates/    # HTML шаблоны
│   ├── Dockerfile
│   └── requirements.txt
├── core_app/             # Тестовое FastAPI приложение для проверки wsb_core
├── scripts/               # Скрипты для работы с БД (создание таблиц, отладка)
└── docker-compose.yml    # Docker Compose для запуска всего стека
```

## Статус проекта

**Текущая версия:** 0.1.0

**Важно:** 
- Боевые версии `WSB/` (v5.1.0) и `WSB_portal/` (v0.3.8) зафиксированы и больше не изменяются
- Вся разработка ведется только в `WSB_core/`
- После стабилизации `WSB_core` будет развернут как замена боевых версий

## План работ

1. ✅ Скопировать все необходимые файлы из `WSB/` и `WSB_portal/` в `WSB_core/`
2. ⏳ Адаптировать импорты в скопированных файлах для работы с `wsb_core`
3. ⏳ Унифицировать логику бронирований между ботом и порталом
4. ⏳ Вынести общие правила уведомлений в `wsb_core/notifications_logic.py`
5. ⏳ Протестировать работу бота и портала из `WSB_core`
6. ⏳ После стабилизации — развернуть `WSB_core` как замену боевых версий
