# --- START OF FILE heatmap_visualization.py ---

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output
from datetime import datetime, timedelta, date # Добавим date
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor # Используем DictCursor для удобства
from dotenv import load_dotenv
import os
import logging # Добавим логирование
from typing import Tuple, Optional, List, Dict # Добавлен Dict


# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Загрузка переменных окружения ---
load_dotenv() # Загружаем из .env в текущей директории или системных переменных

# Используем те же переменные окружения, что и бот
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME") # Должно быть CR для CRB
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_SSLMODE = os.getenv("DB_SSLMODE", "prefer")


STATUS_CODES = {
    "free": 0,
    "pending_confirmation": 1,
    "confirmed": 2,
    "active": 3,
    "finished": 4,
    # "cancelled": 5 # Если решим показывать отмененные
}


# Словарь: строковый статус -> цвет
# Эти цвета будут использоваться для построения colorscale
STATUS_NAME_TO_COLOR = {
    "free": 'white',
    "pending_confirmation": 'lightgreen',
    "confirmed": 'mediumseagreen',
    "active": 'forestgreen',
    "finished": 'lightblue',
    # "cancelled": 'lightgrey',
}

# --- НОВЫЙ СЛОВАРЬ: Английское имя статуса -> Русское название для легенды ---
STATUS_NAME_TO_RUSSIAN = {
    "free": "Свободно",
    "pending_confirmation": "Ожидает подтверждения",
    "confirmed": "Подтверждено",
    "active": "Активно",
    "finished": "Завершено",
}
# --- КОНЕЦ НОВОГО СЛОВАРЯ ---

# Проверка, что для каждого кода статуса есть цвет и русское название
for status_name in STATUS_CODES.keys():
    if status_name not in STATUS_NAME_TO_COLOR:
        logger.warning(f"Для статуса '{status_name}' не определен цвет. Будет использован дефолтный.")
        STATUS_NAME_TO_COLOR[status_name] = 'grey' # Дефолтный цвет
    if status_name not in STATUS_NAME_TO_RUSSIAN:
        logger.warning(f"Для статуса '{status_name}' не определено русское название. Будет использовано англ. название.")
        STATUS_NAME_TO_RUSSIAN[status_name] = status_name.replace('_', ' ').capitalize() # Дефолтное название

# Проверка критически важных переменных
required_vars = {"DB_USER", "DB_PASSWORD", "DB_NAME", "DB_HOST", "DB_PORT"}
if not all(os.getenv(var) for var in required_vars):
    missing = {var for var in required_vars if not os.getenv(var)}
    logger.critical(f"Ошибка: Не заданы переменные окружения для БД: {missing}")
    exit(1) # Завершаем работу, если нет данных для подключения

# --- Инициализация Dash приложения ---
# Используем __name__, чтобы Dash мог найти статические файлы, если они понадобятся
app = Dash(__name__)

# --- Константы и настройки графика ---
# Генерируем временные интервалы (00:00, 00:30, ..., 23:30)
time_intervals = [f'{h:02d}:{m:02d}' for h in range(24) for m in range(0, 60, 30)]
# Устанавливаем дату по умолчанию на вчера (или сегодня, если хотите)
default_date = datetime.now().date() # Берем сегодняшнюю дату

