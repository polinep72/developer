# Инструкции по обновлению базы данных

## Изменения в структуре базы данных

### 1. Новая таблица `calibration_certificates`
Создана для хранения истории поверок и аттестаций:

```sql
CREATE TABLE calibration_certificates (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER NOT NULL,
    certificate_number VARCHAR(100) NOT NULL,
    certificate_date DATE NOT NULL,
    next_calibration_date DATE,
    days_until_calibration INTEGER,
    calibration_cost DECIMAL(10,2),
    certificate_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (equipment_id) REFERENCES equipment (id) ON DELETE CASCADE
);
```

### 2. Добавлен столбец МПИ в таблицу `equipment`
```sql
ALTER TABLE equipment ADD COLUMN mpi VARCHAR(50);
```

### 3. Добавлен столбец веб-ссылок в таблицу `gosregister`
```sql
ALTER TABLE gosregister ADD COLUMN web_url TEXT;
```

### 4. Удалены столбцы из таблицы `equipment`
```sql
ALTER TABLE equipment DROP COLUMN certificate_number;
ALTER TABLE equipment DROP COLUMN certificate_date;
ALTER TABLE equipment DROP COLUMN next_calibration_date;
ALTER TABLE equipment DROP COLUMN days_until_calibration;
```

## Порядок выполнения SQL запросов

### Шаг 1: Создание новой таблицы и добавление столбцов
```sql
-- Создание таблицы поверок/аттестаций
CREATE TABLE IF NOT EXISTS calibration_certificates (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER NOT NULL,
    certificate_number VARCHAR(100) NOT NULL,
    certificate_date DATE NOT NULL,
    next_calibration_date DATE,
    days_until_calibration INTEGER,
    calibration_cost DECIMAL(10,2),
    certificate_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (equipment_id) REFERENCES equipment (id) ON DELETE CASCADE
);

-- Добавление столбца МПИ
ALTER TABLE equipment ADD COLUMN IF NOT EXISTS mpi VARCHAR(50);

-- Добавление столбца веб-ссылок
ALTER TABLE gosregister ADD COLUMN IF NOT EXISTS web_url TEXT;

-- Создание индексов
CREATE INDEX IF NOT EXISTS idx_calibration_certificates_equipment_id ON calibration_certificates(equipment_id);
CREATE INDEX IF NOT EXISTS idx_calibration_certificates_date ON calibration_certificates(certificate_date);
```

### Шаг 2: Миграция данных
```sql
-- Перенос данных о поверке/аттестации из таблицы equipment в новую таблицу
INSERT INTO calibration_certificates (
    equipment_id, certificate_number, certificate_date, 
    next_calibration_date, days_until_calibration, calibration_cost
)
SELECT 
    id, certificate_number, certificate_date,
    next_calibration_date, days_until_calibration, calibration_cost
FROM equipment 
WHERE certificate_number IS NOT NULL 
   AND certificate_number != '' 
   AND certificate_date IS NOT NULL;
```

### Шаг 3: Удаление старых столбцов
```sql
-- Удаление столбцов, связанных с поверкой/аттестацией
ALTER TABLE equipment DROP COLUMN IF EXISTS certificate_number;
ALTER TABLE equipment DROP COLUMN IF EXISTS certificate_date;
ALTER TABLE equipment DROP COLUMN IF EXISTS next_calibration_date;
ALTER TABLE equipment DROP COLUMN IF EXISTS days_until_calibration;
```

### Шаг 4: Создание представления
```sql
-- Создание представления для полной информации об оборудовании
CREATE OR REPLACE VIEW equipment_full_view AS
SELECT 
    e.id, e.row_number, et.type_code, et.type_name,
    e.name, e.type_designation, e.serial_number, e.mpi,
    e.inventory_number, e.year_in_service, e.note,
    g.gosregister_number, g.si_name as gosregister_name,
    g.manufacturer, g.web_url as gosregister_url,
    cc.certificate_number as last_certificate_number,
    cc.certificate_date as last_certificate_date,
    cc.next_calibration_date, cc.days_until_calibration,
    cc.calibration_cost
FROM equipment e
JOIN equipment_types et ON e.equipment_type_id = et.id
LEFT JOIN gosregister g ON e.gosregister_id = g.id
LEFT JOIN LATERAL (
    SELECT certificate_number, certificate_date, next_calibration_date, 
           days_until_calibration, calibration_cost
    FROM calibration_certificates cc
    WHERE cc.equipment_id = e.id
    ORDER BY cc.certificate_date DESC
    LIMIT 1
) cc ON true;
```

### Шаг 5: Функции и триггеры
```sql
-- Функция для автоматического расчета дней до следующей поверки
CREATE OR REPLACE FUNCTION update_calibration_days()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.next_calibration_date IS NOT NULL THEN
        NEW.days_until_calibration = EXTRACT(DAY FROM (NEW.next_calibration_date - CURRENT_DATE));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создание триггера для автоматического обновления
DROP TRIGGER IF EXISTS trigger_update_calibration_days ON calibration_certificates;
CREATE TRIGGER trigger_update_calibration_days
    BEFORE INSERT OR UPDATE ON calibration_certificates
    FOR EACH ROW
    EXECUTE FUNCTION update_calibration_days();
```

## Обновления в коде приложения

### 1. app.py
- Обновлены SQL запросы для работы с новой структурой
- Добавлены новые API endpoints для работы с поверками/аттестациями:
  - `GET /api/calibration-certificates/<equipment_id>` - история поверок
  - `POST /api/calibration-certificates` - добавление новой поверки

### 2. manage_database.py
- Добавлена функция `manage_calibration_certificates()` для управления поверками
- Обновлены запросы поиска с учетом новых полей

### 3. import_excel_data.py
- Обновлен импорт для раздельного сохранения данных оборудования и поверок
- Данные о поверках/аттестациях сохраняются в таблицу `calibration_certificates`

## Новые возможности

### 1. История поверок/аттестаций
- Полная история поверок для каждого оборудования
- Автоматический расчет дней до следующей поверки
- Отслеживание стоимости поверок

### 2. МПИ (Межповерочный интервал)
- Хранение МПИ для каждого типа оборудования
- Возможность планирования поверок на основе МПИ

### 3. Веб-ссылки на Госреестр
- Прямые ссылки на официальные страницы Госреестра
- Быстрый доступ к актуальной информации об оборудовании

### 4. Ссылки на сертификаты поверки/аттестации
- Хранение URL сертификатов в таблице `calibration_certificates`
- Автоматическое отображение номеров свидетельств как гиперссылок на веб-странице
- Прямой доступ к электронным копиям сертификатов

## Проверка обновления

После выполнения всех SQL запросов проверьте:

```sql
-- Проверка структуры таблиц
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'equipment' 
ORDER BY ordinal_position;

SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'calibration_certificates' 
ORDER BY ordinal_position;

-- Проверка количества записей
SELECT 'equipment' as table_name, COUNT(*) as count FROM equipment
UNION ALL
SELECT 'calibration_certificates' as table_name, COUNT(*) as count FROM calibration_certificates
UNION ALL
SELECT 'gosregister' as table_name, COUNT(*) as count FROM gosregister;
```

## Запуск обновленного приложения

После выполнения всех изменений:

1. Убедитесь, что все SQL запросы выполнены успешно
2. Перезапустите веб-сервер: `python app.py`
3. Проверьте работу API: `http://localhost:8084/api/stats`
4. Откройте веб-интерфейс: `http://localhost:8084`

Система готова к работе с новой структурой базы данных!
