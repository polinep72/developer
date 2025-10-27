-- Автоматическая установка (Windows) --
запустите install.bat от имени Администратора

Для последующего запуска используйте run.bat

-- Ручная установка --

Создайте виртуальное окружение и установите все необходимые зависимости.
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

Если у вас есть проблемы с .\venv\Scripts\activate зайдите в PowerShell от имени Администратора и запустите команду 
Set-ExecutionPolicy Unrestricted -Force

Если у вас есть GPU, то дополнительно выполните команду:
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

Запустить приложение (находясь в виртуальном окружении):
python run.py



