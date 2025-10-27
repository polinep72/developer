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
    """Генерирует Reply клавиатуру для администратора (включая пользовательские)."""
    markup = create_user_reply_keyboard() # Начинаем с пользовательской
    # Добавляем кнопки админа
    btn_admin_help = KeyboardButton('/adminhelp')
    btn_add_equip = KeyboardButton('/add_equipment')
    btn_view_equip = KeyboardButton('/view_equipment')
    btn_admin_cancel = KeyboardButton('/admin_cancel')
    btn_all = KeyboardButton('/all')
    btn_broadcast = KeyboardButton('/broadcast')
    btn_manage_user = KeyboardButton('/manage_user')
    btn_users = KeyboardButton('/users')
    btn_schedule = KeyboardButton('/schedule')

    markup.add(btn_admin_help)
    markup.add(btn_add_equip, btn_view_equip)
    markup.add(btn_users, btn_manage_user)
    markup.add(btn_admin_cancel, btn_all)
    markup.add(btn_broadcast, btn_schedule)
    return markup

# --- Inline Keyboards ---

# --- ИЗМЕНЕНО: Ожидаем List[Dict] ---
def generate_equipment_category_keyboard(categories: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """ Генерирует клавиатуру для выбора категории. Ожидает список словарей. """
    markup = InlineKeyboardMarkup(row_width=1)
    if not categories:
        markup.add(InlineKeyboardButton("Нет категорий", callback_data=const.CB_IGNORE))
        return markup
    for category in categories:
        cat_id = category.get('id')
        name = category.get('name_cat', 'Без имени')
        if cat_id is not None:
            markup.add(InlineKeyboardButton(text=name, callback_data=f"{callback_prefix}{cat_id}"))
        else:
            logger.warning(f"Категория без ID в generate_equipment_category_keyboard: {category}")
    return markup
# --- КОНЕЦ ИЗМЕНЕНИЯ ---


def generate_equipment_keyboard(equipment: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """ Генерирует клавиатуру со списком оборудования. Ожидает список словарей. """
    markup = InlineKeyboardMarkup(row_width=1)
    if not equipment:
        markup.add(InlineKeyboardButton("Нет доступного оборудования", callback_data=const.CB_IGNORE))
        return markup
    for item in equipment:
        eq_id = item.get('id')
        name = item.get('name_equip', 'Без имени')
        if eq_id is not None:
            markup.add(InlineKeyboardButton(text=name, callback_data=f"{callback_prefix}{eq_id}"))
        else:
            logger.warning(f"Элемент оборудования без ID в generate_equipment_keyboard: {item}")
    return markup

def generate_date_keyboard(equipment_id: int, callback_prefix: str, single_column: bool = False) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    now = datetime.now().date()
    buttons = []
    for i in range(7):
        day = now + timedelta(days=i)
        day_str = day.strftime('%d-%m-%Y')
        callback = f"{callback_prefix}{day_str}_{equipment_id}"
        buttons.append(InlineKeyboardButton(text=day_str, callback_data=callback))

    if not buttons:
         markup.add(InlineKeyboardButton("Нет доступных дат", callback_data=const.CB_IGNORE))
         return markup
    if single_column:
        for btn in buttons: markup.add(btn)
    else:
        row_width = 3
        for i in range(0, len(buttons), row_width): markup.row(*buttons[i:i+row_width])
    return markup

def generate_time_keyboard(selected_date_str: str, equipment_id: int, callback_prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=4)
    buttons=[]
    start_h = const.START_OF_WORKDAY_HOUR
    end_h = const.END_OF_WORKDAY_HOUR
    time_step = const.BOOKING_TIME_STEP_MINUTES

    try:
        sel_date = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        today = datetime.now().date()
        is_today = (sel_date == today)
        now_dt = datetime.now()
        # Округляем текущее время вверх до ближайшего шага
        minutes_to_add = time_step - (now_dt.minute % time_step) if now_dt.minute % time_step != 0 else 0
        earliest_start_time = (now_dt + timedelta(minutes=minutes_to_add)).time().replace(second=0, microsecond=0)
    except ValueError:
        logger.error(f"Неверный формат даты '{selected_date_str}' в generate_time_keyboard")
        markup.add(InlineKeyboardButton("Ошибка даты", callback_data=const.CB_IGNORE))
        return markup

    current_time = time(hour=start_h, minute=0)
    end_loop_time = time(hour=end_h, minute=0)

    while current_time < end_loop_time:
        if not (is_today and current_time < earliest_start_time):
            t_str = current_time.strftime('%H:%M')
            callback = f"{callback_prefix}{t_str}_{selected_date_str}_{equipment_id}"
            buttons.append(InlineKeyboardButton(text=t_str, callback_data=callback))
        next_dt = datetime.combine(date.min, current_time) + timedelta(minutes=time_step)
        current_time = next_dt.time()

    if not buttons:
        markup.add(InlineKeyboardButton("Нет доступного времени", callback_data=const.CB_IGNORE))
        return markup
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == markup.row_width: markup.row(*row); row = []
    if row: markup.row(*row)
    return markup

def generate_duration_keyboard(start_time_str: str, selected_date_str: str, equipment_id: int, callback_prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=3)
    buttons=[]
    duration = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    max_dur = timedelta(hours=const.MAX_BOOKING_DURATION_HOURS)
    time_step = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)

    while duration <= max_dur and duration > timedelta(0):
        h, rem = divmod(duration.total_seconds(), 3600); m, _ = divmod(rem, 60)
        dur_str = f"{int(h):d}:{int(m):02d}"
        callback = f"{callback_prefix}{dur_str}_{start_time_str}_{selected_date_str}_{equipment_id}"
        buttons.append(InlineKeyboardButton(text=dur_str, callback_data=callback))
        duration += time_step

    if not buttons:
        markup.add(InlineKeyboardButton("Ошибка длительности", callback_data=const.CB_IGNORE))
        return markup
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == markup.row_width: markup.row(*row); row = []
    if row: markup.row(*row)
    return markup

def generate_user_bookings_keyboard(bookings: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not bookings:
        markup.add(InlineKeyboardButton("Нет подходящих бронирований", callback_data=const.CB_IGNORE))
        return markup
    for booking in bookings:
        b_id = booking.get('id')
        eq_name = booking.get('equipment_name', '???')
        b_date = booking.get('date'); b_start = booking.get('time_start'); b_end = booking.get('time_end')
        if not all([b_id, b_date, b_start, b_end]): logger.warning(f"Неполные данные: {booking}"); continue
        try:
            date_str = b_date.strftime('%d.%m') # Короткий формат даты
            start_str = b_start.strftime('%H:%M') if isinstance(b_start, (datetime, time)) else str(b_start)
            end_str = b_end.strftime('%H:%M') if isinstance(b_end, (datetime, time)) else str(b_end)
        except AttributeError: logger.warning(f"Ошибка форматирования {b_id}"); date_str=str(b_date); start_str=str(b_start); end_str=str(b_end)
        max_len = 25; display_name = (eq_name[:max_len] + '..') if len(eq_name) > max_len else eq_name
        btn_text = f"{display_name} | {date_str} | {start_str}-{end_str}"
        markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"{callback_prefix}{b_id}"))
    return markup

