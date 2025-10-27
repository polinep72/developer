#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from config import Config
import psycopg2

def fix_database():
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        database=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD
    )
    
    cursor = conn.cursor()
    
    print('🔧 Исправление функции add_calibration_certificate...')
    
    # Исправляем функцию
    sql_function = """
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

        IF mpi_years IS NULL THEN
            mpi_years := 1;
        END IF;

        next_cal_date := p_certificate_date + (INTERVAL '1 year' * mpi_years);
        days_calc := (next_cal_date - CURRENT_DATE);

        INSERT INTO calibration_certificates (
            equipment_id, certificate_number, certificate_date,
            next_calibration_date, days_until_calibration,
            calibration_cost, certificate_url
        ) VALUES (
            p_equipment_id, p_certificate_number, p_certificate_date,
            next_cal_date, days_calc,
            p_calibration_cost, p_certificate_url
        ) RETURNING id INTO new_id;

        RETURN new_id;
    END;
    $$ LANGUAGE plpgsql;
    """
    
    cursor.execute(sql_function)
    print('✅ Функция исправлена')
    
    # Создаем триггер
    print('🔧 Создание триггера...')
    
    sql_trigger_function = """
    CREATE OR REPLACE FUNCTION update_calibration_dates()
    RETURNS TRIGGER AS $$
    DECLARE
        mpi_years INTEGER;
    BEGIN
        IF TG_OP = 'INSERT' OR (TG_OP = 'UPDATE' AND OLD.certificate_date != NEW.certificate_date) THEN
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

            IF mpi_years IS NULL THEN
                mpi_years := 1;
            END IF;

            NEW.next_calibration_date := NEW.certificate_date + (INTERVAL '1 year' * mpi_years);
        END IF;
        
        IF NEW.next_calibration_date IS NOT NULL THEN
            NEW.days_until_calibration := (NEW.next_calibration_date - CURRENT_DATE);
        END IF;
        
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    
    cursor.execute(sql_trigger_function)
    
    # Удаляем старый триггер
    cursor.execute('DROP TRIGGER IF EXISTS trigger_update_calibration_days ON calibration_certificates;')
    
    # Создаем новый триггер
    sql_trigger = """
    CREATE TRIGGER trigger_update_calibration_dates
        BEFORE INSERT OR UPDATE ON calibration_certificates
        FOR EACH ROW
        EXECUTE FUNCTION update_calibration_dates();
    """
    
    cursor.execute(sql_trigger)
    print('✅ Триггер создан')
    
    # Обновляем существующие записи
    print('🔧 Обновление существующих записей...')
    
    cursor.execute("""
        UPDATE calibration_certificates 
        SET days_until_calibration = (next_calibration_date - CURRENT_DATE)
        WHERE next_calibration_date IS NOT NULL;
    """)
    
    updated_count = cursor.rowcount
    print(f'✅ Обновлено записей: {updated_count}')
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print('\n🎉 Все исправления применены!')
    print('Теперь при добавлении новых сертификатов будут автоматически рассчитываться:')
    print('- Дата следующей поверки')
    print('- Количество дней до поверки')

if __name__ == "__main__":
    fix_database()
