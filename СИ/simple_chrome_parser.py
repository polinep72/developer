#!/usr/bin/env python3
"""
Простой парсер МПИ с Chrome
"""

import psycopg2
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import Config

def get_db_connection():
    """Создает подключение к базе данных"""
    db_config = {
        'host': Config.DB_HOST,
        'port': Config.DB_PORT,
        'database': Config.DB_NAME,
        'user': Config.DB_USER,
        'password': Config.DB_PASSWORD
    }
    return psycopg2.connect(**db_config)

def parse_single_record():
    """Парсит одну запись"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем одну запись
    cursor.execute('''
        SELECT id, gosregister_number, web_url 
        FROM gosregister 
        WHERE web_url IS NOT NULL 
        AND web_url LIKE '%/fundmetrology/cm/mits/%'
        ORDER BY id
        LIMIT 1
    ''')
    
    record = cursor.fetchone()
    if not record:
        print("❌ Нет записей")
        return
    
    record_id, gosregister_number, web_url = record
    print(f"📋 Обрабатываем: {gosregister_number}")
    print(f"🔗 URL: {web_url}")
    
    # Создаем Chrome драйвер
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument(f'--user-data-dir=/tmp/chrome-user-data-{time.time()}')
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        print(f"🌐 Открываем страницу...")
        driver.get(web_url)
        
        # Ждем загрузки
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)
        
        print(f"👀 Страница загружена (5 секунд для просмотра)...")
        time.sleep(5)
        
        # Ищем таблицы
        tbody_elements = driver.find_elements(By.TAG_NAME, "tbody")
        print(f"📊 Найдено таблиц: {len(tbody_elements)}")
        
        for i, tbody in enumerate(tbody_elements):
            rows = tbody.find_elements(By.TAG_NAME, "tr")
            print(f"📋 Таблица {i+1}: {len(rows)} строк")
            
            # Ищем заголовок МПИ
            for row_idx, row in enumerate(rows):
                row_text = row.text
                if 'МПИ' in row_text:
                    print(f"✅ Найден заголовок МПИ: '{row_text}'")
                    
                    # Ищем следующую строку с данными
                    if row_idx + 1 < len(rows):
                        data_row = rows[row_idx + 1]
                        cells = data_row.find_elements(By.TAG_NAME, "td")
                        
                        print(f"📝 Данные ({len(cells)} ячеек):")
                        for cell_idx, cell in enumerate(cells):
                            cell_text = cell.text.strip()
                            print(f"  Ячейка {cell_idx+1}: '{cell_text}'")
                            
                            # Проверяем на МПИ
                            if ('год' in cell_text.lower() or 'месяц' in cell_text.lower()) and cell_text != 'МПИ':
                                print(f"🎯 НАЙДЕН МПИ: '{cell_text}'")
                                
                                # Обновляем в БД
                                cursor.execute('''
                                    UPDATE gosregister 
                                    SET mpi = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = %s
                                ''', (cell_text, record_id))
                                conn.commit()
                                print(f"✅ Сохранен: {cell_text}")
                                break
                    break
        
        print(f"⏳ Закрываем браузер через 3 секунды...")
        time.sleep(3)
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        driver.quit()
        cursor.close()
        conn.close()

def main():
    """Основная функция"""
    print("🚀 Простой парсер МПИ с Chrome")
    parse_single_record()
    print("✅ Завершено")

if __name__ == "__main__":
    main()
