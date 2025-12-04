import os
import logging
from typing import Optional, Dict, List, Any, cast
from datetime import date

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)

# Загружаем .env в следующем порядке:
# 1) Корень монорепозитория WSB_core/.env
# 2) Локальный WSB_portal/.env (может переопределять при разработке)
base_dir = Path(__file__).resolve().parent.parent.parent  # WSB_core/WSB_portal
possible_paths = [
    base_dir.parent / ".env",  # WSB_core/.env
    base_dir / ".env",         # WSB_core/WSB_portal/.env
]

env_loaded = False
for env_path in possible_paths:
    if env_path.exists():
        load_dotenv(env_path, override=env_loaded is False)
        logger.info("Загружен .env из: %s", env_path)
        env_loaded = True

if not env_loaded:
    logger.info("Файлы .env рядом с WSB_portal не найдены, используются только переменные окружения.")


def _get_env(primary_key: str, fallback_key: Optional[str] = None, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(primary_key)
    if value is None and fallback_key:
        value = os.getenv(fallback_key)
    result = value if value is not None else default
    logger.debug("Env %s: %s (fallback: %s, default: %s) -> %s", primary_key, value, fallback_key, default, result)
    return result


# Настройки подключения к БД equipment (отдельная от RM)
# DB_NAME должен быть строго "equipment", остальные параметры могут использовать общие DB_*
EQUIPMENT_DB_USER = _get_env("EQUIPMENT_DB_USER", "DB_USER", "postgres")
EQUIPMENT_DB_PASSWORD = _get_env("EQUIPMENT_DB_PASSWORD", "DB_PASSWORD", "27915002")
EQUIPMENT_DB_NAME = _get_env("EQUIPMENT_DB_NAME", None, "equipment")  # Без fallback на DB_NAME (там "RM")
EQUIPMENT_DB_HOST = _get_env("EQUIPMENT_DB_HOST", "DB_HOST", "192.168.1.139")
EQUIPMENT_DB_PORT = _get_env("EQUIPMENT_DB_PORT", "DB_PORT", "5432")
EQUIPMENT_DB_SSLMODE = _get_env("EQUIPMENT_DB_SSLMODE", None, "prefer")

# Логируем настройки подключения (без пароля)
logger.info("Настройки БД equipment: host=%s, port=%s, dbname=%s, user=%s", 
            EQUIPMENT_DB_HOST, EQUIPMENT_DB_PORT, EQUIPMENT_DB_NAME, EQUIPMENT_DB_USER)


def _connect_equipment_db():
    """Создает подключение к базе данных equipment"""
    try:
        logger.info("Попытка подключения к БД equipment: %s@%s:%s/%s", 
                   EQUIPMENT_DB_USER, EQUIPMENT_DB_HOST, EQUIPMENT_DB_PORT, EQUIPMENT_DB_NAME)
        conn = psycopg.connect(
            dbname=EQUIPMENT_DB_NAME,
            user=EQUIPMENT_DB_USER,
            password=EQUIPMENT_DB_PASSWORD,
            host=EQUIPMENT_DB_HOST,
            port=EQUIPMENT_DB_PORT,
            sslmode=EQUIPMENT_DB_SSLMODE,
            connect_timeout=5,
            row_factory=dict_row,  # type: ignore[arg-type]
        )
        logger.info("Подключение к БД equipment успешно установлено")
        return conn
    except Exception as e:
        logger.error("Ошибка подключения к БД equipment: %s", e, exc_info=True)
        return None


def get_equipment_types() -> Dict[str, Any]:
    """Получить список типов оборудования"""
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM equipment_types ORDER BY id")
            types = cur.fetchall()
        conn.close()
        return {"data": [dict(row) for row in types]}
    except Exception as e:
        conn.close()
        logger.exception("Ошибка получения типов оборудования")
        return {"error": str(e)}


def get_gosregister() -> Dict[str, Any]:
    """Получить данные Госреестра"""
    # Пытаемся получить из кэша
    try:
        from .cache import get_si_module, set_si_module
        cached = get_si_module("gosregister")
        if cached:
            return {"data": cached}
    except Exception:
        pass
    
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, gosregister_number, si_name, type_designation, manufacturer, web_url
                FROM gosregister
                ORDER BY gosregister_number
                """
            )
            gosregister = cur.fetchall()
        conn.close()
        result = [dict(row) for row in gosregister]
        
        # Сохраняем в кэш
        try:
            from .cache import set_si_module
            set_si_module("gosregister", result)
        except Exception:
            pass
        
        return {"data": result}
    except Exception as e:
        conn.close()
        logger.exception("Ошибка получения Госреестра")
        return {"error": str(e)}


def get_equipment_by_type(equipment_type: str) -> Dict[str, Any]:
    """Получить оборудование по типу"""
    # Пытаемся получить из кэша
    try:
        from .cache import get_si_module, set_si_module
        cached = get_si_module(equipment_type.lower())
        if cached:
            return {"data": cached}
    except Exception:
        pass
    
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM equipment_types WHERE type_code = %s", (equipment_type,))
            type_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            if not type_row or "id" not in type_row:
                conn.close()
                return {"error": "Тип оборудования не найден"}

            type_id = type_row["id"]

            equipment_type_lower = equipment_type.lower()
            if equipment_type_lower == "си" or equipment_type_lower == "ио":
                order_clause = "ORDER BY cc.next_calibration_date DESC NULLS LAST, e.row_number"
            else:
                order_clause = "ORDER BY e.row_number"

            cur.execute(
                f"""
                SELECT 
                    e.id,
                    e.row_number,
                    e.name,
                    e.type_designation,
                    e.serial_number,
                    e.mpi,
                    e.note,
                    et.type_code,
                    et.type_name,
                    g.gosregister_number,
                    g.si_name AS gosregister_name,
                    g.web_url AS gosregister_url,
                    COALESCE(g.mpi, e.mpi) AS mpi_priority,
                    cc.certificate_number,
                    cc.certificate_date,
                    cc.next_calibration_date,
                    cc.calibration_cost,
                    cc.certificate_url,
                    (cc.next_calibration_date - CURRENT_DATE) AS days_until_calibration
                FROM equipment e
                JOIN equipment_types et ON e.equipment_type_id = et.id
                LEFT JOIN gosregister g ON e.gosregister_id = g.id
                LEFT JOIN LATERAL (
                    SELECT certificate_number,
                           certificate_date,
                           next_calibration_date,
                           calibration_cost,
                           certificate_url
                    FROM calibration_certificates cc
                    WHERE cc.equipment_id = e.id
                    ORDER BY cc.certificate_date DESC
                    LIMIT 1
                ) cc ON true
                WHERE e.equipment_type_id = %s
                {order_clause}
                """,
                (type_id,),
            )

            equipment = cur.fetchall()
        conn.close()
        result = [dict(row) for row in equipment]
        
        # Сохраняем в кэш
        try:
            from .cache import set_si_module
            set_si_module(equipment_type.lower(), result)
        except Exception:
            pass
        
        return {"data": result}
    except Exception as e:
        conn.close()
        logger.exception("Ошибка получения оборудования по типу")
        return {"error": str(e)}


def get_stats() -> Dict[str, Any]:
    """Получить статистику по оборудованию"""
    logger.info("Запрос статистики оборудования")
    conn = _connect_equipment_db()
    if not conn:
        logger.error("Не удалось подключиться к БД equipment для получения статистики")
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT et.type_code, COUNT(e.id) as count
                FROM equipment_types et
                LEFT JOIN equipment e ON et.id = e.equipment_type_id
                GROUP BY et.id, et.type_code
                ORDER BY et.id
            """)
            stats_query = cur.fetchall()

            stats: Dict[str, int] = {}
            for row in stats_query:
                row_dict = cast(Dict[str, Any], row)
                stats[f'{row_dict["type_code"].lower()}_count'] = int(row_dict["count"])

            cur.execute("SELECT COUNT(*) FROM equipment")
            total_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            stats["total_count"] = int(total_row["count"]) if total_row else 0

            cur.execute("SELECT COUNT(*) FROM gosregister")
            gosregister_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            stats["gosregister_count"] = int(gosregister_row["count"]) if gosregister_row else 0

        conn.close()
        return {"data": stats}
    except Exception as e:
        conn.close()
        logger.exception("Ошибка получения статистики")
        return {"error": str(e)}


