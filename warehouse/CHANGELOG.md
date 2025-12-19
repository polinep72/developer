## Changelog (корень проекта)

Все значимые изменения корневого уровня будут описаны в этом файле.  
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), версияция рекомендуется по [SemVer](https://semver.org/spec/v2.0.0.html).

### [Unreleased]
- Планируется расширение функциональности склада готовой продукции на базе `crystal_wafer/web_app_WebChip`.

## [0.1.0] - 2025-12-18

### Added
- Созданы корневые файлы контекста: `PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `SYNC_INSTRUCTIONS.md`, `CHANGELOG.md`.
- Зафиксирован логический подпроект «Склад готовой продукции», использующий UI и авторизацию из `web_app_WebChip`.
- Описано использование отдельной БД `warehouse` с таблицами `invoice_ms`, `invoice_m`, `invoice_pp`, `consumption_ms`, `consumption_m`, `consumption_pp` (по скрипту `create_warehouse_schema.sql`).


