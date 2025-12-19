-- Скрипт для создания индексов в базе данных
-- Версия: 1.4.15
-- Дата: 2025-12-17
-- Автор: Полин Е.П.

-- Проверка существующих индексов
-- SELECT tablename, indexname, indexdef 
-- FROM pg_indexes 
-- WHERE schemaname = 'public' 
-- ORDER BY tablename, indexname;

-- ============================================
-- ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ USERS
-- ============================================
-- Для аутентификации и поиска пользователей
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin);
CREATE INDEX IF NOT EXISTS idx_users_is_blocked ON users(is_blocked);

-- ============================================
-- ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ CART
-- ============================================
-- Для работы с корзиной пользователей
CREATE INDEX IF NOT EXISTS idx_cart_user_warehouse ON cart(user_id, warehouse_type);
CREATE INDEX IF NOT EXISTS idx_cart_item_id ON cart(item_id);
CREATE INDEX IF NOT EXISTS idx_cart_user_id ON cart(user_id);
CREATE INDEX IF NOT EXISTS idx_cart_date_added ON cart(date_added);

-- ============================================
-- ИНДЕКСЫ ДЛЯ ТАБЛИЦ INVOICE (invoice, invoice_p, invoice_f)
-- ============================================
-- Для фильтрации по статусу (часто используется: status = 1 для прихода, status = 3 для возврата)
CREATE INDEX IF NOT EXISTS idx_invoice_status ON invoice(status);
CREATE INDEX IF NOT EXISTS idx_invoice_p_status ON invoice_p(status);
CREATE INDEX IF NOT EXISTS idx_invoice_f_status ON invoice_f(status);

-- Для поиска по item_id (используется в LIKE запросах)
CREATE INDEX IF NOT EXISTS idx_invoice_item_id ON invoice(item_id);
CREATE INDEX IF NOT EXISTS idx_invoice_p_item_id ON invoice_p(item_id);
CREATE INDEX IF NOT EXISTS idx_invoice_f_item_id ON invoice_f(item_id);

-- Для фильтрации по дате
CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoice(date);
CREATE INDEX IF NOT EXISTS idx_invoice_p_date ON invoice_p(date);
CREATE INDEX IF NOT EXISTS idx_invoice_f_date ON invoice_f(date);

-- Составной индекс для частых запросов: статус + дата
CREATE INDEX IF NOT EXISTS idx_invoice_status_date ON invoice(status, date);
CREATE INDEX IF NOT EXISTS idx_invoice_p_status_date ON invoice_p(status, date);
CREATE INDEX IF NOT EXISTS idx_invoice_f_status_date ON invoice_f(status, date);

-- Индексы для внешних ключей (ускоряют JOIN)
CREATE INDEX IF NOT EXISTS idx_invoice_id_pr ON invoice(id_pr);
CREATE INDEX IF NOT EXISTS idx_invoice_id_lot ON invoice(id_lot);
CREATE INDEX IF NOT EXISTS idx_invoice_id_n_chip ON invoice(id_n_chip);
CREATE INDEX IF NOT EXISTS idx_invoice_id_start ON invoice(id_start);
CREATE INDEX IF NOT EXISTS idx_invoice_id_tech ON invoice(id_tech);
CREATE INDEX IF NOT EXISTS idx_invoice_id_wafer ON invoice(id_wafer);
CREATE INDEX IF NOT EXISTS idx_invoice_id_quad ON invoice(id_quad);
CREATE INDEX IF NOT EXISTS idx_invoice_id_in_lot ON invoice(id_in_lot);
CREATE INDEX IF NOT EXISTS idx_invoice_id_stor ON invoice(id_stor);
CREATE INDEX IF NOT EXISTS idx_invoice_id_cells ON invoice(id_cells);

-- Аналогичные индексы для invoice_p
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_pr ON invoice_p(id_pr);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_lot ON invoice_p(id_lot);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_n_chip ON invoice_p(id_n_chip);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_start ON invoice_p(id_start);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_tech ON invoice_p(id_tech);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_wafer ON invoice_p(id_wafer);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_quad ON invoice_p(id_quad);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_in_lot ON invoice_p(id_in_lot);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_stor ON invoice_p(id_stor);
CREATE INDEX IF NOT EXISTS idx_invoice_p_id_cells ON invoice_p(id_cells);

