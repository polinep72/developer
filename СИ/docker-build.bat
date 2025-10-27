@echo off
REM Скрипт для сборки Docker-образа системы учета оборудования (Windows)

echo 🐳 Сборка Docker-образа системы учета оборудования...

REM Проверяем наличие Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker не установлен. Установите Docker и повторите попытку.
    pause
    exit /b 1
)

REM Проверяем наличие docker-compose
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ❌ docker-compose не установлен. Установите docker-compose и повторите попытку.
    pause
    exit /b 1
)

REM Собираем образ
echo 📦 Сборка образа...
docker-compose build

if errorlevel 1 (
    echo ❌ Ошибка при сборке образа.
    pause
    exit /b 1
)

echo ✅ Образ успешно собран!
echo.
echo 🚀 Для запуска используйте:
echo    docker-compose up -d
echo.
echo 🔧 Для управления БД используйте:
echo    docker-compose --profile tools run db-tools
echo.
echo 📊 Для просмотра логов:
echo    docker-compose logs -f web
echo.
pause
