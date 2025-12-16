-- Расширение поля password для хранения хешированных паролей
-- Хешированные пароли (werkzeug) имеют длину около 98-100 символов, поэтому нужен больший размер

-- Проверяем текущий тип поля
-- Если поле имеет ограничение VARCHAR(128), изменяем на TEXT
-- TEXT не имеет ограничения длины, что идеально для хешей

ALTER TABLE public.users 
ALTER COLUMN password TYPE TEXT;

COMMENT ON COLUMN public.users.password IS 'Пароль пользователя (хешированный через werkzeug.security)';