def generate_equipment_list_with_delete_keyboard(equipment_list: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2) # Кнопки в один ряд
    if not equipment_list:
        markup.add(InlineKeyboardButton("Нет оборудования для удаления", callback_data=const.CB_IGNORE))
        return markup
    for item in equipment_list:
        eq_id = item.get('id'); eq_name = item.get('name_equip', '???')
        if eq_id is not None:
            markup.add(
                InlineKeyboardButton(text=f"{eq_name} (ID:{eq_id})", callback_data=const.CB_IGNORE),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"{const.CB_EQUIP_DELETE_SELECT}{eq_id}")
            )
        else: logger.warning(f"Оборудование без ID: {item}")
    return markup

def generate_admin_cancel_keyboard(bookings: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not bookings:
        markup.add(InlineKeyboardButton("Нет активных броней для отмены", callback_data=const.CB_IGNORE))
        return markup
    for booking in bookings:
        b_id = booking.get('id'); u_name = booking.get('user_name', '???'); eq_name = booking.get('equipment_name', '???')
        b_date = booking.get('date'); b_start = booking.get('time_start'); b_end = booking.get('time_end')
        if not all([b_id, b_date, b_start, b_end]): logger.warning(f"Неполные данные: {booking}"); continue
        try:
            date_str = b_date.strftime('%d.%m'); start_str = b_start.strftime('%H:%M'); end_str = b_end.strftime('%H:%M')
        except AttributeError: logger.warning(f"Ошибка формат. {b_id}"); date_str=str(b_date); start_str=str(b_start); end_str=str(b_end)
        btn_text = f"ID:{b_id} {u_name[:15]} | {eq_name[:15]} | {date_str} {start_str}-{end_str}"
        markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"{const.CB_ADMIN_CANCEL_SELECT}{b_id}"))
    return markup

