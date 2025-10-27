#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Демонстрация автоматического расчета в БД
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from datetime import date

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

def demo_auto_calculation():
    """Демонстрация автоматического расчета в БД"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("🔧 ДЕМОНСТРАЦИЯ: Автоматический расчет в БД")
        print("="*60)
        
        # 1. Найдем СИ для демонстрации
        cursor.execute("""
            SELECT e.id, e.name, e.serial_number, e.mpi
            FROM equipment e
            WHERE e.equipment_type_id = 1 AND e.mpi IS NOT NULL
            LIMIT 1
        """)
        
        equipment = cursor.fetchone()
        if not equipment:
            print("❌ Не найдено СИ с МПИ для демонстрации")
            return
        
        print(f"📋 Выбранное оборудование:")
        print(f"   ID: {equipment['id']}")
        print(f"   Наименование: {equipment['name']}")
        print(f"   Зав.№: {equipment['serial_number']}")
        print(f"   МПИ: {equipment['mpi']}")
        
        # 2. Показываем что мы вводим в БД
        print(f"\n📝 ЧТО МЫ ВВОДИМ В БД:")
        print("="*30)
        
        test_data = {
            'equipment_id': equipment['id'],
            'certificate_number': f'ДЕМО-{date.today().year}-{date.today().strftime("%m%d%H%M")}',
            'certificate_date': date(2024, 6, 15),
            'calibration_cost': 1500.00
        }
        
        print(f"   equipment_id: {test_data['equipment_id']}")
        print(f"   certificate_number: {test_data['certificate_number']}")
        print(f"   certificate_date: {test_data['certificate_date']}")
        print(f"   calibration_cost: {test_data['calibration_cost']}")
        print(f"   ❌ next_calibration_date: НЕ ВВОДИМ (рассчитывается автоматически)")
        print(f"   ❌ days_until_calibration: НЕ ВВОДИМ (рассчитывается автоматически)")
        
        # 3. Выполняем вставку
        print(f"\n⚡ ВЫПОЛНЯЕМ INSERT:")
        print("="*25)
        
        try:
            cursor.execute("""
                INSERT INTO calibration_certificates (
                    equipment_id,
                    certificate_number,
                    certificate_date,
                    calibration_cost
                ) VALUES (%s, %s, %s, %s)
                RETURNING *
            """, (
                test_data['equipment_id'],
                test_data['certificate_number'], 
                test_data['certificate_date'],
                test_data['calibration_cost']
            ))
            
            result = cursor.fetchone()
            
            print(f"✅ Запись успешно добавлена!")
            print(f"   ID: {result['id']}")
            
        except Exception as e:
            if "duplicate key" in str(e).lower():
                print(f"⚠️ Запись с таким номером уже существует")
                # Получаем существующую запись
                cursor.execute("""
                    SELECT * FROM calibration_certificates 
                    WHERE certificate_number = %s
                """, (test_data['certificate_number'],))
                result = cursor.fetchone()
            else:
                raise e
        
        # 4. Показываем что рассчитала БД автоматически
        print(f"\n🤖 ЧТО РАССЧИТАЛА БД АВТОМАТИЧЕСКИ:")
        print("="*40)
        
        print(f"   ✅ next_calibration_date: {result['next_calibration_date']}")
        print(f"   ✅ days_until_calibration: {result['days_until_calibration']}")
        
        # 5. Показываем формулу расчета
        print(f"\n🧮 ФОРМУЛЫ РАСЧЕТА:")
        print("="*20)
        
        # Получаем МПИ для расчета
        mpi_value = equipment['mpi']
        if mpi_value.isdigit():
            mpi_years = int(mpi_value)
        else:
            mpi_years = 1
        
        print(f"   МПИ: {mpi_value} → {mpi_years} год(а)")
        print(f"   certificate_date: {result['certificate_date']}")
        print(f"   ")
        print(f"   next_calibration_date = certificate_date + (mpi * 365 дней) - 1 день")
        print(f"   next_calibration_date = {result['certificate_date']} + ({mpi_years} * 365) - 1")
        
        expected_next = result['certificate_date']
        from datetime import timedelta
        expected_next = expected_next.replace(year=expected_next.year + mpi_years) - timedelta(days=1)
        
        print(f"   next_calibration_date = {expected_next}")
        print(f"   ✅ Фактический результат: {result['next_calibration_date']}")
        
        print(f"   ")
        print(f"   days_until_calibration = next_calibration_date - CURRENT_DATE")
        print(f"   days_until_calibration = {result['next_calibration_date']} - {date.today()}")
        
        manual_days = (result['next_calibration_date'] - date.today()).days
        print(f"   days_until_calibration = {manual_days}")
        print(f"   ✅ Фактический результат: {result['days_until_calibration']}")
        
        # 6. Проверяем правильность
        print(f"\n✅ ПРОВЕРКА:")
        print("="*15)
        
        if result['next_calibration_date'] == expected_next:
            print(f"   ✅ next_calibration_date рассчитан правильно")
        else:
            print(f"   ❌ Ошибка в расчете next_calibration_date")
        
        if abs(result['days_until_calibration'] - manual_days) <= 1:
            print(f"   ✅ days_until_calibration рассчитан правильно")
        else:
            print(f"   ❌ Ошибка в расчете days_until_calibration")
        
        # 7. Показываем статус
        print(f"\n📊 СТАТУС:")
        print("="*10)
        
        days = result['days_until_calibration']
        if days > 30:
            status = f"🟢 В норме ({days} дней)"
        elif days > 0:
            status = f"🟡 Скоро поверка ({days} дней)"
        else:
            status = f"🔴 ПРОСРОЧЕНО ({days} дней)"
        
        print(f"   Статус: {status}")
        
        conn.commit()
        
        # 8. Удаляем тестовую запись
        cursor.execute("DELETE FROM calibration_certificates WHERE id = %s", (result['id'],))
        conn.commit()
        print(f"\n🗑️ Тестовая запись удалена")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def main():
    """Главная функция"""
    demo_auto_calculation()
    input("\nНажмите Enter для выхода...")

if __name__ == "__main__":
    main()
