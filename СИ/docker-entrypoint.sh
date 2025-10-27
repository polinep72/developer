#!/bin/bash
set -e

# Функция для ожидания доступности базы данных
wait_for_db() {
    echo "Ожидание подключения к базе данных..."
    until python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '192.168.1.139'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'equipment'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', '')
    )
    conn.close()
    print('База данных доступна')
except:
    exit(1)
"
    do
        echo "База данных недоступна - ожидание..."
        sleep 2
    done
}

# Проверяем доступность БД
wait_for_db

# Запускаем приложение
echo "Запуск веб-приложения..."
exec "$@"
