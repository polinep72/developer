#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Демонстрация отображения таблицы при множественных поверках
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import date, timedelta

def get_db_connection():
    """Создает подключение к базе данных PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Ошибка подключения к БД: {e}")
        return None

def demo_multiple_calibrations():
    """Демонстрация работы с множественными поверками"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("📊 ДЕМОНСТРАЦИЯ: Множественные поверки для одного СИ")
        print("="*70)
        
        # 1. Найдем СИ с несколькими поверками
        cursor.execute("""
            SELECT 
                e.id,
                e.name,
                e.serial_number,
                COUNT(cc.id) as calibration_count
            FROM equipment e
            LEFT JOIN calibration_certificates cc ON e.id = cc.equipment_id
            WHERE e.equipment_type_id = 1
            GROUP BY e.id, e.name, e.serial_number
            HAVING COUNT(cc.id) > 1
            ORDER BY calibration_count DESC
            LIMIT 3
        """)
        
        equipment_with_multiple = cursor.fetchall()
        
        if not equipment_with_multiple:
            print("❌ Не найдено СИ с несколькими поверками")
            print("💡 Создадим демонстрационный пример...")
            
            # Создаем демонстрационный пример
            cursor.execute("""
                SELECT id, name, serial_number 
                FROM equipment 
                WHERE equipment_type_id = 1 
                LIMIT 1
            """)
            
            demo_equipment = cursor.fetchone()
            if demo_equipment:
                print(f"📋 Используем для демо: {demo_equipment['name']}")
                equipment_id = demo_equipment['id']
                
                # Добавляем несколько поверок для демонстрации
                demo_calibrations = [
                    {
                        'certificate_number': 'ДЕМО-2022-001',
                        'certificate_date': date(2022, 6, 15),
                        'calibration_cost': 1500.00
                    },
                    {
                        'certificate_number': 'ДЕМО-2023-002', 
                        'certificate_date': date(2023, 6, 15),
                        'calibration_cost': 1600.00
                    },
                    {
                        'certificate_number': 'ДЕМО-2024-003',
                        'certificate_date': date(2024, 6, 15), 
                        'calibration_cost': 1700.00
                    }
                ]
                
                for cal in demo_calibrations:
                    try:
                        cursor.execute("""
                            SELECT add_calibration_certificate(%s, %s, %s, %s) as id
                        """, (equipment_id, cal['certificate_number'], cal['certificate_date'], cal['calibration_cost']))
                        print(f"✅ Добавлена поверка: {cal['certificate_number']}")
                    except Exception as e:
                        print(f"⚠️ Поверка {cal['certificate_number']} уже существует")
                
                conn.commit()
        
        # 2. Показываем все поверки для каждого СИ
        print(f"\n📋 ПОЛНАЯ ИСТОРИЯ ПОВЕРОК:")
        print("="*50)
        
        for eq in equipment_with_multiple if equipment_with_multiple else [demo_equipment]:
            print(f"\n🔧 {eq['name'][:50]}...")
            print(f"   Зав.№: {eq['serial_number']}")
            print(f"   Всего поверок: {eq['calibration_count']}")
            
            # Получаем все поверки для этого СИ
            cursor.execute("""
                SELECT 
                    certificate_number,
                    certificate_date,
                    next_calibration_date,
                    days_until_calibration,
                    calibration_cost
                FROM calibration_certificates
                WHERE equipment_id = %s
                ORDER BY certificate_date DESC
            """, (eq['id'],))
            
            calibrations = cursor.fetchall()
            
            for i, cal in enumerate(calibrations, 1):
                status = ""
                if cal['days_until_calibration'] > 30:
                    status = "🟢 В норме"
                elif cal['days_until_calibration'] > 0:
                    status = "🟡 Скоро"
                else:
                    status = "🔴 ПРОСРОЧЕНО"
                
                marker = "👑" if i == 1 else "📄"
                print(f"   {marker} {cal['certificate_number']} ({cal['certificate_date']})")
                print(f"      Следующая: {cal['next_calibration_date']}")
                print(f"      Дней до поверки: {cal['days_until_calibration']} - {status}")
                if cal['calibration_cost']:
                    print(f"      Стоимость: {cal['calibration_cost']} ₽")
        
        # 3. Показываем что отображается в веб-таблице
        print(f"\n🌐 ЧТО ОТОБРАЖАЕТСЯ В ВЕБ-ТАБЛИЦЕ:")
        print("="*50)
        
        # Используем тот же запрос, что и в веб-приложении
        cursor.execute("""
            SELECT e.*, et.type_code, et.type_name, g.gosregister_number, g.si_name as gosregister_name,
                   g.web_url as gosregister_url,
                   cc.certificate_number, cc.certificate_date, cc.next_calibration_date,
                   cc.days_until_calibration, cc.calibration_cost
            FROM equipment e
            JOIN equipment_types et ON e.equipment_type_id = et.id
            LEFT JOIN gosregister g ON e.gosregister_id = g.id
            LEFT JOIN LATERAL (
                SELECT certificate_number, certificate_date, next_calibration_date,
                       days_until_calibration, calibration_cost
                FROM calibration_certificates cc
                WHERE cc.equipment_id = e.id
                ORDER BY cc.certificate_date DESC
                LIMIT 1
            ) cc ON true
            WHERE e.equipment_type_id = 1 AND cc.certificate_number IS NOT NULL
            ORDER BY e.row_number
            LIMIT 5
        """)
        
        web_display = cursor.fetchall()
        
        print(f"| Наименование | № св-ва | Дата поверки | След. поверка | Статус |")
        print(f"|--------------|---------|--------------|---------------|--------|")
        
        for item in web_display:
            status = ""
            if item['days_until_calibration'] > 30:
                status = f"🟢 В норме {item['days_until_calibration']}"
            elif item['days_until_calibration'] > 0:
                status = f"🟡 Скоро {item['days_until_calibration']}"
            else:
                status = "🔴 ПРОСРОЧЕНО"
            
            name = item['name'][:25] + "..." if len(item['name']) > 25 else item['name']
            cert_num = item['certificate_number'][:10] + "..." if len(item['certificate_number']) > 10 else item['certificate_number']
            
            print(f"| {name:<12} | {cert_num:<7} | {item['certificate_date']} | {item['next_calibration_date']} | {status:<18} |")
        
        # 4. Объяснение логики
        print(f"\n💡 ОБЪЯСНЕНИЕ ЛОГИКИ:")
        print("="*30)
        print("1. 📚 История поверок сохраняется в БД (все записи)")
        print("2. 🎯 В веб-таблице отображается только ПОСЛЕДНЯЯ поверка")
        print("3. 📅 Сортировка: ORDER BY certificate_date DESC")
        print("4. 🔢 Ограничение: LIMIT 1 (только одна запись)")
        print("5. ✅ Статус всегда актуален (дней до следующей поверки)")
        
        print(f"\n🎯 РЕЗУЛЬТАТ:")
        print("   • Пользователь видит актуальный статус")
        print("   • История поверок сохраняется для отчетов")
        print("   • Система автоматически выбирает последнюю поверку")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    """Главная функция"""
    demo_multiple_calibrations()
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
