#!/usr/bin/env python3
"""
Тестирование парсера для отладки
"""

import requests
import json

def test_parser():
    """Тестируем парсер через API"""
    
    url = "http://localhost:8084/api/gosregister/parse"
    data = {
        "gosregister_number": "93757-24"
    }
    
    print(f"🚀 Тестируем парсер для номера: {data['gosregister_number']}")
    print(f"📡 URL: {url}")
    print(f"📦 Данные: {data}")
    
    try:
        response = requests.post(url, json=data, timeout=30)
        print(f"📊 Статус ответа: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Успешный ответ:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("❌ Ошибка:")
            print(response.text)
            
    except Exception as e:
        print(f"💥 Исключение: {e}")

if __name__ == "__main__":
    test_parser()
