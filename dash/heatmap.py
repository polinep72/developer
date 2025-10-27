import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
from datetime import datetime, timedelta
import numpy as np
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "27915002")
DB_NAME = os.getenv("DB_NAME", "RM")
DB_HOST = os.getenv("DB_HOST", "192.168.1.139")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_SSLMODE = os.getenv("DB_SSLMODE", "prefer")

app = Dash(__name__)

time_intervals = [f'{h:02d}:{m:02d}' for h in range(24) for m in range(0, 60, 30)]
default_date = (datetime.now() - timedelta(days=1)).date()

def fetch_data(selected_date):
    print(f"Fetching data for: {selected_date}")
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            sslmode=DB_SSLMODE,
            connect_timeout=5
        )
        print("Connected to database")
        cur = conn.cursor()

        cur.execute("SELECT name_equip FROM equipment ORDER BY id")
        equipment = [row[0] for row in cur.fetchall()]
        if not equipment:
            print("No equipment found in database")
            cur.close()
            conn.close()
            return None, "Нет оборудования в базе данных"

        usage_data = np.zeros((len(equipment), len(time_intervals)), dtype=int)

        query = """
            SELECT e.name_equip, b.time_start, b.time_end
            FROM bookings b
            JOIN equipment e ON b.equip_id = e.id
            WHERE b.date = %s AND b.cancel = FALSE
        """
        cur.execute(query, (selected_date,))
        bookings = cur.fetchall()
        print(f"Bookings fetched: {len(bookings)} rows")

        for equip_name, time_start, time_end in bookings:
            equip_idx = equipment.index(equip_name)
            start_idx = int((time_start.hour * 60 + time_start.minute) // 30)
            end_idx = int((time_end.hour * 60 + time_end.minute) // 30)
            for i in range(start_idx, min(end_idx, len(time_intervals))):
                usage_data[equip_idx][i] = 1

        cur.close()
        conn.close()
        print("Data fetched successfully")
        return equipment, usage_data
    except Exception as e:
        print(f"DB error: {e}")
        return None, str(e)

app.layout = html.Div([
    html.H1("Тепловая карта"),
    dcc.DatePickerSingle(
        id='date-picker',
        min_date_allowed=datetime(2024, 5, 1),
        max_date_allowed=datetime(2025, 12, 31),
        initial_visible_month=default_date,
        date=default_date
    ),
    html.Div(id='error-message', style={'color': 'white'}),
    dcc.Graph(id='heatmap-graph')
])

@app.callback(
    [Output('heatmap-graph', 'figure'),
     Output('error-message', 'children')],
    Input('date-picker', 'date')
)
def update_heatmap(selected_date):
    print(f"Selected date: {selected_date}")
    if selected_date is None:
        selected_date = default_date.strftime('%Y-%m-%d')

    equipment, result = fetch_data(selected_date)

    if equipment is None:
        fig = go.Figure()
        fig.update_layout(title="Ошибка загрузки данных")
        return fig, f"Ошибка: {result}"

    fig = go.Figure(data=go.Heatmap(
        z=result,
        x=time_intervals,
        y=equipment,
        colorscale=[[0, 'white'], [1, 'blue']],  # Дискретные цвета
        showscale=True,
        colorbar=dict(
            title='Состояние',
            tickvals=[0, 1],  # Только два значения
            ticktext=['Свободно', 'Забронировано'],
            tickmode='array',  # Режим массива для дискретных значений
            lenmode="pixels",
            len=200,
            outlinecolor='black',  # Граница легенды
            outlinewidth=1
        ),
        zmin=0,
        zmax=1
    ))
    fig.update_layout(
        title=f'Использование оборудования ({selected_date[:10]})',
        xaxis_title='Время',
        yaxis_title='Оборудование',
        xaxis=dict(tickangle=45, tickvals=time_intervals[::2]),
        width=1500,
        height=1000,
        shapes=[
            dict(type="line", x0=i-0.5, x1=i-0.5, y0=-0.5, y1=len(equipment)-0.5, line=dict(color="black", width=1))
            for i in range(len(time_intervals))
        ] + [
            dict(type="line", x0=-0.5, x1=len(time_intervals)-0.5, y0=i-0.5, y1=i-0.5, line=dict(color="black", width=1))
            for i in range(len(equipment))
        ]
    )
    print("Figure created")
    return fig, ""

if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8081)