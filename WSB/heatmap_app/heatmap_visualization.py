# --- START OF FILE heatmap_visualization.py ---

import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, callback_context
from datetime import datetime, timedelta, date, time
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import os
import logging
from typing import Tuple, Optional, List, Dict, Union
from urllib.parse import parse_qs
import pytz

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
logger = logging.getLogger(__name__)

# --- Загрузка переменных окружения ---
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_SSLMODE = os.getenv("DB_SSLMODE", "prefer")

required_db_vars = {"DB_USER", "DB_NAME", "DB_HOST", "DB_PORT"}
missing_vars = {var for var in required_db_vars if not os.getenv(var)}
if missing_vars:
    logger.critical(f"Критическая ошибка: Не заданы обязательные переменные окружения для подключения к БД: {missing_vars}")
    exit(1)

# --- Статусы и их представление для WSB (без confirm_start) ---
STATUS_CODES = {
    "free": 0,
    "booked_future": 1,       # Забронировано, еще не началось (или уже прошло плановое окончание, но не было finish)
    "active_usage": 2,        # Активно используется (текущее время внутри [start, end) и нет finish)
    "finished_usage": 3,      # Завершено (либо по кнопке 'finish', либо по расписанию)
}

STATUS_NAME_TO_COLOR = {
    "free": 'rgb(255, 255, 255)',
    "booked_future": 'rgb(173, 216, 230)', # LightBlue
    "active_usage": 'rgb(50, 205, 50)',    # LimeGreen
    "finished_usage": 'rgb(211, 211, 211)', # LightGrey
}

STATUS_NAME_TO_RUSSIAN = {
    "free": "Свободно",
    "booked_future": "Забронировано",
    "active_usage": "Используется",
    "finished_usage": "Завершено",
}

for status_name_code_val in STATUS_CODES:
    if status_name_code_val not in STATUS_NAME_TO_COLOR:
        STATUS_NAME_TO_COLOR[status_name_code_val] = 'grey'
    if status_name_code_val not in STATUS_NAME_TO_RUSSIAN:
        STATUS_NAME_TO_RUSSIAN[status_name_code_val] = status_name_code_val.replace('_', ' ').capitalize()

app = Dash(__name__, title="Тепловая карта WSB")
time_intervals = [f'{h:02d}:{m:02d}' for h in range(24) for m in range(0, 60, 30)]
default_date_obj = date.today()

def ensure_naive_datetime(dt_object: Optional[datetime], target_timezone_str: Optional[str] = None) -> Optional[datetime]:
    if dt_object is None:
        return None
    if dt_object.tzinfo is None or dt_object.tzinfo.utcoffset(dt_object) is None:
        return dt_object
    try:
        if target_timezone_str:
            target_tz = pytz.timezone(target_timezone_str)
            return dt_object.astimezone(target_tz).replace(tzinfo=None)
        else:
            return dt_object.astimezone().replace(tzinfo=None)
    except Exception as e_tz:
        logger.warning(f"Ошибка приведения времени {dt_object} к таймзоне ({target_timezone_str or 'локальная'}): {e_tz}. Возвращается как есть.")
        return dt_object

