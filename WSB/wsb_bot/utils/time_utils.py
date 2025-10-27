# utils/time_utils.py
from typing import Optional, Union
from datetime import datetime, time, date
from logger import logger # Можно добавить логгер для отладки, если нужно

def format_time(t: Optional[Union[datetime, time]], default_value: str = '??:??') -> str:
    """
    Форматирует время (datetime.datetime или datetime.time) в строку HH:MM.
    """
    if isinstance(t, datetime):
        return t.strftime('%H:%M')
    elif isinstance(t, time):
        return t.strftime('%H:%M')
    else:
        if t is not None: # Логируем, если передан неожиданный тип, но не None
            logger.warning(f"Некорректный тип для format_time: {type(t)}, значение: {t}. Возвращено значение по умолчанию.")
        return default_value

def format_date(d: Optional[Union[datetime, date]], default_value: str = '??-??-????') -> str:
    """
    Форматирует дату (datetime.datetime или datetime.date) в строку DD-MM-YYYY.
    """
    if isinstance(d, (datetime, date)):
        return d.strftime('%d-%m-%Y')
    else:
        if d is not None: # Логируем, если передан неожиданный тип, но не None
            logger.warning(f"Некорректный тип для format_date: {type(d)}, значение: {d}. Возвращено значение по умолчанию.")
        return default_value

def format_datetime(dt: Optional[datetime], date_format: str = '%d-%m-%Y', time_format: str = '%H:%M', separator: str = ' ') -> str:
    """
    Форматирует datetime.datetime в строку "DD-MM-YYYY HH:MM" (или другой формат).
    """
    if isinstance(dt, datetime):
        return dt.strftime(f"{date_format}{separator}{time_format}")
    else:
        if dt is not None:
            logger.warning(f"Некорректный тип для format_datetime: {type(dt)}, значение: {dt}. Возвращено значение по умолчанию.")
        return f"{format_date(None, date_format)}{separator}{format_time(None, time_format)}"