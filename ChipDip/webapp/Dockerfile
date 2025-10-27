# Шаг 1: Базовый образ с Python
FROM python:3.11-slim-bullseye 

LABEL maintainer="Your Name <your.email@example.com>"

# Установка системных переменных для неинтерактивной установки
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1 

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libasound2 \
    curl \
    # Очистка после установки всех пакетов
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Установка Google Chrome Stable
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории в контейнере
WORKDIR /app

# Копирование файла зависимостей и установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения в рабочую директорию
COPY . .

# Открытие порта, на котором будет работать Flask-приложение
EXPOSE 8085

# Переменные окружения для вашего приложения
ENV FLASK_APP=app.py
ENV HEADLESS_MODE="1" 
ENV XLSX_FILE="rezult.xlsx" 
ENV TIME_FORMAT="%d.%m.%Y %H:%M:%S"
ENV CONSOLE_LOG_ACTIVE="1" 
ENV CHROME_EXECUTABLE_PATH="/usr/bin/google-chrome-stable"

# Команда для запуска приложения при старте контейнера
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "120", "--bind", "0.0.0.0:8085", "app:app"]