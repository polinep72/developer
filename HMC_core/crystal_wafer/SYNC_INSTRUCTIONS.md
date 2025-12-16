# Инструкции по синхронизации Soft_IPK

1. Клонируйте репозиторий на новую машину: `git clone <repo-url>`.
2. Установите Poetry и Node.js LTS, затем выполните `poetry install` в Python-подпроектах и `npm install` в `frontend/`.
3. Для каждого подпроекта используйте соответствующий `docker-compose.yml` (например, `web_app_WebChip/docker-compose.yml`) и фиксируйте версии в `.env`/compose.
4. После каждого изменения обновляйте файлы контекста (`PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `CHANGELOG.md`) и коммитьте с осмысленными сообщениями.
5. Перед пушем выполните `git status`, `git diff`, линтеры/тесты, затем `git push`.
6. При переключении между машинами подтягивайте последние изменения (`git pull`) и сверяйте контекстные файлы, чтобы не потерять историю.