-- Аналогичные индексы для invoice_f
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_pr ON invoice_f(id_pr);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_lot ON invoice_f(id_lot);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_n_chip ON invoice_f(id_n_chip);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_start ON invoice_f(id_start);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_tech ON invoice_f(id_tech);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_wafer ON invoice_f(id_wafer);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_quad ON invoice_f(id_quad);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_in_lot ON invoice_f(id_in_lot);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_stor ON invoice_f(id_stor);
CREATE INDEX IF NOT EXISTS idx_invoice_f_id_cells ON invoice_f(id_cells);

-- Составной индекс для GROUP BY запросов (для ускорения агрегации)
CREATE INDEX IF NOT EXISTS idx_invoice_grouping ON invoice(item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells, status);
CREATE INDEX IF NOT EXISTS idx_invoice_p_grouping ON invoice_p(item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells, status);
CREATE INDEX IF NOT EXISTS idx_invoice_f_grouping ON invoice_f(item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells, status);

-- ============================================
-- ИНДЕКСЫ ДЛЯ ТАБЛИЦ CONSUMPTION (consumption, consumption_p, consumption_f)
-- ============================================
-- Для поиска по item_id
CREATE INDEX IF NOT EXISTS idx_consumption_item_id ON consumption(item_id);
CREATE INDEX IF NOT EXISTS idx_consumption_p_item_id ON consumption_p(item_id);
CREATE INDEX IF NOT EXISTS idx_consumption_f_item_id ON consumption_f(item_id);

-- Для фильтрации по дате
CREATE INDEX IF NOT EXISTS idx_consumption_date ON consumption(date);
CREATE INDEX IF NOT EXISTS idx_consumption_p_date ON consumption_p(date);
CREATE INDEX IF NOT EXISTS idx_consumption_f_date ON consumption_f(date);

-- Индексы для внешних ключей (ускоряют JOIN)
CREATE INDEX IF NOT EXISTS idx_consumption_id_pr ON consumption(id_pr);
CREATE INDEX IF NOT EXISTS idx_consumption_id_lot ON consumption(id_lot);
CREATE INDEX IF NOT EXISTS idx_consumption_id_n_chip ON consumption(id_n_chip);
CREATE INDEX IF NOT EXISTS idx_consumption_id_start ON consumption(id_start);
CREATE INDEX IF NOT EXISTS idx_consumption_id_tech ON consumption(id_tech);
CREATE INDEX IF NOT EXISTS idx_consumption_id_wafer ON consumption(id_wafer);
CREATE INDEX IF NOT EXISTS idx_consumption_id_quad ON consumption(id_quad);
CREATE INDEX IF NOT EXISTS idx_consumption_id_in_lot ON consumption(id_in_lot);
CREATE INDEX IF NOT EXISTS idx_consumption_id_stor ON consumption(id_stor);
CREATE INDEX IF NOT EXISTS idx_consumption_id_cells ON consumption(id_cells);

-- Аналогичные индексы для consumption_p
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_pr ON consumption_p(id_pr);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_lot ON consumption_p(id_lot);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_n_chip ON consumption_p(id_n_chip);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_start ON consumption_p(id_start);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_tech ON consumption_p(id_tech);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_wafer ON consumption_p(id_wafer);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_quad ON consumption_p(id_quad);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_in_lot ON consumption_p(id_in_lot);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_stor ON consumption_p(id_stor);
CREATE INDEX IF NOT EXISTS idx_consumption_p_id_cells ON consumption_p(id_cells);

-- Аналогичные индексы для consumption_f
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_pr ON consumption_f(id_pr);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_lot ON consumption_f(id_lot);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_n_chip ON consumption_f(id_n_chip);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_start ON consumption_f(id_start);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_tech ON consumption_f(id_tech);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_wafer ON consumption_f(id_wafer);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_quad ON consumption_f(id_quad);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_in_lot ON consumption_f(id_in_lot);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_stor ON consumption_f(id_stor);
CREATE INDEX IF NOT EXISTS idx_consumption_f_id_cells ON consumption_f(id_cells);

