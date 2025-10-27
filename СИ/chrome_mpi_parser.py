#!/usr/bin/env python3
"""
Парсер МПИ с использованием Chrome и визуальным контролем
"""

import psycopg2
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
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

def create_chrome_driver(visible=True):
    """Создает Chrome драйвер"""
    chrome_options = Options()
    
    if not visible:
        # Headless режим для Docker
        chrome_options.add_argument('--headless')
    
    # Основные опции
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Дополнительные опции для стабильности
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_argument('--disable-images')  # Ускоряем загрузку
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        return driver
    except Exception as e:
        print(f"Ошибка создания Chrome драйвера: {e}")
        return None

def parse_mpi_from_card_with_chrome(card_url, visible=True):
    """Парсит МПИ с карточки СИ используя Chrome с визуальным контролем"""
    driver = None
    try:
        print(f"    🌐 Открываем страницу: {card_url}")
        driver = create_chrome_driver(visible)
        
        if not driver:
            return None
        
        driver.get(card_url)
        
        # Ждем загрузки страницы
        wait = WebDriverWait(driver, 30)
        
        try:
            # Ждем появления контента
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Даем время на полную загрузку JavaScript
            time.sleep(3)
            
            if visible:
                print(f"    👀 Страница открыта в браузере (задержка 5 секунд для просмотра)...")
                time.sleep(5)  # 5 секунд для просмотра
            
            # Ищем таблицы с МПИ
            print(f"    🔍 Ищем таблицы с МПИ...")
            
            # Ищем все таблицы
            tables = driver.find_elements(By.TAG_NAME, "table")
            tbody_elements = driver.find_elements(By.TAG_NAME, "tbody")
            
            print(f"    📊 Найдено таблиц: {len(tables)}, tbody: {len(tbody_elements)}")
            
            # Проверяем каждую таблицу
            for i, tbody in enumerate(tbody_elements):
                try:
                    rows = tbody.find_elements(By.TAG_NAME, "tr")
                    print(f"    📋 Таблица {i+1}: {len(rows)} строк")
                    
                    # Ищем заголовок с "МПИ"
                    header_found = False
                    for row_idx, row in enumerate(rows):
                        try:
                            row_text = row.text
                            if 'МПИ' in row_text:
                                print(f"    ✅ Найден заголовок МПИ в строке {row_idx+1}: '{row_text}'")
                                header_found = True
                                
                                # Ищем следующую строку с данными
                                if row_idx + 1 < len(rows):
                                    data_row = rows[row_idx + 1]
                                    cells = data_row.find_elements(By.TAG_NAME, "td")
                                    
                                    print(f"    📝 Строка с данными ({len(cells)} ячеек):")
                                    for cell_idx, cell in enumerate(cells):
                                        cell_text = cell.text.strip()
                                        cell_style = cell.get_attribute('style') or ''
                                        
                                        print(f"      Ячейка {cell_idx+1}: '{cell_text}' (style: {cell_style})")
                                        
                                        # Проверяем на МПИ
                                        if ('год' in cell_text.lower() or 'месяц' in cell_text.lower()) and cell_text != 'МПИ':
                                            mpi = extract_mpi_from_text(cell_text)
                                            if mpi:
                                                print(f"    🎯 НАЙДЕН МПИ: '{cell_text}' -> '{mpi}'")
                                                return mpi
                                
                                break
                        except Exception as e:
                            print(f"    ⚠️  Ошибка обработки строки {row_idx+1}: {e}")
                            continue
                    
                    if not header_found:
                        print(f"    ❌ Заголовок МПИ не найден в таблице {i+1}")
                
                except Exception as e:
                    print(f"    ⚠️  Ошибка обработки таблицы {i+1}: {e}")
                    continue
            
            # Если не нашли в таблицах, ищем по всему тексту страницы
            print(f"    🔍 Поиск МПИ по всему тексту страницы...")
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            if 'МПИ' in page_text:
                print(f"    ✅ МПИ найден в тексте страницы")
                # Ищем паттерны МПИ
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
        print(f"    ❌ Ошибка при парсинге МПИ: {e}")
        return None
    finally:
        if driver:
            if visible:
                print(f"    ⏳ Закрываем браузер через 3 секунды...")
                time.sleep(3)
            driver.quit()

def extract_mpi_from_text(text):
    """Извлекает МПИ из текста"""
    import re
    
    # Ищем паттерны типа "2 года", "1 год", "6 месяцев"
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

def parse_mpi_for_records(visible=True, limit=5):
    """Парсит МПИ для записей из базы данных"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    
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
        
        print(f"📋 Первые записи:")
        for i, record in enumerate(records[:3]):
            print(f"  {i+1}. ID: {record[0]}, Номер: {record[1]}, URL: {record[2][:50]}...")
        
        for record_id, gosregister_number, web_url in records:
            print(f"\n{'='*60}")
            print(f"📋 Обрабатываем: {gosregister_number}")
            print(f"🔗 URL: {web_url}")
            print(f"{'='*60}")
            
            # Парсим МПИ с карточки
            mpi = parse_mpi_from_card_with_chrome(web_url, visible)
            
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
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    """Основная функция"""
    import sys
    
    visible = True  # По умолчанию видимый браузер
    limit = 3      # По умолчанию 3 записи
    
    # Обработка аргументов командной строки
    for arg in sys.argv[1:]:
        if arg == 'headless':
            visible = False
            print("🔧 Режим: headless (без видимого браузера)")
        elif arg.isdigit():
            limit = int(arg)
            print(f"🔧 Лимит записей: {limit}")
    
    print(f"🚀 Запуск парсера МПИ с Chrome")
    print(f"👀 Видимый браузер: {'Да' if visible else 'Нет'}")
    print(f"📊 Количество записей: {limit}")
    
    parse_mpi_for_records(visible, limit)

if __name__ == "__main__":
    main()