def get_calibration_certificates(equipment_id: int) -> Dict[str, Any]:
    """Получить историю поверок/аттестаций оборудования"""
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM calibration_certificates 
                WHERE equipment_id = %s 
                ORDER BY certificate_date DESC
            """, (equipment_id,))
            certificates = cur.fetchall()
        conn.close()
        return {"data": [dict(row) for row in certificates]}
    except Exception as e:
        conn.close()
        logger.exception("Ошибка получения сертификатов")
        return {"error": str(e)}


def add_si_to_equipment(data: Dict[str, Any]) -> Dict[str, Any]:
    """Добавить СИ в список оборудования"""
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        required_fields = ['gosregister_id', 'type', 'serial_number']
        for field in required_fields:
            if not data.get(field):
                conn.close()
                return {"error": f"Поле {field} обязательно для заполнения"}

        with conn.cursor() as cur:
            # Получаем данные из Госреестра
            cur.execute("SELECT * FROM gosregister WHERE id = %s", (data['gosregister_id'],))
            gosregister_record = cast(Optional[Dict[str, Any]], cur.fetchone())

            if not gosregister_record:
                conn.close()
                return {"error": "Запись в Госреестре не найдена"}

            # Проверяем, не добавлено ли уже это СИ с таким серийным номером
            cur.execute("""
                SELECT id FROM equipment 
                WHERE equipment_type_id = (SELECT id FROM equipment_types WHERE type_name = 'Средства измерений')
                AND serial_number = %s 
                AND gosregister_id = %s
            """, (data['serial_number'], gosregister_record['id']))

            duplicate_row = cur.fetchone()
            if duplicate_row:
                conn.close()
                return {"error": "СИ с таким серийным номером уже добавлено"}

            # Добавляем новую запись в equipment
            cur.execute("""
                INSERT INTO equipment (
                    equipment_type_id, 
                    name, 
                    type_designation, 
                    serial_number, 
                    gosregister_id,
                    created_at
                ) VALUES (
                    (SELECT id FROM equipment_types WHERE type_name = 'Средства измерений'),
                    %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
                RETURNING id
            """, (
                gosregister_record['si_name'],
                data['type'],
                data['serial_number'],
                gosregister_record['id']
            ))

            equipment_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            if not equipment_row:
                conn.close()
                return {"error": "Не удалось создать запись оборудования"}

            equipment_id = equipment_row['id']

            # Если указан номер свидетельства о поверке, добавляем запись о поверке
            if data.get('certificate_number') or data.get('calibration_date'):
                cur.execute("""
                    INSERT INTO calibration_certificates (
                        equipment_id,
                        certificate_number,
                        certificate_date,
                        next_calibration_date,
                        created_at
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id
                """, (
                    equipment_id,
                    data.get('certificate_number'),
                    data.get('calibration_date'),
                    data.get('calibration_date')
                ))

        conn.commit()
        conn.close()
        
        # Инвалидация кэша модуля СИ
        try:
            from .cache import invalidate_si_module
            invalidate_si_module("си")
        except Exception:
            pass
        
        return {
            "message": f"СИ {data['type']} (№{data['serial_number']}) успешно добавлено в оборудование",
            "equipment_id": equipment_id
        }
    except Exception as e:
        conn.close()
        logger.exception("Ошибка добавления СИ")
        return {"error": f"Ошибка при добавлении СИ: {str(e)}"}


def add_io_to_equipment(data: Dict[str, Any]) -> Dict[str, Any]:
    """Добавить ИО в список оборудования"""
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        if not data.get('name'):
            conn.close()
            return {"error": "Наименование обязательно"}
        if not data.get('type'):
            conn.close()
            return {"error": "Обозначение типа обязательно"}
        if not data.get('serial_number'):
            conn.close()
            return {"error": "Заводской номер обязателен"}

        with conn.cursor() as cur:
            # Проверяем, не существует ли уже ИО с таким заводским номером
            cur.execute("""
                SELECT e.id FROM equipment e
                JOIN equipment_types et ON e.equipment_type_id = et.id
                WHERE et.type_name = 'Испытательное оборудование' 
                AND e.serial_number = %s
            """, (data['serial_number'],))

            existing_io = cur.fetchone()
            if existing_io:
                conn.close()
                return {"error": f"ИО с заводским номером {data['serial_number']} уже существует"}

            # Добавляем ИО в таблицу equipment
            cur.execute("""
                INSERT INTO equipment (
                    equipment_type_id,
                    name, 
                    type_designation, 
                    serial_number,
                    mpi,
                    note,
                    created_at
                ) VALUES (
                    (SELECT id FROM equipment_types WHERE type_name = 'Испытательное оборудование'),
                    %s, %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
                RETURNING id
            """, (
                data['name'],
                data['type'],
                data['serial_number'],
                data.get('mpi', '1 год'),
                data.get('note', '')
            ))

            equipment_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            if not equipment_row:
                conn.close()
                return {"error": "Не удалось создать запись ИО"}

            equipment_id = equipment_row['id']

            # Если указаны данные аттестата, добавляем их в calibration_certificates
            if data.get('certificate_number') and data.get('certificate_date'):
                mpi_text = data.get('mpi', '1 год')
                years = 2 if '2' in mpi_text else 1

                cur.execute("""
                    INSERT INTO calibration_certificates (
                        equipment_id,
                        certificate_number,
                        certificate_date,
                        next_calibration_date,
                        created_at
                    ) VALUES (
                        %s, %s, %s::DATE, 
                        %s::DATE + (%s || ' year')::INTERVAL - INTERVAL '1 day',
                        CURRENT_TIMESTAMP
                    )
                """, (
                    equipment_id,
                    data['certificate_number'],
                    data['certificate_date'],
                    data['certificate_date'],
                    years
                ))

        conn.commit()
        conn.close()
        
        # Инвалидация кэша модуля СИ
        try:
            from .cache import invalidate_si_module
            invalidate_si_module("ио")
        except Exception:
            pass
        
        return {
            "message": f"ИО {data['name']} (№{data['serial_number']}) успешно добавлено в оборудование",
            "equipment_id": equipment_id
        }
    except Exception as e:
        conn.close()
        logger.exception("Ошибка добавления ИО")
        return {"error": f"Ошибка при добавлении ИО: {str(e)}"}


def add_vo_to_equipment(data: Dict[str, Any]) -> Dict[str, Any]:
    """Добавить ВО в список оборудования"""
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        if not data.get('name'):
            conn.close()
            return {"error": "Наименование обязательно"}
        if not data.get('type'):
            conn.close()
            return {"error": "Тип оборудования обязателен"}
        if not data.get('serial_number'):
            conn.close()
            return {"error": "Заводской номер обязателен"}

        with conn.cursor() as cur:
            # Проверяем, не существует ли уже ВО с таким заводским номером
            cur.execute("""
                SELECT e.id FROM equipment e
                JOIN equipment_types et ON e.equipment_type_id = et.id
                WHERE et.type_name = 'Вспомогательное оборудование' 
                AND e.serial_number = %s
            """, (data['serial_number'],))

            existing_vo = cur.fetchone()
            if existing_vo:
                conn.close()
                return {"error": f"ВО с заводским номером {data['serial_number']} уже существует"}

            # Добавляем ВО в таблицу equipment
            cur.execute("""
                INSERT INTO equipment (
                    equipment_type_id, 
                    name, 
                    type_designation, 
                    serial_number,
                    note,
                    created_at
                ) VALUES (
                    (SELECT id FROM equipment_types WHERE type_name = 'Вспомогательное оборудование'),
                    %s, %s, %s, %s, CURRENT_TIMESTAMP
                )
                RETURNING id
            """, (
                data['name'],
                data['type'],
                data['serial_number'],
                data.get('note', '')
            ))

            equipment_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            if not equipment_row:
                conn.close()
                return {"error": "Не удалось создать запись ВО"}
            equipment_id = equipment_row['id']

        conn.commit()
        conn.close()
        
        # Инвалидация кэша модуля СИ
        try:
            from .cache import invalidate_si_module
            invalidate_si_module("во")
        except Exception:
            pass
        
        return {
            "message": f"ВО {data['name']} (№{data['serial_number']}) успешно добавлено в оборудование",
            "equipment_id": equipment_id
        }
    except Exception as e:
        conn.close()
        logger.exception("Ошибка добавления ВО")
        return {"error": f"Ошибка при добавлении ВО: {str(e)}"}


def add_gosregister(data: Dict[str, Any]) -> Dict[str, Any]:
    """Добавить запись в Госреестр"""
    conn = _connect_equipment_db()
    if not conn:
        return {"error": "Ошибка подключения к БД equipment"}

    try:
        if not data.get('gosregister_number'):
            conn.close()
            return {"error": "Номер в Госреестре обязателен"}
        if not data.get('si_name'):
            conn.close()
            return {"error": "Наименование СИ обязательно"}
        if not data.get('type_designation'):
            conn.close()
            return {"error": "Обозначение типа СИ обязательно"}

        with conn.cursor() as cur:
            # Проверяем, не существует ли уже запись с таким номером
            cur.execute("SELECT id FROM gosregister WHERE gosregister_number = %s", (data['gosregister_number'],))
            existing_gos = cur.fetchone()
            if existing_gos:
                conn.close()
                return {"error": f"Запись с номером {data['gosregister_number']} уже существует в Госреестре"}

            # Добавляем запись в Госреестр
            cur.execute("""
                INSERT INTO gosregister (
                    gosregister_number,
                    si_name,
                    type_designation,
                    manufacturer,
                    web_url,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                RETURNING id
            """, (
                data['gosregister_number'],
                data['si_name'],
                data['type_designation'],
                data.get('manufacturer', ''),
                data.get('web_url', '')
            ))

            gos_row = cast(Optional[Dict[str, Any]], cur.fetchone())
            if not gos_row:
                conn.close()
                return {"error": "Не удалось создать запись в Госреестре"}

            gosregister_id = gos_row['id']

        conn.commit()
        conn.close()
        
        # Инвалидация кэша модуля СИ
        try:
            from .cache import invalidate_si_module
            invalidate_si_module("gosregister")
        except Exception:
            pass
        
        return {
            "message": f"Запись {data['gosregister_number']} успешно добавлена в Госреестр",
            "gosregister_id": gosregister_id
        }
    except Exception as e:
        conn.close()
        logger.exception("Ошибка добавления в Госреестр")
        return {"error": f"Ошибка при добавлении в Госреестр: {str(e)}"}

