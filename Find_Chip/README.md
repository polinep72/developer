# Find_Chip Bot

Телеграм-бот для поиска остатков кристаллов по базе PostgreSQL.

## Требования
- Python 3.x
- `telebot`, `psycopg2`, `pandas`, `python-dotenv`
- Файл `.env` с параметрами:
  - `TELEGRAM_BOT_TOKEN`
  - `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_HOST`

## Запуск
1) Установить зависимости: `pip install -r requirements.txt` (при наличии) или `pip install telebot psycopg2 pandas python-dotenv`.
2) Создать `.env` с переменными выше.
3) Запустить бота: `python @HowManyCrystals_bot.py`.

## Поведение
- `/start` — приветствие и подсказка формата ввода.
- Любой текст — поиск по `LIKE '%<ввод>%’`, суммирование остатка и ответ пользователю с раздельными секциями:
  - Основной склад (`invoice/consumption`)
  - Пластины неразделенные (`invoice_p/consumption_p`)
  - Дальний склад (`invoice_f/consumption_f`)

## Контекст
- Основные файлы контекста: `PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `SYNC_INSTRUCTIONS.md`, `CHANGELOG.md`.

