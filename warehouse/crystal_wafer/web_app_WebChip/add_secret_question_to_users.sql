-- Добавление полей для секретного вопроса и ответа в таблицу users
-- Это используется для восстановления пароля

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS secret_question VARCHAR(255);

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS secret_answer VARCHAR(255);

COMMENT ON COLUMN public.users.secret_question IS 'Секретный вопрос, заданный пользователем при регистрации';
COMMENT ON COLUMN public.users.secret_answer IS 'Хешированный ответ на секретный вопрос (для восстановления пароля)';

