#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Главное меню системы управления оборудованием
"""

import subprocess
import sys
import os
from datetime import datetime

def run_script(script_name):
    """Запуск скрипта"""
    try:
        if os.path.exists(script_name):
            subprocess.run([sys.executable, script_name], check=True)
        else:
            print(f"❌ Файл {script_name} не найден!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при запуске {script_name}: {e}")
    except KeyboardInterrupt:
        print("\n⏹️ Выполнение прервано пользователем")

def check_system_status():
    """Проверка состояния системы"""
    print("🔍 ПРОВЕРКА СОСТОЯНИЯ СИСТЕМЫ")
    print("="*40)
    
    # Проверка файлов
    files_to_check = [
        'app.py',
        'config.py',
        'create_postgres_database.py',
        'manage_database.py',
        'manage_gosregister.py',
        'import_excel_data.py'
    ]
    
    print("📁 Проверка файлов:")
    all_files_exist = True
    for file in files_to_check:
        if os.path.exists(file):
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} - НЕ НАЙДЕН!")
            all_files_exist = False
    
    # Проверка Excel файла
    excel_file = "ПЕРЕЧЕНЬ СИ и ИО.xlsx"
    if os.path.exists(excel_file):
        print(f"  ✅ {excel_file}")
    else:
        print(f"  ⚠️ {excel_file} - НЕ НАЙДЕН!")
    
    print()
    
    # Проверка веб-сервера
    try:
        import requests
        response = requests.get('http://localhost:8084/api/stats', timeout=5)
        if response.status_code == 200:
            print("🌐 Веб-сервер: ✅ РАБОТАЕТ")
            stats = response.json()
            print(f"  📊 СИ: {stats.get('си_count', 0)}")
            print(f"  🧪 ИО: {stats.get('ио_count', 0)}")
            print(f"  🔧 ВО: {stats.get('во_count', 0)}")
            print(f"  📋 Госреестр: {stats.get('gosregister_count', 0)}")
        else:
            print("🌐 Веб-сервер: ❌ НЕ ОТВЕЧАЕТ")
    except:
        print("🌐 Веб-сервер: ❌ НЕ ЗАПУЩЕН")
    
    print()
    return all_files_exist

def show_quick_actions():
    """Быстрые действия"""
    print("⚡ БЫСТРЫЕ ДЕЙСТВИЯ")
    print("="*30)
    print("1. 🌐 Открыть веб-интерфейс")
    print("2. 🔄 Перезапустить веб-сервер")
    print("3. 📊 Показать статистику")
    print("4. 🔍 Поиск оборудования")
    print("5. 📤 Экспорт данных")
    
    choice = input("\nВыберите действие (1-5): ").strip()
    
    if choice == '1':
        try:
            import webbrowser
            webbrowser.open('http://localhost:8084')
            print("🌐 Веб-интерфейс открыт в браузере")
        except:
            print("❌ Не удалось открыть браузер. Перейдите по адресу: http://localhost:8084")
    
    elif choice == '2':
        print("🔄 Перезапуск веб-сервера...")
        run_script('app.py')
    
    elif choice == '3':
        run_script('manage_database.py')
    
    elif choice == '4':
        search_term = input("Введите поисковый запрос: ").strip()
        if search_term:
            # Здесь можно добавить прямой поиск
            print(f"🔍 Поиск: {search_term}")
    
    elif choice == '5':
        run_script('manage_database.py')
    
    else:
        print("❌ Неверный выбор")

def main():
    """Главное меню"""
    while True:
        print("\n" + "="*60)
        print("🏭 СИСТЕМА УПРАВЛЕНИЯ ОБОРУДОВАНИЕМ")
        print("="*60)
        print(f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        print()
        
        # Проверка состояния системы
        system_ok = check_system_status()
        
        print("\n📋 ОСНОВНЫЕ МОДУЛИ:")
        print("1. 🔧 Управление базой данных")
        print("2. 📋 Управление Госреестром")
        print("3. 📥 Импорт данных из Excel")
        print("4. ⚡ Быстрые действия")
        print("5. 🌐 Запустить веб-сервер")
        print("6. 📖 Документация")
        print("7. ❌ Выход")
        
        choice = input("\nВыберите модуль (1-7): ").strip()
        
        if choice == '1':
            print("\n🔧 УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ")
            run_script('manage_database.py')
        
        elif choice == '2':
            print("\n📋 УПРАВЛЕНИЕ ГОСРЕЕСТРОМ")
            run_script('manage_gosregister.py')
        
        elif choice == '3':
            print("\n📥 ИМПОРТ ДАННЫХ")
            run_script('import_excel_data.py')
        
        elif choice == '4':
            show_quick_actions()
        
        elif choice == '5':
            print("\n🌐 ЗАПУСК ВЕБ-СЕРВЕРА")
            print("Для остановки нажмите Ctrl+C")
            run_script('app.py')
        
        elif choice == '6':
            print("\n📖 ДОКУМЕНТАЦИЯ")
            print("="*40)
            print("📁 Файлы проекта:")
            print("  • app.py - Веб-сервер Flask")
            print("  • config.py - Настройки подключения к БД")
            print("  • create_postgres_database.py - Создание БД")
            print("  • manage_database.py - Управление данными")
            print("  • manage_gosregister.py - Управление Госреестром")
            print("  • import_excel_data.py - Импорт из Excel")
            print("  • gosregister_parser.py - Парсер Госреестра")
            print()
            print("🌐 Веб-интерфейс: http://localhost:8084")
            print("📊 API endpoints:")
            print("  • /api/stats - Статистика")
            print("  • /api/equipment/СИ - Данные СИ")
            print("  • /api/equipment/ИО - Данные ИО")
            print("  • /api/equipment/ВО - Данные ВО")
            print("  • /api/gosregister - Госреестр")
            print()
            print("📋 База данных: PostgreSQL")
            print("  • Host: 192.168.1.139")
            print("  • Database: equipment")
            print("  • User: postgres")
        
        elif choice == '7':
            print("\n👋 До свидания!")
            break
        
        else:
            print("❌ Неверный выбор. Попробуйте снова.")
        
        input("\nНажмите Enter для продолжения...")

if __name__ == "__main__":
    main()
