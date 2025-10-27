#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование правильности расчета days_until_calibration
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import date, datetime, timedelta

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

def test_days_calculation():
    """Тестирование расчета дней до поверки"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("🧪 ТЕСТИРОВАНИЕ РАСЧЕТА ДНЕЙ ДО ПОВЕРКИ")
        print("="*60)
        
        # Тестируем с разными датами
        test_cases = [
            {
                'name': 'Поверка была 1 год назад',
                'certificate_date': date(2023, 6, 15),
                'mpi': 1,
                'expected_next': date(2024, 6, 14),  # certificate_date + 1 год - 1 день
            },
            {
                'name': 'Поверка была 6 месяцев назад',
                'certificate_date': date(2023, 12, 15),
                'mpi': 1,
                'expected_next': date(2024, 12, 14),
            },
            {
                'name': 'Поверка была 2 года назад (МПИ = 2)',
                'certificate_date': date(2022, 6, 15),
                'mpi': 2,
                'expected_next': date(2024, 6, 14),
            }
        ]
        
        today = date.today()
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📊 Тест {i}: {test_case['name']}")
            print(f"   Дата поверки: {test_case['certificate_date']}")
            print(f"   МПИ: {test_case['mpi']} год(а)")
            print(f"   Ожидаемая следующая поверка: {test_case['expected_next']}")
            
            # Рассчитываем вручную
            manual_next = test_case['certificate_date'] + timedelta(days=test_case['mpi'] * 365 - 1)
            manual_days = (manual_next - today).days
            
            print(f"   Расчетная следующая поверка: {manual_next}")
            print(f"   Дней до поверки (ручной расчет): {manual_days}")
            
            # Проверяем правильность
            if manual_next == test_case['expected_next']:
                print(f"   ✅ Расчет даты следующей поверки корректен")
            else:
                print(f"   ❌ Ошибка в расчете даты! Ожидалось: {test_case['expected_next']}, получено: {manual_next}")
            
            # Показываем статус
            if manual_days > 30:
                status = "🟢 В норме"
            elif manual_days > 0:
                status = "🟡 Скоро поверка"
            else:
                status = "🔴 ПРОСРОЧЕНО"
            
            print(f"   Статус: {status}")
        
        # Проверяем существующие записи в БД
        print(f"\n📋 ПРОВЕРКА СУЩЕСТВУЮЩИХ ЗАПИСЕЙ В БД")
        print("="*50)
        
        cursor.execute("""
            SELECT 
                c.id,
                c.certificate_number,
                c.certificate_date,
                c.next_calibration_date,
                c.days_until_calibration,
                e.name,
                e.mpi,
                (c.next_calibration_date - CURRENT_DATE) as manual_days_calc
            FROM calibration_certificates c
            JOIN equipment e ON c.equipment_id = e.id
            ORDER BY c.days_until_calibration ASC
            LIMIT 5
        """)
        
        calibrations = cursor.fetchall()
        
        for cal in calibrations:
            print(f"\n📄 {cal['certificate_number']}")
            print(f"   Оборудование: {cal['name'][:40]}...")
            print(f"   МПИ: {cal['mpi']}")
            print(f"   Дата поверки: {cal['certificate_date']}")
            print(f"   Следующая поверка: {cal['next_calibration_date']}")
            print(f"   Дней до поверки (БД): {cal['days_until_calibration']}")
            print(f"   Дней до поверки (ручной): {cal['manual_days_calc']}")
            
            # Проверяем соответствие
            diff = abs(cal['days_until_calibration'] - cal['manual_days_calc'])
            if diff <= 1:  # допускаем разницу в 1 день
                print(f"   ✅ Расчет корректен (разница: {diff} дней)")
            else:
                print(f"   ❌ Ошибка в расчете! Разница: {diff} дней")
            
            # Статус
            days = cal['days_until_calibration']
            if days > 30:
                status = "🟢 В норме"
            elif days > 0:
                status = "🟡 Скоро"
            else:
                status = "🔴 ПРОСРОЧЕНО"
            print(f"   Статус: {status}")
        
        print(f"\n📝 ВЫВОД:")
        print(f"   Формула days_until_calibration = next_calibration_date - CURRENT_DATE")
        print(f"   где CURRENT_DATE - это текущая дата ({today})")
        print(f"   ✅ Положительные числа = дней до поверки")
        print(f"   ❌ Отрицательные числа = просрочено")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
    finally:
        cursor.close()
        conn.close()

def main():
    """Главная функция"""
    test_days_calculation()
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
