@echo off
chcp 65001 >nul
echo === Запуск WSB Portal контейнеров ===
cd /d %~dp0

echo.
echo Проверка файлов...
if not exist "Dockerfile" (
    echo ОШИБКА: Dockerfile не найден!
    pause
    exit /b 1
)
if not exist "docker-compose.yml" (
    echo ОШИБКА: docker-compose.yml не найден!
    pause
    exit /b 1
)

echo.
echo Остановка старых контейнеров (если есть)...
docker-compose down 2>nul

echo.
echo Сборка образов...
docker-compose build

if errorlevel 1 (
    echo ОШИБКА при сборке!
    pause
    exit /b 1
)

echo.
echo Запуск контейнеров...
docker-compose up -d

if errorlevel 1 (
    echo ОШИБКА при запуске!
    pause
    exit /b 1
)

echo.
echo Ожидание запуска контейнеров (10 секунд)...
timeout /t 10 /nobreak >nul

echo.
echo === Статус контейнеров ===
docker-compose ps

echo.
echo === Последние логи wsb-portal (50 строк) ===
docker-compose logs --tail=50 wsb-portal

echo.
echo === Последние логи wsb-redis (20 строк) ===
docker-compose logs --tail=20 wsb-redis

echo.
echo === Мониторинг логов (Ctrl+C для остановки) ===
echo Портал доступен по адресу: http://localhost:8090
echo.
docker-compose logs -f wsb-portal

