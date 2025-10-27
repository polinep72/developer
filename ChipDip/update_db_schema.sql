-- Скрипт для обновления схемы базы данных
-- Удаляет ограничение уникальности URL и обновляет представление

-- 1. Удаляем ограничение уникальности URL
ALTER TABLE products DROP CONSTRAINT IF EXISTS products_url_key;

-- 2. Добавляем индекс для быстрого поиска по URL (но не уникальный)
CREATE INDEX IF NOT EXISTS idx_products_url ON products(url);

-- 3. Обновляем представление для отображения товаров без дублирования
CREATE OR REPLACE VIEW products_with_latest_stock AS
SELECT DISTINCT ON (p.url)
    p.id,
    p.name,
    p.internal_sku,
    p.url,
    p.current_price,
    p.last_checked_at,
    p.is_active,
    p.user_id,
    CASE 
        WHEN (SELECT COUNT(*) FROM products p2 WHERE p2.url = p.url AND p2.is_active = TRUE) > 1 
        THEN 'Множественные пользователи'
        ELSE u.username 
    END as added_by,
    sh.stock_level as latest_stock,
    sh.status as latest_status,
    sh.check_timestamp as latest_check
FROM products p
LEFT JOIN users u ON p.user_id = u.id
LEFT JOIN LATERAL (
    SELECT stock_level, status, check_timestamp
    FROM stock_history 
    WHERE product_id = p.id 
    ORDER BY check_timestamp DESC 
    LIMIT 1
) sh ON true
WHERE p.is_active = TRUE
ORDER BY p.url, p.id ASC;

-- Комментарии
COMMENT ON INDEX idx_products_url IS 'Индекс для быстрого поиска по URL (не уникальный)';
COMMENT ON VIEW products_with_latest_stock IS 'Представление товаров с последними данными об остатках (без дублирования по URL)';
