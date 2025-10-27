-- Создание триггера для автоматического расчета next_calibration_date
-- Формула: certificate_date + (mpi*365) - 1 день

-- Сначала восстанавливаем столбец next_calibration_date как обычный
ALTER TABLE calibration_certificates 
ADD COLUMN IF NOT EXISTS next_calibration_date DATE;

-- Создаем функцию для извлечения МПИ в годах
CREATE OR REPLACE FUNCTION extract_mpi_years(mpi_text TEXT)
RETURNS INTEGER AS $$
BEGIN
    IF mpi_text IS NULL OR mpi_text = '' THEN
        RETURN 2; -- По умолчанию 2 года
    END IF;
    
    -- Извлекаем число из текста типа "2 год", "1 год", "3 года"
    RETURN COALESCE(
        (regexp_match(mpi_text, '(\d+)'))[1]::INTEGER,
        2 -- По умолчанию 2 года
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Создаем функцию для расчета next_calibration_date
CREATE OR REPLACE FUNCTION calculate_next_calibration_date()
RETURNS TRIGGER AS $$
DECLARE
    mpi_value TEXT;
    mpi_years INTEGER;
BEGIN
    -- Получаем МПИ из связанных таблиц
    SELECT COALESCE(g.mpi, e.mpi) INTO mpi_value
    FROM equipment e
    LEFT JOIN gosregister g ON e.gosregister_id = g.id
    WHERE e.id = NEW.equipment_id;
    
    -- Извлекаем количество лет
    mpi_years := extract_mpi_years(mpi_value);
    
    -- Рассчитываем дату следующей поверки: certificate_date + (mpi_years * 365) - 1 день
    NEW.next_calibration_date := NEW.certificate_date + (mpi_years * 365) - INTERVAL '1 day';
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаем триггер
DROP TRIGGER IF EXISTS trigger_calculate_next_calibration_date ON calibration_certificates;
CREATE TRIGGER trigger_calculate_next_calibration_date
    BEFORE INSERT OR UPDATE ON calibration_certificates
    FOR EACH ROW
    EXECUTE FUNCTION calculate_next_calibration_date();

-- Функция для пересчета всех существующих записей
CREATE OR REPLACE FUNCTION recalculate_all_next_calibration_dates()
RETURNS VOID AS $$
DECLARE
    rec RECORD;
    mpi_value TEXT;
    mpi_years INTEGER;
BEGIN
    FOR rec IN 
        SELECT cc.id, cc.equipment_id, cc.certificate_date
        FROM calibration_certificates cc
    LOOP
        -- Получаем МПИ для каждой записи
        SELECT COALESCE(g.mpi, e.mpi) INTO mpi_value
        FROM equipment e
        LEFT JOIN gosregister g ON e.gosregister_id = g.id
        WHERE e.id = rec.equipment_id;
        
        -- Извлекаем количество лет
        mpi_years := extract_mpi_years(mpi_value);
        
        -- Обновляем дату следующей поверки
        UPDATE calibration_certificates 
        SET next_calibration_date = rec.certificate_date + (mpi_years * 365) - INTERVAL '1 day'
        WHERE id = rec.id;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Пересчитываем все существующие записи
SELECT recalculate_all_next_calibration_dates();

-- Создаем индекс для оптимизации
CREATE INDEX IF NOT EXISTS idx_calibration_certificates_next_date 
ON calibration_certificates(next_calibration_date);

-- Добавляем комментарии
COMMENT ON COLUMN calibration_certificates.next_calibration_date IS 
'Автоматически рассчитываемая дата следующей поверки: certificate_date + (mpi*365) - 1 день';

COMMENT ON FUNCTION extract_mpi_years(TEXT) IS 
'Извлекает количество лет из текста МПИ (например, "2 год" -> 2)';

COMMENT ON FUNCTION calculate_next_calibration_date() IS 
'Триггерная функция для автоматического расчета next_calibration_date';

COMMENT ON FUNCTION recalculate_all_next_calibration_dates() IS 
'Пересчитывает next_calibration_date для всех существующих записей';