def fetch_data_wsb(selected_date_str: str) -> Tuple[Optional[List[str]], Optional[np.ndarray], Optional[str]]:
    logger.info(f"Запрос данных WSB для даты: {selected_date_str}")
    conn = None
    selected_date_obj: Optional[date] = None
    try:
        selected_date_obj = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        logger.error(f"Некорректный формат даты в fetch_data_wsb: '{selected_date_str}'")
        return None, None, "Ошибка: Некорректный формат даты. Ожидается ГГГГ-ММ-ДД."

    try:
        conn_params = {
            "dbname": DB_NAME, "user": DB_USER, "password": DB_PASSWORD,
            "host": DB_HOST, "port": DB_PORT, "sslmode": DB_SSLMODE,
            "connect_timeout": 5, "cursor_factory": RealDictCursor
        }
        conn = psycopg2.connect(**conn_params)
        logger.info(f"Успешное подключение к БД WSB: {DB_NAME}@{DB_HOST}")
        cur = conn.cursor()

        cur.execute("SELECT id, name_equip FROM equipment ORDER BY name_equip ASC")
        equipment_result = cur.fetchall()
        
        if not equipment_result:
            logger.info("В базе данных нет оборудования.")
            return [], np.array([]), None 

        equipment_names_for_y_axis = [row['name_equip'] for row in equipment_result]
        equipment_map: Dict[int, Dict[str, Union[str, int]]] = \
            {row['id']: {'name': row['name_equip'], 'idx': i} for i, row in enumerate(equipment_result)}
        
        num_equipment = len(equipment_names_for_y_axis)
        num_time_slots = len(time_intervals)
        usage_data = np.full((num_equipment, num_time_slots), STATUS_CODES["free"], dtype=int)
        
        # --- НОВАЯ МАТРИЦА ДЛЯ ПОДСКАЗОК ---
        hover_texts = np.full((num_equipment, num_time_slots), "", dtype=object) # dtype=object для строк

        # Модифицируем запрос, чтобы получать user_fi (если он еще не получается)
        query_bookings = """
            SELECT b.equip_id, b.time_start, b.time_end, b.finish, u.fi as user_fi 
            FROM bookings b
            JOIN users u ON b.user_id = u.users_id
            WHERE b.date = %s AND b.cancel = FALSE
        """
        cur.execute(query_bookings, (selected_date_obj,))
        bookings = cur.fetchall()
        logger.info(f"Найдено {len(bookings)} не отмененных бронирований на {selected_date_str}.")

        # ... (логика effective_now_for_status_check как раньше) ...
        now_naive_local = datetime.now()
        effective_now_for_status_check = now_naive_local
        if selected_date_obj < date.today():
            effective_now_for_status_check = datetime.combine(selected_date_obj, time(23, 59, 59))
        elif selected_date_obj > date.today():
            effective_now_for_status_check = datetime.combine(selected_date_obj, time(0, 0, 0))


        for booking in bookings:
            equip_id = booking.get('equip_id')
            db_time_start_raw: Optional[datetime] = booking.get('time_start')
            db_time_end_raw: Optional[datetime] = booking.get('time_end')
            db_finish_time_raw: Optional[datetime] = booking.get('finish')
            user_fi: Optional[str] = booking.get('user_fi') # Получаем ФИО

            db_time_start = ensure_naive_datetime(db_time_start_raw)
            db_time_end = ensure_naive_datetime(db_time_end_raw)
            db_finish_time = ensure_naive_datetime(db_finish_time_raw)

            if not (equip_id and db_time_start and db_time_end):
                logger.warning(f"Пропуск брони из-за неполных данных или ошибки конвертации времени: {booking}")
                continue
            
            equipment_meta = equipment_map.get(equip_id)
            if not equipment_meta:
                 logger.warning(f"Бронирование для неизвестного оборудования equip_id {equip_id}. Пропуск.")
                 continue
            
            equip_idx = int(equipment_meta['idx'])
            
            for i in range(num_time_slots):
                slot_hour, slot_minute = map(int, time_intervals[i].split(':'))
                current_slot_start_dt = datetime.combine(selected_date_obj, time(slot_hour, slot_minute))
                current_slot_end_dt = current_slot_start_dt + timedelta(minutes=30)
                
                effective_booking_end_for_overlap = db_finish_time if db_finish_time else db_time_end
                is_overlapping = (db_time_start < current_slot_end_dt and effective_booking_end_for_overlap > current_slot_start_dt)

                if is_overlapping:
                    determined_status_code = STATUS_CODES["free"]
                    hover_text_for_slot = "" # Текст подсказки по умолчанию

                    # ... (ваша логика определения determined_status_code как раньше) ...
                    # 1. Если бронь была фактически завершена (по кнопке "Финиш")
                    if db_finish_time:
                        if current_slot_start_dt < db_finish_time and current_slot_start_dt >= db_time_start :
                            determined_status_code = STATUS_CODES["finished_usage"]
                            hover_text_for_slot = f"Завершено: {user_fi if user_fi else 'N/A'}"
                    # 2. Если бронь НЕ завершена фактически
                    else:
                        if current_slot_start_dt >= db_time_start and current_slot_start_dt < db_time_end:
                            if effective_now_for_status_check >= db_time_end:
                                determined_status_code = STATUS_CODES["finished_usage"]
                                hover_text_for_slot = f"Завершено (по времени): {user_fi if user_fi else 'N/A'}"
                            else:
                                if effective_now_for_status_check >= db_time_start:
                                    determined_status_code = STATUS_CODES["active_usage"]
                                    hover_text_for_slot = f"Используется: {user_fi if user_fi else 'N/A'}"
                                else: 
                                    determined_status_code = STATUS_CODES["booked_future"]
                                    hover_text_for_slot = f"Забронировано: {user_fi if user_fi else 'N/A'}"
                        elif determined_status_code == STATUS_CODES["free"]:
                             if current_slot_start_dt < db_time_end and current_slot_end_dt > db_time_start:
                                 if effective_now_for_status_check < db_time_start:
                                     determined_status_code = STATUS_CODES["booked_future"]
                                     hover_text_for_slot = f"Забронировано: {user_fi if user_fi else 'N/A'}"
                    # --- КОНЕЦ ЛОГИКИ СТАТУСА ---

                    if determined_status_code != STATUS_CODES["free"]:
                        if usage_data[equip_idx][i] == STATUS_CODES["free"] or \
                           determined_status_code > usage_data[equip_idx][i]: # Если новый статус "важнее"
                            usage_data[equip_idx][i] = determined_status_code
                            hover_texts[equip_idx][i] = hover_text_for_slot 
                        elif determined_status_code == usage_data[equip_idx][i] and not hover_texts[equip_idx][i]:
                            # Если статус тот же, но текст подсказки еще не установлен (например, для booked_future от другой брони)
                            hover_texts[equip_idx][i] = hover_text_for_slot
                            
        # Заполняем подсказки для свободных ячеек
        for r in range(num_equipment):
            for c in range(num_time_slots):
                if usage_data[r][c] == STATUS_CODES["free"] and not hover_texts[r][c]:
                    hover_texts[r][c] = STATUS_NAME_TO_RUSSIAN["free"]
        
        logger.info(f"Матрицы занятости и подсказок WSB для {selected_date_str} успешно сформированы.")
        return equipment_names_for_y_axis, usage_data, hover_texts, None # Возвращаем hover_texts

    except psycopg2.OperationalError as e_op:
        logger.error(f"Ошибка подключения к БД WSB: {e_op}", exc_info=True)
        return None, None, None, f"Ошибка подключения к БД ({e_op}). Проверьте креды и доступность БД." # Добавили None для hover_texts
    except Exception as e_fetch:
        logger.error(f"Неожиданная ошибка при получении данных WSB: {e_fetch}", exc_info=True)
        return None, None, None, f"Неожиданная ошибка: {e_fetch}" # Добавили None для hover_texts
    finally:
        if conn:
            conn.close()
            logger.info("Соединение с БД WSB закрыто.")