-- Составной индекс для GROUP BY запросов
CREATE INDEX IF NOT EXISTS idx_consumption_grouping ON consumption(item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells);
CREATE INDEX IF NOT EXISTS idx_consumption_p_grouping ON consumption_p(item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells);
CREATE INDEX IF NOT EXISTS idx_consumption_f_grouping ON consumption_f(item_id, id_start, id_pr, id_tech, id_lot, id_wafer, id_quad, id_in_lot, id_n_chip, id_stor, id_cells);

-- ============================================
-- ИНДЕКСЫ ДЛЯ СПРАВОЧНЫХ ТАБЛИЦ
-- ============================================
-- Для поиска по именам (используется в WHERE и ORDER BY)
CREATE INDEX IF NOT EXISTS idx_pr_name_pr ON pr(name_pr);
CREATE INDEX IF NOT EXISTS idx_lot_name_lot ON lot(name_lot);
CREATE INDEX IF NOT EXISTS idx_n_chip_n_chip ON n_chip(n_chip);
CREATE INDEX IF NOT EXISTS idx_tech_name_tech ON tech(name_tech);
CREATE INDEX IF NOT EXISTS idx_wafer_name_wafer ON wafer(name_wafer);
CREATE INDEX IF NOT EXISTS idx_quad_name_quad ON quad(name_quad);
CREATE INDEX IF NOT EXISTS idx_in_lot_in_lot ON in_lot(in_lot);
CREATE INDEX IF NOT EXISTS idx_start_p_name_start ON start_p(name_start);
CREATE INDEX IF NOT EXISTS idx_stor_name_stor ON stor(name_stor);
CREATE INDEX IF NOT EXISTS idx_cells_name_cells ON cells(name_cells);
CREATE INDEX IF NOT EXISTS idx_chip_name_chip ON chip(name_chip);
CREATE INDEX IF NOT EXISTS idx_pack_name_pack ON pack(name_pack);

-- Для текстового поиска (ILIKE) по n_chip
-- Используем GIN индекс для полнотекстового поиска или обычный B-tree для ILIKE
-- B-tree индекс с использованием нижнего регистра для ILIKE запросов
CREATE INDEX IF NOT EXISTS idx_n_chip_n_chip_lower ON n_chip(LOWER(n_chip));

-- ============================================
-- ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ USER_LOGS (если используется)
-- ============================================
-- Внимание: Структура таблицы user_logs может отличаться.
-- Раскомментируйте строки ниже, если соответствующие колонки существуют в вашей таблице.
-- CREATE INDEX IF NOT EXISTS idx_user_logs_user_id ON user_logs(user_id);
-- CREATE INDEX IF NOT EXISTS idx_user_logs_table_name ON user_logs(table_name);
-- CREATE INDEX IF NOT EXISTS idx_user_logs_action ON user_logs(action);
-- CREATE INDEX IF NOT EXISTS idx_user_logs_timestamp ON user_logs(timestamp);
-- CREATE INDEX IF NOT EXISTS idx_user_logs_user_action ON user_logs(user_id, action);

-- ============================================
-- КОММЕНТАРИИ ПО ИНДЕКСАМ
-- ============================================
-- 1. Индексы на внешние ключи (id_*) ускоряют JOIN операции
-- 2. Индексы на статус и дату ускоряют фильтрацию в WHERE
-- 3. Составные индексы для GROUP BY ускоряют агрегацию
-- 4. Индексы на имена справочников ускоряют ORDER BY и WHERE с текстовым поиском
-- 5. Индексы на cart(user_id, warehouse_type) оптимизируют выборку корзины пользователя

-- ============================================
-- ПРОВЕРКА СОЗДАННЫХ ИНДЕКСОВ
-- ============================================
-- После выполнения скрипта можно проверить созданные индексы:
-- SELECT tablename, indexname, indexdef 
-- FROM pg_indexes 
-- WHERE schemaname = 'public' 
-- AND indexname LIKE 'idx_%'
-- ORDER BY tablename, indexname;

