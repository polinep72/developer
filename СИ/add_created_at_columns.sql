-- Добавление столбцов created_at в таблицы equipment и gosregister
-- Для отслеживания времени создания записей

-- Добавляем столбец created_at в таблицу equipment
ALTER TABLE equipment ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Добавляем столбец created_at в таблицу gosregister
ALTER TABLE gosregister ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Добавляем столбец updated_at в таблицу gosregister для отслеживания изменений
ALTER TABLE gosregister ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Создаем индексы для улучшения производительности поиска по датам
CREATE INDEX IF NOT EXISTS idx_equipment_created_at ON equipment(created_at);
CREATE INDEX IF NOT EXISTS idx_gosregister_created_at ON gosregister(created_at);
CREATE INDEX IF NOT EXISTS idx_gosregister_updated_at ON gosregister(updated_at);

-- Обновляем существующие записи (устанавливаем дату создания на текущую)
UPDATE equipment SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;
UPDATE gosregister SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;
UPDATE gosregister SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL;

-- Выводим информацию о выполненных изменениях
SELECT 'Столбцы created_at успешно добавлены в таблицы equipment и gosregister' as result;
