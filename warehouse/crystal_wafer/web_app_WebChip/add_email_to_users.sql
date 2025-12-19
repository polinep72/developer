-- Добавление столбца email в таблицу users
-- База данных: ElEngine

-- Добавляем поле email (по умолчанию NULL, может быть пустым)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS email VARCHAR(255);

-- Добавляем комментарий к столбцу для документации
COMMENT ON COLUMN public.users.email IS 'Электронная почта пользователя';

