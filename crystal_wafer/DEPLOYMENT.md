# Документация по развертыванию
# Crystal Wafer Management System

**Версия:** 1.4.21

---

## Содержание

1. [Обзор](#обзор)
2. [Требования](#требования)
3. [Локальное развертывание](#локальное-развертывание)
4. [Развертывание с Docker](#развертывание-с-docker)
5. [Production развертывание](#production-развертывание)
6. [Настройка переменных окружения](#настройка-переменных-окружения)
7. [База данных](#база-данных)
8. [Мониторинг и логирование](#мониторинг-и-логирование)
9. [Обслуживание](#обслуживание)
10. [Устранение неполадок](#устранение-неполадок)

---

## Обзор

Crystal Wafer Management System может быть развернута несколькими способами:
- Локально (для разработки и тестирования)
- С использованием Docker (рекомендуется для production)
- На сервере без Docker (standalone)

---

## Требования

### Минимальные системные требования

- **ОС**: Linux, Windows Server, macOS
- **Python**: 3.14+ (для локального развертывания)
- **PostgreSQL**: 12+ (или доступ к существующей БД)
- **RAM**: 2 GB минимум, 4 GB рекомендуется
- **Диск**: 10 GB свободного места

### Программное обеспечение

- Python 3.14+ с pip
- PostgreSQL 12+ (или доступ к существующей БД)
- Git (для клонирования репозитория)
- Docker и Docker Compose (для развертывания с Docker)

---

## Локальное развертывание

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd crystal_wafer
```

### 2. Установка зависимостей

```bash
cd web_app_WebChip
pip install -r requirements.txt
```

### 3. Настройка переменных окружения

Создайте файл `.env` в директории `web_app_WebChip/`:

```env
# База данных
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ElEngine
DB_USER=your_username
DB_PASSWORD=your_password

# Безопасность
SECRET_KEY=your_secret_key_here

# Режим работы (development или production)
MODE=development

# SMTP (опционально, для email уведомлений об ошибках)
ENABLE_EMAIL=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME=Crystal Wafer Management System
ADMIN_EMAIL=admin@example.com
SMTP_USE_TLS=true

# Логирование (опционально)
LOG_JSON_FORMAT=false
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_ALL_REQUESTS=false
INCLUDE_REQUEST_ID_HEADER=false

# Сессии (опционально, для production за HTTPS)
SESSION_COOKIE_SECURE=false
```

**Важно:** Генерируйте надежный `SECRET_KEY` для production:
```python
import secrets
print(secrets.token_hex(32))
```

### 4. Запуск приложения

#### Режим разработки

```bash
python app.py
```

Приложение будет доступно по адресу `http://localhost:5000`

#### Production режим

Установите `MODE=production` в `.env` файле и запустите:

```bash
python app.py
```

Приложение автоматически запустится через Waitress WSGI сервер.

---

## Развертывание с Docker

### 1. Подготовка

Убедитесь, что установлены Docker и Docker Compose:

```bash
docker --version
docker-compose --version
```

### 2. Настройка переменных окружения

Создайте файл `.env` в директории `web_app_WebChip/` (см. раздел "Настройка переменных окружения").

### 3. Сборка и запуск

#### Использование Docker Compose (рекомендуется)

```bash
cd web_app_WebChip
docker-compose up -d
```

Приложение будет доступно по адресу `http://localhost:8087`

#### Использование Dockerfile напрямую

```bash
cd web_app_WebChip

# Сборка образа
docker build -t crystal-wafer:latest .

# Запуск контейнера
docker run -d \
  --name crystal-wafer-app \
  -p 8087:8087 \
  --env-file .env \
  crystal-wafer:latest
```

### 4. Просмотр логов

```bash
# Для Docker Compose
docker-compose logs -f app

# Для Docker
docker logs -f crystal-wafer-app
```

### 5. Остановка и удаление

```bash
# Docker Compose
docker-compose down

# Docker
docker stop crystal-wafer-app
docker rm crystal-wafer-app
```

---

## Production развертывание

### Рекомендации для production

1. **Используйте HTTPS**: Настройте обратный прокси (nginx, Apache) с SSL сертификатом
2. **Установите SECRET_KEY**: Сгенерируйте надежный секретный ключ
3. **Настройте SESSION_COOKIE_SECURE**: Установите `SESSION_COOKIE_SECURE=true` для HTTPS
4. **Настройте логирование**: Используйте файловое логирование или внешний сервис
5. **Резервное копирование**: Настройте регулярное резервное копирование БД
6. **Мониторинг**: Настройте мониторинг состояния приложения

### Развертывание за nginx (пример)

#### 1. Настройка nginx

Создайте файл `/etc/nginx/sites-available/crystal-wafer`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8087;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (если нужно)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Статические файлы
    location /static {
        alias /path/to/web_app_WebChip/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

#### 2. Активация конфигурации

```bash
sudo ln -s /etc/nginx/sites-available/crystal-wafer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Развертывание как системный сервис (systemd)

Создайте файл `/etc/systemd/system/crystal-wafer.service`:

```ini
[Unit]
Description=Crystal Wafer Management System
After=network.target postgresql.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/web_app_WebChip
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активация сервиса:

```bash
sudo systemctl daemon-reload
sudo systemctl enable crystal-wafer
sudo systemctl start crystal-wafer
sudo systemctl status crystal-wafer
```

---

## Настройка переменных окружения

### Обязательные переменные

| Переменная | Описание | Пример |
|------------|----------|--------|
| `DB_HOST` | Хост базы данных | `localhost` или `192.168.1.139` |
| `DB_PORT` | Порт базы данных | `5432` |
| `DB_NAME` | Имя базы данных | `ElEngine` |
| `DB_USER` | Пользователь БД | `postgres` |
| `DB_PASSWORD` | Пароль БД | `your_password` |
| `SECRET_KEY` | Секретный ключ для сессий | Сгенерированный ключ (см. выше) |

### Опциональные переменные

#### SMTP (для email уведомлений)

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ENABLE_EMAIL` | Включить email уведомления | `true` |
| `SMTP_HOST` | SMTP сервер | - |
| `SMTP_PORT` | Порт SMTP | `587` |
| `SMTP_USERNAME` | Имя пользователя SMTP | - |
| `SMTP_PASSWORD` | Пароль SMTP | - |
| `SMTP_FROM_EMAIL` | Email отправителя | Из `SMTP_USERNAME` |
| `SMTP_FROM_NAME` | Имя отправителя | `Crystal Wafer Management System` |
| `ADMIN_EMAIL` | Email администратора для уведомлений | - |
| `SMTP_USE_TLS` | Использовать TLS | `true` |

#### Логирование

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `LOG_JSON_FORMAT` | Использовать JSON формат логов | `false` |
| `LOG_LEVEL` | Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL) | `INFO` |
| `LOG_DIR` | Директория для файлов логов | `logs/` |
| `LOG_ALL_REQUESTS` | Логировать все запросы | `false` |
| `INCLUDE_REQUEST_ID_HEADER` | Добавлять X-Request-ID в заголовки | `false` |

#### Безопасность

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `MODE` | Режим работы (development/production) | `development` |
| `SESSION_COOKIE_SECURE` | Безопасные куки (только для HTTPS) | `false` |

---

## База данных

### Подключение к существующей БД

Приложение подключается к существующей базе данных PostgreSQL. Убедитесь, что:

1. БД доступна по указанному адресу и порту
2. Пользователь БД имеет необходимые права доступа
3. Таблицы созданы и структура БД соответствует требованиям приложения

### Миграции и индексы

После развертывания рекомендуется применить индексы для оптимизации:

```bash
cd web_app_WebChip
python apply_indexes.py
```

### Резервное копирование

Настройте регулярное резервное копирование БД:

```bash
# Пример скрипта резервного копирования
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -F c -f backup_$(date +%Y%m%d_%H%M%S).dump
```

---

## Мониторинг и логирование

### Логи приложения

Логи сохраняются в:
- `logs/app.log` - все логи приложения
- `logs/errors.log` - только ошибки (ERROR и выше)

### Ротация логов

Логи автоматически ротируются при достижении 10 MB. Хранится до 10 файлов бэкапа.

### Мониторинг через логи

Проверяйте логи на наличие ошибок:

```bash
# Последние 100 строк логов ошибок
tail -n 100 logs/errors.log

# Поиск ошибок в логах
grep ERROR logs/app.log

# Мониторинг логов в реальном времени
tail -f logs/app.log
```

### Метрики производительности

В логах автоматически записываются:
- Время выполнения SQL запросов (>1 секунды логируются как предупреждение)
- Время выполнения HTTP запросов (медленные запросы >1000ms логируются автоматически)
- request_id для трассировки запросов

---

## Обслуживание

### Обновление приложения

1. Остановите приложение
2. Сделайте резервную копию БД
3. Получите обновления:
   ```bash
   git pull
   ```
4. Обновите зависимости (если нужно):
   ```bash
   pip install -r requirements.txt
   ```
5. Примените миграции БД (если есть)
6. Перезапустите приложение

### Очистка кэша

Кэш данных автоматически очищается при изменениях в справочниках. Для ручной очистки перезапустите приложение.

### Очистка старых логов

Старые логи автоматически ротируются. Для ручной очистки:

```bash
# Удалить старые логи (старше 30 дней)
find logs/ -name "*.log.*" -mtime +30 -delete
```

---

## Устранение неполадок

### Проблема: Приложение не запускается

**Решение:**
1. Проверьте логи: `logs/errors.log`
2. Убедитесь, что все переменные окружения установлены
3. Проверьте подключение к БД:
   ```bash
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME
   ```
4. Проверьте, что порт не занят:
   ```bash
   # Linux
   netstat -tulpn | grep 8087
   
   # Windows
   netstat -ano | findstr 8087
   ```

### Проблема: Ошибки подключения к БД

**Решение:**
1. Проверьте параметры подключения в `.env`
2. Убедитесь, что БД доступна по сети
3. Проверьте права доступа пользователя БД
4. Проверьте firewall правила

### Проблема: SMTP уведомления не работают

**Решение:**
1. Убедитесь, что `ENABLE_EMAIL=true`
2. Проверьте настройки SMTP в `.env`
3. Для Gmail используйте "Пароль приложения" вместо обычного пароля
4. Проверьте логи на наличие ошибок SMTP

### Проблема: Медленная работа приложения

**Решение:**
1. Проверьте логи на медленные SQL запросы
2. Убедитесь, что индексы БД применены (`python apply_indexes.py`)
3. Проверьте использование памяти и CPU
4. Рассмотрите возможность увеличения размера пула подключений к БД

### Проблема: Ошибки с CSRF токенами

**Решение:**
1. Убедитесь, что `SECRET_KEY` установлен и не изменяется между перезапусками
2. Проверьте, что все формы включают CSRF токен
3. Для API endpoints CSRF проверка не применяется

---

## Поддержка

Если у вас возникли проблемы с развертыванием:

- **Email:** polin-ep@yandex.ru
- **Telegram:** @PolinEP

---

**Автор идеи и разработчик:** Полин Е.П.  
**Соразработчик:** Cursor  
**Лицензионные права:** ИнноЦентр ВАО и ИПК Электрон-Маш

