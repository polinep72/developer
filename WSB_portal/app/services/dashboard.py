import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, cast

import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
import psycopg
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

def _get_env(primary: str, fallback: str | None = None, default: str | None = None):
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

BOOKINGS_QUERY = """
SELECT
    b.date AS booking_date,
    b.time_start,
    b.time_end,
    b.finish,
    (u.first_name || ' ' || u.last_name) AS user_name,
    e.name_equip AS equipment_name
FROM bookings b
JOIN users u      ON b.user_id  = u.users_id
JOIN equipment e  ON b.equip_id = e.id
WHERE b.cancel IS NOT TRUE
  AND b.date BETWEEN %s AND %s
"""

DATE_BOUNDS_QUERY = """
SELECT MIN(b.date) AS min_date, MAX(b.date) AS max_date
FROM bookings b
WHERE b.cancel IS NOT TRUE
"""
# Если данных нет, ограничиваем 90 днями
DEFAULT_HISTORY_DAYS = 90

@dataclass
class BookingRecord:
    date: date
    equipment: str
    user: str
    hours: float


_RECORDS_CACHE: Dict[Tuple[str, str], Tuple[List[BookingRecord], datetime]] = {}
_CACHE_TTL = timedelta(minutes=10)


def _connect():
    return psycopg.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        sslmode=DB_SSLMODE,
        connect_timeout=5,
    )


def _fetch_records(start_date: date, end_date: date) -> Optional[List[BookingRecord]]:
    if not DB_USER or not DB_PASSWORD:
        logger.warning("DB credentials not configured for dashboard, using demo data.")
        return None

    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(BOOKINGS_QUERY, (start_date, end_date))
            rows = cur.fetchall()
    except Exception as exc:
        logger.exception("Failed to load dashboard data: %s", exc)
        return None

    records: List[BookingRecord] = []
    for row in rows:
        booking_date: Optional[date] = row[0]
        time_start: Optional[datetime] = row[1]
        time_end: Optional[datetime] = row[2]
        finish: Optional[datetime] = row[3]
        user_name: Optional[str] = row[4]
        equipment_name: Optional[str] = row[5]

        if not (booking_date and time_start and equipment_name and user_name):
            continue

        finish_time = finish or time_end
        if not finish_time:
            continue

        hours_used = (finish_time - time_start).total_seconds() / 3600
        hours_used = max(hours_used, 0)

        records.append(
            BookingRecord(
                date=booking_date,
                equipment=equipment_name,
                user=user_name,
                hours=round(hours_used, 2),
            )
        )

    return records


def _demo_records() -> List[BookingRecord]:
    base_date = date.today() - timedelta(days=14)
    equipment = ["Анализатор А", "Осциллограф B", "Генератор C"]
    users = ["Иван Петров", "Анна Смирнова", "Мария Кузнецова"]
    records: List[BookingRecord] = []

    for offset in range(15):
        current_date = base_date + timedelta(days=offset)
        for idx, eq in enumerate(equipment):
            hours = 1.5 + (offset % 3) * 0.5 + idx * 0.25
            records.append(
                BookingRecord(
                    date=current_date,
                    equipment=eq,
                    user=users[(offset + idx) % len(users)],
                    hours=round(hours, 2),
                )
        )
    return records


def _get_records(start_date: date, end_date: date, force_refresh: bool = False) -> List[BookingRecord]:
    key = (start_date.isoformat(), end_date.isoformat())
    now = datetime.utcnow()
    cached = _RECORDS_CACHE.get(key)
    if not force_refresh and cached:
        records, ts = cached
        if now - ts < _CACHE_TTL:
            return list(records)

    records = _fetch_records(start_date, end_date)
    if not records:
        records = _demo_records()

    _RECORDS_CACHE[key] = (records, now)
    return list(records)


def get_dashboard_dataframe(start_date: date, end_date: date) -> List[BookingRecord]:
    return _get_records(start_date, end_date)


def _get_date_bounds() -> Optional[Tuple[date, date]]:
    if not DB_USER or not DB_PASSWORD:
        return None
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(DATE_BOUNDS_QUERY)
            row = cur.fetchone()
            if not row or not row[0] or not row[1]:
                return None
            return cast(date, row[0]), cast(date, row[1])
    except Exception as exc:
        logger.warning("Failed to fetch booking date bounds: %s", exc)
        return None


