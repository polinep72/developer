# Инструкция по миграции на нормализованную структуру БД

## Обзор изменений

Миграция выполняется в 2 этапа:
1) Нормализация справочников номенклатуры: `names_*` → `elements` + `element_types` (английские названия)
2) Нормализация движения: `invoice_* / consumption_*` → `invoices / consumptions` (единые таблицы с `element_type_id`)

### Преимущества нормализации:
- ✅ Единая логика работы со всеми типами элементов
- ✅ Легкое добавление новых типов без изменения структуры БД
- ✅ Упрощение кода бота (один запрос вместо трех)
- ✅ Соответствие принципам нормализации БД (3NF)
- ✅ Масштабируемость для будущих расширений

## Шаг 1: Создание нормализованной структуры номенклатуры (elements / element_types)

Примените SQL-скрипт для создания новых таблиц:

```bash
# Подключитесь к БД warehouse
psql -U postgres -d warehouse -f database/normalized_schema_english.sql
```

Или через psql:

```sql
\c warehouse
\i database/normalized_schema.sql
```

Это создаст:
- Таблицу `element_types` с типами: ms (Микросхемы), m (Модули), pp (ПП)
- Таблицу `elements` для хранения всех наименований (включая `description`, `price`)
- Индексы для быстрого поиска

## Шаг 2: Миграция номенклатуры (names_* → elements)

Запустите скрипт миграции данных:

```bash
# Убедитесь, что в .env указаны правильные параметры подключения
python scripts/migrate_to_english_schema.py
```

Скрипт выполнит:
1. Проверку существования нормализованной структуры
2. Миграцию данных из `names_ms` → `элементы` (тип: ms)
3. Миграцию данных из `names_m` → `элементы` (тип: m)
4. Миграцию данных из `names_pp` → `элементы` (тип: pp)
5. Создание VIEW для обратной совместимости (опционально)
6. Проверку корректности миграции

### Проверка миграции вручную:

```sql
-- Проверить количество элементов по типам
SELECT 
    t.код, 
    t.название, 
    COUNT(e.id) as количество
FROM типы_элементов t
LEFT JOIN элементы e ON e.тип_id = t.id
GROUP BY t.id, t.код, t.название
ORDER BY t.код;

-- Сравнить количество записей
SELECT 
    'names_ms' as таблица, COUNT(*) as количество FROM names_ms
UNION ALL
SELECT 
    'элементы (ms)' as таблица, COUNT(*) as количество 
FROM элементы e
JOIN типы_элементов t ON e.тип_id = t.id
WHERE t.код = 'ms';
```

## Шаг 3: Создание нормализованной структуры движения (invoices / consumptions)

Примените SQL-скрипт:

```bash
python scripts/apply_invoices_consumptions_schema.py
```

Скрипт создаст таблицы:
- `invoices` (вместо `invoice_ms/invoice_m/invoice_pp`)
- `consumptions` (вместо `consumption_ms/consumption_m/consumption_pp`)

## Шаг 4: Миграция движения (invoice_* / consumption_* → invoices / consumptions)

Запустите скрипт:

```bash
python scripts/migrate_invoices_consumptions.py
```

## Шаг 5: Важно про name_id (legacy)

В исходной БД `invoice_* / consumption_*` ссылаются на `names_*` через `name_id`.
После нормализации номенклатуры у `elements.id` свой (новый) идентификатор, поэтому:
- `elements` хранит `legacy_name_id` (старый id из `names_*`)
- в нормализованных `invoices/consumptions` поле `name_id` содержит legacy-id
- JOIN на номенклатуру должен выполняться по `elements.legacy_name_id`

Это уже учтено в `WareHouseIPKBot.py`.

## Шаг 6: Тестирование бота

Перед заменой основного файла протестируйте новую версию:

1. **Остановите текущий бот:**
```bash
docker-compose stop warehouse-bot
```

2. **Создайте резервную копию текущего бота:**
```bash
cp WareHouseIPKBot.py WareHouseIPKBot_backup.py
```

3. **Замените файл бота на нормализованную версию:**
```bash
cp WareHouseIPKBot_normalized.py WareHouseIPKBot.py
```

