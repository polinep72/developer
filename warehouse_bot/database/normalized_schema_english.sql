-- Нормализованная структура БД для warehouse (с английскими названиями)
-- Создание таблицы типов элементов

-- Таблица типов элементов (английские названия)
CREATE TABLE IF NOT EXISTS element_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Вставка существующих типов
INSERT INTO element_types (code, name, description) VALUES
    ('ms', 'Микросхема', 'Микросхемы'),
    ('m', 'Модуль', 'Модули'),
    ('pp', 'Печатная плата', 'Печатные платы')
ON CONFLICT (code) DO NOTHING;

-- Таблица элементов (объединенная замена для names_ms, names_m, names_pp)
-- Включает все поля из исходных таблиц: name, description, price
CREATE TABLE IF NOT EXISTS elements (
    id SERIAL PRIMARY KEY,
    element_type_id INTEGER NOT NULL REFERENCES element_types(id) ON DELETE RESTRICT,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price NUMERIC(12, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_element_by_type UNIQUE (element_type_id, name)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_elements_element_type_id ON elements(element_type_id);
CREATE INDEX IF NOT EXISTS idx_elements_name ON elements(name);
CREATE INDEX IF NOT EXISTS idx_elements_price ON elements(price);

-- Комментарии к таблицам
COMMENT ON TABLE element_types IS 'Справочник типов элементов (микросхемы, модули, ПП)';
COMMENT ON TABLE elements IS 'Объединенная таблица наименований элементов (заменяет names_ms, names_m, names_pp)';
COMMENT ON COLUMN elements.element_type_id IS 'Ссылка на тип элемента (ms/m/pp)';
COMMENT ON COLUMN elements.name IS 'Наименование элемента';
COMMENT ON COLUMN elements.description IS 'Описание элемента';
COMMENT ON COLUMN elements.price IS 'Цена элемента';
