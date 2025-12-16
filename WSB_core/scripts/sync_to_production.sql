-- SQL-запросы для синхронизации структуры БД с продакшн
-- Источник: 192.168.1.22 (тестовая), Цель: 192.168.1.139 (продакшн)
-- Сгенерировано автоматически
-- 
-- ВНИМАНИЕ: Перед применением убедитесь, что:
-- 1. Сделана резервная копия боевой БД
-- 2. Все изменения протестированы в тестовой БД
-- 3. Применение выполняется в период минимальной нагрузки

BEGIN;

-- Добавление столбца status в bookings (если отсутствует)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'bookings' 
          AND column_name = 'status'
    ) THEN
        ALTER TABLE bookings ADD COLUMN status TEXT NULL;
        RAISE NOTICE 'Столбец status добавлен в bookings';
    ELSE
        RAISE NOTICE 'Столбец status уже существует в bookings';
    END IF;
END $$;

-- Добавление столбцов в users (если отсутствуют)
DO $$
BEGIN
    -- email
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'users' 
          AND column_name = 'email'
    ) THEN
        ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL;
        RAISE NOTICE 'Столбец email добавлен в users';
    ELSE
        RAISE NOTICE 'Столбец email уже существует в users';
    END IF;
    
    -- phone
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'users' 
          AND column_name = 'phone'
    ) THEN
        ALTER TABLE users ADD COLUMN phone VARCHAR(50) NULL;
        RAISE NOTICE 'Столбец phone добавлен в users';
    ELSE
        RAISE NOTICE 'Столбец phone уже существует в users';
    END IF;
    
    -- password_hash
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'users' 
          AND column_name = 'password_hash'
    ) THEN
        ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL;
        RAISE NOTICE 'Столбец password_hash добавлен в users';
    ELSE
        RAISE NOTICE 'Столбец password_hash уже существует в users';
    END IF;
END $$;

-- Изменение типа столбца phone в users (если отличается)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'users' 
          AND column_name = 'phone'
          AND data_type != 'character varying'
          AND character_maximum_length != 32
    ) THEN
        ALTER TABLE users ALTER COLUMN phone TYPE VARCHAR(32);
        RAISE NOTICE 'Тип столбца phone изменен на VARCHAR(32)';
    ELSE
        RAISE NOTICE 'Тип столбца phone уже соответствует';
    END IF;
END $$;

-- Создание индексов для bookings (если отсутствуют)
CREATE INDEX IF NOT EXISTS idx_bookings_time_end ON public.bookings USING btree (time_end);
CREATE INDEX IF NOT EXISTS idx_bookings_user_start ON public.bookings USING btree (user_id, time_start);
CREATE INDEX IF NOT EXISTS idx_bookings_active_equip_end ON public.bookings USING btree (equip_id, time_end) WHERE ((cancel = false) AND (finish IS NULL));
CREATE INDEX IF NOT EXISTS idx_bookings_equip_start ON public.bookings USING btree (equip_id, time_start);
CREATE INDEX IF NOT EXISTS idx_bookings_time_start ON public.bookings USING btree (time_start);
CREATE INDEX IF NOT EXISTS idx_bookings_active_user_start ON public.bookings USING btree (user_id, time_start) WHERE ((cancel = false) AND (finish IS NULL));

-- Создание индексов для cat (если отсутствует)
CREATE INDEX IF NOT EXISTS idx_cat_lower_name ON public.cat USING btree (lower(name_cat));

-- Создание индексов для equipment (если отсутствуют)
CREATE INDEX IF NOT EXISTS idx_equipment_category ON public.equipment USING btree (category);
CREATE INDEX IF NOT EXISTS idx_equipment_id ON public.equipment USING btree (id);

-- Создание индексов для users (если отсутствуют)
CREATE UNIQUE INDEX IF NOT EXISTS users_email_uindex ON public.users USING btree (email) WHERE (email IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS users_phone_uindex ON public.users USING btree (phone) WHERE (phone IS NOT NULL);
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON public.users USING btree (is_admin);
CREATE INDEX IF NOT EXISTS idx_users_users_id ON public.users USING btree (users_id);
CREATE INDEX IF NOT EXISTS idx_users_is_blocked ON public.users USING btree (is_blocked);

-- Создание индексов для users_temp (если отсутствуют)
CREATE INDEX IF NOT EXISTS idx_users_temp_users_id ON public.users_temp USING btree (users_id);
CREATE UNIQUE INDEX IF NOT EXISTS constraint_name ON public.users_temp USING btree (users_id);

-- Создание таблиц wsb_* (если отсутствуют)
CREATE TABLE IF NOT EXISTS wsb_time_slots (
    id           SERIAL PRIMARY KEY,
    equipment_id INTEGER      NOT NULL,
    slot_start   TIMESTAMP    NOT NULL,
    slot_end     TIMESTAMP    NOT NULL,
    status       TEXT         NOT NULL DEFAULT 'free',
    booking_id   INTEGER      NULL,
    CONSTRAINT wsb_time_slots_uniq UNIQUE (equipment_id, slot_start, slot_end)
);

CREATE TABLE IF NOT EXISTS wsb_notifications_schedule (
    id              SERIAL PRIMARY KEY,
    booking_id      INTEGER NOT NULL,
    channel         VARCHAR(32) NOT NULL,
    event_type      VARCHAR(32) NOT NULL,
    run_at          TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    payload         JSONB,
    last_error      TEXT,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_run_at
    ON wsb_notifications_schedule (run_at);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_channel_status
    ON wsb_notifications_schedule (channel, status);

CREATE INDEX IF NOT EXISTS idx_wsb_notif_sched_booking
    ON wsb_notifications_schedule (booking_id);

COMMIT;

