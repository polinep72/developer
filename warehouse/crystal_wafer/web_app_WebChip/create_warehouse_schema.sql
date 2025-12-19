-- Создание базы данных warehouse (выполнить один раз от имени администратора PostgreSQL)
-- При необходимости скорректируйте OWNER и кодировку.
--
-- Пример:
-- CREATE DATABASE warehouse
--     WITH OWNER = postgres
--     ENCODING 'UTF8'
--     LC_COLLATE 'ru_RU.UTF-8'
--     LC_CTYPE 'ru_RU.UTF-8'
--     TEMPLATE template0;
--
-- Далее команды CREATE TABLE выполнять уже внутри БД warehouse.

-- =========================
-- Таблицы счетов (Invoice)
-- =========================

CREATE TABLE IF NOT EXISTS invoice_ms (
    id                  BIGSERIAL PRIMARY KEY,          -- Внутренний PK
    invoice_id          VARCHAR(50)      NOT NULL,      -- Номер/идентификатор накладной
    name_id             BIGINT,                         -- Ссылка на наименование микросхемы 
    chip_id             BIGINT,                         -- Ссылка на кристалл
    body_id             BIGINT,                         -- Ссылка на корпус/тип корпуса
    date                DATE            NOT NULL,       -- Дата документа
    quan                INTEGER         NOT NULL,       -- Количество мест/упаковок
    defect_products     INTEGER         DEFAULT 0,      -- Брак
    cond_suit_products  INTEGER         DEFAULT 0,      -- Условно годные
    quantity            INTEGER         GENERATED ALWAYS AS (quan - defect_products - cond_suit_products) STORED, -- Годные изделия (расчёт: quan - брак - условно годные)
    purpose             TEXT,                           -- Назначение / цель (для кого/куда)
    note                TEXT,                           -- Примечание
    date_time_entry     TIMESTAMPTZ     NOT NULL DEFAULT NOW(), -- Дата/время внесения записи
    user_entry_id       BIGINT,                         -- ID пользователя, внесшего запись
    file_name_entry     TEXT                            -- Имя файла, из которого загружены данные (если импорт)
);

CREATE TABLE IF NOT EXISTS invoice_m (
    id                  BIGSERIAL PRIMARY KEY,          -- Внутренний PK
    invoice_id          VARCHAR(50)      NOT NULL,      -- Номер/идентификатор накладной
    name_id             BIGINT,                         -- Ссылка на наименование модуля
    chip_id             BIGINT,                         -- Ссылка на кристалл (если используется)
    body_id             BIGINT,                         -- Ссылка на корпус/тип корпуса
    pp_id               BIGINT,                         -- Ссылка на печатную плату
    date                DATE            NOT NULL,       -- Дата документа
    quan                INTEGER         NOT NULL,       -- Количество мест/упаковок
    defect_products     INTEGER         DEFAULT 0,      -- Брак
    cond_suit_products  INTEGER         DEFAULT 0,      -- Условно годные
    quantity            INTEGER         GENERATED ALWAYS AS (quan - defect_products - cond_suit_products) STORED, -- Годные изделия (расчёт: quan - брак - условно годные)
    purpose             TEXT,                           -- Назначение / цель (для кого/куда)
    note                TEXT,                           -- Примечание
    date_time_entry     TIMESTAMPTZ     NOT NULL DEFAULT NOW(), -- Дата/время внесения записи
    user_entry_id       BIGINT,                         -- ID пользователя, внесшего запись
    file_name_entry     TEXT                            -- Имя файла, из которого загружены данные (если импорт)
);

