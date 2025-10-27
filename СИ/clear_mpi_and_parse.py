#!/usr/bin/env python3
"""
Скрипт для очистки МПИ и парсинга с Chrome
"""

import psycopg2
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config import Config

def get_db_connection():
    """Создает подключение к базе данных"""
    try:
        db_config = {
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'database': Config.DB_NAME,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD
        }
        return psycopg2.connect(**db_config)
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

def clear_mpi_values():
    """Очищает все значения МПИ"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        print("🧹 Очищаем все значения МПИ...")
        cursor.execute('UPDATE gosregister SET mpi = NULL WHERE mpi IS NOT NULL')
        cursor.execute('UPDATE equipment SET mpi = NULL WHERE mpi IS NOT NULL')
        
        conn.commit()
        print("✅ МПИ очищены")
        
    except Exception as e:
        print(f"❌ Ошибка при очистке МПИ: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def create_chrome_driver(visible=True):
    """Создает Chrome драйвер"""
    chrome_options = Options()
    
    if not visible:
        chrome_options.add_argument('--headless')
    
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"Ошибка создания Chrome драйвера: {e}")
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

def parse_mpi_with_chrome(card_url, visible=True):
    """Парсит МПИ с карточки используя Chrome"""
    driver = None
    try:
        print(f"    🌐 Открываем: {card_url}")
        driver = create_chrome_driver(visible)
        
        if not driver:
            return None
        
        driver.get(card_url)
        
        # Ждем загрузки
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)
        
        if visible:
            print(f"    👀 Страница открыта (5 секунд для просмотра)...")
            time.sleep(5)
        
        # Ищем таблицы
        tbody_elements = driver.find_elements(By.TAG_NAME, "tbody")
        print(f"    📊 Найдено таблиц: {len(tbody_elements)}")
        
        for i, tbody in enumerate(tbody_elements):
            try:
                rows = tbody.find_elements(By.TAG_NAME, "tr")
                print(f"    📋 Таблица {i+1}: {len(rows)} строк")
                
                # Ищем заголовок МПИ
                for row_idx, row in enumerate(rows):
                    row_text = row.text
                    if 'МПИ' in row_text:
                        print(f"    ✅ Найден заголовок МПИ: '{row_text}'")
                        
                        # Ищем следующую строку с данными
                        if row_idx + 1 < len(rows):
                            data_row = rows[row_idx + 1]
                            cells = data_row.find_elements(By.TAG_NAME, "td")
                            
                            print(f"    📝 Данные ({len(cells)} ячеек):")
                            for cell_idx, cell in enumerate(cells):
                                cell_text = cell.text.strip()
                                print(f"      Ячейка {cell_idx+1}: '{cell_text}'")
                                
                                # Проверяем на МПИ
                                if ('год' in cell_text.lower() or 'месяц' in cell_text.lower()) and cell_text != 'МПИ':
                                    mpi = extract_mpi_from_text(cell_text)
                                    if mpi:
                                        print(f"    🎯 НАЙДЕН МПИ: '{cell_text}' -> '{mpi}'")
                                        return mpi
                        break
                
            except Exception as e:
                print(f"    ⚠️  Ошибка таблицы {i+1}: {e}")
                continue
        
        print(f"    ❌ МПИ не найден")
        return None
        
    except Exception as e:
        print(f"    ❌ Ошибка: {e}")
        return None
    finally:
        if driver:
            if visible:
                print(f"    ⏳ Закрываем браузер через 3 секунды...")
                time.sleep(3)
            driver.quit()

def parse_mpi_records(visible=True, limit=3):
    """Парсит МПИ для записей"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
    try:
        # Получаем записи
        cursor.execute('''
            SELECT id, gosregister_number, web_url 
            FROM gosregister 
            WHERE web_url IS NOT NULL 
            AND web_url LIKE '%/fundmetrology/cm/mits/%'
            AND web_url NOT LIKE '%?page=%'
            ORDER BY id
            LIMIT %s
        ''', (limit,))
        
        records = cursor.fetchall()
        print(f"🚀 Обрабатываем {len(records)} записей")
        
        for record_id, gosregister_number, web_url in records:
            print(f"\n{'='*60}")
            print(f"📋 {gosregister_number}")
            print(f"🔗 {web_url}")
            print(f"{'='*60}")
            
            mpi = parse_mpi_with_chrome(web_url, visible)
            
            if mpi:
                cursor.execute('''
                    UPDATE gosregister 
                    SET mpi = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (mpi, record_id))
                print(f"✅ Сохранен: {mpi}")
            else:
                print(f"❌ МПИ не найден")
            
            time.sleep(2)
        
        conn.commit()
        print(f"\n✅ Завершено")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    """Основная функция"""
    import sys
    
    visible = True
    limit = 3
    
    for arg in sys.argv[1:]:
        if arg == 'headless':
            visible = False
        elif arg.isdigit():
            limit = int(arg)
    
    print(f"🚀 Парсер МПИ с Chrome")
    print(f"👀 Видимый браузер: {'Да' if visible else 'Нет'}")
    print(f"📊 Записей: {limit}")
    
    # Очищаем МПИ
    clear_mpi_values()
    
    # Парсим
    parse_mpi_records(visible, limit)

if __name__ == "__main__":
    main()
