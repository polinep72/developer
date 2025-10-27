@echo off
setlocal


:: Разрешение выполнения PowerShell-скриптов
powershell -Command "Set-ExecutionPolicy Unrestricted -Force"

:: chcp 1251
set /p GPU=У вас есть GPU? (y/n): 

:: Создание виртуального окружения
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

:: Активация виртуального окружения
call venv\Scripts\activate

:: Установка зависимостей
echo Установка зависимостей...
pip install -r requirements.txt

:: Установка PyTorch, если есть GPU
if /I "%GPU%"=="y" (
    echo Установка PyTorch с CUDA 11.8...
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
)

:: Запуск приложения
echo Запуск приложения...
python run.py
