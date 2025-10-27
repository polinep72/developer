#!/usr/bin/env python3
"""
Парсер МПИ с headless Chrome и подробным логированием
"""

import psycopg2
import time
import os
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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

def create_headless_chrome():
    """Создает headless Chrome драйвер с уникальными настройками"""
    chrome_options = Options()
    
    # Headless режим
    chrome_options.add_argument('--headless')
    
    # Основные опции для стабильности
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-images')
    
    # Уникальные настройки
    unique_id = str(uuid.uuid4())[:8]
    user_data_dir = f'/tmp/chrome-{unique_id}'
    chrome_options.add_argument(f'--user-data-dir={user_data_dir}')
    
    # Размер окна
    chrome_options.add_argument('--window-size=1920,1080')
    
    # User Agent
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Дополнительные опции
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument('--disable-features=VizDisplayCompositor')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print(f"✅ Chrome драйвер создан (ID: {unique_id})")
        return driver, user_data_dir
    except Exception as e:
        print(f"❌ Ошибка создания Chrome драйвера: {e}")
        return None, None

def extract_mpi_from_text(text):
    """Извлекает МПИ из текста"""
    import re
    
    # Паттерны для поиска МПИ
    patterns = [
        r'(\d+)\s*год[а-я]*',
        r'(\d+)\s*месяц[а-я]*',
        r'(\d+)\s*year[s]?',
        r'(\d+)\s*month[s]?'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            value = int(match.group(1))
            if 'месяц' in text.lower() or 'month' in text.lower():
                # Конвертируем месяцы в годы
                if value >= 12:
                    return f"{value // 12} год"
                else:
                    return f"{value} месяцев"
            else:
                return f"{value} год"
    
    return None

def parse_mpi_from_page(driver, url, gosregister_number):
    """Парсит МПИ с конкретной страницы"""
    try:
        print(f"    🌐 Открываем страницу: {url}")
        driver.get(url)
        
        # Ждем загрузки страницы
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # Даем время на загрузку JavaScript
        time.sleep(5)
        print(f"    ⏰ Страница загружена, ищем МПИ...")
        
        # Получаем HTML страницы для анализа
        page_source = driver.page_source
        print(f"    📄 Размер HTML: {len(page_source)} символов")
        
        # Ищем все таблицы
        tables = driver.find_elements(By.TAG_NAME, "table")
        tbody_elements = driver.find_elements(By.TAG_NAME, "tbody")
        
        print(f"    📊 Найдено элементов: tables={len(tables)}, tbody={len(tbody_elements)}")
        
        # Проверяем каждую таблицу
        for i, tbody in enumerate(tbody_elements):
            try:
                rows = tbody.find_elements(By.TAG_NAME, "tr")
                print(f"    📋 Таблица {i+1}: {len(rows)} строк")
                
                # Ищем заголовок с "МПИ"
                for row_idx, row in enumerate(rows):
                    try:
                        row_text = row.text.strip()
                        print(f"      Строка {row_idx+1}: '{row_text[:50]}...'")
                        
                        if 'МПИ' in row_text:
                            print(f"      ✅ Найден заголовок МПИ в строке {row_idx+1}")
                            
                            # Ищем следующую строку с данными
                            if row_idx + 1 < len(rows):
                                data_row = rows[row_idx + 1]
                                cells = data_row.find_elements(By.TAG_NAME, "td")
                                
                                print(f"      📝 Строка с данными: {len(cells)} ячеек")
                                for cell_idx, cell in enumerate(cells):
                                    cell_text = cell.text.strip()
                                    cell_style = cell.get_attribute('style') or ''
                                    
                                    print(f"        Ячейка {cell_idx+1}: '{cell_text}' (style: {cell_style[:30]}...)")
                                    
                                    # Проверяем на МПИ
                                    if ('год' in cell_text.lower() or 'месяц' in cell_text.lower()) and cell_text != 'МПИ':
                                        mpi = extract_mpi_from_text(cell_text)
                                        if mpi:
                                            print(f"        🎯 НАЙДЕН МПИ: '{cell_text}' -> '{mpi}'")
                                            return mpi
                            
                            break
                    
                    except Exception as e:
                        print(f"        ⚠️  Ошибка обработки строки {row_idx+1}: {e}")
                        continue
                
            except Exception as e:
                print(f"    ⚠️  Ошибка обработки таблицы {i+1}: {e}")
                continue
        
        # Если не нашли в таблицах, ищем по всему тексту страницы
        print(f"    🔍 Поиск МПИ по всему тексту страницы...")
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        if 'МПИ' in page_text:
            print(f"    ✅ МПИ найден в тексте страницы")
            
            # Ищем паттерны МПИ в тексте
            import re
            mpi_patterns = [
                r'МПИ[:\s]*(\d+\s*(?:год|лет|месяц|месяцев))',
                r'межповерочный\s+интервал[:\s]*(\d+\s*(?:год|лет|месяц|месяцев))',
            ]
            
            for pattern in mpi_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    mpi_text = match.group(1)
                    mpi = extract_mpi_from_text(mpi_text)
                    if mpi:
                        print(f"    🎯 НАЙДЕН МПИ в тексте: '{mpi_text}' -> '{mpi}'")
                        return mpi
        
        print(f"    ❌ МПИ не найден на странице")
        return None
        
    except TimeoutException:
        print(f"    ⏰ Таймаут загрузки страницы")
        return None
    except Exception as e:
        print(f"    ❌ Ошибка при парсинге: {e}")
        return None

def parse_mpi_records(limit=3):
    """Парсит МПИ для записей из базы данных"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    driver = None
    user_data_dir = None
    
    try:
        # Получаем записи с URL карточек для парсинга МПИ
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
        print(f"🚀 Найдено {len(records)} записей для парсинга МПИ")
        
        if len(records) == 0:
            print("❌ Нет записей для обработки")
            return
        
        # Создаем Chrome драйвер
        driver, user_data_dir = create_headless_chrome()
        if not driver:
            print("❌ Не удалось создать Chrome драйвер")
            return
        
        for record_id, gosregister_number, web_url in records:
            print(f"\n{'='*80}")
            print(f"📋 Обрабатываем: {gosregister_number}")
            print(f"🔗 URL: {web_url}")
            print(f"{'='*80}")
            
            # Парсим МПИ с карточки
            mpi = parse_mpi_from_page(driver, web_url, gosregister_number)
            
            if mpi:
                # Обновляем МПИ в БД
                cursor.execute('''
                    UPDATE gosregister 
                    SET mpi = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (mpi, record_id))
                print(f"✅ МПИ найден и сохранен: {mpi}")
            else:
                print(f"❌ МПИ не найден для {gosregister_number}")
            
            # Пауза между записями
            if len(records) > 1:
                print(f"⏳ Пауза 3 секунды перед следующей записью...")
                time.sleep(3)
        
        conn.commit()
        print(f"\n✅ Парсинг завершен для {len(records)} записей")
        
    except Exception as e:
        print(f"❌ Ошибка при парсинге МПИ: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        if driver:
            driver.quit()
            print("🔒 Chrome драйвер закрыт")
        
        if user_data_dir and os.path.exists(user_data_dir):
            import shutil
            try:
                shutil.rmtree(user_data_dir)
                print(f"🧹 Удален временный каталог: {user_data_dir}")
            except:
                pass
        
        cursor.close()
        conn.close()

def main():
    """Основная функция"""
    import sys
    
    limit = 3  # По умолчанию 3 записи
    
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])
    
    print(f"🚀 Парсер МПИ с headless Chrome")
    print(f"📊 Количество записей: {limit}")
    print(f"🔧 Режим: headless (без видимого браузера)")
    
    parse_mpi_records(limit)

if __name__ == "__main__":
    main()
