import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
import dash
from dash import dcc, html, Input, Output
import pandas as pd
import plotly.express as px
from datetime import datetime

# 1. ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ (из .env)
load_dotenv()

POSTGRE_USER = os.getenv("POSTGRE_USER")
POSTGRE_PASSWORD = os.getenv("POSTGRE_PASSWORD")
POSTGRE_DBNAME = os.getenv("POSTGRE_DBNAME")
POSTGRE_HOST = os.getenv("POSTGRE_HOST", "localhost")
POSTGRE_PORT = os.getenv("POSTGRE_PORT", "5432")

DATABASE_URL = (
    f"postgresql://{POSTGRE_USER}:{POSTGRE_PASSWORD}"
    f"@{POSTGRE_HOST}:{POSTGRE_PORT}/{POSTGRE_DBNAME}"
)

# 2. ПОДКЛЮЧЕНИЕ К БД И ЗАПРОС
#    Условие: WHERE b.cancel IS NOT TRUE (исключаем отменённые бронирования)
engine = create_engine(DATABASE_URL)

query = """
SELECT
    b.id AS booking_id,
    b.date AS "Date",
    b.time_start,
    b.time_end,
    b.finish,
    (u.first_name || ' ' || u.last_name) AS "User",
    e.name_equip AS "Equipment"
FROM bookings b
JOIN users u      ON b.user_id  = u.users_id
JOIN equipment e  ON b.equip_id = e.id
JOIN cat c        ON e.category = c.id
WHERE b.cancel IS NOT TRUE
"""

df = pd.read_sql(query, con=engine)

# 3. ПРЕДОБРАБОТКА
df["time_start"] = pd.to_datetime(df["time_start"], errors="coerce")
df["time_end"]   = pd.to_datetime(df["time_end"], errors="coerce")
df["finish"]     = pd.to_datetime(df["finish"], errors="coerce")

# Заполняем finish из time_end, если finish=None
df["finish"] = df["finish"].fillna(df["time_end"])

# Вычисляем Hours_Used = (finish - time_start) в часах
df["Hours_Used"] = (df["finish"] - df["time_start"]).dt.total_seconds() / 3600
df["Hours_Used"] = df["Hours_Used"].round(2)

# Приводим Date к типу date (если нужно)
df["Date"] = pd.to_datetime(df["Date"]).dt.date

# Формируем список уникальных приборов
equipment_list = sorted(df["Equipment"].unique())

# 4. СОЗДАНИЕ DASH-ПРИЛОЖЕНИЯ
app = dash.Dash(__name__)

app.index_string = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Информационная панель бронирования</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        }
        .header {
            background-color: #f0f0f0;
            border-bottom: 1px solid #ccc;
            padding: 15px;
        }
        .header h1 {
            margin: 0;
        }
        .filters {
            padding: 15px;
            background-color: #fafafa;
            border-bottom: 1px solid #eee;
        }
    </style>
    {%css%}
