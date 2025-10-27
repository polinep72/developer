# --- START OF FILE keyboards.py ---

# utils/keyboards.py
from telebot import types
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    BotCommand
)
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timedelta, date, time
import constants as const
from logger import logger
# Импортируем только нужную функцию из сервиса
from services.booking_service import _format_time

# --- Команды для меню Telegram ---
USER_BOT_COMMANDS = [
    BotCommand("start", "🚀 Старт/Перезапуск"),
    BotCommand("help", "❓ Помощь"),
    BotCommand("booking", "📅 Бронировать"),
    BotCommand("mybookings", "📄 Мои бронирования"),
    BotCommand("cancel", "❌ Отменить бронь"),
    BotCommand("finish", "🏁 Завершить использование"),
    BotCommand("extend", "⏳ Продлить бронь"),
    BotCommand("workspacebookings", "🔬 Брони по месту"),
    BotCommand("datebookings", "🗓️ Брони по дате"),
]

# --- Reply Keyboards ---

def create_user_reply_keyboard() -> ReplyKeyboardMarkup:
    """Генерирует стандартную Reply клавиатуру для обычного пользователя."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    btn_help = KeyboardButton('/help')
    btn_booking = KeyboardButton('/booking')
    btn_cancel = KeyboardButton('/cancel')
    btn_finish = KeyboardButton('/finish')
    btn_extend = KeyboardButton('/extend')
    btn_mybookings = KeyboardButton('/mybookings')
    btn_workspacebookings = KeyboardButton('/workspacebookings')
    btn_datebookings = KeyboardButton('/datebookings')
    markup.add(btn_help)
    markup.add(btn_booking, btn_cancel, btn_finish)
    markup.add(btn_extend)
    markup.add(btn_mybookings, btn_workspacebookings, btn_datebookings)
    return markup

def create_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Генерирует Reply клавиатуру для администратора."""
    markup = create_user_reply_keyboard() # Начинаем с пользовательской
    btn_admin_help = KeyboardButton('/adminhelp')
    btn_add_equip = KeyboardButton('/add_equipment')
    btn_view_equip = KeyboardButton('/view_equipment')
    btn_admin_cancel = KeyboardButton('/admin_cancel')
    btn_all = KeyboardButton('/all')
    btn_broadcast = KeyboardButton('/broadcast')
    btn_manage_user = KeyboardButton('/manage_user')
    btn_users = KeyboardButton('/users')
    btn_schedule = KeyboardButton('/schedule')
    # Добавляем админские кнопки
    markup.add(btn_admin_help)
    markup.add(btn_add_equip, btn_view_equip)
    markup.add(btn_users, btn_manage_user)
    markup.add(btn_admin_cancel, btn_all)
    markup.add(btn_broadcast, btn_schedule)
    return markup

# --- Inline Keyboards ---

def _add_cancel_booking_button(markup: InlineKeyboardMarkup):
     """Добавляет кнопку отмены для процесса бронирования."""
     cancel_button = InlineKeyboardButton("❌ Отменить бронирование", callback_data=const.CB_BOOK_CANCEL_PROCESS)
     markup.add(cancel_button)

