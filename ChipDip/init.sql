-- Инициализация базы данных ChipDip Parser
-- Этот файл выполняется автоматически при первом запуске PostgreSQL контейнера

-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Создание таблицы товаров
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(500) NOT NULL,
    internal_sku VARCHAR(100) NOT NULL,
    url TEXT NOT NULL UNIQUE,
    current_price DECIMAL(10,2),
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Создание таблицы истории остатков
CREATE TABLE IF NOT EXISTS stock_history (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    check_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stock_level INTEGER,
    price DECIMAL(10,2),
    raw_text TEXT,
    status VARCHAR(50) DEFAULT 'success',
    error_message TEXT
);

-- Создание индексов для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_products_active ON products(is_active);
CREATE INDEX IF NOT EXISTS idx_products_last_checked ON products(last_checked_at);
CREATE INDEX IF NOT EXISTS idx_products_user_id ON products(user_id);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_stock_history_product_id ON stock_history(product_id);
CREATE INDEX IF NOT EXISTS idx_stock_history_timestamp ON stock_history(check_timestamp);
CREATE INDEX IF NOT EXISTS idx_stock_history_status ON stock_history(status);

-- Создание представления для последних данных товаров (без дублирования по URL)
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

-- Комментарии к таблицам
COMMENT ON TABLE users IS 'Таблица пользователей системы';
COMMENT ON TABLE products IS 'Таблица товаров для парсинга';
COMMENT ON TABLE stock_history IS 'История проверок остатков товаров';
COMMENT ON VIEW products_with_latest_stock IS 'Представление товаров с последними данными об остатках';
