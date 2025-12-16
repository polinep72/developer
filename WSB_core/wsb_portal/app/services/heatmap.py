import os
import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Union

import numpy as np
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

def _get_env(primary: str, fallback: str | None = None, default: str | None = None) -> str | None:
    value = os.getenv(primary)
    if value:
        return value
    if fallback:
        value = os.getenv(fallback)
        if value:
            return value
    return default

DB_USER = _get_env("DB_USER", "POSTGRE_USER")
DB_PASSWORD = _get_env("DB_PASSWORD", "POSTGRE_PASSWORD")
DB_NAME = _get_env("DB_NAME", "POSTGRE_DBNAME", "RM")
DB_HOST = _get_env("DB_HOST", "POSTGRE_HOST", "localhost")
DB_PORT = _get_env("DB_PORT", "POSTGRE_PORT", "5432")
DB_SSLMODE = _get_env("DB_SSLMODE", None, "prefer")

# Сдвиг локального времени относительно UTC (в минутах), по умолчанию +3 часа (МСК)
LOCAL_TIME_OFFSET_MINUTES = int(os.getenv("LOCAL_TIME_OFFSET_MINUTES", "180"))

STATUS_CODES = {
    "free": 0,
    "booked_future": 1,
    "active_usage": 2,
    "finished_usage": 3,
}

STATUS_NAME_TO_COLOR = {
    "free": "rgb(255, 255, 255)",
    "booked_future": "rgb(173, 216, 230)",
    "active_usage": "rgb(50, 205, 50)",
    "finished_usage": "rgb(211, 211, 211)",
}

STATUS_NAME_TO_RUSSIAN = {
    "free": "Свободно",
    "booked_future": "Забронировано",
    "active_usage": "В работе",
    "finished_usage": "Завершено",
}

TIME_INTERVALS = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, 30)]


def _ensure_naive(dt_object: Optional[datetime]) -> Optional[datetime]:
    if dt_object is None:
        return None
    if dt_object.tzinfo is None or dt_object.tzinfo.utcoffset(dt_object) is None:
        return dt_object
    return dt_object.astimezone().replace(tzinfo=None)


def _connect():
    params = {
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "host": DB_HOST,
        "port": DB_PORT,
        "sslmode": DB_SSLMODE,
        "connect_timeout": 5,
        "row_factory": dict_row,
    }
    return psycopg.connect(**params)


