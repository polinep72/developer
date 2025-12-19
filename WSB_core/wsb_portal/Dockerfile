# Dockerfile для WSB Portal
FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем wsb_core, чтобы он был доступен как пакет
COPY wsb_core/ /app/wsb_core/

# Копирование файлов зависимостей
COPY wsb_portal/requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY wsb_portal/ .

# Переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV PORT=8090

# Открываем порт
EXPOSE 8090

# Health check (используем главную страницу, доступную без авторизации)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/').read()" || exit 1

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]

