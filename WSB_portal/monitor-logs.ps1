# Скрипт мониторинга логов WSB Portal
# Запуск: .\monitor-logs.ps1

$ErrorActionPreference = "Continue"

Write-Host "=== Мониторинг логов WSB Portal ===" -ForegroundColor Green
Write-Host "Для остановки нажмите Ctrl+C" -ForegroundColor Yellow
Write-Host ""

# Проверка наличия контейнеров
$portalExists = docker ps -a --filter "name=wsb-portal" --format "{{.Names}}" | Select-String "wsb-portal"
$redisExists = docker ps -a --filter "name=wsb-redis" --format "{{.Names}}" | Select-String "wsb-redis"

if (-not $portalExists) {
    Write-Host "⚠ Контейнер wsb-portal не найден!" -ForegroundColor Red
    Write-Host "Запустите: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}

if (-not $redisExists) {
    Write-Host "⚠ Контейнер wsb-redis не найден!" -ForegroundColor Red
    Write-Host "Запустите: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Контейнеры найдены" -ForegroundColor Green
Write-Host ""

# Функция для вывода логов с цветами
function Show-Logs {
    param(
        [string]$ContainerName,
        [string]$Color = "White"
    )
    
    Write-Host "=== Логи $ContainerName ===" -ForegroundColor $Color
    docker logs --tail=50 -f $ContainerName 2>&1 | ForEach-Object {
        if ($_ -match "ERROR|Error|error|Exception|Traceback") {
            Write-Host $_ -ForegroundColor Red
        } elseif ($_ -match "WARNING|Warning|warning") {
            Write-Host $_ -ForegroundColor Yellow
        } elseif ($_ -match "INFO|Info|info|Успешно|успешно") {
            Write-Host $_ -ForegroundColor Green
        } else {
            Write-Host $_ -ForegroundColor White
        }
    }
}

# Запуск мониторинга в фоне для обоих контейнеров
Write-Host "Запуск мониторинга логов..." -ForegroundColor Cyan
Write-Host ""

# Мониторинг логов приложения
Write-Host "=== Логи wsb-portal (последние 50 строк) ===" -ForegroundColor Cyan
docker logs --tail=50 wsb-portal 2>&1

Write-Host ""
Write-Host "=== Логи wsb-redis (последние 20 строк) ===" -ForegroundColor Cyan
docker logs --tail=20 wsb-redis 2>&1

Write-Host ""
Write-Host "=== Слежение за логами wsb-portal (Ctrl+C для остановки) ===" -ForegroundColor Cyan
docker logs -f wsb-portal 2>&1 | ForEach-Object {
    $timestamp = Get-Date -Format "HH:mm:ss"
    if ($_ -match "ERROR|Error|error|Exception|Traceback") {
        Write-Host "[$timestamp] $_" -ForegroundColor Red
    } elseif ($_ -match "WARNING|Warning|warning") {
        Write-Host "[$timestamp] $_" -ForegroundColor Yellow
    } elseif ($_ -match "INFO|Info|info|Успешно|успешно|Login|Registration") {
        Write-Host "[$timestamp] $_" -ForegroundColor Green
    } else {
        Write-Host "[$timestamp] $_" -ForegroundColor White
    }
}

