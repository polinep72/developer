# DOCKER ИНСТРУКЦИИ
## Развертывание системы учета оборудования

---

## 📋 Оглавление

1. [Требования](#1-требования)
2. [Быстрый старт](#2-быстрый-старт)
3. [Ручная сборка](#3-ручная-сборка)
4. [Конфигурация](#4-конфигурация)
5. [Управление](#5-управление)
6. [Устранение проблем](#6-устранение-проблем)

---

## 1. ТРЕБОВАНИЯ

### 1.1 Системные требования
- **Docker** версии 20.10+
- **Docker Compose** версии 2.0+
- **RAM:** минимум 2GB, рекомендуется 4GB
- **Диск:** минимум 5GB свободного места

### 1.2 Сетевые требования
- Доступ к серверу PostgreSQL: `192.168.1.139:5432`
- Открытый порт: `8084` (для веб-интерфейса)

### 1.3 Проверка установки
```bash
# Проверка Docker
docker --version

# Проверка Docker Compose
docker-compose --version
```

---

## 2. БЫСТРЫЙ СТАРТ

### 2.1 Автоматический запуск
```bash
# Сборка и запуск одной командой
./docker-build.sh && ./docker-run.sh
```

### 2.2 Пошаговый запуск
```bash
# 1. Сборка образа
./docker-build.sh

# 2. Запуск системы
./docker-run.sh
```

### 2.3 Проверка работы
Откройте браузер: **http://localhost:8084**

---

## 3. РУЧНАЯ СБОРКА

### 3.1 Сборка образа
```bash
# Сборка через docker-compose
docker-compose build

# Или прямая сборка
docker build -t equipment-system .
```

### 3.2 Запуск контейнера
```bash
# Запуск через docker-compose (рекомендуется)
docker-compose up -d

# Или прямой запуск
docker run -d \
  --name equipment-web \
  -p 8084:8084 \
  -e DB_HOST=192.168.1.139 \
  -e DB_PORT=5432 \
  -e DB_NAME=equipment \
  -e DB_USER=postgres \
  -e DB_PASSWORD=your_password \
  equipment-system
```

---

## 4. КОНФИГУРАЦИЯ

### 4.1 Переменные окружения
Создайте файл `.env` в корне проекта:
```env
# База данных
DB_HOST=192.168.1.139
DB_PORT=5432
DB_NAME=equipment
DB_USER=postgres
DB_PASSWORD=your_password_here

# Flask
FLASK_ENV=production
FLASK_APP=app.py
```

### 4.2 Настройка docker-compose.yml
Отредактируйте `docker-compose.yml`:
```yaml
environment:
  - DB_HOST=192.168.1.139
  - DB_PORT=5432
  - DB_NAME=equipment
  - DB_USER=postgres
  - DB_PASSWORD=your_password_here  # Замените на ваш пароль
```

### 4.3 Настройка портов
Измените порт в `docker-compose.yml`:
```yaml
ports:
  - "8084:8084"  # external:internal
```

---

## 5. УПРАВЛЕНИЕ

### 5.1 Основные команды

#### Запуск системы
```bash
docker-compose up -d
```

#### Остановка системы
```bash
docker-compose down
```

#### Перезапуск
```bash
docker-compose restart
```

#### Просмотр статуса
```bash
docker-compose ps
```

#### Просмотр логов
```bash
# Все логи
docker-compose logs

# Логи веб-приложения
docker-compose logs web

# Следить за логами в реальном времени
docker-compose logs -f web
```

### 5.2 Управление базой данных

#### Запуск утилит управления БД
```bash
docker-compose --profile tools run db-tools
```

#### Подключение к БД из контейнера
```bash
docker-compose exec web python manage_database.py
```

#### Импорт данных
```bash
docker-compose exec web python import_excel_data.py
```

### 5.3 Обновление системы

#### Пересборка после изменений
```bash
docker-compose build --no-cache
docker-compose up -d
```

#### Обновление зависимостей
```bash
# Отредактируйте requirements.txt
docker-compose build
docker-compose up -d
```

---

## 6. УСТРАНЕНИЕ ПРОБЛЕМ

### 6.1 Проблемы с запуском

#### Контейнер не запускается
```bash
# Проверьте логи
docker-compose logs web

# Проверьте статус
docker-compose ps

# Пересоберите образ
docker-compose build --no-cache
```

#### Ошибка подключения к БД
```bash
# Проверьте доступность БД
docker-compose exec web python -c "
import psycopg2
conn = psycopg2.connect(
    host='192.168.1.139',
    port=5432,
    database='equipment',
    user='postgres',
    password='your_password'
)
print('Подключение успешно')
conn.close()
"
```

#### Порт занят
```bash
# Проверьте, что использует порт
netstat -tulpn | grep 8084

# Остановите другие сервисы или измените порт в docker-compose.yml
```

### 6.2 Проблемы с производительностью

#### Медленная работа
```bash
# Проверьте использование ресурсов
docker stats

# Увеличьте лимиты в docker-compose.yml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '1.0'
```

#### Нехватка памяти
```bash
# Освободите память
docker system prune -a

# Ограничьте использование памяти
docker-compose down
docker-compose up -d --scale web=1
```

### 6.3 Проблемы с данными

#### Данные не отображаются
```bash
# Проверьте подключение к БД
docker-compose exec web python -c "
from config import Config
import psycopg2
conn = psycopg2.connect(
    host=Config.DB_HOST,
    port=Config.DB_PORT,
    database=Config.DB_NAME,
    user=Config.DB_USER,
    password=Config.DB_PASSWORD
)
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM equipment')
print(f'Записей в equipment: {cursor.fetchone()[0]}')
conn.close()
"
```

#### Проблемы с импортом
```bash
# Запустите импорт вручную
docker-compose exec web python create_postgres_database.py
```

---

## 7. РАЗВЕРТЫВАНИЕ В ПРОДАКШЕНЕ

### 7.1 Рекомендации по безопасности
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8084:8084"
    environment:
      - FLASK_ENV=production
      - DB_PASSWORD_FILE=/run/secrets/db_password
    secrets:
      - db_password
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

### 7.2 Мониторинг
```bash
# Установите мониторинг
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

### 7.3 Резервное копирование
```bash
# Скрипт резервного копирования
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose exec web pg_dump -h 192.168.1.139 -U postgres equipment > backup_$DATE.sql
```

---

## 8. ПОЛЕЗНЫЕ КОМАНДЫ

### 8.1 Отладка
```bash
# Войти в контейнер
docker-compose exec web bash

# Запустить Python shell
docker-compose exec web python

# Проверить переменные окружения
docker-compose exec web env
```

### 8.2 Очистка
```bash
# Удалить остановленные контейнеры
docker-compose rm

# Очистить неиспользуемые образы
docker image prune

# Полная очистка Docker
docker system prune -a
```

### 8.3 Мониторинг
```bash
# Использование ресурсов
docker stats

# Использование диска
docker system df

# Информация о контейнерах
docker-compose top
```

---

## 9. ИНТЕГРАЦИЯ С CI/CD

### 9.1 GitHub Actions
```yaml
name: Deploy Equipment System
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to server
        run: |
          docker-compose build
          docker-compose up -d
```

### 9.2 Автоматическое обновление
```bash
#!/bin/bash
# auto-update.sh
cd /path/to/project
git pull
docker-compose build
docker-compose up -d
```

---

**Версия:** 1.0  
**Дата:** Октябрь 2024  
**Автор:** Система учета оборудования
