# Инструкция по развертыванию с Docker

## Обзор

Проект Crystal Wafer Management System состоит из двух основных компонентов:
1. **Веб-приложение** (web_app_WebChip) - Flask приложение для управления складом
2. **Телеграм-бот** (telegram_bot_HMCB) - бот для поиска остатков кристаллов

Оба компонента могут быть развернуты либо в одном объединенном контейнере, либо отдельно.

---

## Варианты развертывания

### Вариант 1: Объединенный контейнер (рекомендуется)

Оба приложения запускаются в одном контейнере под управлением Supervisor.

**Преимущества:**
- Меньше ресурсов
- Проще управление
- Общие переменные окружения

**Запуск:**
```bash
docker-compose up -d crystal_wafer_combined
```

Или просто:
```bash
docker-compose up -d
```

### Вариант 2: Отдельные контейнеры

Каждое приложение в своем контейнере.

**Только веб-приложение:**
```bash
docker-compose --profile web-only up -d web_app_webchip
```

**Только телеграм-бот:**
```bash
docker-compose --profile bot-only up -d telegram_bot
```

---

## Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# База данных
DB_HOST=192.168.1.139
DB_PORT=5432
DB_USER=your_username
DB_PASSWORD=your_password
DB_NAME=ElEngine

# Flask приложение
SECRET_KEY=your_secret_key_here

# Telegram бот
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
```

**Получение токена Telegram бота:**
1. Найдите бота [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен в `.env` файл

---

## Сборка и запуск

### Сборка образа

```bash
# Объединенный контейнер
docker-compose build crystal_wafer_combined

# Или отдельные контейнеры
docker-compose build web_app_webchip
docker-compose build telegram_bot
```

### Запуск

```bash
# Запуск в фоновом режиме
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Просмотр логов конкретного сервиса
docker-compose logs -f crystal_wafer_combined
```

### Остановка

```bash
docker-compose down
```

---

## Проверка работы

### Веб-приложение

Откройте в браузере: `http://localhost:8089`

### Телеграм-бот

1. Найдите вашего бота в Telegram по username
2. Отправьте команду `/start`
3. Отправьте шифр кристалла (например, `HJB313`)

---

## Логирование

### Логи Supervisor

```bash
# Все логи
docker-compose logs -f crystal_wafer_combined

# Только веб-приложение
docker exec crystal_wafer_combined_container tail -f /var/log/supervisor/web_app.out.log

# Только телеграм-бот
docker exec crystal_wafer_combined_container tail -f /var/log/supervisor/telegram_bot.out.log
```

### Логи приложений

Логи также сохраняются в смонтированные директории:
- `./web_app_WebChip/logs/` - логи веб-приложения
- `./telegram_bot_HMCB/logs/` - логи телеграм-бота
- `./supervisor_logs/` - логи Supervisor

---

## Управление процессами

Supervisor автоматически управляет процессами:
- Автоматический запуск при старте контейнера
- Автоматический перезапуск при падении процесса
- Логирование в отдельные файлы

### Проверка статуса процессов

```bash
docker exec crystal_wafer_combined_container supervisorctl status
```

### Перезапуск процесса

```bash
# Перезапуск веб-приложения
docker exec crystal_wafer_combined_container supervisorctl restart web_app

# Перезапуск телеграм-бота
docker exec crystal_wafer_combined_container supervisorctl restart telegram_bot
```

---

## Troubleshooting

### Проблема: Контейнер не запускается

1. Проверьте логи:
   ```bash
   docker-compose logs crystal_wafer_combined
   ```

2. Проверьте переменные окружения:
   ```bash
   docker exec crystal_wafer_combined_container env | grep -E "(DB_|SECRET_KEY|TELEGRAM)"
   ```

3. Проверьте подключение к базе данных:
   ```bash
   docker exec crystal_wafer_combined_container ping -c 3 ${DB_HOST}
   ```

### Проблема: Веб-приложение недоступно

1. Проверьте, что порт 8089 не занят:
   ```bash
   netstat -an | grep 8089
   ```

2. Проверьте healthcheck:
   ```bash
   docker inspect crystal_wafer_combined_container | grep -A 10 Health
   ```

3. Проверьте логи веб-приложения:
   ```bash
   docker exec crystal_wafer_combined_container tail -f /var/log/supervisor/web_app.err.log
   ```

### Проблема: Телеграм-бот не отвечает

1. Проверьте токен бота:
   ```bash
   docker exec crystal_wafer_combined_container env | grep TELEGRAM_BOT_TOKEN
   ```

2. Проверьте логи телеграм-бота:
   ```bash
   docker exec crystal_wafer_combined_container tail -f /var/log/supervisor/telegram_bot.err.log
   ```

3. Проверьте подключение к базе данных из контейнера:
   ```bash
   docker exec crystal_wafer_combined_container python -c "import psycopg2; psycopg2.connect(host='${DB_HOST}', dbname='${DB_NAME}', user='${DB_USER}', password='${DB_PASSWORD}')"
   ```

---

## Производственное развертывание

### Рекомендации

1. **Используйте HTTPS:**
   - Настройте обратный прокси (nginx) перед контейнером
   - Установите `SESSION_COOKIE_SECURE=true` в `.env`

2. **Резервное копирование:**
   - Настройте автоматические бэкапы базы данных
   - Регулярно делайте бэкапы логов

3. **Мониторинг:**
   - Настройте мониторинг состояния контейнеров
   - Настройте алерты при падении процессов

4. **Обновление:**
   ```bash
   # Остановка контейнера
   docker-compose down
   
   # Обновление кода
   git pull
   
   # Пересборка образа
   docker-compose build --no-cache
   
   # Запуск
   docker-compose up -d
   ```

---

## Структура файлов Docker

```
crystal_wafer/
├── docker-compose.yml              # Главный Docker Compose (объединенный + отдельные сервисы)
├── docker-compose.combined.yml     # Упрощенный Docker Compose (только объединенный)
├── web_app_WebChip/
│   ├── Dockerfile                  # Dockerfile для веб-приложения
│   └── Dockerfile.combined         # Объединенный Dockerfile (веб + бот)
├── telegram_bot_HMCB/
│   └── Dockerfile                  # Dockerfile для телеграм-бота
└── docker/
    └── supervisord.conf            # Конфигурация Supervisor
```

---

## Дополнительная информация

- [DEPLOYMENT.md](DEPLOYMENT.md) - Подробная документация по развертыванию
- [PROJECT_CHECK_REPORT.md](PROJECT_CHECK_REPORT.md) - Отчет о комплексной проверке проекта
- [README.md](README.md) - Главная документация проекта

---

**Автор:** Полин Е.П.  
**Telegram:** @PolinEP  
**E-mail:** polin-ep@yandex.ru

