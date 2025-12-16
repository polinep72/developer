-- Создание таблицы audit_log для логирования действий пользователей
-- Версия: 1.0
-- Дата: 2025-12-16

CREATE TABLE IF NOT EXISTS public.audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
    action_type VARCHAR(50) NOT NULL,  -- 'login', 'logout', 'create', 'update', 'delete', 'export', 'file_upload'
    table_name VARCHAR(100),  -- Имя таблицы, если действие связано с БД
    record_id INTEGER,  -- ID записи, если действие связано с конкретной записью
    details TEXT,  -- Дополнительная информация (JSON или текст)
    ip_address INET,  -- IP адрес пользователя
    user_agent TEXT,  -- User-Agent браузера
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON public.audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON public.audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_type ON public.audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_name ON public.audit_log(table_name);

-- Комментарии к столбцам
COMMENT ON TABLE public.audit_log IS 'Журнал аудита действий пользователей';
COMMENT ON COLUMN public.audit_log.user_id IS 'ID пользователя (может быть NULL для неавторизованных действий)';
COMMENT ON COLUMN public.audit_log.action_type IS 'Тип действия: login, logout, create, update, delete, export, file_upload';
COMMENT ON COLUMN public.audit_log.table_name IS 'Имя таблицы, если действие связано с БД';
COMMENT ON COLUMN public.audit_log.record_id IS 'ID записи в таблице, если действие связано с конкретной записью';
COMMENT ON COLUMN public.audit_log.details IS 'Дополнительная информация в виде JSON или текста';
COMMENT ON COLUMN public.audit_log.ip_address IS 'IP адрес пользователя';
COMMENT ON COLUMN public.audit_log.user_agent IS 'User-Agent браузера пользователя';
COMMENT ON COLUMN public.audit_log.created_at IS 'Дата и время действия';

