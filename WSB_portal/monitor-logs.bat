@echo off
chcp 65001 >nul
echo === Мониторинг логов WSB Portal ===
echo Для остановки нажмите Ctrl+C
echo.

cd /d %~dp0

:check
docker ps --filter "name=wsb-portal" --format "{{.Names}}" | findstr "wsb-portal" >nul
if errorlevel 1 (
    echo ОШИБКА: Контейнер wsb-portal не запущен!
    echo Запустите: docker-compose up -d
    pause
    exit /b 1
)

echo === Последние 50 строк логов wsb-portal ===
docker-compose logs --tail=50 wsb-portal

echo.
echo === Слежение за логами (Ctrl+C для остановки) ===
echo Портал: http://localhost:8090
echo.
docker-compose logs -f wsb-portal

