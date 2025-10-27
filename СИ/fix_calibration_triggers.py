#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для исправления функции и создания триггеров для автоматического расчета
даты следующей поверки и дней до поверки
"""

import psycopg2
from datetime import date
from config import Config

def fix_calibration_triggers():
    """Исправляет функцию и создает правильные триггеры"""
    try:
        conn = psycopg2.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            database=Config.DB_NAME,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        
        cursor = conn.cursor()
        
        print("🔧 Исправление функции add_calibration_certificate...")
        
        # Исправляем функцию add_calibration_certificate
        cursor.execute('''
            CREATE OR REPLACE FUNCTION add_calibration_certificate(
                p_equipment_id INTEGER,
                p_certificate_number VARCHAR(100),
                p_certificate_date DATE,
                p_calibration_cost DECIMAL(10,2) DEFAULT NULL,
                p_certificate_url TEXT DEFAULT NULL
            )
            RETURNS INTEGER AS $$
            DECLARE
                new_id INTEGER;
                mpi_years INTEGER;
                next_cal_date DATE;
                days_calc INTEGER;
            BEGIN
                -- Получаем МПИ из таблицы equipment
                SELECT 
                    CASE 
                        WHEN e.mpi ~ '^\\d+$' THEN e.mpi::INTEGER
                        WHEN e.mpi LIKE '%год%' THEN
                            COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1)
                        ELSE 1
                    END
                INTO mpi_years
                FROM equipment e
                WHERE e.id = p_equipment_id;

                -- Если МПИ не найден, используем 1 год
                IF mpi_years IS NULL THEN
                    mpi_years := 1;
                END IF;

                -- Правильный расчет даты следующей поверки (без вычитания дня)
                next_cal_date := p_certificate_date + (INTERVAL '1 year' * mpi_years);
                
                -- Правильный расчет дней до поверки
                days_calc := (next_cal_date - CURRENT_DATE);

                -- Вставляем новую запись
                INSERT INTO calibration_certificates (
                    equipment_id,
                    certificate_number,
                    certificate_date,
                    next_calibration_date,
                    days_until_calibration,
                    calibration_cost,
                    certificate_url
                ) VALUES (
                    p_equipment_id,
                    p_certificate_number,
                    p_certificate_date,
                    next_cal_date,
                    days_calc,
                    p_calibration_cost,
                    p_certificate_url
                ) RETURNING id INTO new_id;

                RETURN new_id;
            END;
            $$ LANGUAGE plpgsql;
        ''')
        
        print("✅ Функция add_calibration_certificate исправлена")
        
        # Создаем функцию для автоматического обновления дат и дней
        cursor.execute('''
            CREATE OR REPLACE FUNCTION update_calibration_dates()
            RETURNS TRIGGER AS $$
            DECLARE
                mpi_years INTEGER;
                next_cal_date DATE;
                days_calc INTEGER;
            BEGIN
                -- Если изменилась дата сертификата, пересчитываем
                IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND OLD.certificate_date != NEW.certificate_date) THEN
                    -- Получаем МПИ из таблицы equipment
                    SELECT 
                        CASE 
                            WHEN e.mpi ~ '^\\d+$' THEN e.mpi::INTEGER
                            WHEN e.mpi LIKE '%год%' THEN
                                COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1)
                            ELSE 1
                        END
                    INTO mpi_years
                    FROM equipment e
                    WHERE e.id = NEW.equipment_id;

                    -- Если МПИ не найден, используем 1 год
                    IF mpi_years IS NULL THEN
                        mpi_years := 1;
                    END IF;

                    -- Расчет даты следующей поверки
                    NEW.next_calibration_date := NEW.certificate_date + (INTERVAL '1 year' * mpi_years);
                END IF;
                
                -- Всегда пересчитываем дни до поверки
                IF NEW.next_calibration_date IS NOT NULL THEN
                    NEW.days_until_calibration := (NEW.next_calibration_date - CURRENT_DATE);
                END IF;
                
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        ''')
        
        print("✅ Функция update_calibration_dates создана")
        
        # Удаляем старые триггеры
        cursor.execute('DROP TRIGGER IF EXISTS trigger_update_calibration_days ON calibration_certificates;')
        
        # Создаем новый триггер
        cursor.execute('''
            CREATE TRIGGER trigger_update_calibration_dates
                BEFORE INSERT OR UPDATE ON calibration_certificates
                FOR EACH ROW
                EXECUTE FUNCTION update_calibration_dates();
        ''')
        
        print("✅ Триггер trigger_update_calibration_dates создан")
        
        # Обновляем существующие записи
        cursor.execute('''
            UPDATE calibration_certificates 
            SET next_calibration_date = certificate_date + (
                SELECT 
                    CASE 
                        WHEN e.mpi ~ '^\\d+$' THEN (e.mpi::INTEGER || ' year')::INTERVAL
                        WHEN e.mpi LIKE '%год%' THEN 
                            (COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1) || ' year')::INTERVAL
                        ELSE INTERVAL '1 year'
                    END
                FROM equipment e
                WHERE e.id = calibration_certificates.equipment_id
            ),
            days_until_calibration = (
                certificate_date + (
                    SELECT 
                        CASE 
                            WHEN e.mpi ~ '^\\d+$' THEN (e.mpi::INTEGER || ' year')::INTERVAL
                            WHEN e.mpi LIKE '%год%' THEN 
                                (COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1) || ' year')::INTERVAL
                            ELSE INTERVAL '1 year'
                        END
                    FROM equipment e
                    WHERE e.id = calibration_certificates.equipment_id
                ) - CURRENT_DATE
            )
            WHERE next_calibration_date IS NULL OR days_until_calibration IS NULL;
        ''')
        
        updated_records = cursor.rowcount
        print(f"✅ Обновлено существующих записей: {updated_records}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n🎉 Все исправления применены успешно!")
        print("Теперь при добавлении новых сертификатов будут автоматически:")
        print("- Рассчитываться дата следующей поверки")
        print("- Рассчитываться количество дней до поверки")
        
    except Exception as e:
        print(f"❌ Ошибка при исправлении: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_calibration_triggers()