</head>
<body>
    <div class="header">
        <h1>Моя кастомная шапка</h1>
    </div>
    <div id="dash-app">
        {%app_entry%}
    </div>
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>
"""

# 5. LAYOUT
app.layout = html.Div([
    html.H2("Информационная панель статистики бронирования", style={"marginLeft": "15px"}),

    # Фильтры
    html.Div([
        html.Label("Выберите измерительные приборы:"),
        dcc.Dropdown(
            id="equipment-filter",
            options=[{"label": eq, "value": eq} for eq in equipment_list],
            value=equipment_list[:2],
            multi=True
        ),
        html.Br(),

        html.Label("Выберите временной период:"),
        dcc.DatePickerRange(
            id="date-filter",
            start_date=str(df["Date"].min()),
            end_date=str(df["Date"].max()),
            display_format="YYYY-MM-DD"
        ),
        html.Br(),

        html.Label("Целевая загрузка (часов в день):"),
        dcc.Input(
            id="target-load",
            type="number",
            value=8
        )
    ], className="filters"),

    # Индикатор
    html.Div([
        html.H3("Обобщенная загрузка всего парка оборудования:"),
        html.Div(id="overall-utilization", style={"fontSize": "24px", "fontWeight": "bold"})
    ], style={"marginLeft": "15px", "marginBottom": "20px"}),

    # Графики
    dcc.Graph(id="relative-load-graph"),
    dcc.Graph(id="absolute-load-graph"),

    # Таблица пользователей
    html.H3("Список пользователей:", style={"marginLeft": "15px"}),
    html.Div(id="user-table"),

    # Таблица суммарной наработки
    html.H3("Суммарная наработка:", style={"marginLeft": "15px"}),
    html.Div(id="equipment-summary-table")
])

# 6. CALLBACK
@app.callback(
    [
        Output("relative-load-graph", "figure"),
        Output("absolute-load-graph", "figure"),
        Output("overall-utilization", "children"),
        Output("user-table", "children"),
        Output("equipment-summary-table", "children")
    ],
    [
        Input("equipment-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
        Input("target-load", "value")
    ]
)
def update_dashboard(selected_equipments, start_date, end_date, target_load):
    if not selected_equipments or not start_date or not end_date:
        return dash.no_update

    # Преобразуем start_date/end_date в date-объекты (если строка)
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_date_obj   = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Фильтрация
    filtered_df = df[
        (df["Equipment"].isin(selected_equipments)) &
        (df["Date"] >= start_date_obj) &
        (df["Date"] <= end_date_obj)
    ]

    if filtered_df.empty:
        empty_fig = px.scatter(title="Нет данных для отображения")
        return (
            empty_fig,
            empty_fig,
            "0%",
            html.Div("Нет данных"),
            html.Div("Нет данных")
        )

    # Группировка по дате и прибору
    daily_usage = (
        filtered_df
        .groupby(["Date", "Equipment"], as_index=False)["Hours_Used"]
        .sum()
    )

    # Относительная загрузка = (Hours_Used / Target_Load) * 100
    daily_usage["Relative_Load"] = (daily_usage["Hours_Used"] / target_load) * 100

    # График относительной загрузки с переименованной легендой и сеткой
    fig_relative = px.line(
        daily_usage,
        x="Date",
        y="Relative_Load",
        color="Equipment",
        title="Относительная загрузка (%)",
        labels={
            "Relative_Load": "Отн. загрузка (%)",
            "Date": "Дата",
            "Equipment": "Оборудование"
        }
    )
    # Добавляем сетку на оси Х и настраиваем dtick для отображения каждого дня
    fig_relative.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='LightGrey',
        dtick=86400000  # 86400000 мс = 1 день
    )
    # При желании можно также добавить настройки для оси Y:
    fig_relative.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGrey')

    # График абсолютной загрузки с переименованной легендой
    fig_absolute = px.bar(
        daily_usage,
        x="Date",
        y="Hours_Used",
        color="Equipment",
        title="Абсолютная загрузка (часы)",
        labels={
            "Hours_Used": "Абсолютная загрузка (ч)",
            "Date": "Дата",
            "Equipment": "Оборудование"
        }
    )

    # Таблица пользователей
    user_summary = (
        filtered_df
        .groupby("User", as_index=False)["Hours_Used"]
        .sum()
        .sort_values("Hours_Used", ascending=False)
    )

    user_table = html.Table([
        html.Thead([
            html.Tr([html.Th("Пользователь"), html.Th("Длительность (ч)")])
        ]),
        html.Tbody([
            html.Tr([
                html.Td(row["User"]),
                html.Td(row["Hours_Used"])
            ]) for _, row in user_summary.iterrows()
        ])
    ], style={"marginLeft": "15px"})

    # Общая загрузка
    total_usage = filtered_df["Hours_Used"].sum()
    num_days = (end_date_obj - start_date_obj).days + 1
    num_equipment = len(selected_equipments)
    total_target_load = num_days * num_equipment * target_load
    utilization_percentage = (total_usage / total_target_load) * 100 if total_target_load else 0
    utilization_text = f"{utilization_percentage:.2f}%"

    # Таблица суммарной наработки
    equipment_summary = (
        filtered_df
        .groupby("Equipment", as_index=False)["Hours_Used"]
        .sum()
        .sort_values("Hours_Used", ascending=False)
    )

    equipment_summary_table = html.Table([
        html.Thead([
            html.Tr([html.Th("Прибор"), html.Th("Суммарное бронирование (ч)")])
        ]),
        html.Tbody([
            html.Tr([
                html.Td(row["Equipment"]),
                html.Td(row["Hours_Used"])
            ]) for _, row in equipment_summary.iterrows()
        ])
    ], style={"marginLeft": "15px"})

    return (
        fig_relative,
        fig_absolute,
        utilization_text,
        user_table,
        equipment_summary_table
    )

# 7. ЗАПУСК ПРИЛОЖЕНИЯ
if __name__ == "__main__":
    app.run_server(debug=True, host="192.168.1.22", port=8050)
