# Руководство по применению нормализованной структуры БД

## Шаг 1: Применение нормализованной схемы

### Вариант А: Новая БД (рекомендуется для тестирования)

```bash
# Создать новую БД для тестирования
createdb calculation_db_test

# Применить нормализованную схему
psql -U postgres -d calculation_db_test -f database/normalized_schema.sql
```

### Вариант Б: Обновление существующей БД

```bash
# Применить обновленную схему (добавит новые таблицы)
psql -U postgres -d calculation_db -f database/schema.sql
```

**Внимание:** Обновленная схема сохраняет таблицу `изделия` для обратной совместимости и добавляет нормализованные таблицы.

## Шаг 2: Миграция данных из warehouse

```bash
# Убедитесь, что в .env указаны правильные подключения
cd backend
python ../scripts/migrate_from_warehouse.py
```

Скрипт мигрирует:
- `names_ms` → `элементы` (тип: ms)
- `names_m` → `элементы` (тип: m)
- `names_pp` → `элементы` (тип: pp)

## Шаг 3: Проверка миграции

```sql
-- Проверить количество элементов по типам
SELECT t.код, t.название, COUNT(e.id) as количество
FROM типы_элементов t
LEFT JOIN элементы e ON e.тип_id = t.id
GROUP BY t.id, t.код, t.название
ORDER BY t.код;

-- Проверить примеры элементов
SELECT e.id, e.обозначение, e.наименование, t.код as тип
FROM элементы e
JOIN типы_элементов t ON t.id = e.тип_id
LIMIT 10;
```

## Шаг 4: Использование нового API

### Получить все элементы определенного типа

```bash
# Микросхемы
curl http://localhost:8000/api/elements/?type=ms

# Модули
curl http://localhost:8000/api/elements/?type=m

# Платы
curl http://localhost:8000/api/elements/?type=pp
```

### Получить список типов элементов

```bash
curl http://localhost:8000/api/elements/types
```

### Получить состав элемента (BOM)

```bash
curl http://localhost:8000/api/elements/{element_id}/composition
```

### Добавить элемент в состав

```bash
curl -X POST "http://localhost:8000/api/elements/{parent_id}/composition?дочерний_элемент_id={child_id}&количество=2"
```

## Шаг 5: Обновление frontend (опционально)

Создать страницу для работы с элементами:

```jsx
// frontend/src/pages/Elements.jsx
import { useState, useEffect } from 'react'
import { getElements, getElementTypes } from '../api/elements'

function Elements() {
  const [elements, setElements] = useState([])
  const [types, setTypes] = useState([])
  const [selectedType, setSelectedType] = useState('')
  
  // ... реализация
}
```

## Преимущества новой структуры

✅ **Единый API** для всех типов элементов  
✅ **Легко добавлять новые типы** без изменения структуры БД  
✅ **BOM поддержка** - можно описывать состав элементов  
✅ **Масштабируемость** - структура готова к расширению  
✅ **Обратная совместимость** - старые таблицы продолжают работать  

## Примеры использования

### Создание элемента

```python
# Через API
POST /api/elements/
{
    "тип_id": 1,  # ms
    "обозначение": "К1324ПЦ1АУ",
    "наименование": "К1324ПЦ1АУ Микросхема",
    "цена": 1500.00
}
```

### Создание состава элемента

```python
# Плата состоит из микросхемы
POST /api/elements/{плата_id}/composition
{
    "дочерний_элемент_id": {микросхема_id},
    "количество": 2,
    "единица_измерения": "шт"
}
```

### Получение полного состава для расчета себестоимости

```python
GET /api/elements/{element_id}/composition
# Вернет все компоненты с количеством
# Можно использовать для автоматического расчета себестоимости
```

## Следующие шаги

1. ✅ Применить нормализованную схему
2. ✅ Мигрировать данные из warehouse
3. ⏳ Обновить frontend для работы с элементами
4. ⏳ Реализовать автоматический расчет себестоимости на основе BOM
5. ⏳ Добавить версионирование состава элементов

---

**Автор идеи и разработчик:** Полин Е.П. telegram: @PolinEP e-mail: polin-ep@yandex.ru  
**Соразработчик:** Cursor  
**Лицензионные права:** ИнноЦентр ВАО и ИПК Электрон-Маш
