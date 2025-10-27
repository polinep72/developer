# Используем официальный образ Python
FROM python:3.9-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл с зависимостями в рабочую директорию
COPY requirements.txt .

# Устанавливаем зависимости
#RUN pip install --no-cache-dir -r requirements.txt # Обычная установка
# Для ускорения сборки, если зависимости меняются редко, можно разделить:
# Сначала копируем и устанавливаем только зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы из локальной папки app/ в рабочую директорию /app в контейнере
# Предполагается, что ваш код (app.py, zotero_importer_core.py, templates/) будет в подпапке app/
COPY app/ /app/

# Создаем папки, которые могут понадобиться приложению внутри контейнера,
# если они не будут созданы самим приложением при старте или если права не позволят.
# Папка для логов (если LOG_PATH_IN_CONTAINER будет /app/logs)
RUN mkdir -p /app/logs
# Папка для временных Excel (если UPLOAD_FOLDER_EXCEL будет /app/uploads_temp_excel)
RUN mkdir -p /app/uploads_temp_excel

# Указываем порт, на котором будет работать приложение внутри контейнера
EXPOSE 8086

# Устанавливаем переменные окружения по умолчанию, если они не будут переопределены при запуске
# Это больше для информации, docker-compose их переопределит
ENV PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    FLASK_ENV=development \
    # Значения по умолчанию для Zotero (лучше передавать через docker-compose)
    ZOTERO_API_KEY="" \
    ZOTERO_GROUP_ID="" \
    ZOTERO_LIBRARY_TYPE="group" \
    # Пути внутри контейнера (будут переопределены docker-compose)
    SERVER_BASE_PDF_PATH_IN_CONTAINER="/mnt/shared_z_drive" \
    LOG_PATH_IN_CONTAINER="/app/logs"

# Команда для запуска приложения
# Для разработки можно использовать встроенный сервер Flask:
# Flask будет слушать на 0.0.0.0, чтобы быть доступным извне контейнера
CMD ["python", "-u", "app.py"]

# Для более продакшн-готового варианта с gunicorn (если gunicorn добавлен в requirements.txt):
# CMD ["gunicorn", "--bind", "0.0.0.0:8086", "--workers", "2", "--log-level", "info", "app:app"]
# 'app:app' означает: из файла app.py импортировать объект Flask с именем app