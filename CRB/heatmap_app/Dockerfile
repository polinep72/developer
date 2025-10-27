# Используем тот же базовый образ Python для консистентности
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Копируем файл зависимостей визуализации
COPY heatmap_requirements.txt .

# Устанавливаем зависимости визуализации
RUN pip install --no-cache-dir -r heatmap_requirements.txt

# Копируем скрипт визуализации
COPY heatmap_visualization.py .

# Открываем порт, на котором будет работать Dash приложение (8081 как в вашем скрипте)
EXPOSE 8081

# Запускаем приложение визуализации
# Используем gunicorn или waitress для более продакшен-готового варианта,
# но для простоты пока оставим встроенный сервер Dash/Flask.
# Убедитесь, что в heatmap_visualization.py указан host='0.0.0.0'
CMD ["python", "heatmap_visualization.py"]