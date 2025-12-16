-- Добавление поля warehouse_type в таблицу cart для разделения корзин по складам

-- Добавляем поле warehouse_type (по умолчанию 'crystals' для существующих записей)
ALTER TABLE cart 
ADD COLUMN IF NOT EXISTS warehouse_type VARCHAR(20) DEFAULT 'crystals';

-- Обновляем существующие записи, чтобы они были для склада кристаллов
UPDATE cart SET warehouse_type = 'crystals' WHERE warehouse_type IS NULL;

-- Устанавливаем NOT NULL после заполнения
ALTER TABLE cart 
ALTER COLUMN warehouse_type SET NOT NULL;

-- Удаляем старое ограничение уникальности (если оно существует)
ALTER TABLE cart 
DROP CONSTRAINT IF EXISTS cart_user_id_item_id_key;

-- Добавляем новое ограничение уникальности с учетом warehouse_type
ALTER TABLE cart 
ADD CONSTRAINT cart_user_id_item_id_warehouse_type_key 
UNIQUE (user_id, item_id, warehouse_type);

-- Добавляем индекс для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_cart_user_warehouse ON cart(user_id, warehouse_type);

