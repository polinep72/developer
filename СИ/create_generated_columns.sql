-- Создание таблицы с вычисляемыми столбцами (GENERATED COLUMNS)
-- Это альтернативный подход к триггерам

-- 1. Сначала создаем функцию для расчета next_calibration_date
CREATE OR REPLACE FUNCTION calculate_next_calibration_date(
    cert_date DATE,
    mpi_years INTEGER
) RETURNS DATE AS $$
BEGIN
    RETURN cert_date + INTERVAL '1 day' * (mpi_years * 365) - INTERVAL '1 day';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 2. Создаем функцию для расчета days_until_calibration
CREATE OR REPLACE FUNCTION calculate_days_until_calibration(
    next_cal_date DATE
) RETURNS INTEGER AS $$
BEGIN
    RETURN EXTRACT(DAY FROM (next_cal_date - CURRENT_DATE));
END;
$$ LANGUAGE plpgsql STABLE;

-- 3. Создаем новую таблицу с вычисляемыми столбцами
CREATE TABLE calibration_certificates_generated (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER NOT NULL,
    certificate_number VARCHAR(100) NOT NULL,
    certificate_date DATE NOT NULL,
    calibration_cost DECIMAL(10,2),
    
    -- Вычисляемые столбцы
    next_calibration_date DATE GENERATED ALWAYS AS (
        calculate_next_calibration_date(
            certificate_date, 
            COALESCE(
                (SELECT 
                    CASE 
                        WHEN e.mpi ~ '^\d+$' THEN e.mpi::INTEGER
                        WHEN e.mpi LIKE '%год%' THEN 
                            COALESCE(NULLIF(REGEXP_REPLACE(e.mpi, '[^0-9]', '', 'g'), '')::INTEGER, 1)
                        ELSE 1
                    END
                FROM equipment e 
                WHERE e.id = equipment_id), 
                1
            )
        )
    ) STORED,
    
    days_until_calibration INTEGER GENERATED ALWAYS AS (
        calculate_days_until_calibration(next_calibration_date)
    ) STORED,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (equipment_id) REFERENCES equipment (id)
);

-- 4. Создаем индексы
CREATE INDEX idx_calibration_certificates_generated_equipment_id 
ON calibration_certificates_generated(equipment_id);

CREATE INDEX idx_calibration_certificates_generated_certificate_date 
ON calibration_certificates_generated(certificate_date);

-- 5. Создаем функцию для добавления поверки с вычисляемыми столбцами
CREATE OR REPLACE FUNCTION add_calibration_certificate_generated(
    p_equipment_id INTEGER,
    p_certificate_number VARCHAR(100),
    p_certificate_date DATE,
    p_calibration_cost DECIMAL(10,2) DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    new_id INTEGER;
BEGIN
    INSERT INTO calibration_certificates_generated (
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

-- 6. Тестируем вычисляемые столбцы
INSERT INTO calibration_certificates_generated (
    equipment_id, certificate_number, certificate_date, calibration_cost
) VALUES (1, 'TEST-GENERATED-001', '2024-06-15', 1500.00);

-- 7. Проверяем результат
SELECT 
    certificate_number,
    certificate_date,
    next_calibration_date,
    days_until_calibration,
    calibration_cost
FROM calibration_certificates_generated 
WHERE certificate_number = 'TEST-GENERATED-001';

-- 8. Показываем структуру таблицы с вычисляемыми столбцами
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default,
    CASE 
        WHEN column_name IN ('next_calibration_date', 'days_until_calibration') 
        THEN 'GENERATED COLUMN'
        ELSE 'REGULAR COLUMN'
    END as column_type
FROM information_schema.columns 
WHERE table_name = 'calibration_certificates_generated'
ORDER BY ordinal_position;

-- 9. Объяснение различий
/*
РАЗЛИЧИЯ МЕЖДУ ПОДХОДАМИ:

1. ТРИГГЕРЫ (текущий подход):
   ✅ Работает со старой таблицей
   ✅ Гибкая логика расчета
   ✅ Можно обновлять существующие записи
   ❌ Не видно в свойствах столбца
   ❌ Логика "скрыта" в функциях

2. GENERATED COLUMNS (новый подход):
   ✅ Видно в свойствах столбца как "GENERATED ALWAYS AS"
   ✅ Автоматический расчет при INSERT/UPDATE
   ✅ Проще для понимания
   ❌ Требует создания новой таблицы
   ❌ Менее гибкая логика
   ❌ Нельзя вручную изменять значения

РЕКОМЕНДАЦИЯ: Оставить текущий подход с триггерами, 
так как он уже работает и более гибкий.
*/

-- 10. Удаляем тестовую запись
DELETE FROM calibration_certificates_generated WHERE certificate_number = 'TEST-GENERATED-001';

COMMENT ON TABLE calibration_certificates_generated IS 'Альтернативная таблица с вычисляемыми столбцами для демонстрации';
COMMENT ON COLUMN calibration_certificates_generated.next_calibration_date IS 'GENERATED: certificate_date + (mpi * 365) - 1 день';
COMMENT ON COLUMN calibration_certificates_generated.days_until_calibration IS 'GENERATED: next_calibration_date - CURRENT_DATE';
