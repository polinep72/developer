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
    b.date::timestamp AS created_at,
    (u.first_name || ' ' || u.last_name) AS user_name,
    e.name_equip AS equipment_name,
    'Без категории' AS category_name
FROM bookings b
JOIN users u      ON b.user_id  = u.users_id
JOIN equipment e  ON b.equip_id = e.id
WHERE b.cancel IS NOT TRUE
  AND b.date BETWEEN %s AND %s
ORDER BY b.date, b.time_start
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
    category: str = ""
    time_start: Optional[datetime] = None
    created_at: Optional[datetime] = None


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
            logger.info(f"Fetched {len(rows)} raw booking records from DB for period {start_date} to {end_date}")
    except Exception as exc:
        logger.exception("Failed to load dashboard data: %s", exc)
        # При ошибке подключения возвращаем None, чтобы использовать демо-данные
        return None

    records: List[BookingRecord] = []
    for row in rows:
        booking_date: Optional[date] = row[0]
        time_start: Optional[datetime] = row[1]
        time_end: Optional[datetime] = row[2]
        finish: Optional[datetime] = row[3]
        created_at: Optional[datetime] = row[4]
        user_name: Optional[str] = row[5]
        equipment_name: Optional[str] = row[6]
        category_name: Optional[str] = row[7] if len(row) > 7 else ""

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
                category=category_name or "",
                time_start=time_start,
                created_at=created_at,
            )
        )

    # Всегда возвращаем список (даже пустой), если запрос успешен
    # None возвращается только при ошибке подключения
    logger.info(f"Processed {len(records)} valid booking records from {len(rows)} raw rows")
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
    # Демо-данные используем только если запрос к БД не удался (вернул None)
    # Если запрос успешен, но данных нет (пустой список) - возвращаем пустой список
    if records is None:
        logger.info("Using demo data due to DB connection failure")
        records = _demo_records()
    elif len(records) == 0:
        logger.info(f"No booking records found for period {start_date} to {end_date}")

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

    # Ключевые показатели
    insights = _build_dashboard_insights(filtered, date_range)

    return {
        "relativeFigure": json.dumps(relative_figure, cls=PlotlyJSONEncoder),
        "absoluteFigure": json.dumps(absolute_figure, cls=PlotlyJSONEncoder),
        "utilization": utilization,
        "users": users_payload,
        "equipmentSummary": equipment_payload,
        "insights": insights,
        "message": "",
    }


def _build_dashboard_insights(
    records: List[BookingRecord],
    date_range: List[date],
) -> Dict[str, Any]:
    """Построить ключевые показатели для дашборда"""
    if not records:
        return {
            "topCategories": [],
            "leadTime": 0.0,
            "weekendHolidayShare": 0.0,
        }

    # Топ категорий по использованию
    category_hours: Dict[str, float] = defaultdict(float)
    for record in records:
        if record.category:
            category_hours[record.category] += record.hours

    top_categories = sorted(
        [{"name": k, "hours": round(v, 2)} for k, v in category_hours.items()],
        key=lambda x: x["hours"],
        reverse=True,
    )[:5]

    # Время подготовки (lead time) - среднее время между созданием бронирования и началом работы
    lead_times: List[float] = []
    for record in records:
        if record.created_at and record.time_start:
            delta = record.time_start - record.created_at
            lead_times.append(delta.total_seconds() / 3600)  # в часах
    
    lead_time = sum(lead_times) / len(lead_times) if lead_times else 0.0

    # Доля выходных/праздничных дней
    weekend_count = sum(1 for d in date_range if d.weekday() >= 5)
    weekend_share = weekend_count / len(date_range) if date_range else 0.0

    return {
        "topCategories": top_categories,
        "leadTime": round(lead_time, 2),
        "weekendHolidayShare": round(weekend_share, 4),
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
        xaxis_title="Дата",
        yaxis_title="Отн. загрузка (%)",
        xaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
        yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.15,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#e2e8f0",
            borderwidth=1,
        ),
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
        xaxis_title="Дата",
        yaxis_title="Часы",
        barmode="stack",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.15,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0.8)",
            bordercolor="#e2e8f0",
            borderwidth=1,
        ),
    )
    return fig


