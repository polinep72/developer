## Синхронизация проекта Soft_IPK / Склад готовой продукции между компьютерами

1. **Клонирование репозитория**
   - Используйте `git clone <repo-url>` на новой машине.
   - Убедитесь, что структура подпроектов (`crystal_wafer/` и др.) сохранена.

2. **Установка зависимостей**
   - В подпроекте `crystal_wafer/web_app_WebChip` установите Python‑зависимости (по `requirements.txt` или через Poetry, если используется).
   - При наличии фронтенда/доп. сервисов следуйте их README/`DEPLOYMENT.md`.

3. **Настройка БД**
   - На сервере PostgreSQL создайте базу `warehouse` (см. комментарии в `crystal_wafer/web_app_WebChip/create_warehouse_schema.sql`).
   - Выполните SQL‑скрипт `create_warehouse_schema.sql` внутри БД `warehouse`, чтобы создать таблицы:
     - `invoice_ms`, `invoice_m`, `invoice_pp`
     - `consumption_ms`, `consumption_m`, `consumption_pp`
   - В `.env` для `web_app_WebChip` укажите параметры подключения к нужной БД (обычно `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`).

4. **Рабочий процесс с Git**
   - Все изменения в коде и в файлах контекста (`PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `CHANGELOG.md`) обязательно коммитьте в Git.
   - Перед пушем проверяйте `git status`, `git diff`, запускайте тесты/линтеры, если они настроены.

5. **Переход между машинами**
   - Перед началом работы: `git pull`, чтобы получить актуальное состояние.
   - После работы: обновите контекстные файлы (описание новых задач, решений, изменений в схеме БД) и выполните `git commit` + `git push`.


