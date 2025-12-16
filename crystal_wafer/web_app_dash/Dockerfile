FROM python:3.9-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1 # Хорошая практика
ENV PYTHONUNBUFFERED 1      # Хорошая практика для логов Docker

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MODE=production
# ENV STATIC_PATH=/react_static # Если используется

# Uvicorn должен слушать порт 8083 внутри контейнера
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8083"]