app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.H1("Тепловая карта занятости оборудования (WSB)"),
    dcc.DatePickerSingle(
        id='date-picker-wsb',
        min_date_allowed=date(2024, 1, 1),
        max_date_allowed=date.today() + timedelta(days=365), # Увеличим диапазон в будущее
        initial_visible_month=default_date_obj,
        date=default_date_obj.strftime('%Y-%m-%d'),
        display_format='DD-MM-YYYY',
        className='date-picker-style',
        style={'width': '200px', 'margin-bottom': '20px'}
    ),
    html.Div(id='error-message-wsb', style={'color': 'red', 'margin-top': '10px', 'white-space': 'pre-line'}),
    dcc.Graph(id='heatmap-graph-wsb', figure={}, style={'height': '80vh'})
], style={'font-family': 'Arial, sans-serif', 'padding': '20px'})

@app.callback(
    [Output('heatmap-graph-wsb', 'figure'),
     Output('error-message-wsb', 'children'),
     Output('date-picker-wsb', 'date')],
    [Input('date-picker-wsb', 'date'),
     Input('url', 'search')]
)
def update_heatmap_wsb(selected_date_from_picker_str: Optional[str], url_search: Optional[str]):
    # ... (логика определения final_selected_date_str и date_to_set_in_picker_obj как раньше) ...
    ctx = callback_context # Добавьте эту строку, если ее не было
    triggered_input_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered and ctx.triggered[0] else 'date-picker-wsb'

    final_selected_date_str: str
    date_to_set_in_picker_obj: date

    if triggered_input_id == 'url' and url_search:
        try:
            query_params = parse_qs(url_search.lstrip('?'))
            date_from_url_list = query_params.get('date', [])
            if date_from_url_list:
                date_from_url_str = date_from_url_list[0]
                datetime.strptime(date_from_url_str, '%Y-%m-%d') 
                final_selected_date_str = date_from_url_str
            else: 
                final_selected_date_str = selected_date_from_picker_str if selected_date_from_picker_str else default_date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            final_selected_date_str = selected_date_from_picker_str if selected_date_from_picker_str else default_date_obj.strftime('%Y-%m-%d')
    else: 
        final_selected_date_str = selected_date_from_picker_str if selected_date_from_picker_str else default_date_obj.strftime('%Y-%m-%d')
    
    try:
        date_to_set_in_picker_obj = datetime.strptime(final_selected_date_str, '%Y-%m-%d').date()
    except ValueError: 
        final_selected_date_str = default_date_obj.strftime('%Y-%m-%d')
        date_to_set_in_picker_obj = default_date_obj
    # --- Конец логики определения даты ---

    logger.info(f"Обновление тепловой карты WSB для итоговой даты: {final_selected_date_str}")
    
    # Теперь fetch_data_wsb возвращает 4 значения
    equipment_names, usage_data, hover_texts_matrix, error_msg = fetch_data_wsb(final_selected_date_str)

    fig = go.Figure()
    # ... (обновление layout как раньше) ...
    fig.update_layout(
        title_text=f'Занятость оборудования на {final_selected_date_str}',
        xaxis_title='Время', # Можно оставить или убрать, если есть метки на оси
        yaxis_title='Оборудование', # Можно оставить или убрать
        xaxis=dict(tickangle=-45, tickvals=time_intervals[::2], showgrid=True, gridcolor='whitesmoke', zeroline=False),
        yaxis=dict(showgrid=True, gridcolor='whitesmoke', autorange="reversed", zeroline=False),
        plot_bgcolor='rgb(245,245,245)', paper_bgcolor='white',
        autosize=True,
        height=max(500, len(equipment_names) * 30 + 200) if equipment_names else 500, 
        margin=dict(l=max(150, len(max(equipment_names, key=len, default=""))*7 + 40) if equipment_names else 150, r=50, b=100, t=80, pad=4) 
    )


    if error_msg:
        # ... (обработка error_msg как раньше) ...
        fig.add_annotation(text=error_msg, xref="paper", yref="paper", showarrow=False, font={"size": 16})
        return fig, error_msg, date_to_set_in_picker_obj.strftime('%Y-%m-%d')


    if equipment_names is None or usage_data is None or hover_texts_matrix is None: # Проверяем и hover_texts_matrix
        # ... (обработка отсутствия данных как раньше) ...
        no_data_msg = "Нет данных для отображения (внутренняя ошибка)."
        fig.add_annotation(text=no_data_msg, xref="paper", yref="paper", showarrow=False, font={"size": 16})
        return fig, no_data_msg, date_to_set_in_picker_obj.strftime('%Y-%m-%d')
        
    if not equipment_names: 
        # ... (обработка отсутствия оборудования как раньше) ...
        no_equip_msg = "Нет оборудования для отображения."
        fig.add_annotation(text=no_equip_msg, xref="paper", yref="paper", showarrow=False, font={"size": 16})
        return fig, None, date_to_set_in_picker_obj.strftime('%Y-%m-%d')

    # ... (логика colorscale и colorbar tickvals/ticktext как раньше) ...
    unique_status_codes_defined = sorted(list(set(STATUS_CODES.values())))
    plot_discrete_colorscale = []
    num_defined_statuses = len(unique_status_codes_defined)
    code_to_name_map = {v: k for k, v in STATUS_CODES.items()}

    if num_defined_statuses > 0:
        sorted_unique_codes = sorted(unique_status_codes_defined)
        for i, code_val in enumerate(sorted_unique_codes):
            status_name = code_to_name_map.get(code_val, "unknown")
            color = STATUS_NAME_TO_COLOR.get(status_name, 'grey')
            norm_start = i / num_defined_statuses
            norm_end = (i + 1) / num_defined_statuses
            if i == 0: plot_discrete_colorscale.append([0.0, color])
            else: plot_discrete_colorscale.append([norm_start, color])
            if i == num_defined_statuses - 1: plot_discrete_colorscale.append([1.0, color])
            else: plot_discrete_colorscale.append([norm_end, color])
    else:
        plot_discrete_colorscale = [[0, 'white'], [1, 'white']]

    final_colorscale = []
    if plot_discrete_colorscale: # Ваша логика формирования final_colorscale
        temp_scale = sorted(plot_discrete_colorscale, key=lambda x: x[0])
        final_colorscale = temp_scale
        if not final_colorscale or final_colorscale[0][0] > 0:
            first_color = final_colorscale[0][1] if final_colorscale else 'lightgrey'
            final_colorscale.insert(0, [0.0, first_color])
        if final_colorscale[-1][0] < 1.0:
            last_color = final_colorscale[-1][1]
            final_colorscale.append([1.0, last_color])
        if final_colorscale: 
            final_colorscale[0][0] = 0.0
            final_colorscale[-1][0] = 1.0


    tick_values_for_bar = sorted(unique_status_codes_defined)
    tick_texts_for_bar = [STATUS_NAME_TO_RUSSIAN.get(code_to_name_map.get(code, "unknown"), "Неизв.") for code in tick_values_for_bar]
    # --- Конец логики colorscale ---

    fig_data_heatmap = go.Heatmap(
        z=usage_data,
        x=time_intervals,
        y=equipment_names, 
        colorscale=final_colorscale if final_colorscale else "Greys",
        showscale=True if final_colorscale else False,
        xgap=1, ygap=1,
        colorbar=dict(
            title='Состояние оборудования',
            tickvals=tick_values_for_bar,
            ticktext=tick_texts_for_bar,
            tickmode='array',
            lenmode="pixels", len=max(150, num_defined_statuses * 35 + 40), # Динамическая длина
            thicknessmode="pixels", thickness=15,
            outlinecolor='grey', outlinewidth=1
        ),
        zmin=min(STATUS_CODES.values()) if STATUS_CODES else 0,
        zmax=max(STATUS_CODES.values()) if STATUS_CODES else 0,
        # --- ДОБАВЛЯЕМ ИНФОРМАЦИЮ ДЛЯ HOVER ---
        hoverinfo='text', # Указываем, что текст для hover будет взят из hovertext
        hovertext=hover_texts_matrix # Передаем нашу матрицу с текстами подсказок
        # Альтернатива с hovertemplate (более гибко, если нужно форматировать):
        # customdata=hover_texts_matrix, # Передаем данные
        # hovertemplate="<b>Оборудование:</b> %{y}<br>" +
        #               "<b>Время:</b> %{x}<br>" +
        #               "<b>Статус:</b> %{z}<br>" + # %{z} будет значением из usage_data
        #               "<b>Детали:</b> %{customdata}<extra></extra>" # %{customdata} будет из hover_texts_matrix
    )
    fig = go.Figure(data=[fig_data_heatmap])
    # Обновление layout должно быть после создания Figure с данными
    fig.update_layout(
        title_text=f'Занятость оборудования на {final_selected_date_str}',
        xaxis_title='Время',
        yaxis_title='Оборудование',
        xaxis=dict(tickangle=-45, tickvals=time_intervals[::2], showgrid=True, gridcolor='whitesmoke', zeroline=False),
        yaxis=dict(showgrid=True, gridcolor='whitesmoke', autorange="reversed", zeroline=False),
        plot_bgcolor='rgb(245,245,245)', paper_bgcolor='white',
        autosize=True,
        height=max(500, len(equipment_names) * 30 + 200), 
        margin=dict(l=max(150, len(max(equipment_names, key=len, default=""))*7 + 40), r=50, b=100, t=80, pad=4) 
    )
    
    logger.info(f"График WSB для {final_selected_date_str} успешно создан/обновлен.")
    return fig, None, date_to_set_in_picker_obj.strftime('%Y-%m-%d')

if __name__ == '__main__':
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('plotly').setLevel(logging.INFO) 
    
    app.run(debug=True, host='0.0.0.0', port=8082)
# --- END OF FILE heatmap_visualization.py ---