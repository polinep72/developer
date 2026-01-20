-- Нормализованная структура БД для warehouse
-- Создание таблиц invoices и consumptions с объединением invoice_* и consumption_*

-- Таблица прихода (объединение invoice_ms, invoice_m, invoice_pp)
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    element_type_id INTEGER NOT NULL REFERENCES element_types(id) ON DELETE RESTRICT,
    invoice_id BIGINT NOT NULL,
    name_id INTEGER NULL REFERENCES elements(id),
    chip_id INTEGER NULL REFERENCES chips(id),
    body_id INTEGER NULL REFERENCES bodies(id),
    pp_id INTEGER NULL REFERENCES pp(id),  -- NULL для микросхем
    date DATE NOT NULL,
    arrival_date_id INTEGER NOT NULL REFERENCES arrival_dates(id),
    quan INTEGER NOT NULL,
    defect_products INTEGER DEFAULT 0,
    cond_suit_products INTEGER DEFAULT 0,
    quantity INTEGER NULL,
    item_id VARCHAR(255) NULL,  -- Унифицированный формат: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id
    purpose TEXT NULL,
    note TEXT NULL,
    date_time_entry TIMESTAMP DEFAULT NOW(),
    user_entry_id BIGINT NULL,
    file_name_entry TEXT NULL,
    -- Индексы для быстрого поиска
    CONSTRAINT unique_invoice_record UNIQUE (element_type_id, invoice_id, name_id, chip_id, body_id, pp_id, arrival_date_id)
);

-- Индексы для таблицы invoices
CREATE INDEX IF NOT EXISTS idx_invoices_element_type_id ON invoices(element_type_id);
CREATE INDEX IF NOT EXISTS idx_invoices_name_id ON invoices(name_id);
CREATE INDEX IF NOT EXISTS idx_invoices_item_id ON invoices(item_id);
CREATE INDEX IF NOT EXISTS idx_invoices_arrival_date_id ON invoices(arrival_date_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_id ON invoices(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoices_chip_id ON invoices(chip_id);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(date);

-- Таблица расхода (объединение consumption_ms, consumption_m, consumption_pp)
CREATE TABLE IF NOT EXISTS consumptions (
    id SERIAL PRIMARY KEY,
    element_type_id INTEGER NOT NULL REFERENCES element_types(id) ON DELETE RESTRICT,
    invoice_id BIGINT NOT NULL,
    name_id INTEGER NULL,  -- Без FK, так как могут быть ссылки на старые записи
    chip_id INTEGER NULL REFERENCES chips(id),
    body_id INTEGER NULL REFERENCES bodies(id),
    pp_id INTEGER NULL REFERENCES pp(id),  -- NULL для микросхем
    date DATE NOT NULL,
    arrival_date_id INTEGER NOT NULL REFERENCES arrival_dates(id),
    quantity INTEGER NOT NULL,
    item_id VARCHAR(255) NULL,  -- Унифицированный формат: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id
    consumer_name TEXT NOT NULL,
    purpose TEXT NULL,
    note TEXT NULL,
    date_time_entry TIMESTAMP DEFAULT NOW(),
    user_entry_id BIGINT NULL,
    file_name_entry TEXT NULL
);

-- Индексы для таблицы consumptions
CREATE INDEX IF NOT EXISTS idx_consumptions_element_type_id ON consumptions(element_type_id);
CREATE INDEX IF NOT EXISTS idx_consumptions_name_id ON consumptions(name_id);
CREATE INDEX IF NOT EXISTS idx_consumptions_item_id ON consumptions(item_id);
CREATE INDEX IF NOT EXISTS idx_consumptions_arrival_date_id ON consumptions(arrival_date_id);
CREATE INDEX IF NOT EXISTS idx_consumptions_invoice_id ON consumptions(invoice_id);
CREATE INDEX IF NOT EXISTS idx_consumptions_chip_id ON consumptions(chip_id);
CREATE INDEX IF NOT EXISTS idx_consumptions_date ON consumptions(date);

-- Комментарии к таблицам
COMMENT ON TABLE invoices IS 'Объединенная таблица прихода элементов (заменяет invoice_ms, invoice_m, invoice_pp)';
COMMENT ON TABLE consumptions IS 'Объединенная таблица расхода элементов (заменяет consumption_ms, consumption_m, consumption_pp)';
COMMENT ON COLUMN invoices.element_type_id IS 'Ссылка на тип элемента (ms/m/pp)';
COMMENT ON COLUMN invoices.pp_id IS 'Ссылка на ПП (NULL для микросхем)';
COMMENT ON COLUMN invoices.item_id IS 'Унифицированный идентификатор позиции: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id';
COMMENT ON COLUMN consumptions.element_type_id IS 'Ссылка на тип элемента (ms/m/pp)';
COMMENT ON COLUMN consumptions.pp_id IS 'Ссылка на ПП (NULL для микросхем)';
COMMENT ON COLUMN consumptions.item_id IS 'Унифицированный идентификатор позиции: invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id';
