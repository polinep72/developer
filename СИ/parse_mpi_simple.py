#!/usr/bin/env python3
"""
Простой скрипт для парсинга МПИ с карточек СИ
Только requests + BeautifulSoup, без Selenium
"""

import psycopg2
import requests
from bs4 import BeautifulSoup
import time
import re
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

def parse_mpi_from_card(card_url):
    """Парсит МПИ с карточки СИ"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        
        print(f"    🔍 Загружаем карточку: {card_url}")
        response = requests.get(card_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Ищем таблицу с МПИ по паттерну из примера
            # <tbody><tr style="display: none;"><td rowspan="1000"></td></tr>
            # <tr class="borderBetweenChildren" style="text-align: center;">
            #   <td>Условие</td> <td>МПИ</td> <td>Действует</td> <td>Приказ Росстандарта</td>
            # </tr>
            # <tr class="borderBetweenChildren">
            #   <td></td> <td style="text-align: center;">1 год</td> <td></td>
            
            tbody_elements = soup.find_all('tbody')
            for tbody in tbody_elements:
                rows = tbody.find_all('tr')
                
                # Ищем строку заголовков с "МПИ"
                header_row_found = False
                for row in rows:
                    if 'МПИ' in row.get_text():
                        header_row_found = True
                        break
                
                if header_row_found:
                    print(f"    ✅ Найдена таблица с МПИ")
                    
                    # Ищем строку с данными МПИ
                    for row in rows:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            # Ищем ячейку с центрированным текстом (style="text-align: center;")
                            for cell in cells:
                                cell_style = cell.get('style', '')
                                cell_text = cell.get_text(strip=True)
                                
                                # Проверяем, что это не заголовок и содержит период
                                if ('text-align: center' in cell_style and 
                                    ('год' in cell_text.lower() or 'месяц' in cell_text.lower()) and 
                                    cell_text != 'МПИ'):
                                    
                                    # Извлекаем МПИ
                                    mpi = extract_mpi_from_text(cell_text)
                                    if mpi:
                                        print(f"    🎯 Найден МПИ: '{cell_text}' -> '{mpi}'")
                                        return mpi
            
            # Если не нашли в таблицах, ищем по всему документу
            all_text = soup.get_text()
            if 'МПИ' in all_text:
                print(f"    🔍 МПИ найден в документе, поиск по тексту...")
                # Попробуем найти МПИ в тексте напрямую
                mpi_patterns = [
                    r'МПИ[:\s]*(\d+\s*(?:год|лет|месяц|месяцев))',
                    r'межповерочный\s+интервал[:\s]*(\d+\s*(?:год|лет|месяц|месяцев))',
                ]
                for pattern in mpi_patterns:
                    match = re.search(pattern, all_text, re.IGNORECASE)
                    if match:
                        mpi_text = match.group(1)
                        mpi = extract_mpi_from_text(mpi_text)
                        if mpi:
                            print(f"    🎯 Найден МПИ в тексте: '{mpi_text}' -> '{mpi}'")
                            return mpi
            
            print(f"    ❌ МПИ не найден")
            return None
        else:
            print(f"    ❌ HTTP ошибка: {response.status_code}")
            return None
        
    except Exception as e:
        print(f"    ❌ Ошибка при парсинге МПИ с {card_url}: {e}")
        return None

def extract_mpi_from_text(text):
    """Извлекает МПИ из текста"""
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

def main():
    """Основная функция"""
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
            AND (mpi IS NULL OR mpi = '')
            ORDER BY id
            LIMIT 5
        ''')
        
        records = cursor.fetchall()
        print(f"Найдено {len(records)} записей для парсинга МПИ")
        
        for record_id, gosregister_number, web_url in records:
            print(f"\nПарсим МПИ для {gosregister_number}...")
            
            # Парсим МПИ с карточки
            mpi = parse_mpi_from_card(web_url)
            
            if mpi:
                # Обновляем МПИ в БД
                cursor.execute('''
                    UPDATE gosregister 
                    SET mpi = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (mpi, record_id))
                print(f"  ✅ МПИ найден и сохранен: {mpi}")
            else:
                print(f"  ❌ МПИ не найден для {gosregister_number}")
            
            # Небольшая пауза между запросами
            time.sleep(2)
        
        conn.commit()
        print("\n✅ Парсинг МПИ завершен")
        
    except Exception as e:
        print(f"❌ Ошибка при парсинге МПИ: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
