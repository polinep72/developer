@echo off
REM Скрипт для запуска системы учета оборудования в Docker (Windows)

echo 🚀 Запуск системы учета оборудования в Docker...

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

REM Проверяем наличие образа
docker images | findstr "си_web" >nul 2>&1
if errorlevel 1 (
    echo 📦 Образ не найден. Сначала выполните сборку:
    echo    docker-build.bat
    pause
    exit /b 1
)

REM Запускаем контейнеры
echo 🐳 Запуск контейнеров...
docker-compose up -d

if errorlevel 1 (
    echo ❌ Ошибка при запуске контейнеров.
    pause
    exit /b 1
)

echo ⏳ Ожидание запуска сервисов...
timeout /t 5 /nobreak >nul

REM Проверяем статус
echo 📊 Статус контейнеров:
docker-compose ps

echo.
echo ✅ Система запущена!
echo 🌐 Веб-интерфейс доступен по адресу: http://localhost:8084
echo.
echo 📋 Полезные команды:
echo    docker-compose logs -f web     # Просмотр логов
echo    docker-compose down            # Остановка
echo    docker-compose restart         # Перезапуск
echo    docker-compose --profile tools run db-tools  # Управление БД
echo.
pause