CREATE TABLE IF NOT EXISTS invoice_pp (
    id                  BIGSERIAL PRIMARY KEY,          -- Внутренний PK
    invoice_id          VARCHAR(50)      NOT NULL,      -- Номер/идентификатор накладной
    name_id             BIGINT,                         -- Ссылка на наименование печатной платы
    chip_id             BIGINT,                         -- Ссылка на кристалл (если используется)
    body_id             BIGINT,                         -- Ссылка на корпус/тип корпуса
    pp_id               BIGINT,                         -- Ссылка на печатную плату
    date                DATE            NOT NULL,       -- Дата документа
    quan                INTEGER         NOT NULL,       -- Количество мест/упаковок
    defect_products     INTEGER         DEFAULT 0,      -- Брак
    cond_suit_products  INTEGER         DEFAULT 0,      -- Условно годные
    quantity            INTEGER         GENERATED ALWAYS AS (quan - defect_products - cond_suit_products) STORED, -- Годные изделия (расчёт: quan - брак - условно годные)
    purpose             TEXT,                           -- Назначение / цель (для кого/куда)
    note                TEXT,                           -- Примечание
    date_time_entry     TIMESTAMPTZ     NOT NULL DEFAULT NOW(), -- Дата/время внесения записи
    user_entry_id       BIGINT,                         -- ID пользователя, внесшего запись
    file_name_entry     TEXT                            -- Имя файла, из которого загружены данные (если импорт)
);


-- =========================
-- Таблицы расхода (Consumption)
-- =========================

CREATE TABLE IF NOT EXISTS consumption_ms (
    id              BIGSERIAL PRIMARY KEY,
    doc_no          VARCHAR(50)      NOT NULL,         -- Номер документа списания/отгрузки
    doc_date        DATE             NOT NULL,
    consumer_name   TEXT             NOT NULL,         -- Получатель/подразделение
    product_code    VARCHAR(100)     NOT NULL,         -- Шифр/код изделия (микросхема)
    product_name    TEXT,
    quantity        INTEGER          NOT NULL,
    unit            VARCHAR(16)      NOT NULL DEFAULT 'шт',
    reason          TEXT,                              -- Причина списания/отгрузки
    related_invoice_id BIGINT REFERENCES invoice_ms(id), -- Связь с приходным документом (опционально)
    comment         TEXT,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS consumption_m (
    id              BIGSERIAL PRIMARY KEY,
    doc_no          VARCHAR(50)      NOT NULL,
    doc_date        DATE             NOT NULL,
    consumer_name   TEXT             NOT NULL,
    product_code    VARCHAR(100)     NOT NULL,         -- Код модуля
    product_name    TEXT,
    quantity        INTEGER          NOT NULL,
    unit            VARCHAR(16)      NOT NULL DEFAULT 'шт',
    reason          TEXT,
    related_invoice_id BIGINT REFERENCES invoice_m(id),
    comment         TEXT,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS consumption_pp (
    id              BIGSERIAL PRIMARY KEY,
    doc_no          VARCHAR(50)      NOT NULL,
    doc_date        DATE             NOT NULL,
    consumer_name   TEXT             NOT NULL,
    product_code    VARCHAR(100)     NOT NULL,         -- Код печатной платы
    product_name    TEXT,
    quantity        INTEGER          NOT NULL,
    unit            VARCHAR(16)      NOT NULL DEFAULT 'шт',
    reason          TEXT,
    related_invoice_id BIGINT REFERENCES invoice_pp(id),
    comment         TEXT,
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);


-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_invoice_ms_invoice_id ON invoice_ms (invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_ms_chip_id ON invoice_ms (chip_id);

CREATE INDEX IF NOT EXISTS idx_invoice_m_invoice_id ON invoice_m (invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_m_chip_id ON invoice_m (chip_id);

CREATE INDEX IF NOT EXISTS idx_invoice_pp_invoice_id ON invoice_pp (invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_pp_chip_id ON invoice_pp (chip_id);

CREATE INDEX IF NOT EXISTS idx_consumption_ms_doc_no ON consumption_ms (doc_no);
CREATE INDEX IF NOT EXISTS idx_consumption_m_doc_no ON consumption_m (doc_no);
CREATE INDEX IF NOT EXISTS idx_consumption_pp_doc_no ON consumption_pp (doc_no);


