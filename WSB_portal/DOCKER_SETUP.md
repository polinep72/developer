# Инструкция по использованию Docker для WSB Portal

## Требования

- Docker версии 20.10+
- Docker Compose версии 2.0+
- Файл `.env` с настройками БД, Redis и SMTP

## Быстрый старт

### 1. Подготовка окружения

Убедитесь, что файл `.env` существует и содержит все необходимые переменные:

```env
# PostgreSQL (БД RM)
POSTGRE_HOST=192.168.1.139
POSTGRE_PORT=5432
POSTGRE_USER=postgres
POSTGRE_PASSWORD=your_password
POSTGRE_DBNAME=RM

# PostgreSQL (БД equipment)
EQUIPMENT_DB_NAME=equipment
EQUIPMENT_DB_HOST=192.168.1.139
EQUIPMENT_DB_PORT=5432
EQUIPMENT_DB_USER=postgres
EQUIPMENT_DB_PASSWORD=your_password

# Redis (будет переопределено в docker-compose)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_ENABLED=true

# SMTP
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=587
SMTP_USER=your_email@yandex.ru
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=your_email@yandex.ru
SMTP_FROM_NAME=WSB Portal
ENABLE_EMAIL=true

# JWT
AUTH_SECRET_KEY=your_secret_key
```

**Важно:** В `docker-compose.yml` переменные `REDIS_HOST` и `REDIS_PORT` автоматически переопределяются для работы внутри Docker-сети.

### 2. Сборка и запуск

```bash
# Сборка образа и запуск контейнеров
docker-compose up -d --build

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Остановка с удалением volumes (Redis данные будут удалены)
docker-compose down -v
```

### 3. Проверка работоспособности

```bash
# Проверка статуса контейнеров
docker-compose ps

# Проверка health check
docker-compose ps

# Проверка логов приложения
docker-compose logs wsb-portal

# Проверка логов Redis
docker-compose logs redis

# Проверка подключения к Redis
docker-compose exec redis redis-cli ping
```

Портал будет доступен по адресу: `http://localhost:8090`

## Структура docker-compose.yml

### Сервисы

1. **wsb-portal** — основное приложение
   - Порт: `8090:8090`
   - Зависит от Redis (ждёт его готовности)
   - Health check каждые 30 секунд
   - Автоматический перезапуск при сбое

2. **redis** — кеш-сервер
   - Порт: `6379:6379`
   - Лимит памяти: 256 MB
   - Политика вытеснения: `allkeys-lru`
   - Данные сохраняются в volume `redis-data`

### Сети

- `wsb-network` — изолированная сеть для связи между контейнерами

### Volumes

- `redis-data` — постоянное хранилище для данных Redis

## Управление

### Обновление приложения

```bash
# Пересборка образа после изменений в коде
docker-compose up -d --build

# Или только перезапуск
docker-compose restart wsb-portal
```

### Просмотр логов

```bash
# Все логи
docker-compose logs

# Только приложение
docker-compose logs wsb-portal

# Последние 100 строк
docker-compose logs --tail=100 wsb-portal

# Следить за логами в реальном времени
docker-compose logs -f wsb-portal
```

### Выполнение команд внутри контейнера

```bash
# Войти в контейнер приложения
docker-compose exec wsb-portal bash

# Выполнить команду Python
docker-compose exec wsb-portal python scripts/check_user.py

# Выполнить команду в Redis
docker-compose exec redis redis-cli
```

### Очистка

```bash
# Остановка и удаление контейнеров
docker-compose down

# Удаление контейнеров и volumes (Redis данные будут удалены)
docker-compose down -v

# Удаление образов
docker-compose down --rmi all
```

## Разработка

### Локальная разработка с hot-reload

Для разработки с автоматической перезагрузкой при изменении кода:

1. Запустите только Redis:
```bash
docker-compose up -d redis
```

2. Запустите приложение локально с hot-reload:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
```

### Отладка

```bash
# Просмотр переменных окружения в контейнере
docker-compose exec wsb-portal env

# Проверка подключения к БД
docker-compose exec wsb-portal python -c "from app.services.bookings import _connect; _connect()"

# Проверка подключения к Redis
docker-compose exec wsb-portal python -c "import redis; r = redis.Redis(host='redis', port=6379); print(r.ping())"
```

## Production

### Рекомендации для продакшена

1. **Безопасность:**
   - Не монтируйте `.env` файл в контейнер (используйте Docker secrets или переменные окружения)
   - Используйте HTTPS через reverse-proxy (nginx, traefik)
   - Ограничьте доступ к портам только необходимым сетям

2. **Мониторинг:**
   - Настройте сбор логов (ELK, Loki)
   - Добавьте метрики (Prometheus)
   - Настройте алерты на health check failures

3. **Резервное копирование:**
   - Настройте автоматический бэкап БД PostgreSQL
   - Регулярно делайте бэкап volume `redis-data` (если требуется)

4. **Масштабирование:**
   - Для горизонтального масштабирования используйте внешний Redis
   - Настройте load balancer перед несколькими экземплярами приложения

### Пример с nginx reverse-proxy

```yaml
# docker-compose.prod.yml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - wsb-portal
```

## Устранение неполадок

### Контейнер не запускается

```bash
# Проверьте логи
docker-compose logs wsb-portal

# Проверьте конфигурацию
docker-compose config

# Проверьте, что порты не заняты
netstat -an | grep 8090
```

### Ошибки подключения к БД

- Убедитесь, что PostgreSQL доступен с хоста Docker
- Проверьте переменные окружения в `.env`
- Проверьте сетевые настройки Docker

### Ошибки подключения к Redis

```bash
# Проверьте, что Redis запущен
docker-compose ps redis

# Проверьте подключение
docker-compose exec wsb-portal python -c "import redis; r = redis.Redis(host='redis', port=6379); print(r.ping())"
```

### Health check не проходит

- Проверьте логи приложения
- Убедитесь, что приложение запустилось (может потребоваться больше времени)
- Увеличьте `start_period` в healthcheck, если приложение долго инициализируется

## Дополнительная информация

- Полная документация проекта: `README.md`
- Инструкции по синхронизации: `SYNC_INSTRUCTIONS.md`
- Настройка Redis: `REDIS_SETUP.md`
- Настройка уведомлений: `NOTIFICATIONS_SETUP.md`

