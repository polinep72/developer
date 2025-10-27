#!/usr/bin/env python3
"""
Неинтерактивный скрипт для обновления МПИ
"""

import sys
from update_gosregister_mpi import GosregisterMPIUpdater

def main():
    """Основная функция"""
    updater = GosregisterMPIUpdater()
    
    # Получаем аргумент из командной строки
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        print("Использование: python run_mpi_update.py [1|2|3|4]")
        print("1. Обновить URL карточек СИ")
        print("2. Парсить МПИ с карточек")
        print("3. Синхронизировать МПИ в equipment")
        print("4. Полное обновление")
        sys.exit(1)
    
    if choice == '1':
        print("🚀 Обновление URL карточек СИ...")
        updater.update_gosregister_urls()
    elif choice == '2':
        print("🚀 Парсинг МПИ с карточек...")
        updater.parse_mpi_from_cards()
    elif choice == '3':
        print("🚀 Синхронизация МПИ в equipment...")
        updater.sync_equipment_mpi()
    elif choice == '4':
        print("🚀 Полное обновление...")
        updater.run_full_update()
    else:
        print("❌ Неверный выбор. Используйте 1, 2, 3 или 4")
        sys.exit(1)

if __name__ == "__main__":
    main()