def get_dashboard_initial() -> Dict[str, Any]:
    today = date.today()
    bounds = _get_date_bounds()
    if bounds:
        min_date, max_date = bounds
    else:
        # fallback на демо-диапазон
        min_date = today - timedelta(days=DEFAULT_HISTORY_DAYS)
        max_date = today

    default_end = today if today <= max_date else max_date
    default_start = default_end - timedelta(days=DEFAULT_HISTORY_DAYS)
    if default_start < min_date:
        default_start = min_date

    records = get_dashboard_dataframe(default_start, default_end)
    if not records:
        return {"error": "Нет данных для отображения"}

    equipment = sorted({r.equipment for r in records})
    default_selection = equipment[:2] if len(equipment) >= 2 else equipment
    target_load = 8

    payload = prepare_dashboard_payload(
        records=records,
        equipment=default_selection,
        start_date=default_start,
        end_date=default_end,
        target_load=target_load,
    )

    return {
        "equipment": equipment,
        "dateRange": {
            "min": min_date.isoformat(),
            "max": max_date.isoformat(),
        },
        "defaults": {
            "equipment": default_selection,
            "start_date": default_start.isoformat(),
            "end_date": default_end.isoformat(),
            "target_load": target_load,
        },
        "payload": payload,
    }


def prepare_dashboard_payload(
    records: List[BookingRecord],
    equipment: List[str],
    start_date: date,
    end_date: date,
    target_load: float,
) -> Dict[str, Any]:
    filtered = [
        r
        for r in records
        if r.equipment in equipment and start_date <= r.date <= end_date
    ]

    if not filtered:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            title="Нет данных для отображения",
            paper_bgcolor="#f8fbff",
        )
        empty_json = json.dumps(empty_fig, cls=PlotlyJSONEncoder)
        return {
            "relativeFigure": empty_json,
            "absoluteFigure": empty_json,
            "utilization": "0%",
            "users": [],
            "equipmentSummary": [],
            "message": "Нет данных для выбранных параметров.",
        }

    date_range = [
        start_date + timedelta(days=i)
        for i in range((end_date - start_date).days + 1)
    ]
    usage_map: Dict[Tuple[date, str], float] = defaultdict(float)
    user_hours: Dict[str, float] = defaultdict(float)
    equipment_hours: Dict[str, float] = defaultdict(float)

    for record in filtered:
        usage_map[(record.date, record.equipment)] += record.hours
        user_hours[record.user] += record.hours
        equipment_hours[record.equipment] += record.hours

    relative_figure = _build_relative_chart(date_range, equipment, usage_map, target_load)
    absolute_figure = _build_absolute_chart(date_range, equipment, usage_map)

    total_usage = sum(r.hours for r in filtered)
    total_target = max(len(date_range) * len(equipment) * target_load, 1)
    utilization = f"{(total_usage / total_target) * 100:.2f}%"

    users_payload = [
        {"name": name, "hours": round(hours, 2)}
        for name, hours in sorted(user_hours.items(), key=lambda item: item[1], reverse=True)
    ]
    equipment_payload = [
        {"name": name, "hours": round(hours, 2)}
        for name, hours in sorted(
            equipment_hours.items(), key=lambda item: item[1], reverse=True
        )
    ]

    return {
        "relativeFigure": json.dumps(relative_figure, cls=PlotlyJSONEncoder),
        "absoluteFigure": json.dumps(absolute_figure, cls=PlotlyJSONEncoder),
        "utilization": utilization,
        "users": users_payload,
        "equipmentSummary": equipment_payload,
        "message": "",
    }


def _build_relative_chart(
    dates: List[date],
    equipment: List[str],
    usage: Dict[Tuple[date, str], float],
    target_load: float,
) -> go.Figure:
    fig = go.Figure()
    str_dates = [d.isoformat() for d in dates]
    for eq in equipment:
        values = [
            round((usage.get((d, eq), 0) / target_load) * 100, 2) if target_load else 0
            for d in dates
        ]
        fig.add_trace(
            go.Scatter(
                x=str_dates,
                y=values,
                mode="lines+markers",
                name=eq,
            )
        )
    fig.update_layout(
        title="Относительная загрузка (%)",
        xaxis_title="Дата",
        yaxis_title="Отн. загрузка (%)",
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    return fig


def _build_absolute_chart(
    dates: List[date],
    equipment: List[str],
    usage: Dict[Tuple[date, str], float],
) -> go.Figure:
    fig = go.Figure()
    str_dates = [d.isoformat() for d in dates]
    for eq in equipment:
        values = [usage.get((d, eq), 0) for d in dates]
        fig.add_trace(go.Bar(x=str_dates, y=values, name=eq))
    fig.update_layout(
        title="Абсолютная загрузка (часы)",
        xaxis_title="Дата",
        yaxis_title="Часы",
        barmode="stack",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    return fig

