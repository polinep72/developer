-- SQL-запросы для синхронизации структуры БД
-- Источник: 192.168.1.139, Цель: 192.168.1.22
-- Сгенерировано автоматически

BEGIN;

ALTER TABLE bookings ADD COLUMN status TEXT NULL;
CREATE INDEX IF NOT EXISTS idx_bookings_time_end ON public.bookings USING btree (time_end);
CREATE INDEX IF NOT EXISTS idx_bookings_user_start ON public.bookings USING btree (user_id, time_start);
CREATE INDEX IF NOT EXISTS idx_bookings_active_equip_end ON public.bookings USING btree (equip_id, time_end) WHERE ((cancel = false) AND (finish IS NULL));
CREATE INDEX IF NOT EXISTS idx_bookings_equip_start ON public.bookings USING btree (equip_id, time_start);
CREATE INDEX IF NOT EXISTS idx_bookings_time_start ON public.bookings USING btree (time_start);
CREATE INDEX IF NOT EXISTS idx_bookings_active_user_start ON public.bookings USING btree (user_id, time_start) WHERE ((cancel = false) AND (finish IS NULL));
CREATE INDEX IF NOT EXISTS idx_cat_lower_name ON public.cat USING btree (lower(name_cat));
CREATE INDEX IF NOT EXISTS idx_equipment_category ON public.equipment USING btree (category);
CREATE INDEX IF NOT EXISTS idx_equipment_id ON public.equipment USING btree (id);
ALTER TABLE users ALTER COLUMN phone TYPE VARCHAR(32);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_uindex ON public.users USING btree (email) WHERE (email IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS users_phone_uindex ON public.users USING btree (phone) WHERE (phone IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON public.users USING btree (is_admin);
CREATE INDEX IF NOT EXISTS idx_users_users_id ON public.users USING btree (users_id);
CREATE INDEX IF NOT EXISTS idx_users_is_blocked ON public.users USING btree (is_blocked);
CREATE INDEX IF NOT EXISTS idx_users_temp_users_id ON public.users_temp USING btree (users_id);
CREATE UNIQUE INDEX IF NOT EXISTS constraint_name ON public.users_temp USING btree (users_id);

COMMIT;
