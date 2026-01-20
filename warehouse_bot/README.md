# Warehouse Bot (Склад готовой продукции)

Телеграм-бот **@WareHouseIPKBot** для поиска остатков товаров на складе готовой продукции по базе PostgreSQL.

## Требования
- Python 3.x
- `telebot`, `psycopg2`, `pandas`, `python-dotenv`
- Файл `.env` с параметрами:
  - `TELEGRAM_BOT_TOKEN`
  - `DB_USER`, `DB_PASSWORD`, `DB_NAME=warehouse`, `DB_HOST`

## Запуск

### Локальный запуск
1) Установить зависимости: `pip install -r requirements.txt` или `pip install telebot psycopg2-binary python-dotenv`.
2) Создать `.env` с переменными выше (обязательно указать `DB_NAME=warehouse`).
3) Запустить бота: `python WareHouseIPKBot.py`.

### Запуск в Docker

1) Создать файл `.env` с переменными окружения:
   ```
   TELEGRAM_BOT_TOKEN=your_token
   DB_USER=postgres
   DB_PASSWORD=your_password
   DB_NAME=warehouse
   DB_HOST=your_db_host
   ```

2) Создать сеть Docker (если еще не создана):
   ```bash
   docker network create warehouse-network
   ```

3) Запустить бота:
   ```bash
   docker-compose up -d
   ```

4) Просмотр логов:
   ```bash
   docker-compose logs -f warehouse-bot
   ```

5) Остановка бота:
   ```bash
   docker-compose down
   ```

## Поведение
- `/start` — приветствие и подсказка формата ввода.
- Любой текст — поиск по наименованию товара или коду кристалла (`ILIKE '%<ввод>%'`) и ответ пользователю с раздельными секциями:
  - Микросхемы (`element_types.code = 'ms'`)
  - Модули (`element_types.code = 'm'`)
  - ПП (`element_types.code = 'pp'`)

## Поиск
Бот ищет товары по:
- Наименованию товара (таблица `elements.name`)
- Коду кристалла (таблица `chips.chip_code`)

Остатки рассчитываются как разница между приходом и расходом по каждой поставке (`item_id`):
- Приход: `SUM(invoices.quan)`
- Расход: `SUM(consumptions.quantity)`

Данные прихода/расхода нормализованы:
- `invoices` (вместо `invoice_ms/invoice_m/invoice_pp`)
- `consumptions` (вместо `consumption_ms/consumption_m/consumption_pp`)

Важно: в нормализованных `invoices/consumptions` поле `name_id` соответствует legacy-id из `names_*`, поэтому в боте JOIN на номенклатуру выполняется по `elements.legacy_name_id`.

## Контекст
- Основные файлы контекста: `PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `SYNC_INSTRUCTIONS.md`, `CHANGELOG.md`.

