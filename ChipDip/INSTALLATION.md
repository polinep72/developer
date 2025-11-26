# Инструкция по установке и использованию — ChipDip

## 1. Требования
- Docker, Docker Compose
- PostgreSQL (в составе docker-compose)
- Windows/Linux/MacOS; для Windows — PowerShell

## 2. Подготовка окружения
1. Склонируйте репозиторий и перейдите в каталог проекта.
2. Создайте `.env` (см. пример переменных в SYNC_INSTRUCTIONS.md / раздел «Обязательные переменные»).

## 3. Запуск через Docker Compose
```bash
# Первый запуск
docker-compose up -d --build

# Проверка статуса
docker-compose ps
```

## 4. Пересборка и пересоздание webapp (когда менялся код)
```bash
# Пересборка образа
docker-compose build webapp
# Пересоздание контейнера без зависимостей
docker-compose up -d --force-recreate --no-deps webapp
```

## 5. Проверка здоровья
```text
GET http://localhost:8085/health
GET http://localhost:8085/api/health
GET http://localhost:8085/healthz
```
Ожидаемый ответ: `{ "status": "ok", "db": true }`.

## 6. Просмотр логов
- Linux/macOS:
```bash
docker-compose logs -f --tail=200 webapp
```
- Windows PowerShell (команды по отдельности, без `&&`):
```powershell
docker-compose restart webapp
docker-compose logs -f --tail=200 webapp
```

## 7. Использование веб‑интерфейса
- Откройте `http://<хост>:8085/stats` — страница статистики.
- Графики 1–7 доступны без авторизации; в ЛК доступно редактирование названий собственных товаров.
- Экспорт в Excel/PowerPoint — отдельные кнопки над каждым графиком.

## 8. Обновление/миграции
- При изменении схемы БД добавляйте миграционные скрипты и выполняйте их до запуска.

## 9. Типовые команды
```bash
# Остановить всё
docker-compose down
# Очистить всё (осторожно)
docker system prune -a
# Полная пересборка
docker-compose build --no-cache && docker-compose up -d
```

## 10. Тест‑чеклист после деплоя
- `/health` возвращает OK и `db:true`.
- На странице статистики видны графики 3 и 6 без логина.
- Экспорт всех графиков работает, даты по возрастанию, подписи осей присутствуют.
