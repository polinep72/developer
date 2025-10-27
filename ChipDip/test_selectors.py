#!/usr/bin/env python3
"""
Тестовый скрипт для проверки XPath селекторов на ChipDip
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def test_selectors():
    # Настройка Firefox
    firefox_options = Options()
    firefox_options.add_argument('--headless')
    firefox_options.add_argument('--no-sandbox')
    firefox_options.add_argument('--disable-dev-shm-usage')
    
    # Тестовый URL (замените на реальный)
    test_url = "https://www.chipdip.ru/product/9000484616"  # Замените на реальный URL
    
    driver = None
    try:
        driver = webdriver.Firefox(options=firefox_options)
        driver.set_page_load_timeout(30)
        
        print(f"Загружаем страницу: {test_url}")
        driver.get(test_url)
        time.sleep(3)  # Даем странице загрузиться
        
        print("\n=== Тестируем селекторы ===")
        
        # Тест 1: Остатки
        print("\n1. Поиск остатков:")
        selectors_stock = [
            "//span[contains(@class, 'item__avail')]//b",
            "//span[contains(@class, 'item__avail')]",
            "//span[@class='item__avail item__avail_available item__avail_float']//b",
            "//span[@class='item__avail item__avail_available item__avail_float']"
        ]
        
        for i, selector in enumerate(selectors_stock, 1):
            try:
                elements = driver.find_elements(By.XPATH, selector)
                print(f"  {i}. {selector}: найдено {len(elements)} элементов")
                for j, elem in enumerate(elements):
                    print(f"     Элемент {j+1}: '{elem.text}'")
            except Exception as e:
                print(f"  {i}. {selector}: ОШИБКА - {e}")
        
        # Тест 2: Цена
        print("\n2. Поиск цены:")
        selectors_price = [
            "//span[@class='ordering__value']",
            "//span[contains(@class, 'ordering__value')]",
            "//span[@id='price_9000484616']"
        ]
        
        for i, selector in enumerate(selectors_price, 1):
            try:
                elements = driver.find_elements(By.XPATH, selector)
                print(f"  {i}. {selector}: найдено {len(elements)} элементов")
                for j, elem in enumerate(elements):
                    print(f"     Элемент {j+1}: '{elem.text}'")
            except Exception as e:
                print(f"  {i}. {selector}: ОШИБКА - {e}")
        
        # Тест 3: Название товара
        print("\n3. Поиск названия товара:")
        selectors_name = [
            "//h1[@class='product-title']",
            "//h1",
            "//title"
        ]
        
        for i, selector in enumerate(selectors_name, 1):
            try:
                elements = driver.find_elements(By.XPATH, selector)
                print(f"  {i}. {selector}: найдено {len(elements)} элементов")
                for j, elem in enumerate(elements):
                    print(f"     Элемент {j+1}: '{elem.text[:100]}...'")
            except Exception as e:
                print(f"  {i}. {selector}: ОШИБКА - {e}")
        
        # Выводим HTML страницы для анализа
        print("\n=== HTML страницы (первые 2000 символов) ===")
        page_source = driver.page_source
        print(page_source[:2000])
        
    except Exception as e:
        print(f"Ошибка при тестировании: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    test_selectors()
