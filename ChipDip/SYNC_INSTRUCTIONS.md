# Инструкции по синхронизации - ChipDip

## Обзор
Данный документ содержит инструкции по синхронизации проекта ChipDip между разными компьютерами и средами разработки.

## Настройка Git

### Инициализация репозитория
```bash
git init
git add .
git commit -m "Initial commit: ChipDip parser with analytics"
```

### Настройка удаленного репозитория
```bash
git remote add origin <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
git branch -M main
git push -u origin main
```

## Рабочий процесс

### 1. Клонирование проекта на новом компьютере
```bash
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
cd ChipDip
```

### 2. Настройка окружения
```bash
# Создание .env файла
cp .env.example .env

# Редактирование .env файла с вашими настройками
nano .env
```

### 3. Запуск проекта
```bash
# Запуск Docker контейнеров
docker-compose up -d

# Проверка статуса
docker-compose ps
```

## Структура файлов для синхронизации

### Обязательные файлы
- `docker-compose.yml` - конфигурация Docker
- `Dockerfile` - образ контейнера
- `requirements.txt` - зависимости Python
- `webapp/` - веб-интерфейс
- `chipdip_parser/` - модули парсера
- `init.sql` - схема базы данных

### Файлы контекста (рекомендуется синхронизировать)
- `PROJECT_CONTEXT.md` - описание проекта
- `SOLUTIONS_HISTORY.md` - история решений
- `CHAT_HISTORY.md` - история переписки
- `CHANGELOG.md` - история изменений
- `SYNC_INSTRUCTIONS.md` - данный файл

### Файлы, которые НЕ нужно синхронизировать
- `.env` - содержит секретные данные
- `logs/` - логи приложения
- `__pycache__/` - кэш Python
- `.git/` - метаданные Git

## Настройка .env файла

### Обязательные переменные
```env
# База данных
DB_HOST=localhost
DB_PORT=5432
DB_NAME=chipdip_db
DB_USER=chipdip_user
DB_PASSWORD=your_password

# Парсер
PARSER_INTERVAL=900
PARSER_MAX_REQUESTS_PER_HOUR=100
PARSER_HEADLESS=true

# Веб-интерфейс
FLASK_SECRET_KEY=your_secret_key
FLASK_DEBUG=false
```

## Команды для синхронизации

### Отправка изменений
```bash
# Добавление всех изменений
git add .

# Коммит с описанием
git commit -m "Описание изменений"

# Отправка на сервер
git push origin main
```

### Получение изменений
```bash
# Получение последних изменений
git pull origin main

# Перезапуск контейнеров после обновления
docker-compose down
docker-compose up -d --build
```

## Резервное копирование

### База данных
```bash
# Создание бэкапа
docker exec chipdip_postgres pg_dump -U chipdip_user chipdip_db > backup.sql

# Восстановление из бэкапа
docker exec -i chipdip_postgres psql -U chipdip_user chipdip_db < backup.sql
```

### Файлы проекта
```bash
# Создание архива
tar -czf chipdip_backup_$(date +%Y%m%d).tar.gz --exclude='.git' --exclude='logs' .

# Восстановление из архива
tar -xzf chipdip_backup_YYYYMMDD.tar.gz
```

## Устранение проблем

### Проблемы с Docker
```bash
# Очистка контейнеров
docker-compose down
docker system prune -a

# Пересборка с нуля
docker-compose build --no-cache
docker-compose up -d
```

### Проблемы с базой данных
```bash
# Проверка подключения
docker exec chipdip_postgres psql -U chipdip_user -d chipdip_db -c "SELECT 1;"

# Пересоздание базы данных
docker-compose down
docker volume rm chipdip_postgres_data
docker-compose up -d
```

### Проблемы с зависимостями
```bash
# Обновление зависимостей
pip install -r requirements.txt --upgrade

# Пересборка контейнера
docker-compose build --no-cache webapp
```

## Рекомендации

1. **Регулярные коммиты**: Делайте коммиты после каждого значимого изменения
2. **Описательные сообщения**: Используйте понятные описания в коммитах
3. **Тестирование**: Проверяйте работоспособность после синхронизации
4. **Резервные копии**: Создавайте бэкапы перед крупными изменениями
5. **Документация**: Обновляйте файлы контекста при значительных изменениях

## Контакты и поддержка

При возникновении проблем с синхронизацией:
1. Проверьте логи: `docker-compose logs`
2. Убедитесь в правильности настроек .env
3. Проверьте доступность базы данных
4. Обратитесь к файлам контекста для понимания архитектуры
