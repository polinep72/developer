-- Удаление столбца days_until_calibration из БД
-- Дата создания: 13.10.2025
-- Решение: расчет на лету в веб-приложении

-- 1. Удаляем существующий триггер (правильное имя)
DROP TRIGGER IF EXISTS trigger_update_calibration_dates ON calibration_certificates;

-- 2. Удаляем функцию триггера (после удаления триггера)
DROP FUNCTION IF EXISTS update_calibration_dates();

-- 3. Удаляем новые триггер и функцию (если созданы)
DROP TRIGGER IF EXISTS trigger_update_days_until_calibration ON calibration_certificates;
DROP FUNCTION IF EXISTS update_days_until_calibration();
DROP FUNCTION IF EXISTS calculate_days_until_calibration(DATE);

-- 4. Удаляем представление (временно)
DROP VIEW IF EXISTS equipment_full_view CASCADE;

-- 5. Удаляем столбец days_until_calibration
ALTER TABLE calibration_certificates DROP COLUMN IF EXISTS days_until_calibration;

-- 6. Восстанавливаем представление equipment_full_view БЕЗ столбца days_until_calibration
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
    cc.calibration_cost,
    cc.certificate_url
FROM equipment e
JOIN equipment_types et ON e.equipment_type_id = et.id
LEFT JOIN gosregister g ON e.gosregister_id = g.id
LEFT JOIN LATERAL (
    SELECT certificate_number, certificate_date, next_calibration_date,
           calibration_cost, certificate_url
    FROM calibration_certificates cc
    WHERE cc.equipment_id = e.id
    ORDER BY cc.certificate_date DESC
    LIMIT 1
) cc ON true;

-- 7. Проверяем результат
SELECT 
    certificate_number,
    certificate_date,
    next_calibration_date,
    (next_calibration_date - CURRENT_DATE) as calculated_days,
    CURRENT_DATE as today
FROM calibration_certificates 
ORDER BY certificate_date DESC 
LIMIT 5;
