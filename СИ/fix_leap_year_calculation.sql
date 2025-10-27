-- Исправление формулы для корректной работы с високосными годами
-- Используем INTERVAL с годами вместо умножения дней на 365

-- Удаляем старый триггер
DROP TRIGGER IF EXISTS trigger_calculate_next_calibration_date ON calibration_certificates;

-- Создаем улучшенную функцию для расчета next_calibration_date
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
    
    -- Рассчитываем дату следующей поверки с учетом високосных годов:
    -- certificate_date + mpi_years лет - 1 день
    -- PostgreSQL автоматически учитывает високосные годы при использовании INTERVAL
    NEW.next_calibration_date := NEW.certificate_date + (mpi_years || ' years')::INTERVAL - INTERVAL '1 day';
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаем улучшенный триггер
CREATE TRIGGER trigger_calculate_next_calibration_date
    BEFORE INSERT OR UPDATE ON calibration_certificates
    FOR EACH ROW
    EXECUTE FUNCTION calculate_next_calibration_date();

-- Обновляем функцию пересчета всех записей
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
        
        -- Обновляем дату следующей поверки с учетом високосных годов
        UPDATE calibration_certificates 
        SET next_calibration_date = rec.certificate_date + (mpi_years || ' years')::INTERVAL - INTERVAL '1 day'
        WHERE id = rec.id;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Пересчитываем все существующие записи с новой формулой
SELECT recalculate_all_next_calibration_dates();

-- Добавляем комментарий
COMMENT ON FUNCTION calculate_next_calibration_date() IS 
'Триггерная функция для автоматического расчета next_calibration_date с учетом високосных годов';

COMMENT ON FUNCTION recalculate_all_next_calibration_dates() IS 
'Пересчитывает next_calibration_date для всех существующих записей с учетом високосных годов';

-- Тестируем на примерах
-- Пример 1: Поверка 20.03.2023 с МПИ 2 года (через високосный 2024)
-- Результат должен быть: 19.03.2025 (не 18.03.2025)

-- Пример 2: Поверка 29.02.2024 (високосный год) с МПИ 1 год  
-- Результат должен быть: 28.02.2025 (не 27.02.2025)
