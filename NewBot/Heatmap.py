import plotly.graph_objects as go
import numpy as np

# Список оборудования и временные интервалы
equipment = ['Токарный станок', 'Фрезерный станок', 'Пресс', 'Пресс2', 'Пресс3', 'Пресс4']
time_intervals = [f'{h:02d}:{m:02d}' for h in range(24) for m in range(0, 60, 30)]

# Создаем данные: только 0 или 1
usage_data = np.random.randint(0, 2, size=(len(equipment), len(time_intervals)))

# Создаем тепловую карту
fig = go.Figure(data=go.Heatmap(
    z=usage_data,
    x=time_intervals,
    y=equipment,
    colorscale=[[0, 'white'], [1, 'blue']],  # 0 - красный (выключено), 1 - зеленый (включено)
    colorbar=dict(
        title='Состояние',
        tickvals=[0, 1],
        ticktext=['Свободно', 'Забронировано']
    )
))

# Настраиваем внешний вид
fig.update_layout(
    title='Использование оборудования',
    xaxis_title='Время',
    yaxis_title='Оборудование',
    xaxis=dict(
        tickangle=45,
        tickvals=time_intervals[::2]  # Показываем каждый час
    ),
    width=1500,
    height=2000
)
# Добавляем вертикальные линии (границы между интервалами по X)
for i in range(len(time_intervals)):
    fig.add_shape(
        type="line",
        x0=i-0.5, x1=i-0.5,  # Смещение на -0.5 для центрирования между ячейками
        y0=-0.5, y1=len(equipment)-0.5,
        line=dict(color="black", width=1)
    )

# Добавляем горизонтальные линии (границы между оборудованием по Y)
for i in range(len(equipment)):
    fig.add_shape(
        type="line",
        x0=-0.5, x1=len(time_intervals)-0.5,
        y0=i-0.5, y1=i-0.5,  # Смещение на -0.5 для центрирования
        line=dict(color="black", width=1)
    )
# Показываем график
fig.show()