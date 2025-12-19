-- Добавление столбцов is_admin и is_blocked в таблицу users
-- База данных: ElEngine

-- Добавляем поле is_admin (по умолчанию false для существующих пользователей)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE NOT NULL;

-- Добавляем поле is_blocked (по умолчанию false для существующих пользователей)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE NOT NULL;

-- Добавляем комментарии к столбцам для документации
COMMENT ON COLUMN public.users.is_admin IS 'Флаг администратора пользователя (true/false)';
COMMENT ON COLUMN public.users.is_blocked IS 'Флаг блокировки пользователя (true/false)';

