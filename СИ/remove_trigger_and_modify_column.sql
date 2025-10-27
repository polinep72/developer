-- Удаление триггера и изменение столбца days_until_calibration на вычисляемый
-- Дата создания: 13.10.2025

-- 1. Удаляем существующий триггер (правильное имя)
DROP TRIGGER IF EXISTS trigger_update_calibration_dates ON calibration_certificates;

-- 2. Удаляем функцию триггера (после удаления триггера)
DROP FUNCTION IF EXISTS update_calibration_dates();

-- 3. Изменяем столбец days_until_calibration на вычисляемый
-- Сначала сохраняем определение представления для восстановления
-- Затем удаляем представление (временно)
DROP VIEW IF EXISTS equipment_full_view CASCADE;

-- Теперь удаляем существующий столбец
ALTER TABLE calibration_certificates DROP COLUMN IF EXISTS days_until_calibration;

-- Добавляем обычный столбец (не вычисляемый, так как CURRENT_DATE не immutable)
ALTER TABLE calibration_certificates 
ADD COLUMN days_until_calibration INTEGER;

-- Создаем функцию для расчета дней до поверки
CREATE OR REPLACE FUNCTION calculate_days_until_calibration(p_next_calibration_date DATE)
RETURNS INTEGER AS $$
BEGIN
    IF p_next_calibration_date IS NULL THEN
        RETURN NULL;
    ELSE
        RETURN (p_next_calibration_date - CURRENT_DATE);
    END IF;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Обновляем все записи с правильным расчетом
UPDATE calibration_certificates 
SET days_until_calibration = calculate_days_until_calibration(next_calibration_date)
WHERE next_calibration_date IS NOT NULL;

-- Создаем новый триггер для автоматического обновления дней до поверки
CREATE OR REPLACE FUNCTION update_days_until_calibration()
RETURNS TRIGGER AS $$
BEGIN
    -- Обновляем только если изменилась дата следующей поверки
    IF NEW.next_calibration_date IS DISTINCT FROM OLD.next_calibration_date THEN
        NEW.days_until_calibration := calculate_days_until_calibration(NEW.next_calibration_date);
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаем триггер
CREATE TRIGGER trigger_update_days_until_calibration
    BEFORE INSERT OR UPDATE ON calibration_certificates
    FOR EACH ROW
    EXECUTE FUNCTION update_days_until_calibration();

-- 4. Восстанавливаем представление equipment_full_view
-- (представление будет автоматически использовать новый вычисляемый столбец)
CREATE VIEW equipment_full_view AS
SELECT 
    e.*,
    et.type_code,
    et.type_name,
    g.gosregister_number,
    g.si_name as gosregister_name,
    g.web_url as gosregister_url,
    cc.certificate_number,
    cc.certificate_date,
    cc.next_calibration_date,
    cc.days_until_calibration,
    cc.calibration_cost,
    cc.certificate_url
FROM equipment e
JOIN equipment_types et ON e.equipment_type_id = et.id
LEFT JOIN gosregister g ON e.gosregister_id = g.id
LEFT JOIN LATERAL (
    SELECT certificate_number, certificate_date, next_calibration_date,
           days_until_calibration, calibration_cost, certificate_url
    FROM calibration_certificates cc
    WHERE cc.equipment_id = e.id
    ORDER BY cc.certificate_date DESC
    LIMIT 1
) cc ON true;

-- 5. Создаем функцию для обновления всех записей (для ежедневного обновления)
CREATE OR REPLACE FUNCTION recalculate_all_days_until_calibration()
RETURNS void AS $$
BEGIN
    -- Обновляем все записи с актуальным расчетом дней
    UPDATE calibration_certificates 
    SET days_until_calibration = calculate_days_until_calibration(next_calibration_date)
    WHERE next_calibration_date IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- 6. Проверяем результат
SELECT 
    certificate_number,
    certificate_date,
    next_calibration_date,
    days_until_calibration,
    CURRENT_DATE as today
FROM calibration_certificates 
ORDER BY certificate_date DESC 
LIMIT 5;