def generate_confirmation_keyboard(confirm_callback: str, cancel_callback: str = const.CB_ACTION_CANCEL, confirm_text: str = "✅ Да", cancel_text: str = "❌ Нет") -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(confirm_text, callback_data=confirm_callback), InlineKeyboardButton(cancel_text, callback_data=cancel_callback))
    return markup

def generate_start_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✅ Подтвердить начало", callback_data=f"{const.CB_BOOK_CONFIRM_START}{booking_id}"))
    return markup

def generate_registration_confirmation_keyboard(temp_user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("✅ Подтвердить", callback_data=f"{const.CB_REG_CONFIRM_USER}{temp_user_id}"), InlineKeyboardButton("❌ Отклонить", callback_data=f"{const.CB_REG_DECLINE_USER}{temp_user_id}"))
    return markup

def generate_filter_options_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👥 По пользователю", callback_data=f"{const.CB_FILTER_BY_TYPE}users"))
    markup.add(InlineKeyboardButton("🔬 По оборудованию", callback_data=f"{const.CB_FILTER_BY_TYPE}equipment"))
    markup.add(InlineKeyboardButton("🗓️ По дате (месяц)", callback_data=f"{const.CB_FILTER_BY_TYPE}dates"))
    return markup

def generate_filter_selection_keyboard(options: List[Tuple[Any, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not options:
        markup.add(InlineKeyboardButton("Нет данных для выбора", callback_data=const.CB_IGNORE))
        return markup
    for text, val in options:
        display_text = str(text)[:50] + '...' if len(str(text)) > 50 else str(text)
        markup.add(InlineKeyboardButton(display_text, callback_data=f"{callback_prefix}{val}"))
    return markup

def generate_user_management_keyboard(users: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
     markup = InlineKeyboardMarkup(row_width=1)
     if not users:
         markup.add(InlineKeyboardButton("Нет пользователей", callback_data=const.CB_IGNORE))
         return markup
     for user in users:
         u_id = user.get('users_id'); name = user.get('fi', f'ID {u_id}')
         if u_id is not None: markup.add(InlineKeyboardButton(text=name, callback_data=f"{const.CB_MANAGE_SELECT_USER}{u_id}"))
         else: logger.warning(f"Пользователь без ID: {user}")
     return markup

def generate_user_status_keyboard(user_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
     markup = InlineKeyboardMarkup(row_width=1)
     if is_blocked: markup.add(InlineKeyboardButton(text="🟢 Разблокировать", callback_data=f"{const.CB_MANAGE_UNBLOCK_USER}{user_id}"))
     else: markup.add(InlineKeyboardButton(text="🔴 Заблокировать", callback_data=f"{const.CB_MANAGE_BLOCK_USER}{user_id}"))
     markup.add(InlineKeyboardButton("Назад к списку", callback_data=const.CB_ACTION_CANCEL + "manage_user_list"))
     return markup

def generate_extend_time_keyboard(booking_id: int, max_duration: Optional[timedelta] = None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []; current_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    limit_duration = max_duration if max_duration is not None else timedelta(hours=const.MAX_BOOKING_DURATION_HOURS)
    time_step = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)

    while current_delta <= limit_duration and current_delta > timedelta(0):
        h, rem = divmod(current_delta.total_seconds(), 3600); m, _ = divmod(rem, 60)
        ext_str = f"{int(h):d}:{int(m):02d}"
        callback = f"{const.CB_EXTEND_SELECT_TIME}{booking_id}_{ext_str}"
        buttons.append(InlineKeyboardButton(text=f"+ {ext_str}", callback_data=callback))
        current_delta += time_step

    if not buttons:
        markup.add(InlineKeyboardButton("Продление недоступно", callback_data=const.CB_IGNORE))
        return markup
    row = []
    for btn in buttons:
        row.append(btn)
        if len(row) == markup.row_width: markup.row(*row); row = []
    if row: markup.row(*row)
    return markup

def generate_extend_prompt_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("➕ Продлить", callback_data=f"{const.CB_NOTIFY_EXTEND_PROMPT}{booking_id}"), InlineKeyboardButton("🚫 Нет, спасибо", callback_data=f"{const.CB_NOTIFY_DECLINE_EXT}{booking_id}"))
    return markup