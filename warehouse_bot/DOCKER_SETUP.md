# Инструкция по развертыванию в Docker

## Предварительные требования

- Docker и Docker Compose установлены
- Файл `.env` с настройками подключения

## Настройка

1. Создайте файл `.env` в корне проекта со следующим содержимым:
   ```
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   DB_USER=postgres
   DB_PASSWORD=your_database_password
   DB_NAME=warehouse
   DB_HOST=your_database_host
   ```

2. Docker сеть создается автоматически при запуске docker-compose.

## Запуск

### Сборка и запуск
```bash
docker-compose up -d --build
```

### Только запуск (если образ уже собран)
```bash
docker-compose up -d
```

## Управление

### Просмотр логов
```bash
docker-compose logs -f warehouse-bot
```

### Остановка
```bash
docker-compose down
```

### Перезапуск
```bash
docker-compose restart warehouse-bot
```

### Просмотр статуса
```bash
docker-compose ps
```

## Отладка

### Вход в контейнер
```bash
docker exec -it warehouse-ipk-bot bash
```

### Просмотр переменных окружения
```bash
docker exec warehouse-ipk-bot env
```

### Проверка подключения к БД
```bash
docker exec warehouse-ipk-bot python -c "import psycopg2; print('psycopg2 OK')"
```

## Обновление

1. Остановите контейнер:
   ```bash
   docker-compose down
   ```

2. Обновите код (если нужно)

3. Пересоберите и запустите:
   ```bash
   docker-compose up -d --build
   ```
