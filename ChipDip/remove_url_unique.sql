-- Скрипт для удаления ограничения уникальности URL
-- Позволяет разным пользователям добавлять один и тот же товар

-- Удаляем ограничение уникальности URL
ALTER TABLE products DROP CONSTRAINT IF EXISTS products_url_key;

-- Добавляем индекс для быстрого поиска по URL (но не уникальный)
CREATE INDEX IF NOT EXISTS idx_products_url ON products(url);

-- Комментарий
COMMENT ON INDEX idx_products_url IS 'Индекс для быстрого поиска по URL (не уникальный)';
