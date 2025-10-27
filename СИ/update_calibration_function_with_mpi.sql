-- Обновление функции add_calibration_certificate для использования МПИ из gosregister
-- Приоритет: МПИ из gosregister > МПИ из equipment > 2 года по умолчанию

DROP FUNCTION IF EXISTS add_calibration_certificate(INTEGER, VARCHAR, DATE, NUMERIC, TEXT);

CREATE OR REPLACE FUNCTION add_calibration_certificate(
    p_equipment_id INTEGER,
    p_certificate_number VARCHAR(100),
    p_certificate_date DATE,
    p_calibration_cost NUMERIC(10,2),
    p_certificate_url TEXT
)
RETURNS INTEGER AS $$
DECLARE
    v_next_calibration_date DATE;
    v_years_to_add INTEGER := 2; -- По умолчанию 2 года
    v_mpi_value VARCHAR(50);
    v_new_id INTEGER;
BEGIN
    -- Получаем МПИ с приоритетом: gosregister > equipment
    SELECT COALESCE(g.mpi, e.mpi) INTO v_mpi_value
    FROM equipment e
    LEFT JOIN gosregister g ON e.gosregister_id = g.id
    WHERE e.id = p_equipment_id;
    
    -- Парсим МПИ для определения периода поверки
    IF v_mpi_value IS NOT NULL THEN
        -- Ищем годы в МПИ (например, "2 год", "1 год")
        IF v_mpi_value ~ '\d+\s*год' THEN
            v_years_to_add := CAST(
                regexp_replace(v_mpi_value, '.*?(\d+)\s*год.*', '\1', 'g') AS INTEGER
            );
        -- Ищем месяцы в МПИ (например, "6 месяцев", "12 месяцев")
        ELSIF v_mpi_value ~ '\d+\s*месяц' THEN
            v_years_to_add := GREATEST(1, CAST(
                regexp_replace(v_mpi_value, '.*?(\d+)\s*месяц.*', '\1', 'g') AS INTEGER
            ) / 12);
        END IF;
    END IF;
    
    -- Рассчитываем дату следующей поверки
    IF p_certificate_date IS NOT NULL THEN
        -- Добавляем годы и вычитаем 1 день (срок действия заканчивается накануне)
        v_next_calibration_date := p_certificate_date + INTERVAL '1 year' * v_years_to_add - INTERVAL '1 day';
    END IF;
    
    -- Вставляем новую запись
    INSERT INTO calibration_certificates (
        equipment_id,
        certificate_number,
        certificate_date,
        next_calibration_date,
        calibration_cost,
        certificate_url
    ) VALUES (
        p_equipment_id,
        p_certificate_number,
        p_certificate_date,
        v_next_calibration_date,
        p_calibration_cost,
        p_certificate_url
    ) RETURNING id INTO v_new_id;
    
    RETURN v_new_id;
END;
$$ LANGUAGE plpgsql;

-- Создаем функцию для обновления существующих записей поверки с учетом МПИ
CREATE OR REPLACE FUNCTION update_existing_calibrations_with_mpi()
RETURNS INTEGER AS $$
DECLARE
    v_updated_count INTEGER := 0;
    rec RECORD;
BEGIN
    -- Обновляем все существующие записи поверки
    FOR rec IN
        SELECT 
            cc.id,
            cc.equipment_id,
            cc.certificate_date,
            COALESCE(g.mpi, e.mpi) as mpi_value
        FROM calibration_certificates cc
        JOIN equipment e ON cc.equipment_id = e.id
        LEFT JOIN gosregister g ON e.gosregister_id = g.id
        WHERE cc.certificate_date IS NOT NULL
    LOOP
        DECLARE
            v_years_to_add INTEGER := 2;
            v_new_next_date DATE;
        BEGIN
            -- Парсим МПИ
            IF rec.mpi_value IS NOT NULL THEN
                IF rec.mpi_value ~ '\d+\s*год' THEN
                    v_years_to_add := CAST(
                        regexp_replace(rec.mpi_value, '.*?(\d+)\s*год.*', '\1', 'g') AS INTEGER
                    );
                ELSIF rec.mpi_value ~ '\d+\s*месяц' THEN
                    v_years_to_add := GREATEST(1, CAST(
                        regexp_replace(rec.mpi_value, '.*?(\d+)\s*месяц.*', '\1', 'g') AS INTEGER
                    ) / 12);
                END IF;
            END IF;
            
            -- Рассчитываем новую дату
            v_new_next_date := rec.certificate_date + INTERVAL '1 year' * v_years_to_add - INTERVAL '1 day';
            
            -- Обновляем запись
            UPDATE calibration_certificates 
            SET next_calibration_date = v_new_next_date
            WHERE id = rec.id;
            
            v_updated_count := v_updated_count + 1;
        END;
    END LOOP;
    
    RETURN v_updated_count;
END;
$$ LANGUAGE plpgsql;

-- Создаем функцию для синхронизации МПИ в equipment с данными из gosregister
CREATE OR REPLACE FUNCTION sync_equipment_mpi_from_gosregister()
RETURNS INTEGER AS $$
DECLARE
    v_updated_count INTEGER := 0;
BEGIN
    -- Обновляем МПИ в equipment на основе данных из gosregister
    UPDATE equipment 
    SET mpi = g.mpi
    FROM gosregister g
    WHERE equipment.gosregister_id = g.id 
    AND g.mpi IS NOT NULL 
    AND g.mpi != ''
    AND (equipment.mpi IS NULL OR equipment.mpi != g.mpi);
    
    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    
    RETURN v_updated_count;
END;
$$ LANGUAGE plpgsql;

-- Выполняем обновление существующих записей
SELECT update_existing_calibrations_with_mpi() as updated_calibrations_count;

-- Синхронизируем МПИ в equipment
SELECT sync_equipment_mpi_from_gosregister() as synced_equipment_count;
