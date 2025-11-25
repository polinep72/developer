"""
Экспорт данных в PDF
"""
import io
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# Цвета фирменного стиля
PRIMARY_COLOR = colors.HexColor("#027BBC")
HEADER_BG = PRIMARY_COLOR
HEADER_TEXT = colors.white
BORDER_COLOR = colors.grey

# Стили текста
styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=16,
    textColor=PRIMARY_COLOR,
    alignment=1,  # center
    spaceAfter=20,
)
heading_style = ParagraphStyle(
    'CustomHeading',
    parent=styles['Heading2'],
    fontSize=12,
    textColor=PRIMARY_COLOR,
    spaceAfter=10,
)
normal_style = styles['Normal']


def export_bookings_pdf(
    csv_content: str,
    target_date: date,
    include_all: bool = False,
) -> bytes:
    """Экспорт бронирований в PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    
    # Заголовок
    title = f"Бронирования за {target_date.strftime('%d.%m.%Y')}"
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Парсим CSV данные (разделитель - точка с запятой)
    lines = csv_content.strip().split('\n')
    if not lines:
        story.append(Paragraph("Нет данных для экспорта", normal_style))
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    
    headers = lines[0].split(';')
    data = [line.split(';') for line in lines[1:] if line.strip()]
    
    # Создаем таблицу
    table_data = [headers] + data
    
    # Определяем ширину колонок
    num_cols = len(headers)
    if num_cols == 8:  # Все бронирования
        col_widths = [2.5*cm, 2*cm, 2*cm, 2*cm, 4*cm, 2.5*cm, 3*cm, 2*cm]
    else:  # Только мои бронирования
        col_widths = [2.5*cm, 2*cm, 2*cm, 2*cm, 4*cm, 2.5*cm, 2*cm]
    
    table = Table(table_data, colWidths=col_widths)
    
    # Стили таблицы
    table.setStyle(TableStyle([
        # Заголовок
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        # Границы
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Данные
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
    ]))
    
    story.append(table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_dashboard_pdf(
    payload: Dict[str, Any],
    filters: Dict[str, Any],
    start_date: date,
    end_date: date,
) -> bytes:
    """Экспорт данных дашборда в PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    
    # Заголовок
    story.append(Paragraph("Аналитика бронирований рабочих мест", title_style))
    story.append(Spacer(1, 0.3*cm))
    
    # Параметры фильтрации
    story.append(Paragraph("Параметры фильтрации", heading_style))
    
    params_data = [
        ["Начало периода", start_date.strftime("%d.%m.%Y")],
        ["Конец периода", end_date.strftime("%d.%m.%Y")],
        ["Оборудование", ", ".join(filters.get("equipment", [])) or "Все"],
        ["Целевая загрузка (ч/день)", str(filters.get("target_load", 8))],
        ["Фактическая загрузка", str(payload.get("utilization", "0%"))],
    ]
    
    params_table = Table(params_data, colWidths=[5*cm, 10*cm])
    params_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(params_table)
    story.append(Spacer(1, 0.5*cm))
    
    # Суммарная наработка по оборудованию
    story.append(Paragraph("Суммарная наработка по оборудованию", heading_style))
    
    equipment_summary = payload.get("equipmentSummary", [])
    if equipment_summary:
        eq_data = [["Прибор", "Часы"]]
        for item in equipment_summary:
            eq_data.append([
                item.get("name", ""),
                f"{item.get('hours', 0):.2f}"
            ])
        
        eq_table = Table(eq_data, colWidths=[10*cm, 5*cm])
        eq_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(eq_table)
    else:
        story.append(Paragraph("Нет данных", normal_style))
    
    story.append(Spacer(1, 0.5*cm))
    
    # Активность пользователей
    story.append(Paragraph("Активность пользователей", heading_style))
    
    users = payload.get("users", [])
    if users:
        users_data = [["Пользователь", "Часы"]]
        for item in users:
            users_data.append([
                item.get("name", ""),
                f"{item.get('hours', 0):.2f}"
            ])
        
        users_table = Table(users_data, colWidths=[10*cm, 5*cm])
        users_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(users_table)
    else:
        story.append(Paragraph("Нет данных", normal_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_equipment_pdf(
    equipment_data: List[Dict[str, Any]],
    equipment_type: str,
) -> bytes:
    """Экспорт данных оборудования в PDF"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    story = []
    
    # Название типа оборудования
    type_names = {
        "si": "Средства измерения (СИ)",
        "io": "Испытательное оборудование (ИО)",
        "vo": "Вспомогательное оборудование (ВО)",
        "gosregister": "Госреестр средств измерений",
    }
    title = type_names.get(equipment_type, "Оборудование")
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 0.3*cm))
    
    if not equipment_data:
        story.append(Paragraph("Нет данных для экспорта", normal_style))
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()
    
    # Определяем заголовки в зависимости от типа
    if equipment_type == "gosregister":
        headers = ["№", "Наименование", "Обозначение типа", "Зав. №", "№ Госреестра", "Дата поверки", "След. поверка"]
        col_widths = [1*cm, 4*cm, 3*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm]
    else:
        headers = ["№", "Наименование", "Обозначение типа", "Зав. №", "№ св-ва о поверке", "Дата поверки", "След. поверка", "Дней до поверки"]
        col_widths = [1*cm, 3.5*cm, 2.5*cm, 2*cm, 2.5*cm, 2*cm, 2*cm, 2*cm]
    
    # Формируем данные таблицы
    table_data = [headers]
    for idx, item in enumerate(equipment_data, 1):
        row = [str(idx)]
        
        if equipment_type == "gosregister":
            row.extend([
                item.get("name", ""),
                item.get("type_designation", ""),
                item.get("serial_number", ""),
                item.get("gosregister_number", ""),
                item.get("calibration_date", ""),
                item.get("next_calibration_date", ""),
            ])
        else:
            row.extend([
                item.get("name", ""),
                item.get("type_designation", ""),
                item.get("serial_number", ""),
                item.get("certificate_number", ""),
                item.get("calibration_date", ""),
                item.get("next_calibration_date", ""),
                item.get("days_until_calibration", ""),
            ])
        
        table_data.append(row)
    
    # Создаем таблицу
    table = Table(table_data, colWidths=col_widths)
    
    # Стили таблицы
    table.setStyle(TableStyle([
        # Заголовок
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        # Границы
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Данные
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    
    story.append(table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