# --- Функция получения данных из БД ---
def fetch_data(selected_date_str: str) -> Tuple[Optional[List[str]], Optional[np.ndarray], Optional[str]]:
    logger.info(f"Запрос данных для даты: {selected_date_str}")
    conn = None
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        return None, None, "Некорректный формат даты."

    try:
        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, sslmode=DB_SSLMODE, connect_timeout=5, cursor_factory=RealDictCursor)
        logger.info("Успешное подключение к БД.")
        cur = conn.cursor()

        cur.execute("SELECT id, cr_name FROM conferenceroom ORDER BY cr_name")
        rooms_result = cur.fetchall()
        conference_rooms_map = {row['id']: {'name': row['cr_name'], 'idx': i} for i, row in enumerate(rooms_result)}
        conference_room_names = [conference_rooms_map[room_id]['name'] for room_id in sorted(conference_rooms_map.keys(), key=lambda x: conference_rooms_map[x]['name'])]


        if not conference_room_names:
            return None, None, "В базе данных нет переговорных комнат."
        
        usage_data = np.full((len(conference_room_names), len(time_intervals)), STATUS_CODES["free"], dtype=int)

        # Запрос статуса. Если вы НЕ хотите показывать отмененные, добавьте AND b.status != 'cancelled'
        query = """
            SELECT b.cr_id, b.time_start, b.time_end, b.status
            FROM bookings b
            WHERE b.date = %s
            AND b.status != 'cancelled'
        """
        cur.execute(query, (selected_date,))
        bookings = cur.fetchall()
        logger.info(f"Найдено {len(bookings)} бронирований (всех статусов) на {selected_date_str}.")

        for booking in bookings:
            cr_id = booking['cr_id']
            time_start = booking['time_start']
            time_end = booking['time_end']
            status = booking['status'] 

            if not (isinstance(time_start, datetime) and isinstance(time_end, datetime)):
                logger.warning(f"Пропуск брони для cr_id {cr_id}: некорректные типы time_start/time_end")
                continue
            
            room_meta = conference_rooms_map.get(cr_id)
            if not room_meta:
                 logger.warning(f"Бронирование для неизвестной комнаты cr_id {cr_id}. Пропуск.")
                 continue
            room_idx = room_meta['idx']
            
            status_code = STATUS_CODES.get(status, STATUS_CODES["active"]) # Дефолт если статус неизвестен

            start_slot_minute = (time_start.hour * 60 + time_start.minute) // 30 * 30
            start_idx = start_slot_minute // 30
            end_total_minutes = time_end.hour * 60 + time_end.minute
            end_slot_minute = ((end_total_minutes + 29) // 30) * 30 # Округление вверх
            end_idx = min(end_slot_minute // 30, len(time_intervals))

            if start_idx < end_idx:
                for i in range(start_idx, end_idx):
                    if i < len(time_intervals):
                        # Логика перезаписи: если текущий слот свободен ИЛИ
                        # новый статус "важнее" (например, active важнее pending)
                        # Предполагаем, что коды в STATUS_CODES идут по возрастанию "важности"
                        if usage_data[room_idx][i] == STATUS_CODES["free"] or status_code > usage_data[room_idx][i]:
                             usage_data[room_idx][i] = status_code
                        # Если status_code такой же, как уже есть, ничего не делаем (это нормально для пересекающихся записей одного статуса)
                        # Если status_code "менее важный", тоже ничего не делаем
                    else:
                        logger.warning(f"Индекс слота {i} вышел за пределы для cr_id {cr_id}")
        
        logger.info(f"Матрица занятости для {selected_date_str} успешно сформирована.")
        return conference_room_names, usage_data, None

    except psycopg2.OperationalError as e:
        return None, None, f"Ошибка подключения к БД: {e}"
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении данных: {e}", exc_info=True)
        return None, None, f"Неожиданная ошибка: {e}"
    finally:
        if conn: conn.close(); logger.info("Соединение с БД закрыто.")

# ... (app.layout как был) ...
app.layout = html.Div([
    html.H1("Тепловая карта занятости переговорных комнат"),
    dcc.DatePickerSingle(id='date-picker', min_date_allowed=date(2024,1,1), max_date_allowed=date(2030,12,31), initial_visible_month=default_date, date=default_date, display_format='DD-MM-YYYY'),
    html.Div(id='error-message', style={'color': 'red', 'margin-top': '10px'}),
    dcc.Graph(id='heatmap-graph', style={'height': '80vh'})
])

@app.callback(
    [Output('heatmap-graph', 'figure'),
     Output('error-message', 'children')],
    [Input('date-picker', 'date')]
)
def update_heatmap(selected_date_str):
    logger.info(f"Обновление графика для даты: {selected_date_str}")
    if selected_date_str is None: selected_date_str = default_date.strftime('%Y-%m-%d')

    conference_rooms, usage_data, error_msg = fetch_data(selected_date_str)

    if error_msg:
        fig_error = go.Figure()
        fig_error.update_layout(title=f"Ошибка: {selected_date_str}", xaxis={"visible":False}, yaxis={"visible":False}, annotations=[{"text":error_msg, "xref":"paper", "yref":"paper", "showarrow":False, "font":{"size":16}}])
        return fig_error, error_msg

    # --- Формируем colorscale и colorbar для всех статусов ---
    # Отсортированные коды и соответствующие им имена
    sorted_statuses_with_codes = sorted(STATUS_CODES.items(), key=lambda item: item[1])
    
    # Уникальные значения кодов для tickvals (должны быть числовыми)
    tick_values_for_bar = [item[1] for item in sorted_statuses_with_codes]
    # Тексты для colorbar
    # --- ИЗМЕНЕНИЕ: Используем STATUS_NAME_TO_RUSSIAN для ticktext ---
    tick_texts_for_bar = [STATUS_NAME_TO_RUSSIAN.get(item[0], item[0].replace('_', ' ').capitalize()) for item in sorted_statuses_with_codes]
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    
    num_distinct_codes = len(tick_values_for_bar)
    
    plot_discrete_colorscale = []

    if num_distinct_codes > 0:
        # Нормализация: значения кодов должны быть приведены к диапазону [0, 1] для colorscale
        # Если у нас коды 0, 1, 2, 3, 4 (всего 5 значений), то они будут соответствовать точкам на шкале.
        # Точка 0 -> 0.0, Точка 1 -> 1/4, Точка 2 -> 2/4, Точка 3 -> 3/4, Точка 4 -> 4/4=1.0 (если max_code = num_distinct_codes - 1)
        # или 0 -> 0.0, 1 -> 0.2, 2 -> 0.4, 3 -> 0.6, 4 -> 0.8 (если делим на num_distinct_codes, а не на max_code)
        # и последняя точка 1.0 будет иметь цвет последнего статуса.

        # Проверим, что коды статусов идут от 0 до N-1 без пропусков для простоты
        is_contiguous_from_zero = all(tick_values_for_bar[i] == i for i in range(num_distinct_codes))

        if not is_contiguous_from_zero:
            logger.warning("Коды статусов не идут последовательно от 0. Colorscale может быть неточной.")
            # В этом случае, более сложная логика нормализации может потребоваться,
            # но для текущих STATUS_CODES (0,1,2,3,4) это не проблема.

        for i in range(num_distinct_codes):
            current_code = tick_values_for_bar[i] # 0, 1, 2, 3, 4
            status_name = sorted_statuses_with_codes[i][0]
            color = STATUS_NAME_TO_COLOR.get(status_name, 'grey')

            # Нормализованное значение для начала этого цвета
            # Каждый цвет занимает 1/N долю шкалы
            start_norm = i / num_distinct_codes
            # Нормализованное значение для конца этого цвета
            end_norm = (i + 1) / num_distinct_codes
            
            if i == 0: # Для первого цвета, начинаем с 0
                plot_discrete_colorscale.append([0, color])
            else: # Для последующих, начинаем с val_start_norm
                plot_discrete_colorscale.append([start_norm, color])
            
            # Конечная точка для этого цвета
            if i == num_distinct_codes - 1: # Для последнего цвета, заканчиваем на 1.0
                 plot_discrete_colorscale.append([1.0, color])
            else:
                 plot_discrete_colorscale.append([end_norm, color])
    else:
        plot_discrete_colorscale = [[0, 'white'], [1, 'white']] # По умолчанию, если нет статусов

    # Удаляем дубликаты точек по значению, оставляя последний цвет для этого значения
    # (на случай, если из-за округлений или логики start_norm/end_norm получились одинаковые точки)
    final_colorscale = []
    seen_norm_values = set()
    # Идем в обратном порядке, чтобы сохранить цвет для "верхней" границы диапазона, если точки совпадают
    for norm_val, color_val in sorted(plot_discrete_colorscale, key=lambda x: x[0], reverse=True):
        # Округляем для сравнения, чтобы избежать проблем с float precision
        # Учитывая, что у нас всего несколько точек, это может быть излишне,
        # но для более сложных шкал полезно.
        # norm_val_rounded = round(norm_val, 5)
        if norm_val not in seen_norm_values: # Используем оригинальное значение для добавления в set
            final_colorscale.append([norm_val, color_val])
            seen_norm_values.add(norm_val)
    final_colorscale.sort(key=lambda x: x[0]) # Сортируем обратно

    # Убедимся, что colorscale начинается с 0 и заканчивается на 1
    if not final_colorscale:
        final_colorscale = [[0, 'lightgrey'], [1, 'lightgrey']] # Запасной вариант
    else:
        if final_colorscale[0][0] > 0:
            final_colorscale.insert(0, [0, final_colorscale[0][1]])
        if final_colorscale[-1][0] < 1:
            final_colorscale.append([1, final_colorscale[-1][1]])
        final_colorscale[0][0] = 0.0
        final_colorscale[-1][0] = 1.0


    logger.debug(f"Итоговая colorscale: {final_colorscale}")
    logger.debug(f"Tick values для colorbar: {tick_values_for_bar}")
    logger.debug(f"Tick texts для colorbar: {tick_texts_for_bar}")


    fig = go.Figure(data=go.Heatmap(
        z=usage_data,
        x=time_intervals,
        y=conference_rooms,
        colorscale=final_colorscale,
        showscale=True,
        xgap=1, ygap=1,
        colorbar=dict(
            title='Состояние',
            tickvals=tick_values_for_bar, # Используем оригинальные коды статусов (0, 1, 2, 3, 4)
            ticktext=tick_texts_for_bar,  # Соответствующие им текстовые подписи
            tickmode='array',
            lenmode="pixels", len=300,
            thicknessmode="pixels", thickness=20,
            outlinecolor='grey', outlinewidth=1
        ),
        zmin=min(STATUS_CODES.values()), # 0
        zmax=max(STATUS_CODES.values()), # 4
        # zauto=False # Важно для дискретных шкал, чтобы zmin/zmax использовались
    ))

    fig.update_layout(
        title=f'Занятость переговорных комнат на {selected_date_str}',
        xaxis_title='Время',
        yaxis_title='Переговорная комната',
        xaxis=dict(tickangle=45, tickvals=time_intervals[::2], showgrid=True, gridcolor='whitesmoke', zeroline=False),
        yaxis=dict(showgrid=True, gridcolor='whitesmoke', autorange="reversed", zeroline=False),
        plot_bgcolor='white',
        paper_bgcolor='white',
        autosize=True,
        height=max(600, len(conference_rooms) * 40 + 200),
        margin=dict(l=200, r=50, b=100, t=100, pad=4)
    )

    logger.info("График успешно создан/обновлен с разными статусами.")
    return fig, ""

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8081)