#!/usr/bin/env python3
"""
Парсер МПИ через API веб-приложения с видимым Chrome
"""

import requests
import time
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Настройки API
API_BASE_URL = 'http://192.168.1.139:8084'

def create_chrome_driver():
    """Создает видимый Chrome драйвер"""
    chrome_options = Options()
    
    # Браузер будет видимым!
    # chrome_options.add_argument('--headless')  # НЕ используем headless
    
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Уникальный user-data-dir
    unique_id = str(uuid.uuid4())[:8]
    chrome_options.add_argument(f'--user-data-dir=C:/temp/chrome-{unique_id}')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Chrome браузер открыт - вы видите процесс!")
        return driver
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print("💡 Убедитесь, что Chrome установлен")
        return None

def extract_mpi_from_text(text):
    """Извлекает МПИ из текста"""
    import re
    
    patterns = [
        r'(\d+)\s*год[а-я]*',
        r'(\d+)\s*месяц[а-я]*',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            value = int(match.group(1))
            if 'месяц' in text.lower():
                if value >= 12:
                    return f"{value // 12} год"
                else:
                    return f"{value} месяцев"
            else:
                return f"{value} год"
    
    return None

def parse_mpi_from_page(driver, url, gosregister_number):
    """Парсит МПИ с страницы"""
    try:
        print(f"    🌐 Открываем: {url}")
        driver.get(url)
        
        # Ждем загрузки
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(5)
        
        print(f"    👀 Страница загружена - смотрите в браузере!")
        
        # Ищем таблицы
        tbody_elements = driver.find_elements(By.TAG_NAME, "tbody")
        print(f"    📊 Найдено таблиц: {len(tbody_elements)}")
        
        for i, tbody in enumerate(tbody_elements):
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            print(f"    📋 Таблица {i+1}: {len(rows)} строк")
            
            # Ищем заголовок МПИ
            for row_idx, row in enumerate(rows):
                row_text = row.text.strip()
                if 'МПИ' in row_text:
                    print(f"      ✅ Найден заголовок МПИ: '{row_text}'")
                    
                    # Ищем следующую строку с данными
                    if row_idx + 1 < len(rows):
                        data_row = rows[row_idx + 1]
                        cells = data_row.find_elements(By.TAG_NAME, "td")
                        
                        print(f"      📝 Данные: {len(cells)} ячеек")
                        for cell_idx, cell in enumerate(cells):
                            cell_text = cell.text.strip()
                            print(f"        Ячейка {cell_idx+1}: '{cell_text}'")
                            
                            # Проверяем на МПИ
                            if ('год' in cell_text.lower() or 'месяц' in cell_text.lower()) and cell_text != 'МПИ':
                                mpi = extract_mpi_from_text(cell_text)
                                if mpi:
                                    print(f"        🎯 НАЙДЕН МПИ: '{cell_text}' -> '{mpi}'")
                                    return mpi
                    break
        
        print(f"    ❌ МПИ не найден")
        return None
        
    except Exception as e:
        print(f"    ❌ Ошибка: {e}")
        return None

def get_gosregister_records():
    """Получает записи из Госреестра через API"""
    try:
        response = requests.get(f'{API_BASE_URL}/api/gosregister')
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Ошибка API: {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Ошибка подключения к API: {e}")
        return []

def update_mpi_via_api(gosregister_id, mpi):
    """Обновляет МПИ через API"""
    try:
        data = {'mpi': mpi}
        response = requests.put(f'{API_BASE_URL}/api/gosregister/{gosregister_id}/mpi', json=data)
        if response.status_code == 200:
            return True
        else:
            print(f"❌ Ошибка обновления API: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка API: {e}")
        return False

def main():
    """Основная функция"""
    driver = None
    
    try:
        print("🚀 Парсер МПИ через API с видимым Chrome")
        print("👀 Браузер откроется и вы увидите весь процесс!")
        
        # Получаем записи через API
        print("📡 Получаем данные из API...")
        records = get_gosregister_records()
        
        if not records:
            print("❌ Нет записей для обработки")
            return
        
        # Фильтруем записи с URL карточек
        card_records = [r for r in records if r.get('web_url') and '/fundmetrology/cm/mits/' in r['web_url']]
        print(f"📋 Найдено записей с карточками: {len(card_records)}")
        
        if len(card_records) == 0:
            print("❌ Нет записей с карточками")
            return
        
        # Берем первые 3 записи
        records_to_process = card_records[:3]
        print(f"📊 Обрабатываем {len(records_to_process)} записей")
        
        # Создаем видимый драйвер
        print("\n🔧 Открываем Chrome браузер...")
        driver = create_chrome_driver()
        if not driver:
            return
        
        print("✅ Браузер открыт! Вы можете видеть процесс.")
        input("⏳ Нажмите Enter чтобы начать парсинг...")
        
        # Обрабатываем записи
        success_count = 0
        for idx, record in enumerate(records_to_process, 1):
            record_id = record['id']
            gosregister_number = record['gosregister_number']
            web_url = record['web_url']
            
            print(f"\n[{idx}/{len(records_to_process)}] {'='*50}")
            print(f"📋 Обрабатываем: {gosregister_number}")
            print(f"🔗 URL: {web_url}")
            print(f"{'='*50}")
            
            # Парсим МПИ
            mpi = parse_mpi_from_page(driver, web_url, gosregister_number)
            
            if mpi:
                # Сохраняем через API
                if update_mpi_via_api(record_id, mpi):
                    success_count += 1
                    print(f"✅ Сохранен через API: {mpi}")
                else:
                    print(f"❌ Ошибка сохранения через API")
            else:
                print(f"❌ МПИ не найден")
            
            if idx < len(records_to_process):
                print(f"⏳ Пауза 3 секунды...")
                time.sleep(3)
        
        print(f"\n🎉 Готово! Обработано: {success_count}/{len(records_to_process)}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            print("\n🔒 Закрываем браузер...")
            input("⏳ Нажмите Enter чтобы закрыть...")
            driver.quit()

if __name__ == "__main__":
    main()
