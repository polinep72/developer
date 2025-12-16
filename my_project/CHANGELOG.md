# Changelog

Все изменения в этом проекте будут задокументированы в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), проект использует [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- n/a

### Changed
- n/a

### Fixed
- n/a

### Removed
- n/a

## [0.1.0] - 2025-12-12
### Added
- Файлы контекста (`PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `SYNC_INSTRUCTIONS.md`, `.cursorrules`, `CHANGELOG.md`).
- Диагностическое логирование `/search` (параметры формы и итоговый SQL).
- Вкладки на главной странице (`Склад кристаллов`, `Склад пластин`, `Дальний склад`).

### Changed
- `/login` и `/register`: нормализация логинов (нижний регистр, `-`→`_`), расширенное логирование, очистка старых flash-сообщений.
- `get_db_connection()`: основное подключение по `DB_NAME` (fallback `DB_NAME2`).
- Телеграм-бот: агрегирует остатки по трём складам (`invoice/consumption`, `invoice_p/consumption_p`, `invoice_f/consumption_f`) и выводит блоками с разделителем `---------------`.

### Fixed
- Логика табличных копий для дополнительных складов (инструкции выполнены на БД).

### Removed
- n/a

