-- SQL запросы для обновления автоматического расчета полей поверки/аттестации

-- 1. Удаляем старую функцию и триггер
DROP TRIGGER IF EXISTS trigger_update_calibration_days ON calibration_certificates;
DROP FUNCTION IF EXISTS update_calibration_days();

-- 2. Создаем новую функцию для автоматического расчета дат
CREATE OR REPLACE FUNCTION calculate_calibration_dates()
RETURNS TRIGGER AS $$
BEGIN
    -- Получаем МПИ из таблицы equipment (в годах)
    DECLARE
        mpi_years INTEGER;
    BEGIN
        -- Получаем МПИ из таблицы equipment и конвертируем в число лет
        SELECT 
            CASE 
                WHEN e.mpi ~ '^\d+$' THEN e.mpi::INTEGER  -- если МПИ - просто число
                WHEN e.mpi LIKE '%год%' THEN 
                    COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1)  -- извлекаем число из строки
                ELSE 1  -- по умолчанию 1 год
            END
        INTO mpi_years
        FROM equipment e 
        WHERE e.id = NEW.equipment_id;
        
        -- Если МПИ не найден, используем 1 год по умолчанию
        IF mpi_years IS NULL THEN
            mpi_years := 1;
        END IF;
        
        -- Рассчитываем next_calibration_date = certificate_date + (mpi * 365) - 1 день
        NEW.next_calibration_date := NEW.certificate_date + INTERVAL '1 day' * (mpi_years * 365) - INTERVAL '1 day';
        
        -- Рассчитываем days_until_calibration = next_calibration_date - CURRENT_DATE
        NEW.days_until_calibration := EXTRACT(DAY FROM (NEW.next_calibration_date - CURRENT_DATE));
        
        RETURN NEW;
    END;
END;
$$ LANGUAGE plpgsql;

-- 3. Создаем триггер для автоматического расчета при вставке
CREATE TRIGGER trigger_calculate_calibration_dates_insert
    BEFORE INSERT ON calibration_certificates
    FOR EACH ROW
    EXECUTE FUNCTION calculate_calibration_dates();

-- 4. Создаем триггер для автоматического расчета при обновлении
CREATE TRIGGER trigger_calculate_calibration_dates_update
    BEFORE UPDATE ON calibration_certificates
    FOR EACH ROW
    EXECUTE FUNCTION calculate_calibration_dates();

-- 5. Создаем функцию для пересчета всех существующих записей
CREATE OR REPLACE FUNCTION recalculate_all_calibration_dates()
RETURNS VOID AS $$
BEGIN
    UPDATE calibration_certificates 
    SET 
        next_calibration_date = cc.calculated_next_date,
        days_until_calibration = EXTRACT(DAY FROM (cc.calculated_next_date - CURRENT_DATE))
    FROM (
        SELECT 
            c.id,
            c.certificate_date + INTERVAL '1 day' * (
                CASE 
                    WHEN e.mpi ~ '^\d+$' THEN e.mpi::INTEGER
                    WHEN e.mpi LIKE '%год%' THEN 
                        COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1)
                    ELSE 1
                END * 365
            ) - INTERVAL '1 day' as calculated_next_date
        FROM calibration_certificates c
        JOIN equipment e ON c.equipment_id = e.id
    ) cc
    WHERE calibration_certificates.id = cc.id;
END;
$$ LANGUAGE plpgsql;

-- 6. Создаем функцию для обновления МПИ в таблице equipment (примеры значений)
UPDATE equipment 
SET mpi = CASE 
    WHEN mpi IS NULL OR mpi = '' THEN '1'  -- по умолчанию 1 год
    WHEN mpi LIKE '%год%' THEN REGEXP_REPLACE(mpi, '[^0-9]', '', 'g')  -- извлекаем число
    ELSE mpi
END
WHERE equipment_type_id IN (1, 2);  -- только для СИ и ИО

-- 7. Создаем функцию для добавления новой поверки с автоматическим расчетом
CREATE OR REPLACE FUNCTION add_calibration_certificate(
    p_equipment_id INTEGER,
    p_certificate_number VARCHAR(100),
    p_certificate_date DATE,
    p_calibration_cost DECIMAL(10,2) DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    new_id INTEGER;
BEGIN
    INSERT INTO calibration_certificates (
        equipment_id, 
        certificate_number, 
        certificate_date, 
        calibration_cost
    ) VALUES (
        p_equipment_id, 
        p_certificate_number, 
        p_certificate_date, 
        p_calibration_cost
    ) RETURNING id INTO new_id;
    
    RETURN new_id;
END;
$$ LANGUAGE plpgsql;

-- 8. Проверочные запросы
-- Проверяем структуру МПИ в таблице equipment
SELECT DISTINCT mpi, COUNT(*) as count
FROM equipment 
WHERE mpi IS NOT NULL AND mpi != ''
GROUP BY mpi
ORDER BY count DESC;

-- Проверяем расчет дат для существующих записей
SELECT 
    c.id,
    c.certificate_number,
    c.certificate_date,
    e.mpi,
    c.next_calibration_date,
    c.days_until_calibration
FROM calibration_certificates c
JOIN equipment e ON c.equipment_id = e.id
LIMIT 10;

-- 9. Выполняем пересчет всех существующих записей (раскомментируйте при необходимости)
-- SELECT recalculate_all_calibration_dates();

COMMENT ON FUNCTION calculate_calibration_dates() IS 'Автоматически рассчитывает next_calibration_date и days_until_calibration на основе МПИ из таблицы equipment';
COMMENT ON FUNCTION recalculate_all_calibration_dates() IS 'Пересчитывает даты для всех существующих записей поверок';
COMMENT ON FUNCTION add_calibration_certificate(INTEGER, VARCHAR, DATE, DECIMAL) IS 'Добавляет новую поверку с автоматическим расчетом дат';
