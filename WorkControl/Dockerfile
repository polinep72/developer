# Используем официальный образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt ./

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код приложения в рабочую директорию
COPY main.py ./
# Если ваш основной файл называется monitor.py, то:
# COPY monitor.py ./

# Устанавливаем переменную окружения для логгирования Python без буферизации
ENV PYTHONUNBUFFERED=1

# Команда для запуска приложения при старте контейнера
# Если ваш основной файл называется monitor.py, измените main.py на monitor.py
CMD ["python", "main.py"]