def fetch_heatmap_data(target_date: date):
    logger.info("Запрос тепловой карты на %s", target_date.isoformat())
    if not DB_USER or not DB_HOST:
        logger.warning("DB_USER/DB_HOST не заданы, используется демо-режим тепловой карты.")
        return _demo_heatmap(target_date)

    conn = None
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name_equip FROM equipment ORDER BY name_equip ASC")
            equipment_rows = [dict(row) for row in cur.fetchall()]
        summary = {
            "active_bookings": 0,
            "total_bookings": 0,
            "free_slots": 0,
        }

        if not equipment_rows:
            return [], np.array([]), np.array([]), summary, None

        equipment_names = [row["name_equip"] for row in equipment_rows]
        equipment_map: Dict[int, Dict[str, Union[str, int]]] = {
            row["id"]: {"name": row["name_equip"], "idx": idx}
            for idx, row in enumerate(equipment_rows)
        }

        usage = np.full((len(equipment_names), len(TIME_INTERVALS)), STATUS_CODES["free"], dtype=int)
        hover = np.full((len(equipment_names), len(TIME_INTERVALS)), "", dtype=object)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.equip_id, b.time_start, b.time_end, b.finish, u.fi as user_fi
                FROM bookings b
                JOIN users u ON b.user_id = u.users_id
                WHERE b.date = %s AND b.cancel = FALSE
                """,
                (target_date,),
            )
            bookings = [dict(row) for row in cur.fetchall()]

        # Используем время с учётом локального сдвига относительно UTC,
        # чтобы статусы "Забронировано" / "В работе" корректно отражали реальное время.
        now_local = datetime.utcnow() + timedelta(minutes=LOCAL_TIME_OFFSET_MINUTES)
        if target_date < date.today():
            effective_now = datetime.combine(target_date, time(23, 59, 59))
        elif target_date > date.today():
            effective_now = datetime.combine(target_date, time(0, 0))
        else:
            effective_now = now_local

        summary["total_bookings"] = len(bookings)

        def _is_active_booking(start_dt, end_dt, finish_dt):
            if not (start_dt and end_dt):
                return False
            effective_end = finish_dt if finish_dt else end_dt
            return start_dt <= effective_now < effective_end and (finish_dt is None or finish_dt > effective_now)

        if target_date == date.today():
            summary["active_bookings"] = sum(
                1 for booking in bookings if _is_active_booking(
                    _ensure_naive(booking.get("time_start")),
                    _ensure_naive(booking.get("time_end")),
                    _ensure_naive(booking.get("finish")),
                )
            )
        else:
            summary["active_bookings"] = summary["total_bookings"]

        for booking in bookings:
            equip_id = booking.get("equip_id")
            if equip_id not in equipment_map:
                continue
            equip_idx = int(equipment_map[equip_id]["idx"])

            start = _ensure_naive(booking.get("time_start"))
            end = _ensure_naive(booking.get("time_end"))
            finish = _ensure_naive(booking.get("finish"))
            user_fi = booking.get("user_fi") or "Пользователь"

            if not (start and end):
                continue

            # Формируем человекочитаемый интервал сразу
            start_str = start.strftime("%H:%M")
            effective_end_dt = finish if finish else end
            end_str = effective_end_dt.strftime("%H:%M")

            for slot_idx, slot_label in enumerate(TIME_INTERVALS):
                slot_hour, slot_minute = map(int, slot_label.split(":"))
                slot_start = datetime.combine(target_date, time(slot_hour, slot_minute))
                slot_end = slot_start + timedelta(minutes=30)

                effective_end = effective_end_dt
                overlapping = start < slot_end and effective_end > slot_start
                if not overlapping:
                    continue

                status = STATUS_CODES["free"]
                hover_text = ""

                if finish and slot_start < finish and slot_start >= start:
                    status = STATUS_CODES["finished_usage"]
                    hover_text = f"Завершено: {user_fi}\n{start_str}–{end_str}"
                elif not finish:
                    if slot_start >= start and slot_start < end:
                        if effective_now >= end:
                            status = STATUS_CODES["finished_usage"]
                            hover_text = f"Завершено (по времени): {user_fi}\n{start_str}–{end_str}"
                        elif effective_now >= start:
                            status = STATUS_CODES["active_usage"]
                            hover_text = f"Используется: {user_fi}\n{start_str}–{end_str}"
                        else:
                            status = STATUS_CODES["booked_future"]
                            hover_text = f"Забронировано: {user_fi}\n{start_str}–{end_str}"
                    elif slot_start < end and slot_end > start and effective_now < start:
                        status = STATUS_CODES["booked_future"]
                        hover_text = f"Забронировано: {user_fi}\n{start_str}–{end_str}"

                if status != STATUS_CODES["free"]:
                    if usage[equip_idx][slot_idx] == STATUS_CODES["free"] or status > usage[equip_idx][slot_idx]:
                        usage[equip_idx][slot_idx] = status
                        hover[equip_idx][slot_idx] = hover_text

        for r in range(len(equipment_names)):
            for c in range(len(TIME_INTERVALS)):
                if usage[r][c] == STATUS_CODES["free"]:
                    hover[r][c] = hover[r][c] or STATUS_NAME_TO_RUSSIAN["free"]

        summary["free_slots"] = int(np.sum(usage == STATUS_CODES["free"]))

        return equipment_names, usage, hover, summary, None
    except psycopg.OperationalError as err:
        logger.error("Ошибка подключения к БД RM: %s", err)
        return None, None, None, None, f"Ошибка подключения к БД RM: {err}"
    except Exception as exc:
        logger.exception("Неожиданная ошибка получения тепловой карты")
        return None, None, None, None, f"Неожиданная ошибка: {exc}"
    finally:
        if conn:
            conn.close()


def _demo_heatmap(target_date: date):
    equipment = ["Осциллограф #1", "Генератор #2", "Лабораторное место #3"]
    usage = np.zeros((len(equipment), len(TIME_INTERVALS)), dtype=int)
    hover = np.full((len(equipment), len(TIME_INTERVALS)), STATUS_NAME_TO_RUSSIAN["free"], dtype=object)

    for idx in range(len(equipment)):
        for slot in range(idx * 2, idx * 2 + 6):
            col = slot % len(TIME_INTERVALS)
            usage[idx][col] = STATUS_CODES["booked_future"]
            hover[idx][col] = f"Забронировано: DEMO {idx+1}"

    summary = {
        "active_bookings": len(equipment),
        "total_bookings": len(equipment),
        "free_slots": int(np.sum(usage == STATUS_CODES["free"])),
    }

    return equipment, usage, hover, summary, None


def build_heatmap_figure(equipment_names, usage_matrix, hover_matrix, target_date: date):
    import plotly.graph_objects as go

    figure = go.Figure()
    if not equipment_names:
        figure.add_annotation(text="Нет оборудования для отображения", xref="paper", yref="paper", showarrow=False)
        return figure

    unique_codes = sorted(set(STATUS_CODES.values()))
    code_to_name = {v: k for k, v in STATUS_CODES.items()}
    colorscale = []
    if unique_codes:
        count = len(unique_codes)
        for idx, code in enumerate(unique_codes):
            name = code_to_name.get(code, "free")
            color = STATUS_NAME_TO_COLOR.get(name, "grey")
            start = idx / count
            end = (idx + 1) / count
            colorscale.append([start, color])
            colorscale.append([end, color])

    heatmap = go.Heatmap(
        z=usage_matrix,
        x=TIME_INTERVALS,
        y=equipment_names,
        colorscale=colorscale or "Greys",
        hoverinfo="text",
        hovertext=hover_matrix,
        showscale=True,
        zmin=min(STATUS_CODES.values()),
        zmax=max(STATUS_CODES.values()),
        xgap=1,
        ygap=1,
        colorbar=dict(
            title="Состояние",
            lenmode="pixels",
            len=max(150, len(unique_codes) * 35 + 40),
            tickvals=sorted(STATUS_CODES.values()),
            ticktext=[STATUS_NAME_TO_RUSSIAN.get(code_to_name.get(code, "free"), "Свободно") for code in sorted(STATUS_CODES.values())],
        ),
    )
    figure.add_trace(heatmap)
    figure.update_layout(
        title=f"Занятость оборудования на {target_date.strftime('%d.%m.%Y')}",
        xaxis_title="Время",
        yaxis_title="Оборудование",
        autosize=True,
        height=max(500, len(equipment_names) * 30 + 200),
        margin=dict(l=120, r=40, b=80, t=60, pad=4),
        plot_bgcolor="#e0f2fe",
        paper_bgcolor="white",
        xaxis=dict(
            showgrid=True,
            gridcolor="rgba(147, 197, 253, 0.5)",
            gridwidth=1,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(147, 197, 253, 0.5)",
            gridwidth=1,
        ),
    )
    return figure


def get_heatmap_payload(target_date: date):
    """Получить данные тепловой карты с кэшированием"""
    from .cache import get_heatmap, set_heatmap
    
    date_str = target_date.strftime("%Y-%m-%d")
    
    # Для прошлых и будущих дат используем кэш,
    # для текущей даты всегда пересчитываем тепловую карту,
    # чтобы корректно отражать переход слотов из "Забронировано" в "В работе".
    use_cache = target_date != date.today()

    if use_cache:
        cached = get_heatmap(date_str)
        if cached:
            logger.info(f"Тепловая карта загружена из кэша для {date_str}")
            return cached
    
    # Если нет в кэше - загружаем из БД
    equipment_names, usage, hover, summary, error = fetch_heatmap_data(target_date)
    if error:
        return {"error": error}
    if equipment_names is None or usage is None or hover is None:
        return {"error": "Нет данных для отображения"}

    figure = build_heatmap_figure(equipment_names, usage, hover, target_date)
    from plotly.utils import PlotlyJSONEncoder
    import json

    result = {
        "figure_json": json.dumps(figure, cls=PlotlyJSONEncoder),
        "date": date_str,
        "summary": summary or {},
        "error": None,
    }
    
    # Сохраняем в кэш только для дат, отличных от сегодняшней
    if use_cache:
        set_heatmap(date_str, result)
        logger.info(f"Тепловая карта сохранена в кэш для {date_str}")
    
    return result

