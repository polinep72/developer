#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для исправления расчета дней до поверки
"""

import psycopg2
from datetime import date
from config import Config

def fix_calculation_days():
    """Обновляет расчет дней до поверки для всех записей"""
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        
        cursor = conn.cursor()
        
        # Получаем все записи с датами следующей поверки
        cursor.execute('''
            SELECT id, next_calibration_date, days_until_calibration
            FROM calibration_certificates 
            WHERE next_calibration_date IS NOT NULL
        ''')
        
        records = cursor.fetchall()
        today = date.today()
        
        print(f"📊 Обновление расчета дней до поверки (сегодня: {today})")
        print("=" * 60)
        
        updated_count = 0
        
        for record in records:
            record_id, next_cal_date, old_days = record
            
            # Правильный расчет
            correct_days = (next_cal_date - today).days
            
            if old_days != correct_days:
                # Обновляем запись
                cursor.execute('''
                    UPDATE calibration_certificates 
                    SET days_until_calibration = %s
                    WHERE id = %s
                ''', (correct_days, record_id))
                
                print(f"ID {record_id}: {old_days} → {correct_days} дней (разница: {old_days - correct_days})")
                updated_count += 1
        
        conn.commit()
        print("=" * 60)
        print(f"✅ Обновлено записей: {updated_count}")
        
        # Создаем функцию для автоматического обновления
        cursor.execute('''
            CREATE OR REPLACE FUNCTION update_all_calibration_days()
            RETURNS void AS $$
            BEGIN
                UPDATE calibration_certificates 
                SET days_until_calibration = (next_calibration_date - CURRENT_DATE)
                WHERE next_calibration_date IS NOT NULL;
            END;
            $$ LANGUAGE plpgsql;
        ''')
        
        # Создаем функцию для автоматического обновления при изменении дат
        cursor.execute('''
            CREATE OR REPLACE FUNCTION update_calibration_days()
            RETURNS TRIGGER AS $$
            BEGIN
                IF NEW.next_calibration_date IS NOT NULL THEN
                    NEW.days_until_calibration = (NEW.next_calibration_date - CURRENT_DATE);
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        ''')
        
        # Обновляем триггер
        cursor.execute('''
            DROP TRIGGER IF EXISTS trigger_update_calibration_days ON calibration_certificates;
        ''')
        
        cursor.execute('''
            CREATE TRIGGER trigger_update_calibration_days
                BEFORE INSERT OR UPDATE ON calibration_certificates
                FOR EACH ROW
                EXECUTE FUNCTION update_calibration_days();
        ''')
        
        conn.commit()
        print("✅ Функции и триггеры обновлены")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка при обновлении: {e}")

if __name__ == "__main__":
    fix_calculation_days()
