-- Создание саморассчитываемой формулы для next_calibration_date
-- Формула: certificate_date + (mpi*365) - 1 день

-- Сначала удаляем существующий столбец next_calibration_date
ALTER TABLE calibration_certificates DROP COLUMN IF EXISTS next_calibration_date;

-- Создаем функцию для извлечения МПИ в годах
CREATE OR REPLACE FUNCTION extract_mpi_years(mpi_text TEXT)
RETURNS INTEGER AS $$
BEGIN
    IF mpi_text IS NULL THEN
        RETURN 2; -- По умолчанию 2 года
    END IF;
    
    -- Извлекаем число из текста типа "2 год", "1 год", "3 года"
    RETURN COALESCE(
        (regexp_match(mpi_text, '(\d+)'))[1]::INTEGER,
        2 -- По умолчанию 2 года
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Добавляем вычисляемый столбец next_calibration_date
-- Формула: certificate_date + (extract_mpi_years * 365) - 1 день
ALTER TABLE calibration_certificates 
ADD COLUMN next_calibration_date DATE 
GENERATED ALWAYS AS (
    certificate_date + 
    (extract_mpi_years(
        COALESCE(
            (SELECT COALESCE(g.mpi, e.mpi) 
             FROM equipment e 
             LEFT JOIN gosregister g ON e.gosregister_id = g.id 
             WHERE e.id = calibration_certificates.equipment_id),
            '2 год'
        )
    ) * 365) - 
    INTERVAL '1 day'
) STORED;

-- Создаем индекс для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_calibration_certificates_next_date 
ON calibration_certificates(next_calibration_date);

-- Обновляем комментарии
COMMENT ON COLUMN calibration_certificates.next_calibration_date IS 
'Автоматически рассчитываемая дата следующей поверки: certificate_date + (mpi*365) - 1 день';

COMMENT ON FUNCTION extract_mpi_years(TEXT) IS 
'Извлекает количество лет из текста МПИ (например, "2 год" -> 2)';
