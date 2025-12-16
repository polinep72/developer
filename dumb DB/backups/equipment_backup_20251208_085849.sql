--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

-- Started on 2025-12-08 08:58:49

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.equipment DROP CONSTRAINT IF EXISTS equipment_gosregister_id_fkey;
ALTER TABLE IF EXISTS ONLY public.equipment DROP CONSTRAINT IF EXISTS equipment_equipment_type_id_fkey;
ALTER TABLE IF EXISTS ONLY public.calibration_certificates DROP CONSTRAINT IF EXISTS calibration_certificates_equipment_id_fkey;
DROP TRIGGER IF EXISTS trigger_calculate_next_calibration_date ON public.calibration_certificates;
DROP INDEX IF EXISTS public.idx_equipment_type_id;
DROP INDEX IF EXISTS public.idx_equipment_row_number;
DROP INDEX IF EXISTS public.idx_equipment_gosregister_id;
DROP INDEX IF EXISTS public.idx_calibration_certificates_next_date;
DROP INDEX IF EXISTS public.idx_calibration_certificates_equipment_id;
DROP INDEX IF EXISTS public.idx_calibration_certificates_date;
ALTER TABLE IF EXISTS ONLY public.gosregister DROP CONSTRAINT IF EXISTS gosregister_pkey;
ALTER TABLE IF EXISTS ONLY public.gosregister DROP CONSTRAINT IF EXISTS gosregister_gosregister_number_key;
ALTER TABLE IF EXISTS ONLY public.equipment_types DROP CONSTRAINT IF EXISTS equipment_types_type_code_key;
ALTER TABLE IF EXISTS ONLY public.equipment_types DROP CONSTRAINT IF EXISTS equipment_types_pkey;
ALTER TABLE IF EXISTS ONLY public.equipment DROP CONSTRAINT IF EXISTS equipment_pkey;
ALTER TABLE IF EXISTS ONLY public.calibration_certificates DROP CONSTRAINT IF EXISTS calibration_certificates_pkey;
ALTER TABLE IF EXISTS public.gosregister ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.equipment_types ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.equipment ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.calibration_certificates ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE IF EXISTS public.gosregister_id_seq;
DROP TABLE IF EXISTS public.gosregister;
DROP SEQUENCE IF EXISTS public.equipment_types_id_seq;
DROP TABLE IF EXISTS public.equipment_types;
DROP SEQUENCE IF EXISTS public.equipment_id_seq;
DROP TABLE IF EXISTS public.equipment;
DROP SEQUENCE IF EXISTS public.calibration_certificates_id_seq;
DROP TABLE IF EXISTS public.calibration_certificates;
DROP FUNCTION IF EXISTS public.update_existing_calibrations_with_mpi();
DROP FUNCTION IF EXISTS public.sync_equipment_mpi_from_gosregister();
DROP FUNCTION IF EXISTS public.recalculate_all_next_calibration_dates();
DROP FUNCTION IF EXISTS public.extract_mpi_years(mpi_text text);
DROP FUNCTION IF EXISTS public.calculate_next_calibration_date();
DROP FUNCTION IF EXISTS public.add_calibration_certificate(p_equipment_id integer, p_certificate_number character varying, p_certificate_date date, p_calibration_cost numeric, p_certificate_url text);
--
-- TOC entry 225 (class 1255 OID 74003)
-- Name: add_calibration_certificate(integer, character varying, date, numeric, text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.add_calibration_certificate(p_equipment_id integer, p_certificate_number character varying, p_certificate_date date, p_calibration_cost numeric, p_certificate_url text) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_next_calibration_date DATE;
    v_years_to_add INTEGER := 2; -- По умолчанию 2 года
    v_mpi_value VARCHAR(50);
    v_new_id INTEGER;
BEGIN
    -- Получаем МПИ с приоритетом: gosregister > equipment
    SELECT COALESCE(g.mpi, e.mpi) INTO v_mpi_value
    FROM equipment e
    LEFT JOIN gosregister g ON e.gosregister_id = g.id
    WHERE e.id = p_equipment_id;
    
    -- Парсим МПИ для определения периода поверки
    IF v_mpi_value IS NOT NULL THEN
        -- Ищем годы в МПИ (например, "2 год", "1 год")
        IF v_mpi_value ~ '\d+\s*год' THEN
            v_years_to_add := CAST(
                regexp_replace(v_mpi_value, '.*?(\d+)\s*год.*', '\1', 'g') AS INTEGER
            );
        -- Ищем месяцы в МПИ (например, "6 месяцев", "12 месяцев")
        ELSIF v_mpi_value ~ '\d+\s*месяц' THEN
            v_years_to_add := GREATEST(1, CAST(
                regexp_replace(v_mpi_value, '.*?(\d+)\s*месяц.*', '\1', 'g') AS INTEGER
            ) / 12);
        END IF;
    END IF;
    
    -- Рассчитываем дату следующей поверки
    IF p_certificate_date IS NOT NULL THEN
        -- Добавляем годы и вычитаем 1 день (срок действия заканчивается накануне)
        v_next_calibration_date := p_certificate_date + INTERVAL '1 year' * v_years_to_add - INTERVAL '1 day';
    END IF;
    
    -- Вставляем новую запись
    INSERT INTO calibration_certificates (
        equipment_id,
        certificate_number,
        certificate_date,
        next_calibration_date,
        calibration_cost,
        certificate_url
    ) VALUES (
        p_equipment_id,
        p_certificate_number,
        p_certificate_date,
        v_next_calibration_date,
        p_calibration_cost,
        p_certificate_url
    ) RETURNING id INTO v_new_id;
    
    RETURN v_new_id;
END;
$$;


ALTER FUNCTION public.add_calibration_certificate(p_equipment_id integer, p_certificate_number character varying, p_certificate_date date, p_calibration_cost numeric, p_certificate_url text) OWNER TO postgres;

--
-- TOC entry 227 (class 1255 OID 74017)
-- Name: calculate_next_calibration_date(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.calculate_next_calibration_date() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    mpi_value TEXT;
    mpi_years INTEGER;
BEGIN
    -- Получаем МПИ из связанных таблиц
    SELECT COALESCE(g.mpi, e.mpi) INTO mpi_value
    FROM equipment e
    LEFT JOIN gosregister g ON e.gosregister_id = g.id
    WHERE e.id = NEW.equipment_id;
    
    -- Извлекаем количество лет
    mpi_years := extract_mpi_years(mpi_value);
    
    -- Рассчитываем дату следующей поверки с учетом високосных годов:
    -- certificate_date + mpi_years лет - 1 день
    -- PostgreSQL автоматически учитывает високосные годы при использовании INTERVAL
    NEW.next_calibration_date := NEW.certificate_date + (mpi_years || ' years')::INTERVAL - INTERVAL '1 day';
    
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.calculate_next_calibration_date() OWNER TO postgres;

--
-- TOC entry 4851 (class 0 OID 0)
-- Dependencies: 227
-- Name: FUNCTION calculate_next_calibration_date(); Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON FUNCTION public.calculate_next_calibration_date() IS 'Триггерная функция для автоматического расчета next_calibration_date с учетом високосных годов';


--
-- TOC entry 226 (class 1255 OID 74016)
-- Name: extract_mpi_years(text); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.extract_mpi_years(mpi_text text) RETURNS integer
    LANGUAGE plpgsql IMMUTABLE
    AS $$
BEGIN
    IF mpi_text IS NULL OR mpi_text = '' THEN
        RETURN 2; -- По умолчанию 2 года
    END IF;
    
    -- Извлекаем число из текста типа "2 год", "1 год", "3 года"
    RETURN COALESCE(
        (regexp_match(mpi_text, '(\d+)'))[1]::INTEGER,
        2 -- По умолчанию 2 года
    );
END;
$$;


ALTER FUNCTION public.extract_mpi_years(mpi_text text) OWNER TO postgres;

--
-- TOC entry 4852 (class 0 OID 0)
-- Dependencies: 226
-- Name: FUNCTION extract_mpi_years(mpi_text text); Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON FUNCTION public.extract_mpi_years(mpi_text text) IS 'Извлекает количество лет из текста МПИ (например, "2 год" -> 2)';


--
-- TOC entry 239 (class 1255 OID 74019)
-- Name: recalculate_all_next_calibration_dates(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.recalculate_all_next_calibration_dates() RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
    rec RECORD;
    mpi_value TEXT;
    mpi_years INTEGER;
BEGIN
    FOR rec IN 
        SELECT cc.id, cc.equipment_id, cc.certificate_date
        FROM calibration_certificates cc
    LOOP
        -- Получаем МПИ для каждой записи
        SELECT COALESCE(g.mpi, e.mpi) INTO mpi_value
        FROM equipment e
        LEFT JOIN gosregister g ON e.gosregister_id = g.id
        WHERE e.id = rec.equipment_id;
        
        -- Извлекаем количество лет
        mpi_years := extract_mpi_years(mpi_value);
        
        -- Обновляем дату следующей поверки с учетом високосных годов
        UPDATE calibration_certificates 
        SET next_calibration_date = rec.certificate_date + (mpi_years || ' years')::INTERVAL - INTERVAL '1 day'
        WHERE id = rec.id;
    END LOOP;
END;
$$;


ALTER FUNCTION public.recalculate_all_next_calibration_dates() OWNER TO postgres;

--
-- TOC entry 4853 (class 0 OID 0)
-- Dependencies: 239
-- Name: FUNCTION recalculate_all_next_calibration_dates(); Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON FUNCTION public.recalculate_all_next_calibration_dates() IS 'Пересчитывает next_calibration_date для всех существующих записей с учетом високосных годов';


--
-- TOC entry 241 (class 1255 OID 74005)
-- Name: sync_equipment_mpi_from_gosregister(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.sync_equipment_mpi_from_gosregister() RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_updated_count INTEGER := 0;
BEGIN
    -- Обновляем МПИ в equipment на основе данных из gosregister
    UPDATE equipment 
    SET mpi = g.mpi
    FROM gosregister g
    WHERE equipment.gosregister_id = g.id 
    AND g.mpi IS NOT NULL 
    AND g.mpi != ''
    AND (equipment.mpi IS NULL OR equipment.mpi != g.mpi);
    
    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    
    RETURN v_updated_count;
END;
$$;


ALTER FUNCTION public.sync_equipment_mpi_from_gosregister() OWNER TO postgres;

--
-- TOC entry 240 (class 1255 OID 74004)
-- Name: update_existing_calibrations_with_mpi(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_existing_calibrations_with_mpi() RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_updated_count INTEGER := 0;
    rec RECORD;
BEGIN
    -- Обновляем все существующие записи поверки
    FOR rec IN
        SELECT 
            cc.id,
            cc.equipment_id,
            cc.certificate_date,
            COALESCE(g.mpi, e.mpi) as mpi_value
        FROM calibration_certificates cc
        JOIN equipment e ON cc.equipment_id = e.id
        LEFT JOIN gosregister g ON e.gosregister_id = g.id
        WHERE cc.certificate_date IS NOT NULL
    LOOP
        DECLARE
            v_years_to_add INTEGER := 2;
            v_new_next_date DATE;
        BEGIN
            -- Парсим МПИ
            IF rec.mpi_value IS NOT NULL THEN
                IF rec.mpi_value ~ '\d+\s*год' THEN
                    v_years_to_add := CAST(
                        regexp_replace(rec.mpi_value, '.*?(\d+)\s*год.*', '\1', 'g') AS INTEGER
                    );
                ELSIF rec.mpi_value ~ '\d+\s*месяц' THEN
                    v_years_to_add := GREATEST(1, CAST(
                        regexp_replace(rec.mpi_value, '.*?(\d+)\s*месяц.*', '\1', 'g') AS INTEGER
                    ) / 12);
                END IF;
            END IF;
            
            -- Рассчитываем новую дату
            v_new_next_date := rec.certificate_date + INTERVAL '1 year' * v_years_to_add - INTERVAL '1 day';
            
            -- Обновляем запись
            UPDATE calibration_certificates 
            SET next_calibration_date = v_new_next_date
            WHERE id = rec.id;
            
            v_updated_count := v_updated_count + 1;
        END;
    END LOOP;
    
    RETURN v_updated_count;
END;
$$;


ALTER FUNCTION public.update_existing_calibrations_with_mpi() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 224 (class 1259 OID 66033)
-- Name: calibration_certificates; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.calibration_certificates (
    id integer NOT NULL,
    equipment_id integer NOT NULL,
    certificate_number character varying(100) NOT NULL,
    certificate_date date NOT NULL,
    calibration_cost numeric(10,2),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    certificate_url text,
    next_calibration_date date
);


ALTER TABLE public.calibration_certificates OWNER TO postgres;

--
-- TOC entry 4854 (class 0 OID 0)
-- Dependencies: 224
-- Name: COLUMN calibration_certificates.next_calibration_date; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.calibration_certificates.next_calibration_date IS 'Автоматически рассчитываемая дата следующей поверки: certificate_date + (mpi*365) - 1 день';


--
-- TOC entry 223 (class 1259 OID 66032)
-- Name: calibration_certificates_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.calibration_certificates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.calibration_certificates_id_seq OWNER TO postgres;

--
-- TOC entry 4855 (class 0 OID 0)
-- Dependencies: 223
-- Name: calibration_certificates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.calibration_certificates_id_seq OWNED BY public.calibration_certificates.id;


--
-- TOC entry 222 (class 1259 OID 66008)
-- Name: equipment; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.equipment (
    id integer NOT NULL,
    row_number integer,
    equipment_type_id integer NOT NULL,
    gosregister_id integer,
    name text,
    type_designation character varying(200),
    serial_number character varying(100),
    mpi character varying(50),
    inventory_number character varying(50),
    year_in_service date,
    note text,
    calibration_cost numeric(10,2),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.equipment OWNER TO postgres;

--
-- TOC entry 4856 (class 0 OID 0)
-- Dependencies: 222
-- Name: COLUMN equipment.mpi; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.equipment.mpi IS 'Межповерочный интервал';


--
-- TOC entry 221 (class 1259 OID 66007)
-- Name: equipment_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.equipment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.equipment_id_seq OWNER TO postgres;

--
-- TOC entry 4857 (class 0 OID 0)
-- Dependencies: 221
-- Name: equipment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.equipment_id_seq OWNED BY public.equipment.id;


--
-- TOC entry 218 (class 1259 OID 65988)
-- Name: equipment_types; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.equipment_types (
    id integer NOT NULL,
    type_code character varying(10) NOT NULL,
    type_name character varying(100) NOT NULL
);


ALTER TABLE public.equipment_types OWNER TO postgres;

--
-- TOC entry 217 (class 1259 OID 65987)
-- Name: equipment_types_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.equipment_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.equipment_types_id_seq OWNER TO postgres;

--
-- TOC entry 4858 (class 0 OID 0)
-- Dependencies: 217
-- Name: equipment_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.equipment_types_id_seq OWNED BY public.equipment_types.id;


--
-- TOC entry 220 (class 1259 OID 65997)
-- Name: gosregister; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gosregister (
    id integer NOT NULL,
    gosregister_number character varying(50) NOT NULL,
    si_name text NOT NULL,
    type_designation character varying(200),
    manufacturer character varying(200),
    web_url text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    mpi character varying(50)
);


ALTER TABLE public.gosregister OWNER TO postgres;

--
-- TOC entry 4859 (class 0 OID 0)
-- Dependencies: 220
-- Name: COLUMN gosregister.web_url; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.gosregister.web_url IS 'Веб-ссылка на страницу официального Госреестра';


--
-- TOC entry 219 (class 1259 OID 65996)
-- Name: gosregister_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gosregister_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gosregister_id_seq OWNER TO postgres;

--
-- TOC entry 4860 (class 0 OID 0)
-- Dependencies: 219
-- Name: gosregister_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gosregister_id_seq OWNED BY public.gosregister.id;


--
-- TOC entry 4668 (class 2604 OID 66036)
-- Name: calibration_certificates id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calibration_certificates ALTER COLUMN id SET DEFAULT nextval('public.calibration_certificates_id_seq'::regclass);


--
-- TOC entry 4666 (class 2604 OID 66011)
-- Name: equipment id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment ALTER COLUMN id SET DEFAULT nextval('public.equipment_id_seq'::regclass);


--
-- TOC entry 4662 (class 2604 OID 65991)
-- Name: equipment_types id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment_types ALTER COLUMN id SET DEFAULT nextval('public.equipment_types_id_seq'::regclass);


--
-- TOC entry 4663 (class 2604 OID 66000)
-- Name: gosregister id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gosregister ALTER COLUMN id SET DEFAULT nextval('public.gosregister_id_seq'::regclass);


--
-- TOC entry 4845 (class 0 OID 66033)
-- Dependencies: 224
-- Data for Name: calibration_certificates; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.calibration_certificates (id, equipment_id, certificate_number, certificate_date, calibration_cost, created_at, updated_at, certificate_url, next_calibration_date) FROM stdin;
2	2	С-ДВУ/06-06-2025/439994813	2025-06-06	24365.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-418329776	2026-06-05
23	23	1/120-1318-17	2018-11-21	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	\N	2019-11-20
24	24	1/120-1317-17	2018-11-21	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	\N	2019-11-20
1	1	С-ГДИ/31-07-2024/358976725	2024-07-31	13800.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-358976725	2026-07-30
30	79	С-АКЗ/22-04-2024/334253247	2024-04-22	\N	2025-10-14 10:29:34.399561	2025-10-14 10:29:34.399561	https://fgis.gost.ru/fundmetrology/cm/results/1-334253247	2025-04-21
8	8	С-ГДИ/31-07-2024/358977888	2024-07-31	14000.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-358977888	2025-07-30
10	10	С-МА/07-06-2024/346698454	2024-06-07	18800.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-258940008	2025-06-06
14	14	С-ГЖЕ/01-03-2024/320207254	2024-03-01	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-320207254	2025-02-28
15	15	С-ВТЖ/22-01-2024/310573973	2024-01-22	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-310573973	2025-01-21
16	16	С-ДЮП/18-09-2023/279127743	2023-09-18	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-279127743	2024-09-17
17	17	С-ДИЭ/18-09-2023/279127774	2023-09-18	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-279127774	2024-09-17
18	18	С-ДИЭ/18-09-2023/279127773	2023-09-18	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-279127773	2025-09-17
19	19	С-ДЮП/18-09-2023/279127742	2023-09-18	2500.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-279127742	2024-09-17
20	20	С-ДЕЧ/07-09-2023/276430250	2023-09-07	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-276430250	2024-09-06
21	21	С-МА/21-08-2023/271682401	2023-08-21	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-271682401	2024-08-20
22	22	С-Н/23-06-2023/256753512	2023-06-23	24365.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-256753512	2024-06-22
4	4	С-АВФ/19-02-2024/322585227	2024-02-19	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-322585227	2026-02-18
5	5	С-АВФ/17-02-2024/322581466	2024-02-17	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-322581466	2026-02-16
6	6	С-АВФ/02-11-2023/295570963	2023-11-02	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-295570963	2025-11-01
9	9	С-АВФ/10-06-2023/258940008	2023-06-10	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-258940008	2025-06-09
13	13	С-ДТЖ/26-03-2024/326695028	2024-03-26	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-326695028	2025-03-25
7	7	С-ДХЛ/18-09-2024/371577672	2024-09-18	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-371577672	2025-09-17
11	11	С-ДЮП/08-05-2024/338255856	2024-05-08	250.00	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-338255856	2025-05-07
12	12	С-АЕЯ/08-05-2024/337705076	2024-05-08	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-337705076	2025-05-07
3	3	С-АВФ/16-04-2024/337273316	2024-04-16	\N	2025-10-07 13:04:12.395978	2025-10-07 13:04:12.395978	https://fgis.gost.ru/fundmetrology/cm/results/1-337273316	2026-04-15
\.


--
-- TOC entry 4843 (class 0 OID 66008)
-- Dependencies: 222
-- Data for Name: equipment; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.equipment (id, row_number, equipment_type_id, gosregister_id, name, type_designation, serial_number, mpi, inventory_number, year_in_service, note, calibration_cost, created_at) FROM stdin;
26	26	1	1	Частотомеры универсальные	GFC-8270H	CJ860020	\N		\N		7000.00	2025-10-14 08:03:45.676447
27	27	1	3	Источники питания	UT3005EP	202106063125	\N	13	\N		5200.00	2025-10-14 08:03:45.676447
28	28	1	3	Источники питания	UT3005EP	202106063123	\N	16	\N		5200.00	2025-10-14 08:03:45.676447
29	29	1	3	Источники питания	UT3005EP	202106063120	\N	БП-000064	\N	ВТРМ-3 ПП109	5200.00	2025-10-14 08:03:45.676447
3	3	1	55	Гигрометры психрометрические	ВИТ-2	312	\N		\N	Гигрометр для контроля климатических условий<br>в чистой зоне.	\N	2025-10-14 08:03:45.676447
80	80	1	2	Штангенглубиномеры	ШГЦ 150мм	AII14639	\N	БП-000070	\N	ВТРМ-4 ПП110	\N	2025-10-14 08:03:45.676447
64	64	1	5	Мультиметры цифровые	Fluke 17B+	42114294WS	\N		\N		2500.00	2025-10-14 08:03:45.676447
50	50	1	7	Источники питания постоянного тока	АКИП-1118	800199030787020005	\N		\N		5200.00	2025-10-14 08:03:45.676447
48	48	1	8	Измерители температуры электронные	Сenter 303	171105825	\N		\N		\N	2025-10-14 08:03:45.676447
16	16	1	9	Меры напряжения и тока	E3632A	MY57386018	\N	00-000020	\N		\N	2025-10-14 08:03:45.676447
44	44	1	11	Генераторы сигналов специальной формы	SFG-2110	EM872979	\N	000000011	\N		7000.00	2025-10-14 08:03:45.676447
45	45	1	11	Генераторы сигналов специальной формы	SFG-2110	GEN851998	\N	000000015	\N		7000.00	2025-10-14 08:03:45.676447
35	35	1	12	Анализаторы спектра	R3465	52420236	\N	27	\N		24365.00	2025-10-14 08:03:45.676447
49	49	1	13	Источники питания	MPS-3003S	D202100WX	\N		\N	Источник питания на участке обработки материалов	5200.00	2025-10-14 08:03:45.676447
78	78	1	14	Системный источник питания	6653A	MY53000565	\N	00-000022	\N		5200.00	2025-10-14 08:03:45.676447
47	47	1	15	Измерители мощности СВЧ	М3М-18	2409210183	\N	БП-000061	\N		14000.00	2025-10-14 08:03:45.676447
75	75	1	16	Преобразователи измерительные	NRP-Z11	113209	\N	БП-000087	\N	ВТРМ-7 ПП109	14000.00	2025-10-14 08:03:45.676447
19	19	1	17	Вольтметры универсальные цифровые	GDM-78251A	RI130329	\N	9	\N		2500.00	2025-10-14 08:03:45.676447
39	39	1	17	Вольтметры универсальные цифровые	GDM-78255A	RL110157	\N	10	\N		2500.00	2025-10-14 08:03:45.676447
65	65	1	18	Мультиметры цифровые	RD701	20125100402	\N		\N		2500.00	2025-10-14 08:03:45.676447
66	66	1	18	Мультиметры цифровые	RD701	20125100417	\N		\N		2500.00	2025-10-14 08:03:45.676447
67	67	1	18	Мультиметры цифровые	RD701	20125100420	\N		\N		2500.00	2025-10-14 08:03:45.676447
68	68	1	18	Мультиметры цифровые	RD701	20125100418	\N		\N		2500.00	2025-10-14 08:03:45.676447
72	72	1	21	Осциллографы цифровые	MSO5104	MS5A251001856	\N	БП-000088	\N	ВТРМ-6 ПП109	\N	2025-10-14 08:03:45.676447
74	74	1	22	Осциллографы цифровые	DSO-X 3034A	MY51451753	\N	24	\N		4750.00	2025-10-14 08:03:45.676447
55	55	1	23	Источники питания программируемые	PWS4323	C010803	\N	17	\N		5200.00	2025-10-14 08:03:45.676447
56	56	1	23	Источники питания программируемые	PWS4323	C010796	\N	14	\N		5200.00	2025-10-14 08:03:45.676447
63	63	1	24	Микрометр	МК-25 0.01	CU130035	\N		\N		\N	2025-10-14 08:03:45.676447
23	23	1	26	Генератор шума	ГШМ2-20А-13	2391080632	\N		\N		\N	2025-10-14 08:03:45.676447
24	24	1	26	Генератор шума	ГШМ2-20В-13	2389080731	\N		\N		\N	2025-10-14 08:03:45.676447
31	31	1	28	Источники питания постоянного тока <br>программируемые	DP832	DP8B250800211	\N		\N	Источник питания для рабочего места контроля<br>параметров изделий	5200.00	2025-10-14 08:03:45.676447
37	37	1	37	Анализаторы фазовых шумов	PNA20	223-03D306F00-0525	\N		\N		\N	2025-10-14 08:03:45.676447
4	4	1	55	Гигрометры психрометрические	ВИТ-2	241	\N		\N	Гигрометр для контроля климатических условий<br>в складской зоне.	\N	2025-10-14 08:03:45.676447
5	5	1	55	Гигрометры психрометрические	ВИТ-2	509	\N		\N	Гигрометр для контроля климатических условий<br>в чистой зоне.	\N	2025-10-14 08:03:45.676447
30	30	1	3	Источники питания	UT3005EP	202106063117	\N		\N	Источник питания для рабочего места контроля<br>параметров изделий	5200.00	2025-10-14 08:03:45.676447
83	83	1	41	Штангенциркули	ШЦ, ШЦК, ШЦЦ<br>(ШЦК-I-150-0,01)	452711	\N		\N	Штангенциркуль на участке обработки материалов<br>Тип: с глубиномером<br>Способ отсчета: стрелочный\r\n<br>Диапазон измерений: 0-150 мм<br>Размерность: длина губок 40 мм<br>Точность отсчета: 0,01 мм	\N	2025-10-14 08:03:45.676447
41	41	1	25	Генераторы сигналов	Advantex SG8	03273-2051-001	\N		\N		10350.00	2025-10-14 08:03:45.676447
25	25	1	29	Генераторы сигналов	HMC-T2000	0932	\N		\N		10350.00	2025-10-14 08:03:45.676447
22	22	1	20	Анализаторы цепей векторные	Р4М-18	1102170233	\N	00-000028	\N		24365.00	2025-10-14 08:03:45.676447
73	73	1	22	Осциллографы цифровые	DSO-X 3032A	MY53400165	\N	00-000013	\N		4750.00	2025-10-14 08:03:45.676447
1	1	1	6	Генераторы сигналов произвольной формы	33510B	MY52200936	\N	00-000017	\N		13800.00	2025-10-14 08:03:45.676447
58	58	1	10	Меры напряжения и тока	E3642A	MY52500054	\N		\N	в составе U2702A ( 00-000014)	\N	2025-10-14 08:03:45.676447
71	71	3	\N	Цифровой осциллограф	DSO4254C	CN1805002001356	\N		\N		\N	2025-10-14 08:03:45.676447
59	59	1	10	Меры напряжения и тока	E3642A	MY532000037	\N		\N		\N	2025-10-14 08:03:45.676447
60	60	1	10	Меры напряжения и тока	E3642A	MY53130010	\N		\N		\N	2025-10-14 08:03:45.676447
61	61	1	10	Меры напряжения и тока	E3643A	MY53346003	\N		\N		\N	2025-10-14 08:03:45.676447
62	62	1	10	Меры напряжения и тока	E3644A	MY53070007	\N		\N		\N	2025-10-14 08:03:45.676447
14	14	1	39	Штангенциркули торговой марки "Micron"	Нет данных	082081	\N		\N	Штангенциркуль для проведения входного контроля	\N	2025-10-14 08:03:45.676447
32	32	1	51	Приборы для измерений текстуры поверхности, <br>отклонения от формы дуги окружности, <br>прямолинейности и радиуса дуги <br>средней линии по методу наименьших квадратов	Form Talysurf	41	\N		\N	Профилометр	\N	2025-10-14 08:03:45.676447
21	21	1	44	Анализаторы цепей векторные	ZNA43	101232	\N		\N		\N	2025-10-14 08:03:45.676447
76	76	1	45	Преобразователи измерительные ваттметров <br>поглощаемой мощности	N1922A	MY57390003	\N	00-000024	\N		\N	2025-10-14 08:03:45.676447
77	77	1	45	Преобразователи измерительные ваттметров <br>поглощаемой мощности	N1922A	MY57390004	\N	00-000027	\N		\N	2025-10-14 08:03:45.676447
38	38	1	47	Ваттметры поглощаемой мощности	PLS26-13M	1131210128	\N	БП-000061	\N	ВТРМ-2 ПП109	\N	2025-10-14 08:03:45.676447
10	10	1	48	Генераторы сигналов	N5183B	MY612502924	\N		\N		18800.00	2025-10-14 08:03:45.676447
42	42	1	48	Генераторы сигналов	N5183B	MY57280387	\N	00-000025	\N		18800.00	2025-10-14 08:03:45.676447
43	43	1	50	Генераторы сигналов	PLG20-12F	1106210002	\N	БП-000061	\N	ВТРМ-2 ПП109	13800.00	2025-10-14 08:03:45.676447
79	79	1	53	Тепловизоры инфракрасные	Guide H3	ZC16B3023420031	\N		\N		\N	2025-10-14 08:03:45.676447
51	51	1	54	Источники питания постоянного тока <br>программируемые	DP832A	DP8B233001492	\N	БП-000088	\N	ВТРМ-6 ПП109	5200.00	2025-10-14 08:03:45.676447
52	52	1	54	Источники питания постоянного тока <br>программируемые	DP832A	DP8B233101658	\N		\N		5200.00	2025-10-14 08:03:45.676447
53	53	1	54	Источники питания постоянного тока <br>программируемые	DP832A	DP8B233101661	\N		\N		5200.00	2025-10-14 08:03:45.676447
54	54	1	54	Источники питания постоянного тока <br>программируемые	DP832A	DP8B244803129	\N	БП-000087	\N	ВТРМ-7 ПП109	5200.00	2025-10-14 08:03:45.676447
82	82	1	52	Штангенциркули	NCR-1502	20231027144	\N		\N		\N	2025-10-14 08:03:45.676447
7	7	1	46	Камеры тепловизионные <br>стационарные	PI, Xi	24052111/24050108	\N		\N		\N	2025-10-14 08:03:45.676447
17	17	1	42	Мультиметры цифровые	34461A	MY5500624	\N	00-000018	\N		\N	2025-10-14 08:03:45.676447
69	69	1	42	Мультиметры цифровые	34461A	MY53226177	\N	00-000026	\N		\N	2025-10-14 08:03:45.676447
18	18	1	43	Осциллографы цифровые	MSOX3102A	MY57230126	\N	00-000021	\N		\N	2025-10-14 08:03:45.676447
13	13	1	49	Термогигрометры	RGK моделей<br>ТН-10, ТН-12	23053715	\N		\N	Термогигрометр для контроля климатических<br>условий в складской зоне	\N	2025-10-14 08:03:45.676447
197	\N	1	62	Блоки питания импульсные	MAISHENG<br>MP6010D	2025051670	\N	\N	\N	Возможность регулировки напряжения<br>Выходное напряжение: 0 - 60 В (регулируемое) <br>Выходной ток: 0 - 10 А (регулируемый) <br>Тип: импульсный	\N	2025-10-14 12:31:20.508245
115	29	3	\N	Электронный микроскоп	MC-6.3<br>(USB-3.0)	XC1480	\N	БП-000069	\N	ОС ФСИ эт.2	\N	2025-10-14 08:03:45.676447
116	30	3	\N	Электронный микроскоп 	Beiyinhu		\N		\N		\N	2025-10-14 08:03:45.676447
148	62	3	\N	Bias Tees	QBT-10-12000	24225061	\N		\N	0.01~12GHz	\N	2025-10-14 08:03:45.676447
86	2	2	\N	Климатическая камера	КХТ-0,064	144-1/16	\N		2016-07-08	-70…+155 C\n64л	\N	2025-10-14 08:03:45.676447
87	1	3	\N	DC-18GHz 50W coaxial fixed attenuator	MFT180F050F40L		\N		\N		\N	2025-10-14 08:03:45.676447
88	2	3	\N	Directional coupler	ZUDC30-183+	01817	\N		\N		\N	2025-10-14 08:03:45.676447
89	3	3	\N	Termination	KARN-50-18+	31837	\N		\N		\N	2025-10-14 08:03:45.676447
101	15	3	\N	Разводной ключ 	с тонкими губками<br>150 мм Inforce		\N		\N		\N	2025-10-14 08:03:45.676447
96	10	3	\N	Микроскоп	ЭМ60 30	16	\N		\N	НБ-1 (92029)	\N	2025-10-14 08:03:45.676447
97	11	3	\N	Мультиметры цифровые	MS8250D	MCAE009936	\N		\N		\N	2025-10-14 08:03:45.676447
102	16	3	\N	Цифровой осциллограф	DSO4254C	CN1734002000656	\N		\N		\N	2025-10-14 08:03:45.676447
103	17	3	\N	Электронная нагрузка батарей	ET5420A+	09722321080	\N		\N		\N	2025-10-14 08:03:45.676447
198	\N	3	\N	Блок питания лабораторный	MCH K605D-II	WT0506394	\N	\N	\N	3 типа защиты<br>Выходное напряжение: 0 - 60 В<br>Выходной ток: 0 - 5 А<br>Тип: линейный<br>M25C1556-3H	\N	2025-10-14 12:38:43.232454
109	23	3	\N	Набор отверток ProsKit	8PK-SD001N		\N		\N	20 в 1	\N	2025-10-14 08:03:45.676447
90	4	3	\N	Анализатор спектра Rigol	RSA3015E-TG	RSA3H260200006	\N		\N		\N	2025-10-14 08:03:45.676447
84	84	1	30	Штангенциркули торговой марки "GRIFF" <br>с отсчетом по нониусу и <br>с цифровым отсчетным устройством	ШЦЦ-I-300-0,01	22050110	\N		\N	Штангенциркуль на участке обработки материалов	\N	2025-10-14 08:03:45.676447
93	7	3	\N	Комплект коаксиальных аттенюаторов	11582A	61382	\N		\N	Набор из четырех аттенюаторов 8491B<br>(3, 6, 10 и 20 дБ) (90763) с разъемами type-N<br>идеально подходит для калибровочных лабораторий.	\N	2025-10-14 08:03:45.676447
94	8	3	\N	Комплект коаксиальных аттенюаторов	11583C	61216	\N		\N	Набор из четырех аттенюаторов 8493C<br>(3, 6, 10 и 20 дБ)  (90273) с разъемами APC-3.5<br>идеально подходит для калибровочных лабораторий	\N	2025-10-14 08:03:45.676447
95	9	3	\N	Комплект коаксиальных аттенюаторов	11583C	61213	\N		\N	Набор из четырех аттенюаторов 8493C<br>(3, 6, 10 и 20 дБ) (90270) с разъемами APC-3.5<br>идеально подходит для калибровочных лабораторий	\N	2025-10-14 08:03:45.676447
105	19	3	\N	Источник питания	HY1505D	476829	\N		\N	Выходное напряжение: 0~15V <br>точность установки 0.1V<br>\r\nВыходной ток: 0~5A<br>точность установки 0.01A<br>\r\nточность: напряжение: ±1%, ток: ±2%\r\n<br>Защита от короткого замыкания<br>Габариты: 206х153х110 (мм)<br>вес 3.6 кг<br>\r\nПитание: 110/220V ±10%	\N	2025-10-14 08:03:45.676447
106	20	3	\N	Источник питания	HY1505D	476807	\N		\N	Выходное напряжение: 0~15V<br> точность установки 0.1V<br>\r\nВыходной ток: 0~5A<br>точность установки 0.01A<br>\r\nточность: напряжение: ±1%, ток: ±2%\r\n<br>Защита от короткого замыкания\r\n<br>Габариты: 206х153х110 (мм), вес 3.6 кг<br>\r\nПитание: 110/220V ±10%	\N	2025-10-14 08:03:45.676447
108	22	3	\N	Лабораторная нагревательная плита	ULAB UH-3545A	206101	\N		\N	Таймер:  нет\r\n<br>Температура нагрева: до + 350 оС\r<br>\nМощность: 2,0 кВт\r\n<br>Размер платформы: 450х350\r\n<br>Материал платформы: чугун\r\n<br>Контроллер: аналоговый	\N	2025-10-14 08:03:45.676447
110	24	3	\N	Набор шестигранных ключей ProsKit 00237023	8PK-027		\N		\N	Тип HEX\r\n<br>Размер min 0.7 мм<br>Размер max 10 мм\r\n<br>Материал CrV\r\n<br>Количество в наборе 30 шт\r\n<br>Форма угловой\r\n<br>Вид упаковки пластиковый пенал	\N	2025-10-14 08:03:45.676447
111	25	3	\N	Power splitter	ZFRSC-183-S+	FG79301902	\N		\N	Диапазон частот: 0 Гц – 18 ГГц\r\n<br>Изоляция (типичная): 7 дБ\r\n<br>Симметричный дисбаланс: 10° (максимум)\r\n<br>Потери включения: 1 дБ (типично)\r\n<br>Размеры: 25.40 мм x 19.05 мм x 15.49 мм\r\n<br>Корпус/Разъемы: Модуль, разъемы SMA	\N	2025-10-14 08:03:45.676447
91	5	3	\N	Генератор сигналов специальной формы	ArbStudio 1104	LCRY2341/00481	\N	00-000002	\N		\N	2025-10-14 08:03:45.676447
113	27	3	\N	Генератор сигналов	DG832	DG8A221200786	\N	БП-000061	\N	Тип прибора Настольный, Спец. формы\r\n<br>Количество каналов 2\r\n<br>Мин. частота (кГц) 0.000001\r\nМакс. частота (ГГц) 35\r\n<br>Частотный диапазон 1 мкГц ... 35 МГц\r\n<br>Интерфейс USB device, USB host, USB-GPIB опция	\N	2025-10-14 08:03:45.676447
114	28	3	\N	Low noise current preamplifier\n	SR570	162623	\N		\N	5 fA/√Hz input noise\r\n1 MHz <br>maximum bandwidth\r\n1 pA/V <br>maximum gain\r\n<br>Adjustable bias voltage\r\n<br>Two configurable signal filters\r\n<br>Variable input offset current\r\nLine or battery operation\r\n<br>RS-232 interface	\N	2025-10-14 08:03:45.676447
98	12	3	\N	Источник питания <br>программируемый	DP711	DP7A233001068	\N		\N		\N	2025-10-14 08:03:45.676447
99	13	3	\N	Источник питания <br>программируемый	DP711	DP7A230600177	\N		\N		\N	2025-10-14 08:03:45.676447
100	14	3	\N	Источник питания <br>программируемый	DP932A	DP9A253800511	\N		\N		\N	2025-10-14 08:03:45.676447
104	18	3	\N	Дифференциальный пробник <br>с интерфейсом AutoProbe	N2818A	PH58380021	\N		\N	200 МГц, 10:1	\N	2025-10-14 08:03:45.676447
117	31	3	\N	Источник питания программируемый	DP711	DP7A232901032	\N		\N		\N	2025-10-14 08:03:45.676447
118	32	3	\N	Анализатор спектра реального времени	RSA250X	A3-X-03000478	\N		\N	полоса анализа 80 МГц\nанализ спектральных характеристик радиосигналов	\N	2025-10-14 08:03:45.676447
121	35	3	\N	Векторный генератор сигналов	VSG6G1C	CN62800508	\N		\N	1 МГц до 6,1 ГГц.	\N	2025-10-14 08:03:45.676447
122	36	3	\N	Синтезатор опорной частоты	DSG-38M-RF	53500-2062-073	\N		\N	0 до 250 МГц, мощность до +20 дБм	\N	2025-10-14 08:03:45.676447
123	37	3	\N	Векторный генератор сигналов	VSG6G1C	CN62800480	\N	БП-000088 (ВТРМ-6 ПП190)	\N	1 МГц до 6,1 ГГц.	\N	2025-10-14 08:03:45.676447
131	45	3	\N	Измерительный СВЧ усилитель	IGPA-03 	2127-0063	\N	БП-000071	\N	3Вт GaN 2 до 18 ГГЦ	\N	2025-10-14 08:03:45.676447
132	46	3	\N	Малошумящий СВЧ Синтезатор 100 кГц — 21 ГГц	SGU21-01M-C2U42HP315	51792-1031-001	\N		\N		\N	2025-10-14 08:03:45.676447
134	48	3	\N	Directional Coupler	QSDC-1000-40000-30	24235156	\N		\N	30 W, 30 dB Directional Coupler from 1000 to 4000 MHz	\N	2025-10-14 08:03:45.676447
135	49	3	\N	Directional Coupler	QSDC-1000-40000-30	24235157	\N		\N	31 W, 30 dB Directional Coupler from 1000 to 4000 MHz	\N	2025-10-14 08:03:45.676447
136	50	3	\N	Directional Coupler	QSDC-1000-40000-30	24235158	\N		\N	32 W, 30 dB Directional Coupler from 1000 to 4000 MHz	\N	2025-10-14 08:03:45.676447
137	51	3	\N	Directional coupler	ZUDC30-183+	01904	\N		\N		\N	2025-10-14 08:03:45.676447
138	52	3	\N	Directional coupler	ZUDC30-183+	01904	\N		\N		\N	2025-10-14 08:03:45.676447
139	53	3	\N	Directional coupler	ZUDC30-183+	0817	\N		\N		\N	2025-10-14 08:03:45.676447
140	54	3	\N	Ответвитель направленный	HO16-0,5-26-13P-13P		\N		\N		\N	2025-10-14 08:03:45.676447
141	55	3	\N	RF Amplifier	ZHL-4240N+	415401843	\N		\N		\N	2025-10-14 08:03:45.676447
142	56	3	\N	RF Amplifier 	ZVE-3W-83+	588901904	\N		\N		\N	2025-10-14 08:03:45.676447
143	57	3	\N	RF Amplifier 	ZVE-3W-183+	362601834	\N		\N		\N	2025-10-14 08:03:45.676447
144	58	3	\N	Power Divider	ZN2PD2-14W-S+	FG90701905	\N		\N	35 W, 2-way 0° Splitter/Combiner from 500 to 10500 MHz	\N	2025-10-14 08:03:45.676447
145	59	3	\N	RF & Microwave Circulator	QCC-26500-40000-5-K-1	24205006	\N		\N		\N	2025-10-14 08:03:45.676447
146	60	3	\N	RF & Microwave Circulator	QCC-26500-40000-5-K-1	24205007	\N		\N		\N	2025-10-14 08:03:45.676447
129	43	3	\N	Источник питания <br>программируемый	DP932E	DP9A253701237	\N		\N	Цветной сенсорный дисплей 4,3 дюйма\r\n<br>3 независимых канала 32В/3А, 32В/3А, 6В/3А\r\n<br>Автоматическое объединение каналов последовательно или параллельно\r\n<br>Время обработки команд менее 1 О мс<br>\r\nНизкие выходные пульсации <350 мкВср.кв / 2 мВпик-пик\r\n<br>Минимальное время пребывания в точке 100мс\r\n<br>Безопасные штекеры на передней панели\r\nLAN, USB, <br>цифровые входы/выходы\r<br>\nЗащита от температуры, скачков тока напряжения	\N	2025-10-14 08:03:45.676447
133	47	3	\N	Аттенюатор программируемый	RCDAT-30G-30	01907290045	\N		\N	от 0,1 до 30 ГГц, от 0 до 30 дБ, шаг 0,5 дБ	\N	2025-10-14 08:03:45.676447
147	61	3	\N	Bias Network	11612A		\N		\N	frequency range of 40 MHz to 26.5 GHz.	\N	2025-10-14 08:03:45.676447
126	40	3	\N	Усилитель мощности	Arinst KPAM-3000	б/н	\N	БП-000068 (ОС ФСИ эт.1)	\N	Диапазон частот 200-3000 МГц\r<br>\nКоэффициент усиления 42 дБ\r\n<br>Встроенный Li-ion аккумулятор	\N	2025-10-14 08:03:45.676447
130	44	3	\N	Весовой индикатор	SH-20	WXK21080201	\N	БП-000070 (ВТРМ-4 ПП109)	\N	Рабочая температура, °С 0..+40<br>\r\nПитание:<br>Адаптер: AC 100~220V / DC 12V\r\n<br>Аккумулятор: DC 6V / 1.2Ah (в комплект не входит)\r\n-<br>Элементы питания АА х 6 шт (в комплект не входят)\r\n<br>Питания датчиков, В ⎓5 (100 мА)\r\n<br>Не более датчиков, шт х Ом 4х350 или 8х750\r\n<br>Внешнее разрешение 1/1000-1/15000\r\n<br>Нелинейность 0.016% от максимального веса\r\n<br>Выбор единиц –kg, -lb, -шт	\N	2025-10-14 08:03:45.676447
119	33	3	\N	Источник питания	HY1505D	476816	\N		\N	Выходное напряжение: 0~15V точность установки 0.1V\r\n<br>Выходной ток: 0~5A, точность установки 0.01A\r\n<br>Малый уровень пульсаций: ≤ 0.5mV\r\n<br>Малое влияние нагрузки: ≤ 0.01% ±3mV\r\n<br>Малое влияние сетевого напряжения: ≤ 0.01% ±2mV\r\n<br>Режимы стабилизации тока и напряжения\r\n<br>Индикация: 3-разрядные LED-дисплеи на ток и напряжение, <br>\r\nточность: напряжение: ±1%, ток: ±2%\r\n<br>Защита от короткого замыкания\r<br>\nГабариты: 206х153х110 (мм), вес 3.6 кг\r\n<br>Питание: 110/220V ±10%	\N	2025-10-14 08:03:45.676447
120	34	3	\N	Векторный анализатор спектра	VSA6G2	CN63800600	\N		\N	100 Гц - 6.2ГГц с динамическим диапазоном измерения (-140 дБм), \r\n<br>максимальная входная мощность более + 30 дБм (1 Вт)	\N	2025-10-14 08:03:45.676447
125	39	3	\N	Анализатор спектра <br>портативный 	ARINST SSA R3	2536	\N		\N	Диапазон частот 24 МГц - 12 ГГц\r\n<br>Динамический диапазон 80 дБ\r\n<br>Демодуляция ШЧМ/ЧМ/АМ\r\n<br>Скорость сканирования до 20 ГГц/с\r\n<br>Разрешение по частоте 2,5 кГц	\N	2025-10-14 08:03:45.676447
127	41	3	\N	Усилитель мощности	Arinst KPAM-3000	52420236	\N	БП-000067 (ОС ФСИ эт.1)	\N	Диапазон частот 200-3000 МГц\r<br>\nКоэффициент усиления 42 дБ\r\n<br>Встроенный Li-ion аккумулятор	\N	2025-10-14 08:03:45.676447
149	63	3	\N	Mechanical Phase Shifter	QMPS60-8-S-A	24225063	\N		\N	\n60°/GHz, Manual Phase Shifter from DC to 8 GHz	\N	2025-10-14 08:03:45.676447
150	64	3	\N	Mechanical Phase Shifter	QMPS20-18-SSF	21095023	\N		\N	0°/GHz, Manual Phase Shifter from DC to 18 GHz	\N	2025-10-14 08:03:45.676447
151	65	3	\N	Manual Phase Shifters	QMPS10-26,5-SSF		\N		\N	10.2°/GHz, DC~26.5GHz	\N	2025-10-14 08:03:45.676447
152	66	3	\N	Штангенциркуль			\N		\N	Штангенциркуль на участке обработки материалов, \n150мм	\N	2025-10-14 08:03:45.676447
153	67	3	\N	Штангенциркуль			\N		\N	Штангенциркуль на участке обработки материалов, \n150 мм	\N	2025-10-14 08:03:45.676447
154	68	3	\N	Штангенциркуль			\N		\N	Штангенциркуль на складе, \n150 мм	\N	2025-10-14 08:03:45.676447
161	75	3	\N	Микроскоп	Микромед<br>МС-4-ZOOM	018290	\N		\N	Микроскоп для визуального контроля (в чистой зоне).\r\n<br>Стереоскопический микроскоп МИКРОМЕД МС-4-ZOOM LED предназначен для наблюдения как объемных, <br>так и тонких пленочных и прозрачных объектов,	\N	2025-10-14 08:03:45.676447
156	70	3	\N	Микрометр	Mitutoyo<br>M120-25	66925001	\N		\N	Микрометр на участке обработки материалов\r\n<br>Материал: металл\r\n<br>Точность: 0,001 мм\r\n<br>Диапазон: 0-25 мм	\N	2025-10-14 08:03:45.676447
166	80	3	\N	Микроскоп	МБС-10		\N		\N	Старый микроскоп для визуального контроля.	\N	2025-10-14 08:03:45.676447
167	81	3	\N	Граммометр			\N		\N	Граммометр 5-60 гр. 1986г.	\N	2025-10-14 08:03:45.676447
155	69	3	\N	Микрометр	OUTAD ZK256500		\N		\N	Микрометр на участке обработки материалов<br>\r\nМатериал: металл\r<br>\nТочность: 0,01 мм\r\n<br>Диапазон: 0-25 мм\r\n<br>Размер: 140x65x25мм	\N	2025-10-14 08:03:45.676447
158	72	3	\N	Набор измерительных щупов	Gigant  GGS-17		\N		\N	Участок обработки материалов\r\n<br>Набор измерительных щупов Gigant 17 шт., 0,02-1,00 мм <br>GGS-17 - это набор измерительных пластин разной толщины в металлическом корпусе. <br>Плоские измерительные щупы применяются для <br>контроля зазоров между плоскостями. 	\N	2025-10-14 08:03:45.676447
159	73	3	\N	Токовые клещи	СЕМ DT-3361	170403311	\N		\N	Участок обработки материалов.\r\n<br>Токовые клещи СЕМ DT-3361 481936 <br>оснащается контрастным ЖК-экраном с подсветкой для удобного считывания показаний. <br>Сфера применения модели - измерение параметров электросети - напряжения, <br>силы переменного тока, сопротивления, емкости, частоты, <br>а так же проведение диод-тестов и прозвонка цепи.	\N	2025-10-14 08:03:45.676447
157	71	3	\N	Рычажно-зубчатый индикатор	Mitutoyo<br>513-425-10E	ADKX47	\N		\N	Участок обработки материалов\r\n<br>Индикатор 0-0,6мм 0,002 <br>рычажный горизонтальный	\N	2025-10-14 08:03:45.676447
168	82	3	\N	Граммометр	Mitutoyo 546-134	333838	\N		\N	30-300 мН. <br>Пружинный граммометр Mitutoyo 546-134. <br>Особенности и преимущества <br>Для регулировки микропереключателей, пружин и клапанов реле <br>Для проверки измерительного усилия измерительных головок <br>Для регулировки пружин на сжатие и растяжение	\N	2025-10-14 08:03:45.676447
165	79	3	\N	Микроскоп с тринокулярной головкой <br>с цифровой камерой			\N		\N	Микроскоп для визуального контроля (в чистой зоне).	\N	2025-10-14 08:03:45.676447
164	78	3	\N	Микроскоп цифровой	Levenhuk Discovery<br>Artisan		\N		\N	Цифровой микроскоп Levenhuk Discovery Artisan <br>с профессиональным штативом и программой для фотографирования, <br>видеозаписи и измерений объектов станет отличным помощником человеку, <br>который занимается ремонтом техники, оценкой качества металлов, <br>заточкой ножей, реставрацией предметов искусства, <br>ювелирным делом или другими прикладными работами.	\N	2025-10-14 08:03:45.676447
169	83	3	\N	Граммометр	Jonard GD-10		\N		\N	10-100 гр.	\N	2025-10-14 08:03:45.676447
181	95	3	\N	Мультиметр цифровой	UNI-T UT121B	C23040441	\N		\N	Мультиметр (в производственной зоне)	\N	2025-10-14 08:03:45.676447
182	96	3	\N	Мультиметр цифровой	DUWI M830L		\N		\N	Мультиметр (в производственной зоне)	\N	2025-10-14 08:03:45.676447
183	97	3	\N	Мультиметр цифровой	МЕГЕОН MY-64	2316316045	\N		\N	Мультиметр (в производственной зоне)	\N	2025-10-14 08:03:45.676447
186	100	3	\N	Термометр контактный	Center 520	230105935	\N		\N	Диапазон измерения: -200°С — +1370°С\n Погрешность: ±0,1°C	\N	2025-10-14 08:03:45.676447
175	89	3	\N	Микроскоп	Микромед<br>МС-4-ZOOM	018289	\N		\N	Микроскоп для визуального контроля (в производственной зоне).\r\n<br>Стереоскопический микроскоп МИКРОМЕД МС-4-ZOOM LED предназначен для наблюдения как объемных, <br>так и тонких пленочных и прозрачных объектов,	\N	2025-10-14 08:03:45.676447
176	90	3	\N	Микроскоп	Микромед<br>МС-4-ZOOM	018288	\N		\N	Микроскоп для визуального контроля (в производственной зоне).\r\n<br>Стереоскопический микроскоп МИКРОМЕД МС-4-ZOOM LED предназначен для наблюдения как объемных, <br>так и тонких пленочных и прозрачных объектов,	\N	2025-10-14 08:03:45.676447
170	84	3	\N	Мультиметр	MASTECH MS8239C		\N		\N	Мультиметр MASTECH MS8239C 13-2020 <br>предназначен для измерения постоянного и переменного напряжение, <br>а также постоянного и переменного тока, <br>сопротивления в цепи, емкости, частоты и даже температуры. 	\N	2025-10-14 08:03:45.676447
173	87	3	\N	Микроскоп с тринокулярной головкой <br>с цифровой камерой			\N		\N	Микроскоп для визуального контроля (в производственной зоне).	\N	2025-10-14 08:03:45.676447
178	92	3	\N	Портативный анализатор спектра <br>с трекинг-генератором	Arinst SSA-TG R2s	2052	\N		\N		\N	2025-10-14 08:03:45.676447
179	93	3	\N	Портативный анализатор спектра <br>с трекинг-генератором	Arinst SSA-TG R2		\N	БП-000067 ОС ФСИ эт.1	\N	Анализатор для контроля парамеров изделий в производственной зоне.\n	\N	2025-10-14 08:03:45.676447
184	98	3	\N	Цифровой мультиметр-пинцет <br>для SMD компонентов	UNI-T UT116C	C220395661	\N		\N	Мультиметр (в производственной зоне)	\N	2025-10-14 08:03:45.676447
185	99	3	\N	Генератор сигналов <br>произвольной и специальной формы	DG912 Pro	DG9Q262100176	\N		\N	150 МГц, 2 канала 	\N	2025-10-14 08:03:45.676447
187	101	3	\N	Электронная нагрузка <br>с интерфейсами lan/digital io RIGOL 	DL3021A	DL3B252200379	\N		\N		\N	2025-10-14 08:03:45.676447
177	91	3	\N	Анализатор цепей <br>векторный	Обзор-TR1300/1	0260913	\N		\N	Анализатор для контроля параметров изделий в производственной зоне	\N	2025-10-14 08:03:45.676447
180	94	3	\N	Портативный генератор <br>синусоидального сигнала	ARINST ArSiG-S		\N	БП-000067 ОС ФСИ эт.1	\N	Генератор сигнала для контроля парамеров изделий в производственной зоне.\n	\N	2025-10-14 08:03:45.676447
172	86	3	\N	Установка для автоматизированного <br>контроля параметров микросхем	Иволга		\N		\N	Установка для контроля микросхем	\N	2025-10-14 08:03:45.676447
85	1	2	\N	Климатическая камера	Climcontrol ШС<br>30/250-100-П Standard	2724/М-24/МО	\N		2024-01-11	+30…+250 C\n100л	\N	2025-10-14 08:03:45.676447
171	85	3	\N	Микроскоп	Микромед<br>МС-4-ZOOM	012096	\N		\N	Микроскоп для визуального контроля (в чистой зоне).<br>\r\nСтереоскопический микроскоп МИКРОМЕД МС-4-ZOOM LED <br>предназначен для наблюдения как объемных, <br>так и тонких пленочных и прозрачных объектов,	\N	2025-10-14 08:03:45.676447
174	88	3	\N	Микроскоп	Микромед<br>МС-4-ZOOM		\N		\N	Микроскоп для визуального контроля (в производственной зоне).\r\n<br>Стереоскопический микроскоп МИКРОМЕД МС-4-ZOOM LED <br>предназначен для наблюдения как объемных, так и тонких пленочных и прозрачных объектов,	\N	2025-10-14 08:03:45.676447
162	76	3	\N	Металлографический микроскоп <br>с цифровой камерой	Микроскоп:<br>МЕТАМ РН-41,<br>Камера:<br>MC-3	Камера № XC1469	\N		\N	Микроскоп для контроля кристаллов.\r\n<br>Металлографический микроскоп МЕТАМ РН-41 предназначен для визуального наблюдения <br>микроструктуры непрозрачных объектов в отраженном свете при прямом освещении в светлом и темном поле, <br>а также для исследования объектов в поляризованном свете.	\N	2025-10-14 08:03:45.676447
92	6	3	\N	Комплект коаксиальных аттенюаторов	11582A	61383	\N		\N	Набор из четырех аттенюаторов 8491B<br>(3, 6, 10 и 20 дБ) (90764) с разъемами type-N<br>идеально подходит для калибровочных лабораторий.	\N	2025-10-14 08:03:45.676447
107	21	3	\N	Источник питания	HY1505D	476814	\N		\N	Выходное напряжение: 0~15V точность установки 0.1V\r\n<br>Выходной ток: 0~5A, точность установки 0.01A\r\n<br>точность: напряжение: ±1%, ток: ±2%\r<br>\nЗащита от короткого замыкания\r\n<br>Габариты: 206х153х110 (мм), вес 3.6 кг<br>\r\nПитание: 110/220V ±10%	\N	2025-10-14 08:03:45.676447
163	77	3	\N	Телецентрический микроскоп <br>с цифровой камерой 	Камера:<br>E3ISPM12000KPA	Камера № 1904170201	\N		\N	Телецентрические объективы применяются в измерительных микроскопах <br>и системах машинного зрения, поскольку такие объективы имеют параллельный ход пучков, <br>а увеличение не зависит от расстояния между объективом и измеряемым предметом. <br>Полученное изображение с телецентрического объектива схоже <br>с проекцией на чертеже и идеально подходит для анализа и измерений.	\N	2025-10-14 08:03:45.676447
124	38	3	\N	Панорамный детектор электромагнитного поля <br>со встроенной антенной и демодулятором	ARINST SFM 3	2467	\N		\N	Диапазон частот 23 МГц - 6.2 ГГц\r\n<br>Динамический диапазон 80 дБ\r\n<br>Встроенная поисковая антенна\r\n<br>Одновременное отображение до 4 диапазонов\r\n<br>Демодуляция ШЧМ/ЧМ/АМ\r\n<br>Скорость сканирования до 20 ГГц/с\r<br>\nРазрешение по частоте до 2.5 кГц	\N	2025-10-14 08:03:45.676447
128	42	3	\N	Источник питания <br>программируемый	DP932E	DP9A253800691	\N		\N	Цветной сенсорный дисплей 4,3 дюйма\r\n<br>3 независимых канала 32В/3А, 32В/3А, 6В/3А\r\n<br>Автоматическое объединение каналов последовательно или параллельно\r\n<br>Время обработки команд менее 1 О мс\r\n<br>Низкие выходные пульсации <350 мкВср.кв / 2 мВпик-пик\r\n<br>Минимальное время пребывания в точке 100мс\r\n<br>Защита от температуры, скачков тока напряжения	\N	2025-10-14 08:03:45.676447
70	70	1	18	Мультиметры цифровые	RD701	20125100407	\N	№БП-000064	\N	Мультиметр для конроля параметров изделий<br>в производственной зоне\r\nВТРМ-3 ПП109	2500.00	2025-10-14 08:03:45.676447
6	6	1	55	Гигрометры психрометрические	ВИТ-2	568	\N		\N	Гигрометр для контроля климатических условий<br>в производственной зоне.	\N	2025-10-14 08:03:45.676447
9	9	1	55	Гигрометры психрометрические	ВИТ-2	374	\N		\N	Гигрометр для контроля климатических условий<br>в складской зоне.	\N	2025-10-14 08:03:45.676447
112	26	3	\N	Анализатор цепей векторный<br>двухпортовый<br>портативный 	ARINST VNA-PR1		\N	БП-000064	\N	ВТРМ-3 ПП109\r\n<br>Диапазон частот 1-6200 МГц, <br>Измерение параметров S11 и S21\r\n2 измерительных порта, <br>Число точек сканирования 1000\r\n<br>Память на 32 предустановки и 32 трассы, <br>Опция компенсации электрической длины кабеля\r\n<br>Регулировка выходной мощности зондирующего сигнала\r\n<br>Сдвиг амплитудной шкалы при измерении АЧХ активных устройств и аттенюаторов\r\n<br>Встроенный аккумулятор на 5000 мАч	\N	2025-10-14 08:03:45.676447
160	74	3	\N	Цифровой микроскоп <br>(комплекс визуализации)	ЛОМО-Микросистемы<br>МС-AF	230820238	\N		\N	Микроскоп для визуального контроля (в чистой зоне).\r\n<br>Оптико-электронная система ультра высокого разрешения (Ultra HD 4K) <br>с выводом изображения на HDMI <br>ЖК дисплей 4K с увеличенным полем зрения. <br>Оснащена zoom-системой c электромеханическим управлением и автофокусировкой. <br>Позволяет производить линейные измерения, <br>запись фото-/видео изображения.\r\n<br>Целевое применение -микроэлектроника. <br>Макроскоп является безокулярной оптической системой, <br>имеет встроенный объектив с зум системой с электромеханическим управлением.	\N	2025-10-14 08:03:45.676447
81	81	1	30	Штангенциркули торговой марки "GRIFF" <br>с отсчетом по нониусу и <br>с цифровым отсчетным устройством	ШЦЦ-I-300-0,01	22010076	\N	БП-000070	\N	ВТРМ-4 ПП109	\N	2025-10-14 08:03:45.676447
34	34	1	19	Осциллографы модульные	U2702A	MY53242001	\N	00-000014	\N	(в комплекте Е3642А источник питания)	4750.00	2025-10-14 08:03:45.676447
40	40	1	25	Генераторы сигналов	Advantex SG8	47954-5051-003	\N	00-000015 или  00-000016	\N		10350.00	2025-10-14 08:03:45.676447
2	2	1	34	Анализаторы спектра	СК4М-18	1101170113	\N	00-000030	\N		24365.00	2025-10-14 08:03:45.676447
11	11	1	4	Мультиметры цифровые	Fluke 106	47080293WS	\N		\N	Мультиметр для проведения входного контроля	250.00	2025-10-14 08:03:45.676447
36	36	1	40	Анализаторы спектра портативные	Signal Hound<br>USB-SA44B	б/н	\N		\N		12000.00	2025-10-14 08:03:45.676447
57	57	1	9	Меры напряжения и тока	E3631A	MY55226290	\N	00-000019	\N		\N	2025-10-14 08:03:45.676447
8	8	1	31	Блоки измерительные ваттметров	N1912A	MY57340037	\N	00-000023	\N		14000.00	2025-10-14 08:03:45.676447
33	33	1	32	Установки для проверки параметров <br>электрической безопасности	GPT-79903	GEX171620	\N		\N	Установки для проверки параметров электрической<br>безопасности (пробои корпусов)	\N	2025-10-14 08:03:45.676447
20	20	1	33	Весы электронные лабораторные	HCB123	AE1230258	\N		\N		\N	2025-10-14 08:03:45.676447
15	15	1	35	Измерители сопротивления, <br>относительной влажности и температуры	VKG A-770	PG30-A2329	\N		\N	Средство контроля заземления в складской зоне	\N	2025-10-14 08:03:45.676447
46	46	1	36	Измерители RLC	U1732C	10149	\N		\N		\N	2025-10-14 08:03:45.676447
12	12	1	38	Весы лабораторные электронные <br>неавтоматического действия	ВЛТЭ	I01-024	\N		\N	Весы для проведения входного контроля	\N	2025-10-14 08:03:45.676447
\.


--
-- TOC entry 4839 (class 0 OID 65988)
-- Dependencies: 218
-- Data for Name: equipment_types; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.equipment_types (id, type_code, type_name) FROM stdin;
1	СИ	Средства измерений
2	ИО	Испытательное оборудование
3	ВО	Вспомогательное оборудование
\.


--
-- TOC entry 4841 (class 0 OID 65997)
-- Dependencies: 220
-- Data for Name: gosregister; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gosregister (id, gosregister_number, si_name, type_designation, manufacturer, web_url, created_at, updated_at, mpi) FROM stdin;
31	57386-14	Блоки измерительные ваттметров	N1912A	\tКомпания "Keysight Technologies Microwave Products (M) Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/0e5c6654-fb2e-90e9-fb53-042a8a7524ce	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
12	31045-06	Анализаторы спектра	R3465	Фирма "Advantest Co.", Япония	https://all-pribors.ru/opisanie/31045-06-advantest-r3465-30782?ysclid=mggio6a5gi425248621	2025-10-14 08:04:37.922889	2025-10-14 09:46:06.343392	1 год
28	55491-13	Источники питания постоянного тока<br>программируемые	DP832	Фирма "RIGOL Technologies, Inc.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/3932b2ea-8fd7-adbd-2b72-1218c5e17e84	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	2 года
3	54631-13	Источники питания	UT3005EP	\tФирма "Korad Technology Co., Ltd.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/87fd54b1-5828-2ebb-2f65-3262176f012a	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	2 года
1	19818-00	Частотомеры универсальные	GFC-8270H	Фирма "Good Will Instrument Co., Ltd.", Тайвань	https://fgis.gost.ru/fundmetrology/cm/mits/26099442-7413-0cc3-c706-5a0cf8e89801	2025-10-14 08:04:37.922889	2025-10-14 10:51:52.890072	1 год
4	57587-14	Мультиметры цифровые	Fluke 106	Фирма "Fluke Corporation", США	https://fgis.gost.ru/fundmetrology/cm/mits/491a2e16-d2ac-a177-43c0-28027bbf1c40	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
10	26951-04	Меры напряжения и тока	E3642A	Фирма "Keysight Technologies Microwave Products (M) Sdn. Bhd."	https://fgis.gost.ru/fundmetrology/cm/mits/3a665ce0-ebe0-8076-228a-c1b1aa1cb1d6	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
11	29967-05	Генераторы сигналов специальной формы	SFG-2110	Фирма "Good Will Instrument Co., Ltd.", Тайвань	https://fgis.gost.ru/fundmetrology/cm/mits/8d3b61eb-e8d6-f24f-64d1-6c7e68a939fb	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
16	37008-08	Преобразователи измерительные	NRP-Z11	Фирма "Rohde & Schwarz GmbH & Co. KG", Германия	https://fgis.gost.ru/fundmetrology/cm/mits/d7311f32-3c34-9509-fb64-97a6ec62dfb6	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
17	38428-08	Вольтметры универсальные цифровые	GDM-78251A	Фирма "Good Will Instrument Co., Ltd.", Тайвань.	https://fgis.gost.ru/fundmetrology/cm/mits/cf656026-95f1-742d-2b99-cdead0f41203	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
18	44402-10	Мультиметры цифровые	RD701	Фирма "Sanwa Electric Instrument Co., Ltd.", Япония	https://fgis.gost.ru/fundmetrology/cm/mits/16211fd4-debc-e3d0-42b1-1ad32e5b9cfa	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
19	45328-10	Осциллографы модульные	U2702A	Фирма "Keysight Technologies Microwave Products (M) Sdn. Bhd.", Малайзия;	https://fgis.gost.ru/fundmetrology/cm/mits/6b81a97f-5af3-d423-34fe-7c40c59a636c	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
21	48469-11	Осциллографы цифровые	MSO5104	Фирма "Tektronix (China) Co. Ltd.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/6262d33b-1545-0690-27cd-6a15eeec09f6	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
22	48998-12	Осциллографы цифровые	DSO-X 3032A	Фирма "Keysight Technologies Microwave Products (M) Sdn. Bhd.", Малайзия;	https://fgis.gost.ru/fundmetrology/cm/mits/b8266a02-ba48-a545-05f4-fb210fc0518e	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
23	49916-12	Источники питания программируемые	PWS4323	Компания "Tektronix (China) Co., Ltd.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/35be6a44-8ef6-3aaa-d940-20a90522eafa	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
24	50593-12	Микрометр	МК-25 0.01	ООО НПП "Челябинский инструментальный завод",<br>г. Челябинск	https://fgis.gost.ru/fundmetrology/cm/mits/d9a0dd2d-b809-374d-e902-d3b4fb8ac551	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
33	60181-15	Весы электронные лабораторные	HCB123	Фирма "Adam Equipment Co. Ltd.", Великобритания	https://fgis.gost.ru/fundmetrology/cm/mits/9833acd1-dcdf-22ce-ec74-fc433e3301c0	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
32	58755-14	Установки для проверки параметров электрической безопасности	GPT-79903	Фирма "Good Will Instrument Co., Ltd.", Тайвань	https://fgis.gost.ru/fundmetrology/cm/mits/b653cf8e-f9ba-4197-fc9d-d01d5df724ab	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	2 года
30	56450-14	Штангенциркули торговой марки "GRIFF"<br>с отсчетом по нониусу и с цифровым отсчетным устройством	ШЦЦ-I-300-0,01	Фирма "Guilin Measuring & Cutting Tool Co. Ltd.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/26790058-3ebd-05bf-ee51-da8fb1b4871f	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
25	52071-12	Генераторы сигналов	Advantex SG8	ООО "АДВАНТЕХ", г.Москва	https://fgis.gost.ru/fundmetrology/cm/mits/14d4a883-6204-5a63-1f45-8116b2849a1d	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
29	55499-13	Генераторы сигналов	HMC-T2000	Фирма "Hittite Microwave Corporation", США	https://fgis.gost.ru/fundmetrology/cm/mits/9a1bc845-3f93-9f8b-6d68-6838c4e19c60	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
5	59778-15	Мультиметры цифровые	Fluke 17B+	Фирма "Fluke Corporation", США	https://fgis.gost.ru/fundmetrology/cm/mits/f0146782-255b-920f-2a79-6dcfc0d06de3	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
7	75676-19	Источники питания постоянного тока	АКИП-1118	Фирма "Iтесн Electronic Со., Ltd.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/231a3daf-e3ae-bbd0-d554-6ab72c2c31c4	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
35	61553-15	Измерители сопротивления,<br>относительной влажности и температуры	VKG A-770	ООО «Профигрупп» (ООО «Профигрупп»),<br>г. Санкт-Петербург	https://fgis.gost.ru/fundmetrology/cm/mits/35b52190-6bd9-21ba-34a0-91addd41a798	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
36	65890-16	Измерители RLC	U1732C	Компания "Keysight Technologies Products (M) Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/b19bc151-23d4-9b3f-122c-01a247bda7fd	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
52	91177-24	Штангенциркули	NCR-1502	ООО "Норгау Руссланд"<br>(ООО "Норгау Руссланд"), г. Москва.	https://fgis.gost.ru/fundmetrology/cm/mits/791a0530-d526-534a-cd05-723d306c62ae	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
2	52059-12	Штангенглубиномеры	ШГЦ 150мм	ООО НПП "Челябинский инструментальный завод",<br>г. Челябинск	https://fgis.gost.ru/fundmetrology/cm/mits/96739542-2a8a-c7f3-4a4b-463a827e04fc	2025-10-14 08:04:37.922889	2025-10-14 09:46:06.343392	1 год
6	72915-18	Генераторы сигналов произвольной формы	33510B	Компания "Keysight Technologies Malaysia Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/d7650372-d311-7e0e-13f6-ac8b1b2db00e	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	2 года
8	22128-07	Измерители температуры электронные	Сenter 303	Фирма "CENTER Technology Corp.", Тайвань	https://fgis.gost.ru/fundmetrology/cm/mits/f45954a3-d4c3-5234-b804-a88cb798f461	2025-10-14 08:04:37.922889	2025-10-14 10:52:06.335629	1 год
9	26950-04	Меры напряжения и тока	E3632A	Фирма "Keysight Technologies Microwave Products (M) Sdn. Bhd."	https://fgis.gost.ru/fundmetrology/cm/mits/3f947d07-0e2c-ae29-63c2-e5dd6d712adb	2025-10-14 08:04:37.922889	2025-10-14 10:52:19.360474	1 год
55	9364-08	Гигрометры психрометрические	ВИТ-2	\tАкционерное общество «ТЕРМОПРИБОР»<br>(АО «ТЕРМОПРИБОР»), Московская обл., г. Клин	https://fgis.gost.ru/fundmetrology/cm/mits/3c4b9428-b05e-c1c0-b324-7eca0c217bf8	2025-10-14 08:04:37.922889	2025-10-14 09:46:06.343392	2 года
42	72879-18	Мультиметры цифровые	34461A	Компания "Keysight Technologies Malaysia Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/fdffd4e3-66a8-cd0f-d44a-97a799463511	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
41	72189-18	Штангенциркули	ШЦ, ШЦК, ШЦЦ\n(ШЦК-I-150-0,01)	ООО НПП "Челябинский инструментальный завод"<br>(ООО НПП "ЧИЗ"), г. Челябинск	https://fgis.gost.ru/fundmetrology/cm/mits/119676b7-7622-92c6-8444-9d2076148385	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
44	75840-19	Анализаторы цепей векторные	ZNA43	Фирма "Rohde & Schwarz GmbH & Co. KG", Германия	https://fgis.gost.ru/fundmetrology/cm/mits/4f3c3bbd-09d1-7318-c535-49dc5c8d8cfa	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
45	76369-19	Преобразователи измерительные ваттметров поглощаемой мощности	N1922A	Компания "Keysight Technologies Malaysia Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/cb8c2bd8-696e-d802-59b4-915edcc640e5	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
47	79042-20	Ваттметры поглощаемой мощности	PLS26-13M	АО "НПФ "МИКРАН", г.Томск	https://fgis.gost.ru/fundmetrology/cm/mits/98ad1ae0-7cdf-f8c7-efdd-02e01a212da9	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
48	79635-20	Генераторы сигналов	N5183B	Компания "Technologies Malaysia Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/f2456322-b90c-daec-8cb9-90a650c3607a	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
49	80307-20	Термогигрометры	RGK моделей ТН-10, ТН-12	Фирма "UNI TREND TECHNOLOGY (CHINA) CO., LTD", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/8cd9dd30-910c-170b-8087-488fe59a6cb0	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
50	80595-20	Генераторы сигналов	PLG20-12F	АО "Научно-производственная фирма "МИКРАН"<br>(АО "НПФ "МИКРАН"), г. Томск	https://fgis.gost.ru/fundmetrology/cm/mits/c4c1ba46-f5a5-2424-9c49-6c3b78ce43b8	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
60	42593-09	Анализаторы спектра	R&S FSV3/7/13/30/40	Фирма "Rohde & Schwarz GmbH & Co. KG", Германия	https://fgis.gost.ru/fundmetrology/cm/mits/cde2d951-222d-8be8-3f2c-d76ffa7c4186	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
43	72922-18	Осциллографы цифровые	MSOX3102A	Компания "Keysight Technologies Malaysia Sdn. Bhd.", Малайзия	https://fgis.gost.ru/fundmetrology/cm/mits/5f00ad50-0d36-9661-e311-c368ab76817d	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	2 года
62	93757-24	Блоки питания импульсные	MAISHENG MP	Dongguan Maihao Electronic Technology Co., Ltd., Китай	https://fgis.gost.ru/fundmetrology/cm/mits/e3175bd6-eca4-94e3-728a-4a62a5643c63	2025-10-14 12:30:27.592538	2025-10-14 12:30:27.592538	1 год
46	78610-20	Камеры тепловизионные стационарные	PI, Xi	Фирма "Optris GmbH", Германия	https://fgis.gost.ru/fundmetrology/cm/mits/9d579ae7-9957-bbe7-93e2-1aac5d9d0b5b	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
13	32050-06	Источники питания	MPS-3003S	Фирма "Matrix Technology Inc.", Китай.	https://fgis.gost.ru/fundmetrology/cm/mits/64d9a06e-b1ce-f0d8-3956-beec7d6a42b4	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
14	35423-07	Системный источник питания	6653A	Фирма "Agilent Technologies Inc.", США	https://fgis.gost.ru/fundmetrology/cm/mits/dcdaa798-528d-ff66-4c9f-73e39e90d52d	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
37	68540-17	Анализаторы фазовых шумов	PNA20	Компания "Anapico Ltd.", Швейцария	https://fgis.gost.ru/fundmetrology/cm/mits/021d792e-ba57-a9f8-0aa7-c5a5236eadc4	2025-10-14 08:04:37.922889	2025-10-14 09:46:06.343392	2 года
20	47185-11	Анализаторы цепей векторные	Р4М-18	АО "НПФ "МИКРАН", г.Томск	https://fgis.gost.ru/fundmetrology/cm/mits/fe2c771e-53c7-cb0d-6d13-3c9d25e76c6e	2025-10-14 08:04:37.922889	2025-10-14 09:46:06.343392	1 год
34	60404-15	Анализаторы спектра	СК4М-18	АО "НПФ "МИКРАН", г.Томск	https://fgis.gost.ru/fundmetrology/cm/mits/ec917faf-40a2-9516-89fd-7c5ba047d890	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
15	36974-08	Измерители мощности СВЧ	М3М-18	АО «Научно-производственная фирма «МИКРАН»<br>(АО «НПФ «МИКРАН»), г. Томск	https://fgis.gost.ru/fundmetrology/cm/mits/2426a998-eaed-db71-5c83-ced2ff0b9ae0	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
26	52705-13	Генератор шума	ГШМ2-20А-13	АО «Научно-производственная фирма «МИКРАН»<br>(АО «НПФ «МИКРАН»), г. Томск	https://fgis.gost.ru/fundmetrology/cm/mits/2bd5912d-32a1-a243-1619-1f7c8033df3d	2025-10-14 08:04:37.922889	2025-10-14 09:46:06.343392	1 год
39	70557-18	Штангенциркули торговой марки "Micron"	Нет данных	Фирма "MICRONTOOLS S.P.O.", Чехия	https://fgis.gost.ru/fundmetrology/cm/mits/7f007b7d-631d-bebf-ba41-caea7061ae6f	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
40	71344-18	Анализаторы спектра портативные	Signal Hound USB-SA44B	Компания "Signal Hound, Inc.", США	https://fgis.gost.ru/fundmetrology/cm/mits/beba293b-ae52-fa06-82f6-c7bdd97eed22	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
53	91351-24	Тепловизоры инфракрасные	Guide H3	Фирма "Wuhan Guide Sensmart Tech Co., Ltd.", Китай	https://fgis.gost.ru/fundmetrology/cm/mits/81970826-8792-78a8-4631-a8f1751db7e6	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
54	91448-24	Источники питания постоянного тока<br>программируемые	DP832A	\tКомпания Rigol Technologies Co., Ltd, Китай	https://fgis.gost.ru/fundmetrology/cm/mits/3a486912-058c-213e-08ef-32ad7ad0e326	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
51	87757-22	Приборы для измерений текстуры поверхности,<br>отклонения от формы дуги окружности,<br>прямолинейности и радиуса дуги средней линии<br>по методу наименьших квадратов	Form Talysurf	Taylor Hobson Ltd., Англия	https://fgis.gost.ru/fundmetrology/cm/mits/8e0f374f-e703-db40-ad92-267c55336c46	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	2 года
38	69452-17	Весы лабораторные электронные<br>неавтоматического действия	ВЛТЭ	ООО «Научно-производственное предприятие Госметр»<br>(ООО «НПП Госметр»), г. Санкт-Петербург	https://fgis.gost.ru/fundmetrology/cm/mits/45dd3e43-75cd-0a94-b2cb-f89bd329683c	2025-10-14 08:04:37.922889	2025-10-14 10:20:11.619785	1 год
\.


--
-- TOC entry 4861 (class 0 OID 0)
-- Dependencies: 223
-- Name: calibration_certificates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.calibration_certificates_id_seq', 31, true);


--
-- TOC entry 4862 (class 0 OID 0)
-- Dependencies: 221
-- Name: equipment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.equipment_id_seq', 203, true);


--
-- TOC entry 4863 (class 0 OID 0)
-- Dependencies: 217
-- Name: equipment_types_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.equipment_types_id_seq', 3, true);


--
-- TOC entry 4864 (class 0 OID 0)
-- Dependencies: 219
-- Name: gosregister_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gosregister_id_seq', 62, true);


--
-- TOC entry 4685 (class 2606 OID 66040)
-- Name: calibration_certificates calibration_certificates_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calibration_certificates
    ADD CONSTRAINT calibration_certificates_pkey PRIMARY KEY (id);


--
-- TOC entry 4680 (class 2606 OID 66015)
-- Name: equipment equipment_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment
    ADD CONSTRAINT equipment_pkey PRIMARY KEY (id);


--
-- TOC entry 4672 (class 2606 OID 65993)
-- Name: equipment_types equipment_types_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment_types
    ADD CONSTRAINT equipment_types_pkey PRIMARY KEY (id);


--
-- TOC entry 4674 (class 2606 OID 65995)
-- Name: equipment_types equipment_types_type_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment_types
    ADD CONSTRAINT equipment_types_type_code_key UNIQUE (type_code);


--
-- TOC entry 4676 (class 2606 OID 66006)
-- Name: gosregister gosregister_gosregister_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gosregister
    ADD CONSTRAINT gosregister_gosregister_number_key UNIQUE (gosregister_number);


--
-- TOC entry 4678 (class 2606 OID 66004)
-- Name: gosregister gosregister_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gosregister
    ADD CONSTRAINT gosregister_pkey PRIMARY KEY (id);


--
-- TOC entry 4686 (class 1259 OID 66047)
-- Name: idx_calibration_certificates_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_calibration_certificates_date ON public.calibration_certificates USING btree (certificate_date);


--
-- TOC entry 4687 (class 1259 OID 66046)
-- Name: idx_calibration_certificates_equipment_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_calibration_certificates_equipment_id ON public.calibration_certificates USING btree (equipment_id);


--
-- TOC entry 4688 (class 1259 OID 74020)
-- Name: idx_calibration_certificates_next_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_calibration_certificates_next_date ON public.calibration_certificates USING btree (next_calibration_date);


--
-- TOC entry 4681 (class 1259 OID 66027)
-- Name: idx_equipment_gosregister_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_equipment_gosregister_id ON public.equipment USING btree (gosregister_id);


--
-- TOC entry 4682 (class 1259 OID 66028)
-- Name: idx_equipment_row_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_equipment_row_number ON public.equipment USING btree (row_number);


--
-- TOC entry 4683 (class 1259 OID 66026)
-- Name: idx_equipment_type_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_equipment_type_id ON public.equipment USING btree (equipment_type_id);


--
-- TOC entry 4692 (class 2620 OID 74021)
-- Name: calibration_certificates trigger_calculate_next_calibration_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_calculate_next_calibration_date BEFORE INSERT OR UPDATE ON public.calibration_certificates FOR EACH ROW EXECUTE FUNCTION public.calculate_next_calibration_date();


--
-- TOC entry 4691 (class 2606 OID 66041)
-- Name: calibration_certificates calibration_certificates_equipment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calibration_certificates
    ADD CONSTRAINT calibration_certificates_equipment_id_fkey FOREIGN KEY (equipment_id) REFERENCES public.equipment(id) ON DELETE CASCADE;


--
-- TOC entry 4689 (class 2606 OID 66016)
-- Name: equipment equipment_equipment_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment
    ADD CONSTRAINT equipment_equipment_type_id_fkey FOREIGN KEY (equipment_type_id) REFERENCES public.equipment_types(id);


--
-- TOC entry 4690 (class 2606 OID 66021)
-- Name: equipment equipment_gosregister_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.equipment
    ADD CONSTRAINT equipment_gosregister_id_fkey FOREIGN KEY (gosregister_id) REFERENCES public.gosregister(id);


-- Completed on 2025-12-08 08:58:50

--
-- PostgreSQL database dump complete
--

