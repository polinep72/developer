#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования автоматического расчета дат поверки/аттестации
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import date, datetime

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

def test_calibration_calculation():
    """Тестирование автоматического расчета дат поверки"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("🧪 ТЕСТИРОВАНИЕ АВТОМАТИЧЕСКОГО РАСЧЕТА ДАТ ПОВЕРКИ")
        print("="*60)
        
        # 1. Показываем текущие МПИ в базе данных
        print("\n📋 Текущие МПИ в базе данных:")
        cursor.execute("""
            SELECT DISTINCT mpi, COUNT(*) as count
            FROM equipment 
            WHERE mpi IS NOT NULL AND mpi != '' AND equipment_type_id IN (1, 2)
            GROUP BY mpi
            ORDER BY count DESC
        """)
        
        mpi_data = cursor.fetchall()
        for row in mpi_data:
            print(f"  {row['mpi']}: {row['count']} записей")
        
        # 2. Тестируем функцию добавления поверки
        print("\n🧪 Тестирование функции add_calibration_certificate:")
        
        # Находим оборудование СИ для тестирования
        cursor.execute("""
            SELECT e.id, e.name, e.mpi
            FROM equipment e
            WHERE e.equipment_type_id = 1 AND e.mpi IS NOT NULL
            LIMIT 3
        """)
        
        test_equipment = cursor.fetchall()
        
        for eq in test_equipment:
            print(f"\n📊 Тестирование для: {eq['name'][:50]}...")
            print(f"   МПИ: {eq['mpi']}")
            
            # Тестируем расчет
            test_date = date(2024, 1, 1)
            certificate_number = f"TEST-{eq['id']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            try:
                cursor.execute("""
                    SELECT add_calibration_certificate(%s, %s, %s, 1000.00) as id
                """, (eq['id'], certificate_number, test_date))
                
                new_id = cursor.fetchone()['id']
                
                # Получаем рассчитанные даты
                cursor.execute("""
                    SELECT 
                        certificate_date,
                        next_calibration_date,
                        days_until_calibration,
                        e.mpi
                    FROM calibration_certificates c
                    JOIN equipment e ON c.equipment_id = e.id
                    WHERE c.id = %s
                """, (new_id,))
                
                result = cursor.fetchone()
                
                print(f"   📅 Дата поверки: {result['certificate_date']}")
                print(f"   📅 Следующая поверка: {result['next_calibration_date']}")
                print(f"   ⏰ Дней до поверки: {result['days_until_calibration']}")
                
                # Проверяем правильность расчета
                expected_days = (result['next_calibration_date'] - date.today()).days
                if abs(result['days_until_calibration'] - expected_days) <= 1:  # допускаем разницу в 1 день
                    print(f"   ✅ Расчет корректен")
                else:
                    print(f"   ❌ Ошибка в расчете! Ожидалось: {expected_days}, получено: {result['days_until_calibration']}")
                
                # Удаляем тестовую запись
                cursor.execute("DELETE FROM calibration_certificates WHERE id = %s", (new_id,))
                
            except Exception as e:
                print(f"   ❌ Ошибка: {e}")
        
        # 3. Показываем примеры расчетов для разных МПИ
        print("\n📐 Примеры расчетов для разных МПИ:")
        
        test_cases = [
            ("1", "1 год"),
            ("2", "2 года"), 
            ("3", "3 года"),
            ("4", "4 года"),
            ("5", "5 лет")
        ]
        
        base_date = date(2024, 6, 15)
        
        for mpi, description in test_cases:
            # Рассчитываем вручную
            years = int(mpi)
            calculated_next = base_date.replace(year=base_date.year + years) - date(2024, 1, 1)  # -1 день
            calculated_next = base_date.replace(year=base_date.year + years) - date(2024, 1, 2)  # -1 день
            
            # Правильный расчет: certificate_date + (mpi * 365) - 1 день
            from datetime import timedelta
            calculated_next = base_date + timedelta(days=years * 365 - 1)
            days_until = (calculated_next - date.today()).days
            
            print(f"   МПИ {description}:")
            print(f"     Дата поверки: {base_date}")
            print(f"     Следующая поверка: {calculated_next}")
            print(f"     Дней до поверки: {days_until}")
        
        conn.commit()
        print("\n✅ Тестирование завершено!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def show_current_calibrations():
    """Показать текущие поверки с рассчитанными датами"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("\n📋 ТЕКУЩИЕ ПОВЕРКИ/АТТЕСТАЦИИ")
        print("="*50)
        
        cursor.execute("""
            SELECT 
                c.id,
                e.name,
                e.mpi,
                c.certificate_number,
                c.certificate_date,
                c.next_calibration_date,
                c.days_until_calibration,
                c.calibration_cost
            FROM calibration_certificates c
            JOIN equipment e ON c.equipment_id = e.id
            ORDER BY c.days_until_calibration ASC
            LIMIT 10
        """)
        
        calibrations = cursor.fetchall()
        
        for cal in calibrations:
            status = ""
            if cal['days_until_calibration'] > 30:
                status = "🟢 В норме"
            elif cal['days_until_calibration'] > 0:
                status = "🟡 Скоро"
            else:
                status = "🔴 ПРОСРОЧЕНО"
            
            print(f"📄 {cal['certificate_number']}")
            print(f"   Оборудование: {cal['name'][:40]}...")
            print(f"   МПИ: {cal['mpi']}")
            print(f"   Дата поверки: {cal['certificate_date']}")
            print(f"   Следующая: {cal['next_calibration_date']}")
            print(f"   Статус: {status} ({cal['days_until_calibration']} дней)")
            if cal['calibration_cost']:
                print(f"   Стоимость: {cal['calibration_cost']} ₽")
            print()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        cursor.close()
        conn.close()

def main():
    """Главное меню тестирования"""
    while True:
        print("\n" + "="*60)
        print("🧪 ТЕСТИРОВАНИЕ РАСЧЕТА ДАТ ПОВЕРКИ/АТТЕСТАЦИИ")
        print("="*60)
        print("1. 🧪 Тестировать автоматический расчет")
        print("2. 📋 Показать текущие поверки")
        print("3. ❌ Выход")
        
        choice = input("\nВыберите действие (1-3): ").strip()
        
        if choice == '1':
            test_calibration_calculation()
        elif choice == '2':
            show_current_calibrations()
        elif choice == '3':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")
        
        input("\nНажмите Enter для продолжения...")

if __name__ == "__main__":
    main()
