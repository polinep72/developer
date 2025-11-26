# Архитектура и описание компонентов — ChipDip

## 1. Обзор
Трёхкомпонентная система: парсер (`chipdip_parser`), веб‑приложение (`webapp`) и база данных (PostgreSQL). Контейнеризация через Docker Compose.

## 2. Сервисы
- `webapp`: Flask, отвечает за UI/графики, REST‑API, экспорт, health.
- `parser`: сбор остатков/цен, запись в БД, устойчив к разрывам соединения.
- `postgres`: хранение данных.

## 3. Взаимодействие
- `parser → postgres`: INSERT в `stock_history`, обновление данных товара.
- `webapp → postgres`: SELECT для API/страниц, агрегации для графиков.
- Клиент (браузер) ↔ `webapp`: загрузка страниц и JSON‑API, рендер Plotly.

## 4. Модули (основные)
- `webapp/routes.py`: все маршруты Flask (страницы, API, экспорт, health).
- `webapp/templates/*.html`: Jinja2‑шаблоны, JS для загрузки графиков и экспорта.
- `chipdip_parser/database.py`: соединения с БД, запись истории.
- `chipdip_parser/app.py`: основной цикл парсера, восстановление соединения при `conn.closed`.

## 5. База данных (логическая модель)
- `products` — справочник товаров, принадлежность пользователю, `is_active`.
- `stock_history` — измерения времени (`check_timestamp`), `stock_level`, `price`.
- `users` — пользователи, хеш пароля, `is_active`.

Ключевые индексы: `stock_history(product_id, check_timestamp)`.

## 6. API (сводка ключевых маршрутов)
- Страницы: `/`, `/products`, `/my_products`, `/stats`.
- Данные графиков (выборочно):
  - `/api/stats/overview`, `/api/stats/sales`, `/api/stats/yearly/monthly`
  - `/api/stats/product/<id>/series`, `/api/stats/product/<id>/monthly`
  - `/api/stats/revenue/monthly` (публично)
  - `/api/stats/revenue/product-monthly?product_id=...` (публично)
- Экспорт:
  - `/api/export/excel`, `/api/export/powerpoint`
  - `/api/export/chart/*/excel` (для всех 6 графиков, параметры см. `stats.html`)
- Health: `/health`, `/api/health`, `/healthz`.

## 7. Графики (соответствие типам)
- Временные ряды (остатки/цены/продажи по товару) — Line/Bar соответствуют веб‑версии.
- Агрегаты по месяцам (все товары) — stacked bar, совпадают с веб‑страницей.

## 8. Политика доступа
- Просмотр статистики и экспорт — публично.
- Редактирование названий товаров — только владелец (авторизованный пользователь).

## 9. Мониторинг и логи
- Health‑URL: `/health`, `/api/health`, `/healthz`.
- Логи webapp: `docker-compose logs -f --tail=200 webapp`.
- PowerShell на Windows — выполняйте команды отдельно (без `&&`).

## 10. Диагностика типовых сбоев
- 404 на экспорт/графики → проверить, что контейнер пересоздан: `up -d --force-recreate --no-deps webapp`.
- 401 на API → убедиться, что маршруты без `login_required` (см. `routes.py`).
- Пустые графики у гостя → сбросить кэш (Ctrl+F5) и проверить в Network ответы API.
