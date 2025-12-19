FROM python:3.9-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Установка системных зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование файлов приложения
COPY . .

# Создание директорий для логов
RUN mkdir -p logs

ENV MODE=production

# Expose порт для веб-приложения
EXPOSE 8089

# Запуск приложения (веб + телеграм-бот в одном процессе)
CMD ["python", "-u", "app.py"]
