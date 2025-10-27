#!/usr/bin/env python3
"""
Локальный парсер МПИ с видимым Chrome для контроля процесса
"""

import psycopg2
import time
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
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

def create_visible_chrome():
    """Создает видимый Chrome драйвер"""
    chrome_options = Options()
    
    # НЕ headless - браузер будет видимым!
    # chrome_options.add_argument('--headless')  # Закомментировано!
    
    # Основные опции
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Уникальный user-data-dir
    unique_id = str(uuid.uuid4())[:8]
    chrome_options.add_argument(f'--user-data-dir=C:/temp/chrome-{unique_id}')
    
    # Дополнительные опции для стабильности
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        print("✅ Видимый Chrome драйвер создан - браузер откроется!")
        return driver
    except Exception as e:
        print(f"❌ Ошибка создания Chrome драйвера: {e}")
        print("💡 Убедитесь, что Chrome установлен и ChromeDriver в PATH")
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

def parse_mpi_from_url(driver, url, gosregister_number):
    """Парсит МПИ с URL с видимым контролем"""
    try:
        print(f"    🌐 Открываем страницу в браузере...")
        print(f"    🔗 URL: {url}")
        driver.get(url)
        
        # Ждем загрузки
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        print(f"    ⏰ Ждем 5 секунд для полной загрузки JavaScript...")
        time.sleep(5)
        
        print(f"    👀 Страница открыта в браузере - вы можете видеть процесс!")
        print(f"    📄 Ищем МПИ на странице...")
        
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
                        
                        print(f"      📝 Строка с данными: {len(cells)} ячеек")
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
        
        print(f"    ❌ МПИ не найден на странице")
        return None
        
    except Exception as e:
        print(f"    ❌ Ошибка при парсинге: {e}")
        return None

def main():
    """Основная функция"""
    import sys
    
    # Определяем количество записей
    limit = 3  # По умолчанию 3 записи
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    driver = None
    
    try:
        print("🚀 Локальный парсер МПИ с видимым Chrome")
        print("👀 Браузер будет открыт и вы увидите весь процесс!")
        print(f"📊 Обрабатываем {limit} записей")
        
        # Получаем записи
        cursor.execute('''
            SELECT id, gosregister_number, web_url 
            FROM gosregister 
            WHERE web_url IS NOT NULL 
            AND web_url LIKE '%/fundmetrology/cm/mits/%'
            ORDER BY id
            LIMIT %s
        ''', (limit,))
        
        records = cursor.fetchall()
        print(f"📋 Найдено записей: {len(records)}")
        
        if len(records) == 0:
            print("❌ Нет записей для обработки")
            return
        
        # Создаем видимый драйвер
        print("\n🔧 Создаем видимый Chrome драйвер...")
        driver = create_visible_chrome()
        if not driver:
            print("❌ Не удалось создать Chrome драйвер")
            return
        
        print("✅ Браузер открыт! Вы можете видеть процесс парсинга.")
        input("⏳ Нажмите Enter чтобы продолжить...")
        
        # Обрабатываем каждую запись
        success_count = 0
        for idx, record in enumerate(records, 1):
            record_id = record[0]
            gosregister_number = record[1]
            web_url = record[2]
            
            print(f"\n[{idx}/{len(records)}] {'='*60}")
            print(f"📋 Обрабатываем: {gosregister_number}")
            print(f"🔗 URL: {web_url}")
            print(f"{'='*60}")
            
            # Парсим МПИ
            mpi = parse_mpi_from_url(driver, web_url, gosregister_number)
            
            if mpi:
                # Сохраняем в БД
                cursor.execute('''
                    UPDATE gosregister 
                    SET mpi = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (mpi, record_id))
                success_count += 1
                print(f"✅ МПИ найден и сохранен в БД: {mpi}")
            else:
                print(f"❌ МПИ не найден для {gosregister_number}")
            
            # Пауза между записями
            if idx < len(records):
                print(f"⏳ Пауза 3 секунды перед следующей записью...")
                time.sleep(3)
        
        conn.commit()
        print(f"\n🎉 Парсинг завершен!")
        print(f"✅ Успешно обработано: {success_count}/{len(records)} записей")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        if driver:
            print("\n🔒 Закрываем браузер...")
            input("⏳ Нажмите Enter чтобы закрыть браузер...")
            driver.quit()
            print("✅ Браузер закрыт")
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
