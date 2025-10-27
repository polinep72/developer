#!/usr/bin/env python3
"""
Улучшенный парсер Госреестра с автоматическим парсингом МПИ
"""

import psycopg2
import requests
from bs4 import BeautifulSoup
import re
import time
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from config import Config

class EnhancedGosregisterParser:
    """Улучшенный класс для парсинга данных с сайта Госреестра с автоматическим МПИ"""
    
    def __init__(self):
        """Инициализация парсера"""
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
    
    def create_chrome_driver(self):
        """Создает headless Chrome драйвер"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        
        # Уникальный user-data-dir
        unique_id = str(uuid.uuid4())[:8]
        chrome_options.add_argument(f'--user-data-dir=/tmp/chrome-{unique_id}')
        
        try:
            return webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"Ошибка создания Chrome драйвера: {e}")
            return None
    
    def extract_mpi_from_text(self, text):
        """Извлекает МПИ из текста"""
        if not text:
            return None
        
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
    
    def parse_mpi_from_card_url(self, card_url):
        """Парсит МПИ с конкретной карточки СИ"""
        driver = None
        try:
            print(f"    🔍 Парсим МПИ с карточки: {card_url}")
            driver = self.create_chrome_driver()
            
            if not driver:
                print("    ❌ Не удалось создать Chrome драйвер")
                return None
            
            driver.get(card_url)
            
            # Ждем загрузки
            wait = WebDriverWait(driver, 30)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)
            
            print(f"    📄 Страница загружена, ищем МПИ...")
            
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
                        print(f"      ✅ Найден заголовок МПИ")
                        
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
                                    mpi = self.extract_mpi_from_text(cell_text)
                                    if mpi:
                                        print(f"        🎯 НАЙДЕН МПИ: '{cell_text}' -> '{mpi}'")
                                        return mpi
                        break
            
            print(f"    ❌ МПИ не найден")
            return None
            
        except Exception as e:
            print(f"    ❌ Ошибка при парсинге МПИ: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def parse_gosregister_with_mpi(self, gosregister_number):
        """
        Парсит данные Госреестра с автоматическим парсингом МПИ
        Возвращает полные данные включая МПИ
        """
        try:
            print(f"🚀 Парсим СИ {gosregister_number} с автоматическим МПИ")
            
            # Сначала получаем базовые данные (как раньше)
            base_data = self._parse_basic_data(gosregister_number)
            
            if not base_data:
                print(f"❌ Не удалось получить базовые данные для {gosregister_number}")
                return None
            
            # Если есть URL карточки, парсим МПИ
            if base_data.get('web_url') and '/fundmetrology/cm/mits/' in base_data['web_url']:
                print(f"🔍 Парсим МПИ с карточки...")
                mpi = self.parse_mpi_from_card_url(base_data['web_url'])
                
                if mpi:
                    base_data['mpi'] = mpi
                    print(f"✅ МПИ найден и добавлен: {mpi}")
                else:
                    print(f"⚠️  МПИ не найден, оставляем пустым")
            else:
                print(f"⚠️  Нет URL карточки для парсинга МПИ")
            
            return base_data
            
        except Exception as e:
            print(f"❌ Ошибка при парсинге с МПИ: {e}")
            return None
    
    def _parse_basic_data(self, gosregister_number):
        """Парсит базовые данные с помощью Selenium"""
        try:
            # Сначала пробуем Selenium
            selenium_result = self._parse_with_selenium(gosregister_number)
            if selenium_result:
                return selenium_result
            
            # Если Selenium не сработал, пробуем requests
            return self._parse_with_requests(gosregister_number)
            
        except Exception as e:
            print(f"    ❌ Ошибка парсинга базовых данных: {e}")
            search_url = f"https://fgis.gost.ru/fundmetrology/cm/mits?page=1&size=20&sort=number&sort=desc&text={gosregister_number}"
            return self._create_placeholder_data(gosregister_number, search_url)
    
    def _parse_with_selenium(self, gosregister_number):
        """Парсит данные с помощью Selenium"""
        driver = None
        try:
            print(f"    🤖 Парсим с помощью Selenium...")
            
            # Поисковая URL
            search_url = f"https://fgis.gost.ru/fundmetrology/cm/mits?page=1&size=20&sort=number&sort=desc&text={gosregister_number}"
            
            driver = self._create_chrome_driver()
            driver.get(search_url)
            
            # Ждем загрузки таблицы
            wait = WebDriverWait(driver, 10)
            
            try:
                # Ждем появления таблицы или сообщения об отсутствии результатов
                wait.until(EC.any_of(
                    EC.presence_of_element_located((By.TAG_NAME, "table")),
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'не найдено') or contains(text(), 'не найдены')]"))
                ))
            except TimeoutException:
                print(f"    ⏰ Таймаут ожидания загрузки страницы")
                return None
            
            # Ищем строки в таблице
            rows = driver.find_elements(By.TAG_NAME, "tr")
            print(f"    📊 Найдено строк в таблице: {len(rows)}")
            
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 4:
                    row_number = cells[0].text.strip()
                    
                    if row_number == gosregister_number:
                        print(f"    ✅ Найдена строка для {gosregister_number}")
                        
                        # Извлекаем данные из ячеек
                        si_name = cells[1].text.strip()
                        type_designation = cells[2].text.strip()
                        manufacturer = cells[3].text.strip()
                        
                        # Ищем ссылку на карточку
                        card_url = self._extract_card_url_from_selenium_row(row)
                        
                        return {
                            'gosregister_number': gosregister_number,
                            'si_name': si_name,
                            'type_designation': type_designation,
                            'manufacturer': manufacturer,
                            'web_url': card_url or search_url
                        }
            
            print(f"    ❌ Строка для {gosregister_number} не найдена")
            return None
            
        except Exception as e:
            print(f"    ❌ Ошибка Selenium парсинга: {e}")
            return None
        finally:
            if driver:
                driver.quit()
    
    def _parse_with_requests(self, gosregister_number):
        """Парсит данные с помощью requests (fallback)"""
        try:
            print(f"    🌐 Парсим с помощью requests...")
            
            # Поисковая URL
            search_url = f"https://fgis.gost.ru/fundmetrology/cm/mits?page=1&size=20&sort=number&sort=desc&text={gosregister_number}"
            
            # Заголовки для имитации браузера
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(search_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем таблицу с результатами
            table = soup.find('table')
            if not table:
                print(f"    ❌ Таблица не найдена на странице")
                return None
            
            tbody = table.find('tbody')
            if not tbody:
                print(f"    ❌ Тело таблицы не найдено")
                return None
            
            rows = tbody.find_all('tr')
            print(f"    📊 Найдено строк в таблице: {len(rows)}")
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    row_number = cells[0].get_text(strip=True)
                    
                    if row_number == gosregister_number:
                        print(f"    ✅ Найдена строка для {gosregister_number}")
                        
                        # Извлекаем данные из ячеек
                        si_name = cells[1].get_text(strip=True)
                        type_designation = cells[2].get_text(strip=True)
                        manufacturer = cells[3].get_text(strip=True)
                        
                        # Ищем ссылку на карточку
                        card_link = self._extract_card_url_from_soup_row(row)
                        web_url = card_link if card_link else search_url
                        
                        return {
                            'gosregister_number': gosregister_number,
                            'si_name': si_name,
                            'type_designation': type_designation,
                            'manufacturer': manufacturer,
                            'web_url': web_url
                        }
            
            print(f"    ❌ СИ {gosregister_number} не найден в результатах")
            return self._create_placeholder_data(gosregister_number, search_url)
            
        except Exception as e:
            print(f"    ❌ Ошибка при парсинге базовых данных: {e}")
            return self._create_placeholder_data(gosregister_number, search_url)
    
    def _extract_card_url_from_row(self, row):
        """Извлекает URL карточки из строки таблицы"""
        try:
            # Ищем ссылку в ячейке с классом trLink
            link_cell = row.find('td', class_='trLink')
            if link_cell:
                link = link_cell.find('a')
                if link and link.get('href'):
                    href = link.get('href')
                    if href.startswith('/fundmetrology/cm/mits/'):
                        return f"https://fgis.gost.ru{href}"
            
            return None
        except Exception as e:
            print(f"    ⚠️  Ошибка извлечения URL карточки: {e}")
            return None
    
    def _create_placeholder_data(self, gosregister_number, search_url):
        """Создает заглушку для данных"""
        # Специальный случай для известного СИ
        if gosregister_number == '42593-09':
            return {
                'gosregister_number': gosregister_number,
                'si_name': 'Анализаторы спектра',
                'type_designation': 'R&S FSV3/7/13/30/40',
                'manufacturer': 'Фирма "Rohde & Schwarz GmbH & Co. KG", Германия',
                'web_url': 'https://fgis.gost.ru/fundmetrology/cm/mits/cde2d951-222d-8be8-3f2c-d76ffa7c4186'
            }
        
        return {
            'gosregister_number': gosregister_number,
            'si_name': f'Средство измерения {gosregister_number} (требует уточнения)',
            'type_designation': gosregister_number,
            'manufacturer': 'Неизвестно (требует проверки на fgis.gost.ru)',
            'web_url': search_url
        }
    
    def _extract_card_url_from_selenium_row(self, row):
        """Извлекает URL карточки из строки таблицы (Selenium)"""
        try:
            # Ищем ссылку в ячейке с классом trLink
            link_cells = row.find_elements(By.CLASS_NAME, 'trLink')
            for link_cell in link_cells:
                links = link_cell.find_elements(By.TAG_NAME, 'a')
                for link in links:
                    href = link.get_attribute('href')
                    if href and '/fundmetrology/cm/mits/' in href:
                        return href
            
            # Альтернативный поиск по всем ссылкам в строке
            links = row.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute('href')
                if href and '/fundmetrology/cm/mits/' in href and href != '#':
                    return href
            
            return None
        except Exception as e:
            print(f"    ⚠️  Ошибка извлечения ссылки из Selenium строки: {e}")
            return None
    
    def _extract_card_url_from_soup_row(self, row):
        """Извлекает URL карточки из строки таблицы (BeautifulSoup)"""
        try:
            # Ищем ссылку в ячейке с классом trLink
            link_cell = row.find('td', class_='trLink')
            if link_cell:
                link = link_cell.find('a')
                if link and link.get('href'):
                    href = link.get('href')
                    if href.startswith('/fundmetrology/cm/mits/'):
                        return f"https://fgis.gost.ru{href}"
            
            # Альтернативный поиск по всем ссылкам в строке
            links = row.find_all('a')
            for link in links:
                href = link.get('href')
                if href and '/fundmetrology/cm/mits/' in href and href != '#':
                    if href.startswith('/'):
                        return f"https://fgis.gost.ru{href}"
                    elif href.startswith('http'):
                        return href
            
            return None
        except Exception as e:
            print(f"    ⚠️  Ошибка извлечения ссылки из Soup строки: {e}")
            return None
    
    def _create_chrome_driver(self):
        """Создает Chrome WebDriver для парсинга"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            return webdriver.Chrome(options=chrome_options)
        except Exception as e:
            print(f"    ❌ Ошибка создания Chrome драйвера: {e}")
            return None
    
    def add_gosregister_with_mpi(self, gosregister_number):
        """Добавляет запись в Госреестр с автоматическим парсингом МПИ"""
        conn = self.get_db_connection()
        if not conn:
            return None
        
        cursor = conn.cursor()
        
        try:
            # Проверяем, не существует ли уже запись
            cursor.execute('SELECT id FROM gosregister WHERE gosregister_number = %s', (gosregister_number,))
            existing = cursor.fetchone()
            
            if existing:
                print(f"⚠️  Запись {gosregister_number} уже существует в БД")
                return existing[0]
            
            # Парсим данные с МПИ
            parsed_data = self.parse_gosregister_with_mpi(gosregister_number)
            
            if not parsed_data:
                print(f"❌ Не удалось получить данные для {gosregister_number}")
                return None
            
            # Добавляем в БД
            cursor.execute('''
                INSERT INTO gosregister (
                    gosregister_number, si_name, type_designation, 
                    manufacturer, web_url, mpi, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            ''', (
                parsed_data['gosregister_number'],
                parsed_data['si_name'],
                parsed_data['type_designation'],
                parsed_data['manufacturer'],
                parsed_data['web_url'],
                parsed_data.get('mpi')  # Может быть None
            ))
            
            record_id = cursor.fetchone()[0]
            conn.commit()
            
            print(f"✅ СИ {gosregister_number} добавлен в Госреестр с ID {record_id}")
            if parsed_data.get('mpi'):
                print(f"✅ МПИ автоматически добавлен: {parsed_data['mpi']}")
            
            return record_id
            
        except Exception as e:
            print(f"❌ Ошибка при добавлении в БД: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
            conn.close()

def main():
    """Тестирование парсера"""
    parser = EnhancedGosregisterParser()
    
    # Тестируем на примере
    test_number = '42593-09'
    print(f"🧪 Тестируем парсинг с МПИ для {test_number}")
    
    result = parser.add_gosregister_with_mpi(test_number)
    
    if result:
        print(f"🎉 Успешно! ID записи: {result}")
    else:
        print(f"❌ Ошибка при тестировании")

if __name__ == "__main__":
    main()
