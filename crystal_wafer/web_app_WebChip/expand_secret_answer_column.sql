-- Расширение поля secret_answer для хранения хешированных ответов
-- Хешированные ответы (werkzeug) могут иметь длину около 98-100 символов
-- Поэтому расширяем VARCHAR(255) до TEXT для надежности

ALTER TABLE public.users 
ALTER COLUMN secret_answer TYPE TEXT;

COMMENT ON COLUMN public.users.secret_answer IS 'Хешированный ответ на секретный вопрос (для восстановления пароля)';