def get_advanced_dashboard_data(
    start_date: date,
    end_date: date,
    equipment: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Получить данные для расширенной аналитики"""
    records = _get_records(start_date, end_date)
    if not records:
        return {
            "equipment_stats": {},
            "user_stats": {},
            "temporal_patterns": {},
            "forecast": {},
            "recommendations": {"systemic": [], "peak": [], "recent": []},
        }

    # Фильтруем записи по оборудованию, если указано
    filtered_records = records
    if equipment:
        filtered_records = [r for r in records if r.equipment in equipment]

    # Базовые расчеты
    equipment_hours: Dict[str, float] = defaultdict(float)
    equipment_by_category: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    user_hours: Dict[str, float] = defaultdict(float)
    date_usage: Dict[date, float] = defaultdict(float)

    for record in filtered_records:
        equipment_hours[record.equipment] += record.hours
        if record.category:
            equipment_by_category[record.category][record.equipment] += record.hours
        user_hours[record.user] += record.hours
        date_usage[record.date] += record.hours

    # Статистика по оборудованию с графиками
    equipment_stats = _build_equipment_stats(equipment_hours, equipment_by_category, filtered_records)

    # Статистика по пользователям с графиками
    user_stats = _build_user_stats(user_hours, filtered_records)

    # Временные паттерны
    temporal_patterns = _build_temporal_patterns(filtered_records)

    # Прогноз загрузки
    forecast = _build_forecast(date_usage, end_date)

    # Рекомендации
    recommendations = _build_recommendations(equipment_hours, date_usage, equipment_by_category, filtered_records)

    return {
        "equipment_stats": equipment_stats,
        "user_stats": user_stats,
        "temporal_patterns": temporal_patterns,
        "forecast": forecast,
        "recommendations": recommendations,
    }


BASE_EQUIPMENT_TARGET_HOURS = 8.0
SYSTEMIC_OVERLOAD_THRESHOLD = 1.3  # 30% перегрузка
UNDERUTILIZED_THRESHOLD = 0.4  # Меньше 40% использования


def _build_equipment_stats(
    equipment_hours: Dict[str, float],
    equipment_by_category: Dict[str, Dict[str, float]],
    records: List[BookingRecord],
) -> Dict[str, Any]:
    """Построить статистику по оборудованию с графиками"""
    # Топ оборудования
    top_equipment = sorted(
        [{"name": k, "hours": round(v, 2)} for k, v in equipment_hours.items()],
        key=lambda x: x["hours"],
        reverse=True,
    )[:10]

    # График топ оборудования
    if top_equipment:
        fig = go.Figure()
        names = [e["name"] for e in top_equipment]
        hours = [e["hours"] for e in top_equipment]
        fig.add_trace(go.Bar(x=names, y=hours, name="Часы использования"))
        fig.update_layout(
            xaxis_title="Оборудование",
            yaxis_title="Часы",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=120),
            xaxis=dict(tickangle=-45),
        )
        equipment_figure = json.dumps(fig, cls=PlotlyJSONEncoder)
    else:
        equipment_figure = "{}"

    # Статистика по оборудованию (вместо категорий показываем конкретное оборудование)
    category_stats = []
    for equipment_name, hours in sorted(equipment_hours.items(), key=lambda x: x[1], reverse=True):
        category_stats.append({"name": equipment_name, "hours": round(hours, 2)})

    # Дополнительная аналитика по оборудованию
    equipment_bookings_count: Dict[str, int] = defaultdict(int)
    equipment_avg_duration: Dict[str, List[float]] = defaultdict(list)
    equipment_weekday_dist: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    equipment_hour_dist: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    equipment_early_finish: Dict[str, Tuple[int, int]] = defaultdict(lambda: (0, 0))  # (раньше, всего)
    equipment_top_users: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    equipment_monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    
    days_in_period = len(set(r.date for r in records)) if records else 1
    
    for record in records:
        eq = record.equipment
        equipment_bookings_count[eq] += 1
        equipment_avg_duration[eq].append(record.hours)
        
        # Распределение по дням недели (0=понедельник, 6=воскресенье)
        weekday = record.date.weekday()
        equipment_weekday_dist[eq][weekday] += 1
        
        # Пиковые часы использования
        if record.time_start:
            hour = record.time_start.hour
            equipment_hour_dist[eq][hour] += record.hours
        
        # Топ пользователей оборудования
        equipment_top_users[eq][record.user] += record.hours
        
        # Динамика по месяцам
        month_key = record.date.strftime("%Y-%m")
        equipment_monthly[eq][month_key] += record.hours
    
    # Формируем детальную статистику
    equipment_detailed = []
    for eq in sorted(equipment_hours.keys(), key=lambda x: equipment_hours[x], reverse=True):
        bookings_count = equipment_bookings_count[eq]
        avg_duration = sum(equipment_avg_duration[eq]) / len(equipment_avg_duration[eq]) if equipment_avg_duration[eq] else 0
        utilization_pct = (equipment_hours[eq] / (days_in_period * BASE_EQUIPMENT_TARGET_HOURS) * 100) if days_in_period > 0 else 0
        
        # Процент досрочного завершения (нужно проверить finish vs time_end, но у нас нет time_end в записи)
        # Пока пропускаем, так как нет данных о time_end в BookingRecord
        
        # Топ пользователей (топ-3)
        top_users_list = sorted(
            equipment_top_users[eq].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        equipment_detailed.append({
            "name": eq,
            "hours": round(equipment_hours[eq], 2),
            "bookings_count": bookings_count,
            "avg_duration": round(avg_duration, 2),
            "utilization_pct": round(utilization_pct, 1),
            "top_users": [{"name": u, "hours": round(h, 2)} for u, h in top_users_list],
        })
    
    # График распределения по дням недели (для топ-5 оборудования)
    weekday_figure = "{}"
    if top_equipment:
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        fig_weekday = go.Figure()
        for eq_data in top_equipment[:5]:
            eq_name = str(eq_data["name"])
            weekday_counts = [equipment_weekday_dist[eq_name].get(i, 0) for i in range(7)]
            fig_weekday.add_trace(go.Bar(
                x=weekday_names,
                y=weekday_counts,
                name=eq_name,
            ))
        fig_weekday.update_layout(
            xaxis_title="День недели",
            yaxis_title="Количество бронирований",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=60),
            barmode="group",
        )
        weekday_figure = json.dumps(fig_weekday, cls=PlotlyJSONEncoder)
    
    # График пиковых часов (для топ-5 оборудования)
    peak_hours_figure = "{}"
    if top_equipment:
        fig_hours = go.Figure()
        for eq_data in top_equipment[:5]:
            eq_name = str(eq_data["name"])
            hour_data = [equipment_hour_dist[eq_name].get(h, 0) for h in range(24)]
            fig_hours.add_trace(go.Bar(
                x=list(range(24)),
                y=hour_data,
                name=eq_name,
            ))
        fig_hours.update_layout(
            xaxis_title="Час дня",
            yaxis_title="Часы использования",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=60),
            barmode="group",
        )
        peak_hours_figure = json.dumps(fig_hours, cls=PlotlyJSONEncoder)
    
    # График динамики использования (для топ-5 оборудования)
    monthly_figure = "{}"
    if top_equipment and records:
        fig_monthly = go.Figure()
        all_months = sorted(set(record.date.strftime("%Y-%m") for record in records))
        for eq_data in top_equipment[:5]:
            eq_name = str(eq_data["name"])
            monthly_data = [equipment_monthly[eq_name].get(month, 0) for month in all_months]
            fig_monthly.add_trace(go.Scatter(
                x=all_months,
                y=monthly_data,
                mode="lines+markers",
                name=eq_name,
            ))
        fig_monthly.update_layout(
            xaxis_title="Месяц",
            yaxis_title="Часы использования",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=80),
            xaxis=dict(tickangle=-45),
        )
        monthly_figure = json.dumps(fig_monthly, cls=PlotlyJSONEncoder)

    return {
        "top_equipment": top_equipment,
        "equipment_figure": equipment_figure,
        "category_stats": category_stats,
        "equipment_detailed": equipment_detailed,
        "weekday_figure": weekday_figure,
        "peak_hours_figure": peak_hours_figure,
        "monthly_figure": monthly_figure,
    }


def _build_user_stats(
    user_hours: Dict[str, float],
    records: List[BookingRecord],
) -> Dict[str, Any]:
    """Построить статистику по пользователям с графиками"""
    # Топ пользователей
    top_users = sorted(
        [{"name": k, "hours": round(v, 2)} for k, v in user_hours.items()],
        key=lambda x: x["hours"],
        reverse=True,
    )[:10]

    # График топ пользователей
    if top_users:
        fig = go.Figure()
        names = [u["name"] for u in top_users]
        hours = [u["hours"] for u in top_users]
        fig.add_trace(go.Bar(x=names, y=hours, name="Часы использования"))
        fig.update_layout(
            xaxis_title="Пользователь",
            yaxis_title="Часы",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=120),
            xaxis=dict(tickangle=-45),
        )
        user_figure = json.dumps(fig, cls=PlotlyJSONEncoder)
    else:
        user_figure = "{}"

    # Дополнительная аналитика по пользователям
    user_bookings_count: Dict[str, int] = defaultdict(int)
    user_avg_duration: Dict[str, List[float]] = defaultdict(list)
    user_frequent_equipment: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    user_weekday_dist: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    user_hour_dist: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
    user_monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    user_equipment_diversity: Dict[str, set] = defaultdict(set)
    
    for record in records:
        user = record.user
        user_bookings_count[user] += 1
        user_avg_duration[user].append(record.hours)
        
        # Часто используемое оборудование
        user_frequent_equipment[user][record.equipment] += record.hours
        
        # Разнообразие оборудования
        user_equipment_diversity[user].add(record.equipment)
        
        # Распределение по дням недели
        weekday = record.date.weekday()
        user_weekday_dist[user][weekday] += 1
        
        # Пиковые часы работы
        if record.time_start:
            hour = record.time_start.hour
            user_hour_dist[user][hour] += record.hours
        
        # Динамика по месяцам
        month_key = record.date.strftime("%Y-%m")
        user_monthly[user][month_key] += record.hours
    
    # Формируем детальную статистику
    user_detailed = []
    for user in sorted(user_hours.keys(), key=lambda x: user_hours[x], reverse=True):
        bookings_count = user_bookings_count[user]
        avg_duration = sum(user_avg_duration[user]) / len(user_avg_duration[user]) if user_avg_duration[user] else 0
        
        # Часто используемое оборудование (топ-3)
        frequent_eq_list = sorted(
            user_frequent_equipment[user].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        # Разнообразие оборудования
        equipment_count = len(user_equipment_diversity[user])
        
        user_detailed.append({
            "name": user,
            "hours": round(user_hours[user], 2),
            "bookings_count": bookings_count,
            "avg_duration": round(avg_duration, 2),
            "frequent_equipment": [{"name": eq, "hours": round(h, 2)} for eq, h in frequent_eq_list],
            "equipment_diversity": equipment_count,
        })
    
    # График распределения по дням недели (для топ-5 пользователей)
    weekday_figure = "{}"
    if top_users:
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        fig_weekday = go.Figure()
        for user_data in top_users[:5]:
            user_name = str(user_data["name"])
            weekday_counts = [user_weekday_dist[user_name].get(i, 0) for i in range(7)]
            fig_weekday.add_trace(go.Bar(
                x=weekday_names,
                y=weekday_counts,
                name=user_name,
            ))
        fig_weekday.update_layout(
            xaxis_title="День недели",
            yaxis_title="Количество бронирований",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=60),
            barmode="group",
        )
        weekday_figure = json.dumps(fig_weekday, cls=PlotlyJSONEncoder)
    
    # График пиковых часов работы (для топ-5 пользователей)
    peak_hours_figure = "{}"
    if top_users:
        fig_hours = go.Figure()
        for user_data in top_users[:5]:
            user_name = str(user_data["name"])
            hour_data = [user_hour_dist[user_name].get(h, 0) for h in range(24)]
            fig_hours.add_trace(go.Bar(
                x=list(range(24)),
                y=hour_data,
                name=user_name,
            ))
        fig_hours.update_layout(
            xaxis_title="Час дня",
            yaxis_title="Часы использования",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=60),
            barmode="group",
        )
        peak_hours_figure = json.dumps(fig_hours, cls=PlotlyJSONEncoder)
    
    # График динамики активности (для топ-5 пользователей)
    monthly_figure = "{}"
    if top_users and records:
        fig_monthly = go.Figure()
        all_months = sorted(set(record.date.strftime("%Y-%m") for record in records))
        for user_data in top_users[:5]:
            user_name = str(user_data["name"])
            monthly_data = [user_monthly[user_name].get(month, 0) for month in all_months]
            fig_monthly.add_trace(go.Scatter(
                x=all_months,
                y=monthly_data,
                mode="lines+markers",
                name=user_name,
            ))
        fig_monthly.update_layout(
            xaxis_title="Месяц",
            yaxis_title="Часы использования",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            autosize=True,
            margin=dict(l=60, r=20, t=40, b=80),
            xaxis=dict(tickangle=-45),
        )
        monthly_figure = json.dumps(fig_monthly, cls=PlotlyJSONEncoder)

    return {
        "top_users": top_users,
        "user_figure": user_figure,
        "user_detailed": user_detailed,
        "weekday_figure": weekday_figure,
        "peak_hours_figure": peak_hours_figure,
        "monthly_figure": monthly_figure,
    }


def _build_temporal_patterns(records: List[BookingRecord]) -> Dict[str, Any]:
    """Построить временные паттерны (почасовые и недельные)"""
    if not records:
        return {"hourly": {}, "weekly": {}}

    # Почасовые паттерны
    hourly_usage: Dict[int, float] = defaultdict(float)
    for record in records:
        if record.time_start:
            hour = record.time_start.hour
            hourly_usage[hour] += record.hours

    hourly_data = [hourly_usage.get(h, 0) for h in range(24)]
    hourly_fig = go.Figure()
    hourly_fig.add_trace(go.Bar(x=list(range(24)), y=hourly_data, name="Использование"))
    hourly_fig.update_layout(
        xaxis_title="Час дня",
        yaxis_title="Часы использования",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    # Недельные паттерны
    weekday_usage: Dict[int, float] = defaultdict(float)
    weekday_labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for record in records:
        weekday = record.date.weekday()
        weekday_usage[weekday] += record.hours

    weekly_data = [weekday_usage.get(wd, 0) for wd in range(7)]
    weekly_fig = go.Figure()
    weekly_fig.add_trace(go.Bar(x=weekday_labels, y=weekly_data, name="Использование"))
    weekly_fig.update_layout(
        xaxis_title="День недели",
        yaxis_title="Часы использования",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    return {
        "hourly": {
            "figure": json.dumps(hourly_fig, cls=PlotlyJSONEncoder),
            "data": hourly_data,
        },
        "weekly": {
            "figure": json.dumps(weekly_fig, cls=PlotlyJSONEncoder),
            "data": weekly_data,
        },
    }


def _build_forecast(date_usage: Dict[date, float], end_date: date) -> Dict[str, Any]:
    """Построить прогноз загрузки на основе исторических данных"""
    if not date_usage:
        return {"figure": "{}", "types": [], "colors": [], "legend": []}

    # Группируем по дням недели
    weekday_usage: Dict[int, List[float]] = defaultdict(list)
    for d, hours in date_usage.items():
        weekday_usage[d.weekday()].append(hours)

    # Средние значения по дням недели
    weekday_avg: Dict[int, float] = {}
    for wd, hours_list in weekday_usage.items():
        weekday_avg[wd] = sum(hours_list) / len(hours_list) if hours_list else 0

    # Прогноз на следующие 14 дней
    forecast_dates: List[date] = []
    forecast_values: List[float] = []
    forecast_types: List[str] = []
    forecast_colors: List[str] = []

    for i in range(14):
        forecast_date = end_date + timedelta(days=i + 1)
        forecast_dates.append(forecast_date)
        wd = forecast_date.weekday()
        avg_hours = weekday_avg.get(wd, 0)
        forecast_values.append(round(avg_hours, 2))

        # Определяем тип дня
        if wd >= 5:  # Суббота, воскресенье
            forecast_types.append("weekend")
            forecast_colors.append("#94a3b8")
        else:
            forecast_types.append("workday")
            forecast_colors.append("#3b82f6")

    # Создаем график
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[d.isoformat() for d in forecast_dates],
            y=forecast_values,
            marker_color=forecast_colors,
            name="Прогноз",
        )
    )
    fig.update_layout(
        xaxis_title="Дата",
        yaxis_title="Часы",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )

    legend = [
        {"color": "#3b82f6", "label": "Рабочий день"},
        {"color": "#94a3b8", "label": "Выходной"},
    ]

    return {
        "figure": json.dumps(fig, cls=PlotlyJSONEncoder),
        "types": forecast_types,
        "colors": forecast_colors,
        "legend": legend,
    }


def _build_recommendations(
    equipment_hours: Dict[str, float],
    date_usage: Dict[date, float],
    equipment_by_category: Optional[Dict[str, Dict[str, float]]] = None,
    records: Optional[List[BookingRecord]] = None,
) -> Dict[str, List[str]]:
    """Построить рекомендации на основе данных"""
    systemic: List[str] = []
    peak: List[str] = []
    recent: List[str] = []

    days = len(date_usage) if date_usage else 1

    # Системные перегрузки (долгосрочные перегрузки)
    overloaded_by_category: Dict[str, List[str]] = defaultdict(list)
    for eq, hours in equipment_hours.items():
        if days > 0:
            avg_hours_per_day = hours / days
            if avg_hours_per_day > BASE_EQUIPMENT_TARGET_HOURS * SYSTEMIC_OVERLOAD_THRESHOLD:
                # Находим категорию оборудования
                category = ""
                if equipment_by_category:
                    for cat, eq_dict in equipment_by_category.items():
                        if eq in eq_dict:
                            category = cat
                            break
                
                if category:
                    overloaded_by_category[category].append(eq)
                
                systemic.append(
                    f"Оборудование {eq} систематически перегружено: "
                    f"{avg_hours_per_day:.1f} ч/день (целевая загрузка: {BASE_EQUIPMENT_TARGET_HOURS} ч/день). "
                    f"Рекомендуется увеличить парк оборудования этого типа."
                )

    # Рекомендации по категориям с множественными перегрузками
    for category, eq_list in overloaded_by_category.items():
        if len(eq_list) >= 2:
            systemic.append(
                f"В категории '{category}' обнаружено {len(eq_list)} перегруженных единиц оборудования. "
                f"Рекомендуется расширить парк оборудования этой категории."
            )

    # Пиковые инциденты (кратковременные перегрузки в отдельные дни)
    if records:
        # Группируем записи по оборудованию и дате
        equipment_daily_hours: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
        for record in records:
            equipment_daily_hours[record.equipment][record.date] += record.hours
        
        # Находим дни с пиковыми перегрузками (более 10-12 часов в день)
        PEAK_OVERLOAD_THRESHOLD = 10.0  # Порог пиковой перегрузки в часах
        peak_incidents: Dict[str, List[Tuple[date, float]]] = defaultdict(list)
        
        for eq, daily_hours in equipment_daily_hours.items():
            for target_date, hours_in_day in daily_hours.items():
                if hours_in_day >= PEAK_OVERLOAD_THRESHOLD:
                    peak_incidents[eq].append((target_date, hours_in_day))
        
        # Формируем рекомендации по пиковым инцидентам
        for eq, incidents in peak_incidents.items():
            if incidents:
                # Сортируем по дате (самые свежие первыми)
                incidents.sort(key=lambda x: x[0], reverse=True)
                # Берем последние 3 инцидента
                for target_date, hours_in_day in incidents[:3]:
                peak.append(
                        f"Оборудование {eq} было перегружено {target_date.strftime('%d.%m.%Y')}: "
                        f"использовано {hours_in_day:.1f} часов за день. "
                        f"Рекомендуется распределить нагрузку на другие дни или оборудование."
                    )
        
        # Анализ пиковых инцидентов для рекомендаций по расширению парка
        peak_conclusions: List[str] = []  # Собираем все выводы отдельно
        
        if peak_incidents:
            # Подсчитываем количество инцидентов для каждого оборудования
            equipment_incident_count: Dict[str, int] = {
                eq: len(incidents) for eq, incidents in peak_incidents.items()
            }
            
            # Находим оборудование с частыми пиковыми перегрузками (3+ инцидента)
            FREQUENT_PEAK_THRESHOLD = 3
            frequently_overloaded: List[Tuple[str, int]] = [
                (eq, count) for eq, count in equipment_incident_count.items()
                if count >= FREQUENT_PEAK_THRESHOLD
            ]
            
            # Сортируем по количеству инцидентов (самые проблемные первыми)
            frequently_overloaded.sort(key=lambda x: x[1], reverse=True)
            
            # Собираем рекомендации по расширению парка для отдельных единиц оборудования
            for eq, incident_count in frequently_overloaded:
                # Находим категорию оборудования
                category = ""
                if equipment_by_category:
                    for cat, eq_dict in equipment_by_category.items():
                        if eq in eq_dict:
                            category = cat
                            break
                
                if category and category != "Без категории":
                    peak_conclusions.append(
                        f"Оборудование {eq} (категория '{category}') имеет {incident_count} пиковых инцидента. "
                        f"Рекомендуется расширить парк оборудования этого типа для предотвращения перегрузок."
                    )
                else:
                    peak_conclusions.append(
                        f"Оборудование {eq} имеет {incident_count} пиковых инцидента. "
                        f"Рекомендуется расширить парк данного оборудования для предотвращения перегрузок."
                    )
            
            # Анализ по категориям: если в категории несколько единиц с пиковыми инцидентами
            if equipment_by_category:
                category_peak_count: Dict[str, int] = defaultdict(int)
                category_equipment: Dict[str, List[str]] = defaultdict(list)
                for eq, incident_count in equipment_incident_count.items():
                    if incident_count >= FREQUENT_PEAK_THRESHOLD:
                        for cat, eq_dict in equipment_by_category.items():
                            if eq in eq_dict:
                                # Пропускаем категорию "Без категории"
                                if cat and cat != "Без категории":
                                    category_peak_count[cat] += 1
                                    category_equipment[cat].append(eq)
                                break
                
                # Рекомендации по категориям с множественными проблемами
                for cat, count in category_peak_count.items():
                    if count >= 2:
                        equipment_list = ", ".join(category_equipment[cat][:3])  # Показываем до 3 единиц
                        if len(category_equipment[cat]) > 3:
                            equipment_list += f" и еще {len(category_equipment[cat]) - 3}"
                        peak_conclusions.append(
                            f"В категории '{cat}' обнаружено {count} единиц оборудования с частыми пиковыми перегрузками "
                            f"({equipment_list}). Рекомендуется расширить парк оборудования этой категории."
                        )
                
                # Для оборудования без категории показываем конкретные названия
                no_category_equipment: List[str] = []
                for eq, incident_count in equipment_incident_count.items():
                    if incident_count >= FREQUENT_PEAK_THRESHOLD:
                        # Проверяем, что оборудование действительно без категории
                        has_category = False
                        if equipment_by_category:
                            for cat, eq_dict in equipment_by_category.items():
                                if eq in eq_dict and cat and cat != "Без категории":
                                    has_category = True
                                    break
                        if not has_category:
                            no_category_equipment.append(eq)
                
                if len(no_category_equipment) >= 2:
                    equipment_list = ", ".join(no_category_equipment[:3])
                    if len(no_category_equipment) > 3:
                        equipment_list += f" и еще {len(no_category_equipment) - 3}"
                    peak_conclusions.append(
                        f"Обнаружено {len(no_category_equipment)} единиц оборудования с частыми пиковыми перегрузками "
                        f"({equipment_list}). Рекомендуется расширить парк данного оборудования."
                    )
            
            # Добавляем один блок "ВЫВОД:" в конце со всеми рекомендациями
            if peak_conclusions:
                conclusions_text = " ".join(peak_conclusions)
                peak.append(f"<strong>ВЫВОД:</strong> {conclusions_text}")

    # Свежие события (последняя неделя)
    if records:
        week_ago = date.today() - timedelta(days=7)
        recent_records = [r for r in records if r.date >= week_ago]
        
        if recent_records:
            # Пиковые перегрузки за последнюю неделю
            recent_equipment_daily_hours: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
            for record in recent_records:
                recent_equipment_daily_hours[record.equipment][record.date] += record.hours
            
            PEAK_OVERLOAD_THRESHOLD_RECENT = 10.0
            for eq, daily_hours in recent_equipment_daily_hours.items():
                for target_date, hours_in_day in daily_hours.items():
                    if hours_in_day >= PEAK_OVERLOAD_THRESHOLD_RECENT:
                        recent.append(
                            f"Пиковая перегрузка: {eq} использовано {hours_in_day:.1f} часов {target_date.strftime('%d.%m.%Y')}"
                        )
            
            # Новые системные перегрузки (оборудование, которое стало перегруженным за последнюю неделю)
            recent_equipment_hours: Dict[str, float] = defaultdict(float)
            recent_days = len(set(r.date for r in recent_records))
            if recent_days > 0:
                for record in recent_records:
                    recent_equipment_hours[record.equipment] += record.hours
                
                for eq, hours in recent_equipment_hours.items():
                    avg_hours_per_day = hours / recent_days
                    if avg_hours_per_day > BASE_EQUIPMENT_TARGET_HOURS * SYSTEMIC_OVERLOAD_THRESHOLD:
                        # Проверяем, не было ли это оборудование перегружено раньше
                        total_avg = equipment_hours.get(eq, 0) / days if days > 0 else 0
                        if total_avg <= BASE_EQUIPMENT_TARGET_HOURS * SYSTEMIC_OVERLOAD_THRESHOLD:
                            recent.append(
                                f"Новая системная перегрузка: {eq} - {avg_hours_per_day:.1f} ч/день за последнюю неделю"
                )

    return {
        "systemic": systemic,
        "peak": peak,
        "recent": recent,
    }

