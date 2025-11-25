# Инструкции по синхронизации — WSB Portal

## Git-процесс
1. `cd C:\Soft_IPK\WSB_portal`
2. Работать в ветках `feature/wsb-portal-*`
3. Перед коммитом убеждаться, что обновлены файлы контекста (`PROJECT_CONTEXT.md`, `SOLUTIONS_HISTORY.md`, `CHAT_HISTORY.md`, `CHANGELOG.md`)

## Перенос модулей
- Подключать бизнес-логику из `..\WSB\wsb_bot\services` симлинками или editable-пакетами
- Не копировать код без проверки дубликатов
- На каждом уровне обновлять файлы контекста об использовании общих модулей

## Деплой

### Вариант 1: Docker Compose (рекомендуется)

1. На сервере подготовить `.env` с параметрами БД, Redis и SMTP (см. README/REDIS_SETUP/NOTIFICATIONS_SETUP).
2. Убедиться, что Docker и Docker Compose установлены (`docker --version`, `docker-compose --version`).
3. Запустить все сервисы: `docker-compose up -d --build`.
4. Проверить статус: `docker-compose ps`.
5. Проверить доступность `http://192.168.1.139:8090`.
6. Просмотр логов: `docker-compose logs -f wsb-portal`.

**Подробная инструкция:** см. `DOCKER_SETUP.md`.

### Вариант 2: Ручной запуск (без Docker)

1. На сервере подготовить `.env` с параметрами БД, Redis и SMTP (см. README/REDIS_SETUP/NOTIFICATIONS_SETUP).
2. Создать/активировать виртуальное окружение `python -m venv .venv && source .venv/bin/activate` (или `.venv\Scripts\activate` в Windows).
3. Выполнить `pip install -r requirements.txt`.
4. Запустить сервис командой `uvicorn app.main:app --host 0.0.0.0 --port 8090` (рекомендуется оформить как systemd‑сервис или pm2).
5. Проверить доступность `http://192.168.1.139:8090`.
6. Redis: убедиться, что сервис доступен на `REDIS_HOST:REDIS_PORT` (по умолчанию `localhost:6379`) и объём памяти ограничен 256 MB. При первой настройке следовать `REDIS_SETUP.md`.
7. SMTP: заполнить `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, выполнить авторизацию/принятие EULA на почтовом сервисе, установить `ENABLE_EMAIL=true`.

### Пример systemd unit (Linux)
```
/etc/systemd/system/wsb-portal.service
[Unit]
Description=WSB Portal (uvicorn)
After=network.target redis.service

[Service]
WorkingDirectory=/opt/WSB_portal
EnvironmentFile=/opt/WSB_portal/.env
ExecStart=/opt/WSB_portal/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8090
Restart=on-failure
User=wsb
Group=wsb

[Install]
WantedBy=multi-user.target
```
Команды: `sudo systemctl daemon-reload`, `sudo systemctl enable --now wsb-portal`.

### Пример автозапуска в Windows
- Создать задачу в Task Scheduler: *Action* — запуск `powershell.exe`, аргументы `-File C:\Soft_IPK\WSB_portal\run-uvicorn.ps1`.
- В `run-uvicorn.ps1` активировать venv и вызвать uvicorn:
```
cd C:\Soft_IPK\WSB_portal
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8090
```
- Установить параметры “Run whether user is logged on or not” и автоматический перезапуск по ошибке.

## Мониторинг и эксплуатация
1. **Логи приложения:** файл `uvicorn.log` (ротация через logrotate/systemd journald). Проверять ошибки FastAPI, APScheduler и уведомлений.
2. **Redis:** команда `redis-cli info memory` (контроль лимита 256 MB), проверка доступности `redis-cli ping`.
3. **PostgreSQL:** базовые метрики (активные соединения, VACUUM). Рекомендуется включить авто-вакуум и алерты на долгие запросы.
4. **APScheduler напоминания:** в логах каждые 60 секунд должно появляться сообщение `Задача отправки напоминаний выполнена ...`. При остановке — перезапустить сервис.
5. **SMTP:** следить за сообщениями `[EMAIL ERROR]` в логах; при смене пароля или EULA обновлять `.env`.
6. **Health-check:** можно добавить HTTP-пинг (`/auth/me` с сервисным токеном) или скрипт проверки (`python scripts/check_user.py`), запускать из Cron/Task Scheduler.
7. **Backup:** пока автоматизация отсутствует — выполнять `pg_dump` БД `RM` и `equipment` минимум раз в сутки.

## План развития
- ✅ Подготовить docker-compose (app + Redis) и включить его в документацию.
- Настроить Prometheus/Grafana или аналогичную систему для сбора метрик.
- Добавить скрипты автоматического бэкапа и уведомления об ошибках деплоя.

## Проверка окружений
- Если работаете на другом ПК, перед стартом читать корневые файлы контекста Soft_IPK
- После правок в подпроекте синхронизировать изменения на корне (`git add ..`)

## Рекомендации
- Использовать Conventional Commits (`feat:`, `fix:`, `docs:`)
- Хранить все данные только в PostgreSQL, не создавать локальные CSV
- Все новые решения документировать в `SOLUTIONS_HISTORY.md`
- При активации кеширования убеждаться, что Redis доступен; при недоступности устанавливать `ENABLE_CACHE=false`
- При отладке уведомлений можно временно отключать отправку переменной `ENABLE_EMAIL=false`

