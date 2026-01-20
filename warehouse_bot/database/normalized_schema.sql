-- Нормализованная структура БД для warehouse
-- Создание таблицы типов элементов

-- Таблица типов элементов
CREATE TABLE IF NOT EXISTS типы_элементов (
    id SERIAL PRIMARY KEY,
    код VARCHAR(10) UNIQUE NOT NULL,
    название VARCHAR(100) NOT NULL,
    описание TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Вставка существующих типов
INSERT INTO типы_элементов (код, название, описание) VALUES
    ('ms', 'Микросхема', 'Микросхемы'),
    ('m', 'Модуль', 'Модули'),
    ('pp', 'Печатная плата', 'Печатные платы')
ON CONFLICT (код) DO NOTHING;

-- Таблица элементов (объединенная замена для names_ms, names_m, names_pp)
CREATE TABLE IF NOT EXISTS элементы (
    id SERIAL PRIMARY KEY,
    тип_id INTEGER NOT NULL REFERENCES типы_элементов(id) ON DELETE RESTRICT,
    обозначение VARCHAR(200),
    наименование VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_элемент_по_типу UNIQUE (тип_id, наименование)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_элементы_тип_id ON элементы(тип_id);
CREATE INDEX IF NOT EXISTS idx_элементы_наименование ON элементы(наименование);
CREATE INDEX IF NOT EXISTS idx_элементы_обозначение ON элементы(обозначение);

-- Комментарии к таблицам
COMMENT ON TABLE типы_элементов IS 'Справочник типов элементов (микросхемы, модули, ПП)';
COMMENT ON TABLE элементы IS 'Объединенная таблица наименований элементов (заменяет names_ms, names_m, names_pp)';
COMMENT ON COLUMN элементы.тип_id IS 'Ссылка на тип элемента (ms/m/pp)';
COMMENT ON COLUMN элементы.обозначение IS 'Обозначение элемента (например, К1324ПЦ5У)';
COMMENT ON COLUMN элементы.наименование IS 'Полное наименование элемента';