def generate_equipment_category_keyboard(categories: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора категории."""
    markup = InlineKeyboardMarkup(row_width=1) # Категории по одной в ряду
    if not categories:
        no_cat_button = InlineKeyboardButton("Нет категорий для выбора", callback_data=const.CB_IGNORE)
        markup.add(no_cat_button)
        _add_cancel_booking_button(markup)
        return markup

    for category in categories:
        cat_id = category.get('id')
        name = category.get('name_cat', 'Без имени')
        if cat_id is not None:
            button = InlineKeyboardButton(text=name, callback_data=f"{callback_prefix}{cat_id}")
            markup.add(button)
        else:
             logger.warning(f"Обнаружена категория без ID при генерации клавиатуры: {category}")

    _add_cancel_booking_button(markup) # Добавляем кнопку отмены процесса бронирования
    return markup

def generate_add_equipment_category_keyboard(categories: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру для выбора категории при добавлении оборудования.
    Включает существующие категории, кнопку "Добавить новую" и "Отмена".
    """
    markup = InlineKeyboardMarkup(row_width=1) # Категории по одной в ряду

    # Добавляем кнопки для существующих категорий
    if categories:
        for category in categories:
            cat_id = category.get('id')
            name = category.get('name_cat', 'Без имени')
            if cat_id is not None:
                # Используем новый префикс для выбора категории при добавлении
                callback_data = f"{const.CB_ADMIN_ADD_EQUIP_SELECT_CAT_}{cat_id}"
                button = InlineKeyboardButton(text=name, callback_data=callback_data)
                markup.add(button)
            else:
                 logger.warning(f"Обнаружена категория без ID при генерации клавиатуры добавления: {category}")

    # Добавляем кнопки "Добавить новую" и "Отмена" в отдельном ряду
    add_new_button = InlineKeyboardButton("➕ Добавить новую категорию", callback_data=const.CB_ADMIN_ADD_EQUIP_NEW_CAT)
    cancel_button = InlineKeyboardButton("❌ Отмена", callback_data=const.CB_ADMIN_ADD_EQUIP_CANCEL)
    markup.add(add_new_button, cancel_button) # Две кнопки в одном ряду

    return markup

def generate_equipment_keyboard(equipment: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру со списком оборудования."""
    markup = InlineKeyboardMarkup(row_width=1) # Оборудование по одному в ряду
    if not equipment:
        no_eq_button = InlineKeyboardButton("Нет доступного оборудования", callback_data=const.CB_IGNORE)
        markup.add(no_eq_button)
        _add_cancel_booking_button(markup) # Все равно добавляем отмену
        return markup

    for item in equipment:
        eq_id = item.get('id')
        name = item.get('name_equip', 'Без имени')
        if eq_id is not None:
            button = InlineKeyboardButton(text=name, callback_data=f"{callback_prefix}{eq_id}")
            markup.add(button)
        else:
             logger.warning(f"Обнаружено оборудование без ID при генерации клавиатуры: {item}")

    _add_cancel_booking_button(markup)
    return markup

def generate_date_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру выбора даты (ближайшие 7 дней)."""
    markup = InlineKeyboardMarkup(row_width=1) # Даты по одной в ряду для читаемости
    now = datetime.now().date()
    buttons: List[InlineKeyboardButton] = []
    for i in range(7):
        day = now + timedelta(days=i)
        day_str = day.strftime('%d-%m-%Y')
        callback = f"{callback_prefix}{day_str}"
        button = InlineKeyboardButton(text=day_str, callback_data=callback)
        buttons.append(button)

    if not buttons:
         no_dates_button = InlineKeyboardButton("Нет доступных дат", callback_data=const.CB_IGNORE)
         markup.add(no_dates_button)
    else:
        for btn in buttons:
            markup.add(btn) # Добавляем каждую кнопку в новый ряд

    _add_cancel_booking_button(markup)
    return markup

def generate_available_slots_keyboard(slots: List[Tuple[time, time]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора доступного временного слота."""
    markup = InlineKeyboardMarkup(row_width=1) # Слоты по одному в ряду
    if not slots:
        no_slots_button = InlineKeyboardButton("Нет доступных слотов", callback_data=const.CB_IGNORE)
        markup.add(no_slots_button)
        _add_cancel_booking_button(markup)
        return markup

    for i, slot in enumerate(slots):
        start_time = slot[0]
        end_time = slot[1]
        # Используем импортированную функцию форматирования
        start_str = _format_time(start_time)
        end_str = _format_time(end_time)
        callback = f"{callback_prefix}{i}" # Кодируем индекс слота
        button = InlineKeyboardButton(f"{start_str} - {end_str}", callback_data=callback)
        markup.add(button)

    _add_cancel_booking_button(markup)
    return markup

def generate_time_keyboard_in_slot(selected_slot: Tuple[time, time], selected_date: date, callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру времени начала бронирования внутри заданного слота."""
    markup = InlineKeyboardMarkup(row_width=4) # Несколько кнопок времени в ряду
    buttons: List[InlineKeyboardButton] = []
    slot_start = selected_slot[0]
    slot_end = selected_slot[1]
    time_step = const.BOOKING_TIME_STEP_MINUTES

    today = datetime.now().date()
    is_today = (selected_date == today)
    now_dt = datetime.now()
    earliest_start_time = time(0, 0) # Самое раннее время по умолчанию

    # Если выбран сегодняшний день, вычисляем ближайшее доступное время старта
    if is_today:
        # Округляем текущее время вверх до ближайшего шага
        minutes_to_add = 0
        if now_dt.minute % time_step != 0:
             minutes_to_add = time_step - (now_dt.minute % time_step)
        # Добавляем минуты и обнуляем секунды/микросекунды
        earliest_start_dt = now_dt + timedelta(minutes=minutes_to_add)
        earliest_start_time = earliest_start_dt.time().replace(second=0, microsecond=0)

    current_time_dt = datetime.combine(selected_date, slot_start)
    slot_end_dt = datetime.combine(selected_date, slot_end)

    # Генерируем кнопки времени
    while current_time_dt < slot_end_dt:
        current_time = current_time_dt.time()
        # Проверяем, что время начала не раньше конца слота
        # и что потенциальное окончание (через time_step) не позже конца слота
        potential_end_dt = current_time_dt + timedelta(minutes=time_step)

        is_after_slot_start = (current_time >= slot_start)
        is_after_earliest_today = (not is_today or current_time >= earliest_start_time)
        is_before_slot_end = (potential_end_dt <= slot_end_dt) # Проверяем, что хотя бы один шаг помещается

        if is_after_slot_start and is_after_earliest_today and is_before_slot_end:
            t_str = current_time.strftime('%H:%M')
            callback = f"{callback_prefix}{t_str}"
            button = InlineKeyboardButton(text=t_str, callback_data=callback)
            buttons.append(button)

        # Переходим к следующему шагу времени
        current_time_dt += timedelta(minutes=time_step)

    if not buttons:
        no_time_button = InlineKeyboardButton("Нет доступного времени", callback_data=const.CB_IGNORE)
        markup.add(no_time_button)
    else:
        row: List[InlineKeyboardButton] = []
        for btn in buttons:
            row.append(btn)
            # Если ряд заполнен, добавляем его и очищаем
            if len(row) == markup.row_width:
                markup.row(*row)
                row = []
        # Добавляем оставшиеся кнопки, если они есть
        if row:
            markup.row(*row)

    _add_cancel_booking_button(markup)
    return markup

def generate_duration_keyboard_in_slot(start_time: time, selected_date: date, slot_end_time: time, callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру длительности, ограниченную концом слота и MAX."""
    markup = InlineKeyboardMarkup(row_width=3) # 3 кнопки длительности в ряду
    buttons: List[InlineKeyboardButton] = []
    time_step_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    max_overall_duration = timedelta(hours=const.MAX_BOOKING_DURATION_HOURS)
    start_dt = datetime.combine(selected_date, start_time)
    slot_end_dt = datetime.combine(selected_date, slot_end_time)
    current_duration = time_step_delta # Начинаем с минимального шага

    while True:
        potential_end_dt = start_dt + current_duration

        # Проверяем условия выхода из цикла
        if current_duration <= timedelta(0): # На всякий случай
            break
        if current_duration > max_overall_duration: # Превышена максимальная длительность
            break
        if potential_end_dt > slot_end_dt: # Выход за пределы слота
            break

        # Форматируем строку длительности HH:MM
        total_seconds = current_duration.total_seconds()
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        dur_str = f"{int(hours):d}:{int(minutes):02d}"

        # Создаем кнопку
        callback = f"{callback_prefix}{dur_str}"
        button = InlineKeyboardButton(text=dur_str, callback_data=callback)
        buttons.append(button)

        # Увеличиваем длительность для следующей итерации
        current_duration += time_step_delta

    if not buttons:
        no_dur_button = InlineKeyboardButton("Нет доступной длительности", callback_data=const.CB_IGNORE)
        markup.add(no_dur_button)
    else:
        row: List[InlineKeyboardButton] = []
        for btn in buttons:
            row.append(btn)
            if len(row) == markup.row_width:
                markup.row(*row)
                row = []
        if row:
            markup.row(*row)

    _add_cancel_booking_button(markup)
    return markup

def generate_booking_confirmation_keyboard() -> InlineKeyboardMarkup:
     """Генерирует кнопки Да/Нет для финального подтверждения брони."""
     markup = InlineKeyboardMarkup(row_width=2)
     confirm_button = InlineKeyboardButton("✅ Подтвердить", callback_data=const.CB_BOOK_CONFIRM_FINAL)
     cancel_button = InlineKeyboardButton("❌ Отмена", callback_data=const.CB_BOOK_CANCEL_PROCESS)
     markup.add(confirm_button, cancel_button)
     return markup

def generate_user_bookings_keyboard(bookings: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру со списком бронирований пользователя."""
    markup = InlineKeyboardMarkup(row_width=1) # Каждая бронь в своем ряду
    if not bookings:
        no_bookings_button = InlineKeyboardButton("У вас нет активных бронирований", callback_data=const.CB_IGNORE)
        markup.add(no_bookings_button)
        return markup

    for booking in bookings:
        b_id = booking.get('id')
        eq_name = booking.get('name_equip', '???')
        b_date = booking.get('date')
        b_start = booking.get('time_start')
        b_end = booking.get('time_end')

        # Проверяем наличие всех необходимых данных
        if not all([b_id, b_date, b_start, b_end]):
             logger.warning(f"Неполные данные для бронирования при генерации клавиатуры: {booking}")
             continue # Пропускаем это бронирование

        # Форматируем дату и время
        date_str = "??.??"
        start_str = "??:??"
        end_str = "??:??"
        try:
            if isinstance(b_date, date):
                 date_str = b_date.strftime('%d.%m')
            else:
                 logger.warning(f"Некорректный тип даты {type(b_date)} для брони {b_id}")
                 date_str = str(b_date)

            if isinstance(b_start, time):
                 start_str = _format_time(b_start)
            else:
                 logger.warning(f"Некорректный тип времени начала {type(b_start)} для брони {b_id}")
                 start_str = str(b_start)

            if isinstance(b_end, time):
                 end_str = _format_time(b_end)
            else:
                 logger.warning(f"Некорректный тип времени конца {type(b_end)} для брони {b_id}")
                 end_str = str(b_end)

        except AttributeError as e:
             logger.warning(f"Ошибка форматирования даты/времени для брони {b_id}: {e}")
             # Используем строковые представления как запасной вариант

        # Обрезаем длинные названия оборудования
        max_len = 25
        display_name = eq_name
        if len(eq_name) > max_len:
             display_name = eq_name[:max_len] + '..'

        btn_text = f"{display_name} | {date_str} | {start_str}-{end_str}"
        button = InlineKeyboardButton(text=btn_text, callback_data=f"{callback_prefix}{b_id}")
        markup.add(button)

    # Добавляем кнопку "Отмена действия", если были брони
    if bookings:
        # Извлекаем контекст из префикса (убираем 'cb_' и последний '_')
        context_parts = callback_prefix.split('_')
        if len(context_parts) > 1:
             cancel_context = "_".join(context_parts[1:-1]) # Берем среднюю часть префикса
             if cancel_context:
                 cancel_button = InlineKeyboardButton("🔙 Назад / Отмена", callback_data=f"{const.CB_ACTION_CANCEL}{cancel_context}")
                 markup.add(cancel_button)

    return markup

def generate_equipment_list_with_delete_keyboard(equipment_list: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра и удаления оборудования админом."""
    markup = InlineKeyboardMarkup(row_width=2) # Имя и кнопка удаления в одном ряду
    if not equipment_list:
        no_equip_button = InlineKeyboardButton("Нет оборудования в базе", callback_data=const.CB_IGNORE)
        markup.add(no_equip_button)
        return markup

    for item in equipment_list:
        eq_id = item.get('id')
        eq_name = item.get('name_equip', '???')
        if eq_id is not None:
            # Кнопка с именем (некликабельная или игнорируемая)
            name_button = InlineKeyboardButton(text=f"{eq_name} (ID:{eq_id})", callback_data=const.CB_IGNORE)
            # Кнопка удаления
            delete_button = InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"{const.CB_EQUIP_DELETE_SELECT}{eq_id}")
            markup.add(name_button, delete_button)
        else:
             logger.warning(f"Обнаружено оборудование без ID в списке для удаления: {item}")

    return markup

def generate_admin_cancel_keyboard(bookings: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура для админа для выбора брони для отмены."""
    markup = InlineKeyboardMarkup(row_width=1) # Каждая бронь в своем ряду
    if not bookings:
        no_bookings_button = InlineKeyboardButton("Нет активных бронирований", callback_data=const.CB_IGNORE)
        markup.add(no_bookings_button)
        return markup

    for booking in bookings:
        b_id = booking.get('id')
        u_name = booking.get('user_name', '???') # Имя пользователя
        eq_name = booking.get('equipment_name', '???') # Имя оборудования
        b_date = booking.get('date')
        b_start = booking.get('time_start')
        b_end = booking.get('time_end')

        if not all([b_id, b_date, b_start, b_end]):
             logger.warning(f"Неполные данные для бронирования при генерации админ-клавиатуры отмены: {booking}")
             continue

        # Форматируем дату и время
        date_str = "??.??"
        start_str = "??:??"
        end_str = "??:??"
        try:
            if isinstance(b_date, date): date_str = b_date.strftime('%d.%m')
            else: date_str = str(b_date)
            if isinstance(b_start, time): start_str = _format_time(b_start)
            else: start_str = str(b_start)
            if isinstance(b_end, time): end_str = _format_time(b_end)
            else: end_str = str(b_end)
        except AttributeError as e:
             logger.warning(f"Ошибка форматирования даты/времени для брони {b_id} (админ-отмена): {e}")

        # Формируем текст кнопки, обрезая длинные имена
        max_name_len = 15
        user_display = u_name[:max_name_len] + '..' if len(u_name) > max_name_len else u_name
        equip_display = eq_name[:max_name_len] + '..' if len(eq_name) > max_name_len else eq_name
        btn_text = f"ID:{b_id} {user_display} | {equip_display} | {date_str} {start_str}-{end_str}"
        button = InlineKeyboardButton(text=btn_text, callback_data=f"{const.CB_ADMIN_CANCEL_SELECT}{b_id}")
        markup.add(button)

    return markup

def generate_confirmation_keyboard(
    confirm_callback: str,
    cancel_callback: str = const.CB_ACTION_CANCEL + "general", # Добавляем дефолтный контекст
    confirm_text: str = "✅ Да",
    cancel_text: str = "❌ Нет"
) -> InlineKeyboardMarkup:
    """Стандартная клавиатура Да/Нет для подтверждения действий."""
    markup = InlineKeyboardMarkup(row_width=2)
    confirm_button = InlineKeyboardButton(confirm_text, callback_data=confirm_callback)
    cancel_button = InlineKeyboardButton(cancel_text, callback_data=cancel_callback)
    markup.add(confirm_button, cancel_button)
    return markup

def generate_start_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Кнопка подтверждения начала брони из уведомления."""
    markup = InlineKeyboardMarkup(row_width=1)
    confirm_button = InlineKeyboardButton("✅ Подтвердить начало", callback_data=f"{const.CB_BOOK_CONFIRM_START}{booking_id}")
    markup.add(confirm_button)
    return markup

def generate_registration_confirmation_keyboard(temp_user_id: int) -> InlineKeyboardMarkup:
    """Кнопки подтверждения/отклонения регистрации админом."""
    markup = InlineKeyboardMarkup(row_width=2)
    confirm_button = InlineKeyboardButton("✅ Подтвердить", callback_data=f"{const.CB_REG_CONFIRM_USER}{temp_user_id}")
    decline_button = InlineKeyboardButton("❌ Отклонить", callback_data=f"{const.CB_REG_DECLINE_USER}{temp_user_id}")
    markup.add(confirm_button, decline_button)
    return markup

def generate_filter_options_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора типа фильтра для /all."""
    markup = InlineKeyboardMarkup(row_width=1) # Каждый тип фильтра в своем ряду
    users_button = InlineKeyboardButton("👥 По пользователю", callback_data=f"{const.CB_FILTER_BY_TYPE}users")
    equip_button = InlineKeyboardButton("🔬 По оборудованию", callback_data=f"{const.CB_FILTER_BY_TYPE}equipment")
    dates_button = InlineKeyboardButton("🗓️ По дате (месяц)", callback_data=f"{const.CB_FILTER_BY_TYPE}dates")
    markup.add(users_button)
    markup.add(equip_button)
    markup.add(dates_button)
    return markup

def generate_filter_selection_keyboard(options: List[Tuple[Any, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора значения для фильтра /all."""
    markup = InlineKeyboardMarkup(row_width=1) # Каждое значение в своем ряду
    if not options:
        no_data_button = InlineKeyboardButton("Нет данных для выбора", callback_data=const.CB_IGNORE)
        markup.add(no_data_button)
        return markup

    for text, val in options:
        # Обрезаем слишком длинный текст кнопки
        max_text_len = 50
        display_text = str(text)
        if len(display_text) > max_text_len:
             display_text = display_text[:max_text_len] + '...'

        button = InlineKeyboardButton(display_text, callback_data=f"{callback_prefix}{val}")
        markup.add(button)

    return markup

def generate_user_management_keyboard(users: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
     """Клавиатура выбора пользователя для управления админом."""
     markup = InlineKeyboardMarkup(row_width=1) # Каждый пользователь в своем ряду
     if not users:
         no_users_button = InlineKeyboardButton("Нет пользователей для управления", callback_data=const.CB_IGNORE)
         markup.add(no_users_button)
         return markup

     for user in users:
         u_id = user.get('users_id')
         name = user.get('fi', f'ID {u_id}') # Используем ФИ, если есть
         if u_id is not None:
             button = InlineKeyboardButton(text=name, callback_data=f"{const.CB_MANAGE_SELECT_USER}{u_id}")
             markup.add(button)
         else:
              logger.warning(f"Обнаружен пользователь без ID в списке для управления: {user}")

     return markup

def generate_user_status_keyboard(user_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
     """Кнопки Блок/Разблок/Назад для управления пользователем."""
     markup = InlineKeyboardMarkup(row_width=1) # Каждое действие в своем ряду
     # Кнопка действия (Блок или Разблок)
     if is_blocked:
         action_button = InlineKeyboardButton(text="🟢 Разблокировать пользователя", callback_data=f"{const.CB_MANAGE_UNBLOCK_USER}{user_id}")
     else:
         action_button = InlineKeyboardButton(text="🔴 Заблокировать пользователя", callback_data=f"{const.CB_MANAGE_BLOCK_USER}{user_id}")
     markup.add(action_button)

     # Кнопка Назад
     back_button = InlineKeyboardButton("🔙 Назад к списку пользователей", callback_data=const.CB_ACTION_CANCEL + "manage_user_list") # Используем контекст
     markup.add(back_button)
     return markup

def generate_extend_time_keyboard(booking_id: int, max_duration: Optional[timedelta] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени продления."""
    markup = InlineKeyboardMarkup(row_width=3) # 3 кнопки в ряду
    buttons: List[InlineKeyboardButton] = []
    current_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    # Определяем лимит: либо max_duration, либо стандартный максимум
    limit_duration = max_duration
    if limit_duration is None:
         limit_duration = timedelta(hours=const.MAX_BOOKING_DURATION_HOURS)
    # Убедимся, что лимит не отрицательный
    if limit_duration < timedelta(0):
         limit_duration = timedelta(0)

    time_step = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)

    # Генерируем кнопки, пока не достигнем лимита
    while current_delta <= limit_duration and current_delta > timedelta(0):
        # Форматируем HH:MM
        total_seconds = current_delta.total_seconds()
        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        ext_str = f"{int(hours):d}:{int(minutes):02d}"

        # Создаем кнопку
        callback = f"{const.CB_EXTEND_SELECT_TIME}{booking_id}_{ext_str}"
        button = InlineKeyboardButton(text=f"+ {ext_str}", callback_data=callback)
        buttons.append(button)

        # Переходим к следующему шагу
        current_delta += time_step

    if not buttons:
        no_extend_button = InlineKeyboardButton("Продление недоступно", callback_data=const.CB_IGNORE)
        markup.add(no_extend_button)
        # Добавляем кнопку отмены, даже если продление недоступно
        cancel_context = const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1) # Контекст для отмены
        cancel_button = InlineKeyboardButton("❌ Отмена", callback_data=f"{const.CB_ACTION_CANCEL}{cancel_context}")
        markup.add(cancel_button)
        return markup

    # Распределяем кнопки по рядам
    row: List[InlineKeyboardButton] = []
    for btn in buttons:
        row.append(btn)
        if len(row) == markup.row_width:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)

    # Добавляем кнопку отмены в конце
    cancel_context = const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1) # Контекст для отмены
    cancel_button = InlineKeyboardButton("❌ Отмена", callback_data=f"{const.CB_ACTION_CANCEL}{cancel_context}")
    markup.add(cancel_button)
    return markup

def generate_extend_prompt_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления: Продлить / Нет."""
    markup = InlineKeyboardMarkup(row_width=2)
    extend_button = InlineKeyboardButton("➕ Продлить", callback_data=f"{const.CB_NOTIFY_EXTEND_PROMPT}{booking_id}")
    decline_button = InlineKeyboardButton("🚫 Нет, спасибо", callback_data=f"{const.CB_NOTIFY_DECLINE_EXT}{booking_id}")
    markup.add(extend_button, decline_button)
    return markup

# --- END OF FILE keyboards.py ---