# Автоматический расчет дат поверки/аттестации

## Описание

Система автоматически рассчитывает даты следующей поверки/аттестации на основе МПИ (межповерочного интервала) из таблицы `equipment`.

## Формулы расчета

### 1. next_calibration_date
```
next_calibration_date = certificate_date + (mpi * 365 дней) - 1 день
```

### 2. days_until_calibration  
```
days_until_calibration = next_calibration_date - CURRENT_DATE (текущая дата)
```

## Логика работы

### Парсинг МПИ
Система поддерживает различные форматы МПИ:
- `"1"` → 1 год
- `"2"` → 2 года  
- `"1 год"` → 1 год
- `"3 года"` → 3 года
- `"5 лет"` → 5 лет

### Автоматические триггеры
1. **При INSERT** - автоматически рассчитываются даты при добавлении новой поверки
2. **При UPDATE** - пересчитываются даты при изменении существующей поверки

## SQL функции

### calculate_calibration_dates()
Основная функция для расчета дат. Вызывается автоматически через триггеры.

### add_calibration_certificate()
Функция для добавления новой поверки с автоматическим расчетом:
```sql
SELECT add_calibration_certificate(
    equipment_id, 
    certificate_number, 
    certificate_date, 
    calibration_cost
);
```

### recalculate_all_calibration_dates()
Функция для пересчета всех существующих записей:
```sql
SELECT recalculate_all_calibration_dates();
```

## Примеры использования

### 1. Добавление новой поверки через API
```javascript
POST /api/calibration-certificates
{
    "equipment_id": 1,
    "certificate_number": "ПОВ-2024-001",
    "certificate_date": "2024-06-15",
    "calibration_cost": 1500.00
}
```

### 2. Добавление через SQL
```sql
SELECT add_calibration_certificate(1, 'ПОВ-2024-001', '2024-06-15', 1500.00);
```

### 3. Примеры расчетов

| МПИ | Дата поверки | Следующая поверка | Дней до поверки |
|-----|--------------|-------------------|-----------------|
| 1 год | 2024-06-15 | 2025-06-14 | 365 |
| 2 года | 2024-06-15 | 2026-06-14 | 730 |
| 3 года | 2024-06-15 | 2027-06-14 | 1095 |

## Порядок выполнения SQL запросов

1. **Выполните файл `update_calibration_calculations.sql`** в pgAdmin
2. **Обновите МПИ** в таблице equipment (если необходимо)
3. **Пересчитайте существующие записи**:
   ```sql
   SELECT recalculate_all_calibration_dates();
   ```

## Тестирование

Запустите скрипт для тестирования:
```bash
python test_calibration_calculations.py
```

## Интеграция с приложением

### 1. app.py
- API endpoint `/api/calibration-certificates` использует новую функцию
- Автоматический расчет дат при добавлении поверок

### 2. manage_database.py  
- Функция `manage_calibration_certificates()` использует новую логику
- Показывает рассчитанные даты после добавления

### 3. import_excel_data.py
- Импорт данных использует новую функцию
- Автоматический расчет дат при импорте

## Преимущества

1. **Автоматизация** - не нужно вручную рассчитывать даты
2. **Точность** - расчеты основаны на МПИ из базы данных
3. **Гибкость** - поддержка различных форматов МПИ
4. **Консистентность** - единая логика расчета во всей системе
5. **Актуальность** - автоматический пересчет при изменении данных

## Мониторинг

Для проверки правильности расчетов:

```sql
-- Проверка расчетов для последних поверок
SELECT 
    c.certificate_number,
    c.certificate_date,
    e.mpi,
    c.next_calibration_date,
    c.days_until_calibration,
    (c.next_calibration_date - CURRENT_DATE) as manual_calculation
FROM calibration_certificates c
JOIN equipment e ON c.equipment_id = e.id
ORDER BY c.certificate_date DESC
LIMIT 10;
```

Система готова к использованию с автоматическим расчетом дат!
