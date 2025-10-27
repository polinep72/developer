#!/usr/bin/env python3
"""
Тестирование парсера внутри контейнера
"""

import sys
sys.path.append('/app')

from enhanced_gosregister_parser import EnhancedGosregisterParser

def test_parser():
    """Тестируем парсер напрямую"""
    
    print("🚀 Тестируем EnhancedGosregisterParser напрямую")
    
    try:
        parser = EnhancedGosregisterParser()
        print("✅ Парсер создан успешно")
        
        # Тестируем парсинг
        result = parser.parse_gosregister_with_mpi("93757-24")
        
        if result:
            print("✅ Данные получены:")
            for key, value in result.items():
                print(f"  {key}: {value}")
        else:
            print("❌ Данные не получены")
            
    except Exception as e:
        print(f"💥 Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_parser()
