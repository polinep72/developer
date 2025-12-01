# Инструкция по запуску контейнеров WSB Portal

## Быстрый запуск

### Вариант 1: Автоматический запуск с мониторингом

```bash
cd C:\Soft_IPK\WSB_portal
start-and-monitor.bat
```

Этот скрипт:
1. Остановит старые контейнеры (если есть)
2. Соберет образы
3. Запустит контейнеры
4. Покажет статус
5. Выведет логи и начнет мониторинг

### Вариант 2: Ручной запуск

```bash
cd C:\Soft_IPK\WSB_portal

# 1. Проверьте наличие .env файла
# Если файла нет, создайте его (см. DOCKER_SETUP.md)

# 2. Соберите образы
docker-compose build

# 3. Запустите контейнеры
docker-compose up -d

# 4. Проверьте статус
docker-compose ps

# 5. Просмотрите логи
docker-compose logs -f
```

## Мониторинг логов

### Вариант 1: PowerShell скрипт
```powershell
cd C:\Soft_IPK\WSB_portal
.\monitor-logs.ps1
```

### Вариант 2: Batch скрипт
```bash
cd C:\Soft_IPK\WSB_portal
monitor-logs.bat
```

### Вариант 3: Вручную
```bash
# Логи приложения
docker-compose logs -f wsb-portal

# Логи Redis
docker-compose logs -f wsb-redis

# Все логи
docker-compose logs -f
```

## Проверка статуса

```bash
# Статус контейнеров
docker-compose ps

# Проверка через Docker
docker ps --filter "name=wsb"

# Проверка health check
docker inspect wsb-portal | findstr "Health"
```

## Устранение проблем

### Контейнеры не запускаются

1. Проверьте наличие .env файла:
```bash
Test-Path .env
```

2. Проверьте конфигурацию:
```bash
docker-compose config
```

3. Проверьте логи сборки:
```bash
docker-compose build --no-cache
```

4. Проверьте, не занят ли порт 8090:
```bash
netstat -ano | findstr :8090
```

### Ошибки при сборке

1. Проверьте наличие Dockerfile и requirements.txt
2. Проверьте доступность Docker:
```bash
docker --version
docker-compose --version
```

3. Пересоберите образ:
```bash
docker-compose build --no-cache
```

### Ошибки при запуске

1. Проверьте логи:
```bash
docker-compose logs wsb-portal
```

2. Проверьте переменные окружения:
```bash
docker-compose exec wsb-portal env
```

3. Перезапустите контейнеры:
```bash
docker-compose restart
```

## Остановка контейнеров

```bash
# Остановка
docker-compose stop

# Остановка и удаление
docker-compose down

# Остановка с удалением volumes (Redis данные будут удалены)
docker-compose down -v
```

## Доступ к порталу

После успешного запуска портал будет доступен по адресу:
- http://localhost:8090
- http://192.168.1.139:8090