4. **Пересоберите и запустите контейнер:**
```bash
docker-compose build warehouse-bot
docker-compose up -d warehouse-bot
```

5. **Проверьте логи:**
```bash
docker-compose logs -f warehouse-bot
```

6. **Протестируйте бота в Telegram:**
   - Отправьте `/start`
   - Выполните несколько поисковых запросов
   - Проверьте корректность результатов

## Шаг 4: Откат (если что-то пошло не так)

Если обнаружены проблемы, выполните откат:

1. **Восстановите исходный файл:**
```bash
cp WareHouseIPKBot_backup.py WareHouseIPKBot.py
```

2. **Перезапустите контейнер:**
```bash
docker-compose restart warehouse-bot
```

### Важно:

- Старые таблицы `names_ms`, `names_m`, `names_pp` **НЕ удаляются** автоматически
- Таблицы `invoice_ms`, `invoice_m`, `invoice_pp` **продолжают работать** со ссылками на `name_id`
- После миграции новые записи должны добавляться в таблицу `элементы`, а не в старые таблицы

## Шаг 5: Опционально - Создание VIEW для обратной совместимости

Если другие приложения используют старые таблицы напрямую, создайте VIEW:

```sql
-- VIEW для names_ms
CREATE OR REPLACE VIEW names_ms AS
SELECT 
    e.id,
    e.наименование as name
FROM элементы e
JOIN типы_элементов t ON e.тип_id = t.id
WHERE t.код = 'ms';

-- VIEW для names_m
CREATE OR REPLACE VIEW names_m AS
SELECT 
    e.id,
    e.наименование as name
FROM элементы e
JOIN типы_элементов t ON e.тип_id = t.id
WHERE t.код = 'm';

-- VIEW для names_pp
CREATE OR REPLACE VIEW names_pp AS
SELECT 
    e.id,
    e.наименование as name
FROM элементы e
JOIN типы_элементов t ON e.тип_id = t.id
WHERE t.код = 'pp';
```

**Внимание:** VIEW работают только для SELECT. Для INSERT/UPDATE потребуется изменение логики или использование триггеров.

## Изменения в коде бота

### Основные изменения:

1. **Функция `fetch_stock` → `fetch_stock_by_type`:**
   - Добавлен параметр `type_code` ('ms', 'm', 'pp')
   - Заменен `LEFT JOIN {names} n` на `LEFT JOIN элементы e` с фильтрацией по типу

2. **SQL-запросы:**
   - Используется таблица `элементы` вместо `names_ms/names_m/names_pp`
   - Добавлена фильтрация через `WHERE t.код = %s` для выбора нужного типа
   - JOIN с таблицей `типы_элементов` для фильтрации по типу

3. **Логика работы:**
   - Бот продолжает выполнять три запроса (по одному на тип)
   - В будущем можно объединить в один запрос с GROUP BY по типу

## Структура новой БД

```
типы_элементов
├── id (PK)
├── код (UNIQUE) - 'ms', 'm', 'pp'
├── название - 'Микросхема', 'Модуль', 'Печатная плата'
└── описание

элементы
├── id (PK)
├── тип_id (FK → типы_элементов.id)
├── обозначение
├── наименование (UNIQUE с тип_id)
└── created_at, updated_at

invoice_ms/invoice_m/invoice_pp
└── name_id → элементы.id (существующие связи сохраняются)
```

## Поддержка добавления новых типов

Для добавления нового типа элементов:

1. **Добавить тип в таблицу:**
```sql
INSERT INTO типы_элементов (код, название, описание) 
VALUES ('new_type', 'Новый тип', 'Описание нового типа');
```

2. **Создать таблицы прихода/расхода (если нужно):**
```sql
CREATE TABLE invoice_new_type (...);
CREATE TABLE consumption_new_type (...);
```

3. **Обновить код бота** (добавить обработку нового типа в `get_product_count`)

## Контакты

**Автор идеи и разработчик:** Полин Е.П. telegram: @PolinEP e-mail: polin-ep@yandex.ru  
**Соразработчик:** Cursor  
**Лицензионные права:** ИнноЦентр ВАО и ИПК Электрон-Маш
