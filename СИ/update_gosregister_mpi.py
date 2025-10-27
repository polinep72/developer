#!/usr/bin/env python3
"""
Скрипт для обновления URL карточек СИ и парсинга МПИ из Госреестра
"""

import psycopg2
import requests
from bs4 import BeautifulSoup
import time
import re
from urllib.parse import urljoin
from config import Config
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class GosregisterMPIUpdater:
    """Класс для обновления МПИ из карточек Госреестра"""
    
    def __init__(self):
        """Инициализация"""
        self.db_config = {
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'database': Config.DB_NAME,
            'user': Config.DB_USER,
            'password': Config.DB_PASSWORD
        }
    
    def get_db_connection(self):
        """Создает подключение к базе данных"""
        try:
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            print(f"Ошибка подключения к БД: {e}")
            return None
    
    def update_gosregister_urls(self):
        """Обновляет URL карточек СИ в таблице gosregister"""
        conn = self.get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        try:
            # Получаем ВСЕ записи для обновления URL
            cursor.execute('''
                SELECT id, gosregister_number, web_url 
                FROM gosregister 
                ORDER BY id
            ''')
            
            records = cursor.fetchall()
            print(f"Найдено {len(records)} записей для обновления URL")
            
            for record_id, gosregister_number, current_url in records:
                print(f"Обновляем URL для {gosregister_number}...")
                
                # Ищем карточку СИ с помощью Selenium
                card_url = self._find_si_card_url_with_selenium(gosregister_number)
                
                if card_url:
                    # Обновляем URL в БД
                    cursor.execute('''
                        UPDATE gosregister 
                        SET web_url = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (card_url, record_id))
                    print(f"  ✅ URL обновлен: {card_url}")
                else:
                    print(f"  ❌ Карточка не найдена для {gosregister_number}")
                
                # Небольшая пауза между запросами
                time.sleep(2)
            
            conn.commit()
            print("✅ Обновление URL завершено")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при обновлении URL: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def _find_si_card_url_with_selenium(self, gosregister_number):
        """Находит URL карточки СИ по номеру Госреестра используя Selenium"""
        driver = None
        try:
            # Настраиваем Chrome для работы в headless режиме
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            
            # Формируем URL для поиска
            clean_number = gosregister_number.strip().replace(' ', '')
            search_url = f'https://fgis.gost.ru/fundmetrology/cm/mits?page=1&size=20&sort=number&sort=desc&text={clean_number}'
            
            print(f"    🔍 Поиск: {search_url}")
            driver.get(search_url)
            
            # Ждем загрузки результатов поиска
            wait = WebDriverWait(driver, 30)
            
            try:
                # Ждем появления таблицы с результатами
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
                
                # Получаем HTML после загрузки JavaScript
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем строку с нашим номером Госреестра
                rows = soup.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 4 and gosregister_number in row.text:
                        print(f"    ✅ Найдена строка с номером {gosregister_number}")
                        
                        # Ищем ссылку на карточку в последней ячейке (td class="trLink")
                        tr_link_cell = row.find('td', class_='trLink')
                        if tr_link_cell:
                            link = tr_link_cell.find('a')
                            if link:
                                href = link.get('href')
                                if href and "/fundmetrology/cm/mits/" in href and href != "#":
                                    if href.startswith("/"):
                                        full_url = f"https://fgis.gost.ru{href}"
                                    else:
                                        full_url = href
                                    print(f"    🎯 URL карточки: {full_url}")
                                    return full_url
                
                print(f"    ❌ Карточка не найдена для {gosregister_number}")
                return None
                
            except TimeoutException:
                print(f"    ⏰ Таймаут загрузки результатов поиска")
                return None
            
        except Exception as e:
            print(f"    ❌ Ошибка при поиске карточки {gosregister_number}: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def _find_si_card_url(self, gosregister_number):
        """Находит URL карточки СИ по номеру Госреестра (fallback метод)"""
        try:
            # Формируем URL для поиска
            clean_number = gosregister_number.strip().replace(' ', '')
            search_url = f'https://fgis.gost.ru/fundmetrology/cm/mits?page=1&size=20&sort=number&sort=desc&text={clean_number}'
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            }
            
            response = requests.get(search_url, headers=headers, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Ищем строку с нашим номером
                rows = soup.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 4 and gosregister_number in row.text:
                        # Ищем ссылку на карточку
                        links = row.find_all('a')
                        for link in links:
                            href = link.get('href')
                            if href and "/fundmetrology/cm/mits/" in href and href != "#":
                                if href.startswith("/"):
                                    return f"https://fgis.gost.ru{href}"
                                else:
                                    return href
            
            return None
            
        except Exception as e:
            print(f"Ошибка при поиске карточки {gosregister_number}: {e}")
            return None
    
    def parse_mpi_from_cards(self):
        """Парсит МПИ с карточек СИ"""
        conn = self.get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        try:
            # Получаем записи с URL карточек
            cursor.execute('''
                SELECT id, gosregister_number, web_url 
                FROM gosregister 
                WHERE web_url IS NOT NULL 
                AND web_url LIKE '%/fundmetrology/cm/mits/%'
                AND web_url NOT LIKE '%?page=%'
                AND (mpi IS NULL OR mpi = '')
                ORDER BY id
            ''')
            
            records = cursor.fetchall()
            print(f"Найдено {len(records)} записей для парсинга МПИ")
            
            for record_id, gosregister_number, web_url in records:
                print(f"Парсим МПИ для {gosregister_number}...")
                
                # Парсим МПИ с карточки
                mpi = self._parse_mpi_from_card(web_url)
                
                if mpi:
                    # Обновляем МПИ в БД
                    cursor.execute('''
                        UPDATE gosregister 
                        SET mpi = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    ''', (mpi, record_id))
                    print(f"  ✅ МПИ найден: {mpi}")
                else:
                    print(f"  ❌ МПИ не найден для {gosregister_number}")
                
                # Небольшая пауза между запросами
                time.sleep(2)
            
            conn.commit()
            print("✅ Парсинг МПИ завершен")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при парсинге МПИ: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def _parse_mpi_from_card(self, card_url):
        """Парсит МПИ с карточки СИ используя Selenium"""
        driver = None
        try:
            # Настраиваем Chrome для работы в headless режиме
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(card_url)
            
            # Ждем загрузки контента
            wait = WebDriverWait(driver, 30)
            
            try:
                # Ждем появления контента (либо таблицы, либо сообщения об ошибке)
                wait.until(EC.any_of(
                    EC.presence_of_element_located((By.TAG_NAME, "tbody")),
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                ))
                
                # Получаем HTML после загрузки JavaScript
                html = driver.page_source
                soup = BeautifulSoup(html, 'html.parser')
                
            except TimeoutException:
                print(f"    ⏰ Таймаут загрузки страницы {card_url}")
                return None
            
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
                                    mpi = self._extract_mpi_from_text(cell_text)
                                    if mpi:
                                        print(f"    🎯 Найден МПИ: '{cell_text}' -> '{mpi}'")
                                        return mpi
            
            print(f"    ❌ МПИ не найден в таблицах")
            return None
            
        except Exception as e:
            print(f"    ❌ Ошибка при парсинге МПИ с {card_url}: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def _extract_mpi_from_text(self, text):
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
    
    def sync_equipment_mpi(self):
        """Синхронизирует столбец mpi в equipment с данными из gosregister"""
        conn = self.get_db_connection()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        try:
            # Обновляем МПИ в equipment на основе данных из gosregister
            cursor.execute('''
                UPDATE equipment 
                SET mpi = g.mpi
                FROM gosregister g
                WHERE equipment.gosregister_id = g.id 
                AND g.mpi IS NOT NULL 
                AND g.mpi != ''
                AND (equipment.mpi IS NULL OR equipment.mpi != g.mpi)
            ''')
            
            updated_count = cursor.rowcount
            conn.commit()
            print(f"✅ Синхронизировано {updated_count} записей МПИ в equipment")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при синхронизации МПИ: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def run_full_update(self):
        """Запускает полное обновление"""
        print("🚀 Начинаем полное обновление МПИ из Госреестра...")
        
        # 1. Обновляем URL карточек
        print("\n1️⃣ Обновление URL карточек СИ...")
        self.update_gosregister_urls()
        
        # 2. Парсим МПИ с карточек
        print("\n2️⃣ Парсинг МПИ с карточек СИ...")
        self.parse_mpi_from_cards()
        
        # 3. Синхронизируем МПИ в equipment
        print("\n3️⃣ Синхронизация МПИ в equipment...")
        self.sync_equipment_mpi()
        
        print("\n✅ Полное обновление завершено!")

def main():
    """Основная функция"""
    updater = GosregisterMPIUpdater()
    
    print("Выберите действие:")
    print("1. Обновить URL карточек СИ")
    print("2. Парсить МПИ с карточек")
    print("3. Синхронизировать МПИ в equipment")
    print("4. Полное обновление")
    
    choice = input("Введите номер (1-4): ").strip()
    
    if choice == '1':
        updater.update_gosregister_urls()
    elif choice == '2':
        updater.parse_mpi_from_cards()
    elif choice == '3':
        updater.sync_equipment_mpi()
    elif choice == '4':
        updater.run_full_update()
    else:
        print("Неверный выбор")

if __name__ == "__main__":
    main()
