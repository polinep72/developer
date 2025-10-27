# Используем официальный образ Python
FROM python:3.10-slim

# Set the environment variable for the timezone
ENV TZ=Europe/Moscow
# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем переменные окружения для Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Устанавливаем зависимости системы, если они нужны (например, для psycopg2)
# Обычно для -slim не требуется, но может понадобиться build-essential, libpq-dev
# RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Копируем файл зависимостей бота
COPY requirements.txt .

# Устанавливаем зависимости бота
# Используем --no-cache-dir для уменьшения размера образа
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота в рабочую директорию
COPY . .

# Запускаем бота при старте контейнера
CMD ["python", "main.py"]