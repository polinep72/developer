# Рекомендации по нормализации таблиц invoice_* и consumption_*

## Текущая ситуация

### Структура таблиц

#### Invoice таблицы (приход):
- **invoice_ms** (167 записей): нет столбца `pp_id`
- **invoice_m** (80 записей): есть столбец `pp_id`
- **invoice_pp** (52 записей): есть столбец `pp_id`

#### Consumption таблицы (расход):
- **consumption_ms** (290 записей): нет столбца `pp_id`
- **consumption_m** (14 записей): есть столбец `pp_id`
- **consumption_pp** (12 записей): есть столбец `pp_id`

### Формирование item_id

Анализ показывает, что `item_id` формируется по-разному:

1. **invoice_ms**: `invoice_id-name_id-chip_id-body_id-arrival_date_id`
   - Пример: `295-121-151-27-1`
   - **НЕТ pp_id** в составе

2. **invoice_m/invoice_pp**: `invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id`
   - Пример: `487-32-235-32-21-79`
   - **ЕСТЬ pp_id** в составе

### Общие столбцы

**Invoice таблицы (16 общих столбцов):**
- id, invoice_id, name_id, chip_id, body_id, date, arrival_date_id
- quan, defect_products, cond_suit_products, quantity
- item_id, purpose, note, date_time_entry, user_entry_id, file_name_entry

**Consumption таблицы (14 общих столбцов):**
- id, invoice_id, name_id, chip_id, body_id, date, arrival_date_id
- quantity, item_id, consumer_name, purpose, note
- date_time_entry, user_entry_id, file_name_entry

**Различие:** только наличие/отсутствие `pp_id`

## Рекомендации

### ✅ Вариант 1: Полная нормализация (РЕКОМЕНДУЕТСЯ)

**Преимущества:**
- ✅ Единая логика работы со всеми типами элементов
- ✅ Легкое добавление новых типов без изменения структуры БД
- ✅ Упрощение кода бота (один запрос вместо трех)
- ✅ Соответствие принципам нормализации БД (3NF)
- ✅ Упрощение администрирования и поддержки

**Действия:**
1. Создать таблицы `invoices` и `consumptions` с английскими названиями
2. Добавить столбец `pp_id` в общую структуру (NULL для микросхем)
3. Добавить столбец `element_type_id` для связи с `element_types`
4. Мигрировать данные из всех таблиц `invoice_*` и `consumption_*`
5. Обновить логику формирования `item_id` для единообразия

**Структура нормализованных таблиц:**

```sql
-- Таблица прихода (invoice)
CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    element_type_id INTEGER NOT NULL REFERENCES element_types(id),
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
    item_id VARCHAR(255) NULL,  -- Унифицированный формат с pp_id
    purpose TEXT NULL,
    note TEXT NULL,
    date_time_entry TIMESTAMP DEFAULT NOW(),
    user_entry_id BIGINT NULL,
    file_name_entry TEXT NULL
);

-- Таблица расхода (consumption)
CREATE TABLE consumptions (
    id SERIAL PRIMARY KEY,
    element_type_id INTEGER NOT NULL REFERENCES element_types(id),
    invoice_id BIGINT NOT NULL,
    name_id INTEGER NULL REFERENCES elements(id),
    chip_id INTEGER NULL REFERENCES chips(id),
    body_id INTEGER NULL REFERENCES bodies(id),
    pp_id INTEGER NULL REFERENCES pp(id),  -- NULL для микросхем
    date DATE NOT NULL,
    arrival_date_id INTEGER NOT NULL REFERENCES arrival_dates(id),
    quantity INTEGER NOT NULL,
    item_id VARCHAR(255) NULL,  -- Унифицированный формат с pp_id
    consumer_name TEXT NOT NULL,
    purpose TEXT NULL,
    note TEXT NULL,
    date_time_entry TIMESTAMP DEFAULT NOW(),
    user_entry_id BIGINT NULL,
    file_name_entry TEXT NULL
);
```

**Важно:**
- В `invoice_ms`/`consumption_ms` столбец `pp_id` всегда будет `NULL`
- `item_id` должен формироваться единообразно: `invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id`
- Для микросхем: `pp_id` будет `NULL` или можно использовать `0` для унификации

### ⚠️ Вариант 2: Добавление pp_id в *_ms таблицы (КОМПРОМИСС)

**Преимущества:**
- ✅ Минимальные изменения в структуре
- ✅ Единообразное формирование `item_id`
- ✅ Корректное сопоставление прихода и расхода

**Действия:**
1. Добавить столбец `pp_id` в `invoice_ms` и `consumption_ms`
2. Установить `pp_id = NULL` для всех существующих записей
3. Обновить логику формирования `item_id` для использования `pp_id` (NULL → '0' или пропуск)
4. Оставить разделение по типам (3 таблицы прихода, 3 таблицы расхода)

**Недостатки:**
- ❌ Сохраняется разделение на 3 таблицы
- ❌ Дублирование логики в коде
- ❌ Сложнее добавлять новые типы

### ❌ Вариант 3: Оставить как есть (НЕ РЕКОМЕНДУЕТСЯ)

**Причины не рекомендовать:**
- ❌ Несоответствие формирования `item_id` между типами
- ❌ Потенциальные проблемы при сопоставлении прихода и расхода
- ❌ Дублирование структуры и логики
- ❌ Сложность поддержки и расширения

## Рекомендуемый подход

**Рекомендую Вариант 1 (Полная нормализация)** по следующим причинам:

1. **Уже выполнена нормализация `names_*` → `elements`** - логично продолжить в том же направлении
2. **Единая структура** упростит код бота и других приложений
3. **Масштабируемость** - легко добавить новые типы элементов
4. **Соответствие принципам БД** - правильная нормализация
5. **Столбец `pp_id` с NULL** корректно обрабатывается в SQL и не создаст проблем

### Критические моменты при нормализации:

1. **Формирование item_id:**
   - Для микросхем: `invoice_id-name_id-chip_id-body_id-NULL-arrival_date_id` → можно использовать `0` вместо NULL
   - Для модулей/ПП: `invoice_id-name_id-chip_id-body_id-pp_id-arrival_date_id`
   - Важно: обеспечить уникальность `item_id` в рамках каждого типа

2. **Сопоставление прихода и расхода:**
   - JOIN должен учитывать `element_type_id` и `item_id`
   - Для микросхем `pp_id` будет `NULL`, что корректно обрабатывается в SQL

3. **Миграция данных:**
   - Переименовать существующие `item_id` для добавления `pp_id` (NULL → '0' или пропуск)
   - Или сгенерировать новые `item_id` с учетом `pp_id`

## Вывод

**Для полной нормализации рекомендуется:**
1. ✅ Создать таблицы `invoices` и `consumptions` с `element_type_id`
2. ✅ Добавить `pp_id` (NULL для микросхем)
3. ✅ Унифицировать формирование `item_id`
4. ✅ Мигрировать данные
5. ✅ Обновить код бота для работы с нормализованной структурой

**Альтернатива (если полная нормализация пока невозможна):**
- Добавить `pp_id` в `invoice_ms`/`consumption_ms` с NULL
- Обновить логику формирования `item_id` для единообразия
- Оставить разделение по типам

---

**Автор:** Полин Е.П. (@PolinEP)  
**Соразработчик:** Cursor  
**Лицензионные права:** ИнноЦентр ВАО и ИПК Электрон-Маш
