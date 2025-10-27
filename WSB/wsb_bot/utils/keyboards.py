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
# Для URL тепловой карты
import config
# <<< ИСПРАВЛЕНО: Импортируем только нужную функцию из сервиса >>>
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

ADMIN_BOT_COMMANDS = [
    BotCommand("adminhelp", "🪄 Помощь Админу"),
    BotCommand("add_equipment", "💻 Добавить оборудование"),
    BotCommand("view_equipment", "⚙️ Оборудование (Удал.)"),
    BotCommand("admin_cancel", "❌ Отменить бронь"),
    BotCommand("all", "📊 Отчет / Фильтр"),
    BotCommand("broadcast", "📢 Рассылка"),
    BotCommand("manage_user", "👤 Упр. польз."),
    BotCommand("users", "👥 Список польз."),
    BotCommand("schedule", "⚙️ Обновить график"),
]


# --- Reply Keyboards ---

def create_user_reply_keyboard() -> ReplyKeyboardMarkup:
    """Генерирует стандартную Reply клавиатуру для обычного пользователя."""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    btn_help = KeyboardButton(const.BTN_TEXT_HELP)
    btn_booking = KeyboardButton(const.BTN_TEXT_BOOKING)
    btn_cancel = KeyboardButton(const.BTN_TEXT_CANCEL)
    btn_finish = KeyboardButton(const.BTN_TEXT_FINISH)
    btn_extend = KeyboardButton(const.BTN_TEXT_EXTEND)
    btn_mybookings = KeyboardButton(const.BTN_TEXT_MYBOOKINGS)
    btn_workspacebookings = KeyboardButton(const.BTN_TEXT_WORKSPACEBOOKINGS)
    btn_datebookings = KeyboardButton(const.BTN_TEXT_DATEBOOKINGS)
    markup.add(btn_help)
    markup.add(btn_booking, btn_cancel, btn_finish)
    markup.add(btn_extend)
    markup.add(btn_mybookings, btn_workspacebookings, btn_datebookings)
    return markup

def create_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Генерирует Reply клавиатуру для администратора."""
    markup = create_user_reply_keyboard()
    btn_admin_help = KeyboardButton(const.BTN_TEXT_ADMIN_HELP)
    btn_add_equip = KeyboardButton(const.BTN_TEXT_ADD_EQUIPMENT)
    btn_view_equip = KeyboardButton(const.BTN_TEXT_MANAGE_EQUIPMENT)
    btn_admin_cancel = KeyboardButton(const.BTN_TEXT_ADMIN_CANCEL_KB)
    btn_all = KeyboardButton(const.BTN_TEXT_ALL_KB)
    btn_broadcast = KeyboardButton(const.BTN_TEXT_BROADCAST_KB)
    btn_manage_user = KeyboardButton(const.BTN_TEXT_MANAGE_USER_KB)
    btn_users = KeyboardButton(const.BTN_TEXT_USERS_KB)
    btn_schedule = KeyboardButton(const.BTN_TEXT_SCHEDULE_KB)
    markup.add(btn_admin_help)
    markup.add(btn_add_equip, btn_view_equip)
    markup.add(btn_users, btn_manage_user)
    markup.add(btn_admin_cancel, btn_all)
    markup.add(btn_broadcast, btn_schedule)
    return markup

# --- Inline Keyboards ---

def _add_cancel_booking_button(markup: InlineKeyboardMarkup):
     """Добавляет кнопку отмены для процесса бронирования."""
     markup.add(InlineKeyboardButton("❌ Отменить бронирование", callback_data=const.CB_BOOK_CANCEL_PROCESS))

def generate_equipment_category_keyboard(categories: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора категории."""
    markup = InlineKeyboardMarkup(row_width=1)
    if not categories:
        markup.add(InlineKeyboardButton("Нет категорий", callback_data=const.CB_IGNORE))
        return markup
    for category in categories:
        cat_id = category.get('id'); name = category.get('name_cat', 'Без имени')
        if cat_id is not None:
            markup.add(InlineKeyboardButton(text=name, callback_data=f"{callback_prefix}{cat_id}"))
        else: logger.warning(f"Категория без ID: {category}")
    _add_cancel_booking_button(markup)
    return markup

def generate_equipment_keyboard(equipment: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру со списком оборудования."""
    markup = InlineKeyboardMarkup(row_width=1)
    if not equipment:
        markup.add(InlineKeyboardButton("Нет оборудования", callback_data=const.CB_IGNORE))
        return markup
    for item in equipment:
        eq_id = item.get('id'); name = item.get('name_equip', 'Без имени')
        if eq_id is not None:
            markup.add(InlineKeyboardButton(text=name, callback_data=f"{callback_prefix}{eq_id}"))
        else: logger.warning(f"Оборудование без ID: {item}")
    _add_cancel_booking_button(markup)
    return markup

def generate_date_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру выбора даты (ближайшие 7 дней)."""
    markup = InlineKeyboardMarkup()
    now = datetime.now().date(); buttons = []
    for i in range(7):
        day = now + timedelta(days=i); day_str = day.strftime('%d-%m-%Y')
        callback = f"{callback_prefix}{day_str}"
        buttons.append(InlineKeyboardButton(text=day_str, callback_data=callback))
    if not buttons:
         markup.add(InlineKeyboardButton("Нет дат", callback_data=const.CB_IGNORE))
         return markup
    for btn in buttons: markup.add(btn) # Даты в один столбец
    _add_cancel_booking_button(markup)
    return markup

def generate_available_slots_keyboard(slots: List[Tuple[time, time]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для выбора доступного временного слота."""
    markup = InlineKeyboardMarkup(row_width=1)
    if not slots:
        markup.add(InlineKeyboardButton("Нет слотов", callback_data=const.CB_IGNORE))
        return markup
    for i, slot in enumerate(slots):
        start_str = _format_time(slot[0]); end_str = _format_time(slot[1])
        callback = f"{callback_prefix}{i}" # Кодируем индекс слота
        markup.add(InlineKeyboardButton(f"{start_str} - {end_str}", callback_data=callback))
    _add_cancel_booking_button(markup)
    return markup

def generate_time_keyboard_in_slot(selected_slot: Tuple[time, time], selected_date: date, callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру времени начала бронирования внутри заданного слота."""
    markup = InlineKeyboardMarkup(row_width=4); buttons = []; slot_start = selected_slot[0]; slot_end = selected_slot[1]; time_step = const.BOOKING_TIME_STEP_MINUTES
    today = datetime.now().date(); is_today = (selected_date == today); now_dt = datetime.now(); earliest_start_time = time(0, 0)
    if is_today:
        minutes_to_add = time_step - (now_dt.minute % time_step) if now_dt.minute % time_step != 0 else 0
        earliest_start_dt = now_dt + timedelta(minutes=minutes_to_add); earliest_start_time = earliest_start_dt.time().replace(second=0, microsecond=0)
    current_time_dt = datetime.combine(selected_date, slot_start); slot_end_dt = datetime.combine(selected_date, slot_end)
    while current_time_dt < slot_end_dt:
        current_time = current_time_dt.time(); potential_end_dt = current_time_dt + timedelta(minutes=time_step)
        if current_time >= slot_start and (not is_today or current_time >= earliest_start_time) and potential_end_dt <= slot_end_dt:
            t_str = current_time.strftime('%H:%M'); callback = f"{callback_prefix}{t_str}"
            buttons.append(InlineKeyboardButton(text=t_str, callback_data=callback))
        current_time_dt += timedelta(minutes=time_step)
    if not buttons: markup.add(InlineKeyboardButton("Нет времени", callback_data=const.CB_IGNORE))
    else:
        row = [];
        for btn in buttons:
            row.append(btn);
            if len(row) == markup.row_width: markup.row(*row); row = []
        if row: markup.row(*row)
        _add_cancel_booking_button(markup)
    return markup

def generate_duration_keyboard_in_slot(start_time: time, selected_date: date, slot_end_time: time, callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру длительности, ограниченную концом слота и MAX."""
    markup = InlineKeyboardMarkup(row_width=3); buttons = []; time_step_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    max_overall_duration = timedelta(hours=const.MAX_BOOKING_DURATION_HOURS); start_dt = datetime.combine(selected_date, start_time)
    slot_end_dt = datetime.combine(selected_date, slot_end_time); current_duration = time_step_delta
    while True:
        potential_end_dt = start_dt + current_duration
        if current_duration > max_overall_duration: break
        if potential_end_dt > slot_end_dt: break
        if current_duration <= timedelta(0): current_duration += time_step_delta; continue
        h, rem = divmod(current_duration.total_seconds(), 3600); m, _ = divmod(rem, 60); dur_str = f"{int(h):d}:{int(m):02d}"
        callback = f"{callback_prefix}{dur_str}"; buttons.append(InlineKeyboardButton(text=dur_str, callback_data=callback)); current_duration += time_step_delta
    if not buttons: markup.add(InlineKeyboardButton("Нет длит.", callback_data=const.CB_IGNORE))
    else:
        row = [];
        for btn in buttons:
            row.append(btn);
            if len(row) == markup.row_width: markup.row(*row); row = []
        if row: markup.row(*row)
        _add_cancel_booking_button(markup)
    return markup

def generate_booking_confirmation_keyboard() -> InlineKeyboardMarkup:
     """Генерирует кнопки Да/Нет для финального подтверждения брони."""
     markup = InlineKeyboardMarkup(row_width=2)
     markup.add(InlineKeyboardButton("✅ Подтвердить", callback_data=const.CB_BOOK_CONFIRM_FINAL), InlineKeyboardButton("❌ Отмена", callback_data=const.CB_BOOK_CANCEL_PROCESS))
     return markup

def generate_user_bookings_keyboard(bookings: List[Dict[str, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру со списком бронирований пользователя."""
    markup = InlineKeyboardMarkup(row_width=1)
    if not bookings: markup.add(InlineKeyboardButton("Нет броней", callback_data=const.CB_IGNORE)); return markup
    for booking in bookings:
        b_id = booking.get('id'); eq_name = booking.get('name_equip', '???'); b_date = booking.get('date'); b_start = booking.get('time_start'); b_end = booking.get('time_end')
        if not all([b_id, b_date, b_start, b_end]): logger.warning(f"Неполные данные: {booking}"); continue
        try: date_str = b_date.strftime('%d.%m'); start_str = _format_time(b_start); end_str = _format_time(b_end)
        except AttributeError as e: logger.warning(f"Ошибка формат. {b_id}: {e}"); date_str=str(b_date); start_str=str(b_start); end_str=str(b_end)
        max_len = 25; display_name = (eq_name[:max_len] + '..') if len(eq_name) > max_len else eq_name; btn_text = f"{display_name} | {date_str} | {start_str}-{end_str}"
        markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"{callback_prefix}{b_id}"))
    if bookings: cancel_context = callback_prefix.replace('cb_', '', 1); markup.add(InlineKeyboardButton("❌ Отмена действия", callback_data=const.CB_ACTION_CANCEL + cancel_context))
    return markup

def generate_equipment_list_with_delete_keyboard(equipment_list: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра и удаления оборудования админом."""
    markup = InlineKeyboardMarkup(row_width=2)
    if not equipment_list: markup.add(InlineKeyboardButton("Нет оборуд.", callback_data=const.CB_IGNORE)); return markup
    for item in equipment_list:
        eq_id = item.get('id'); eq_name = item.get('name_equip', '???')
        if eq_id is not None: markup.add(InlineKeyboardButton(text=f"{eq_name} (ID:{eq_id})", callback_data=const.CB_IGNORE), InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"{const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP}{eq_id}"))
        else: logger.warning(f"Обор. без ID: {item}")
    return markup

def generate_admin_cancel_keyboard(bookings: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Клавиатура для админа для выбора брони для отмены."""
    markup = InlineKeyboardMarkup(row_width=1)
    if not bookings: markup.add(InlineKeyboardButton("Нет броней", callback_data=const.CB_IGNORE)); return markup
    for booking in bookings:
        b_id = booking.get('id'); u_name = booking.get('user_name', '???'); eq_name = booking.get('equipment_name', '???')
        b_date = booking.get('date'); b_start = booking.get('time_start'); b_end = booking.get('time_end')
        if not all([b_id, b_date, b_start, b_end]): logger.warning(f"Неполные данные: {booking}"); continue
        try: date_str = b_date.strftime('%d.%m'); start_str = _format_time(b_start); end_str = _format_time(b_end)
        except AttributeError as e: logger.warning(f"Ошибка формат. {b_id}: {e}"); date_str=str(b_date); start_str=str(b_start); end_str=str(b_end)
        btn_text = f"ID:{b_id} {u_name[:15]} | {eq_name[:15]} | {date_str} {start_str}-{end_str}"; markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"{const.CB_ADMIN_CANCEL_SELECT}{b_id}"))
    return markup

def generate_confirmation_keyboard(confirm_callback: str, cancel_callback: str = const.CB_ACTION_CANCEL, confirm_text: str = "✅ Да", cancel_text: str = "❌ Нет") -> InlineKeyboardMarkup:
    """Стандартная клавиатура Да/Нет для подтверждения действий."""
    markup = InlineKeyboardMarkup(row_width=2); markup.add(InlineKeyboardButton(confirm_text, callback_data=confirm_callback), InlineKeyboardButton(cancel_text, callback_data=cancel_callback)); return markup

def generate_start_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Кнопка подтверждения начала брони из уведомления."""
    markup = InlineKeyboardMarkup(row_width=1); markup.add(InlineKeyboardButton("✅ Подтвердить начало", callback_data=f"{const.CB_BOOK_CONFIRM_START}{booking_id}")); return markup

def generate_registration_confirmation_keyboard(temp_user_id: int) -> InlineKeyboardMarkup:
    """Кнопки подтверждения/отклонения регистрации админом."""
    markup = InlineKeyboardMarkup(row_width=2); markup.add(InlineKeyboardButton("✅ Подтвердить", callback_data=f"{const.CB_REG_CONFIRM_USER}{temp_user_id}"), InlineKeyboardButton("❌ Отклонить", callback_data=f"{const.CB_REG_DECLINE_USER}{temp_user_id}")); return markup

def generate_filter_options_keyboard() -> InlineKeyboardMarkup:
    """Кнопки выбора типа фильтра для /all."""
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("👥 По пользователю", callback_data=f"{const.CB_FILTER_BY_TYPE}users"))
    markup.add(InlineKeyboardButton("🔬 По оборудованию", callback_data=f"{const.CB_FILTER_BY_TYPE}equipment"))
    markup.add(InlineKeyboardButton("🗓️ По дате (месяц)", callback_data=f"{const.CB_FILTER_BY_TYPE}dates"))

    # Кнопка-ссылка на тепловую карту (WSB)
    heatmap_url = (config.HEATMAP_BASE_URL or "http://192.168.1.139:8082/").strip()
    if heatmap_url:
        markup.add(InlineKeyboardButton("📊 Тепловая карта занятости (WSB)", url=heatmap_url))

    return markup

def generate_filter_selection_keyboard(options: List[Tuple[Any, Any]], callback_prefix: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора значения для фильтра /all."""
    markup = InlineKeyboardMarkup(row_width=1);
    if not options: markup.add(InlineKeyboardButton("Нет данных", callback_data=const.CB_IGNORE)); return markup
    for text, val in options: display_text = str(text)[:50] + '...' if len(str(text)) > 50 else str(text); markup.add(InlineKeyboardButton(display_text, callback_data=f"{callback_prefix}{val}"))
    return markup

def generate_user_management_keyboard(users: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
     """Клавиатура выбора пользователя для управления админом."""
     markup = InlineKeyboardMarkup(row_width=1);
     if not users: markup.add(InlineKeyboardButton("Нет польз.", callback_data=const.CB_IGNORE)); return markup
     for user in users:
         u_id = user.get('users_id'); name = user.get('fi', f'ID {u_id}');
         if u_id is not None: markup.add(InlineKeyboardButton(text=name, callback_data=f"{const.CB_MANAGE_USER_SELECT}{u_id}"))
         else: logger.warning(f"Польз. без ID: {user}")
     return markup


def generate_user_status_keyboard(user_id: int, is_blocked: bool, is_admin: bool) -> InlineKeyboardMarkup:
    """
    Генерирует клавиатуру для управления статусом пользователя (блокировка, админские права).
    """
    markup = InlineKeyboardMarkup(row_width=1)  # Можно поставить row_width=2, если хотите кнопки в два ряда

    # Кнопка блокировки/разблокировки
    if is_blocked:
        markup.add(InlineKeyboardButton(
            text="🟢 Разблокировать",  # Текст можно взять из const, если он там есть
            callback_data=f"{const.CB_MANAGE_USER_ACTION_UNBLOCK}{user_id}"
        ))
    else:
        markup.add(InlineKeyboardButton(
            text="🔴 Заблокировать",  # Текст можно взять из const
            callback_data=f"{const.CB_MANAGE_USER_ACTION_BLOCK}{user_id}"
        ))

    # Кнопка назначения/снятия админских прав
    if is_admin:
        markup.add(InlineKeyboardButton(
            text="👤 Снять права админа",  # Текст можно взять из const
            callback_data=f"{const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN}{user_id}"
        ))
    else:
        markup.add(InlineKeyboardButton(
            text="👑 Назначить админом",  # Текст можно взять из const
            callback_data=f"{const.CB_MANAGE_USER_ACTION_MAKE_ADMIN}{user_id}"
        ))

    # Кнопка "Назад к списку"
    # Убедитесь, что `const.CB_ACTION_CANCEL + "_manage_user_list"` или другая константа
    # корректно обрабатывается для возврата к списку пользователей.
    # Если у вас есть специальный callback для возврата к списку пользователей, используйте его.
    # Например, если бы у вас была константа const.CB_ADMIN_MANAGE_USER_BACK_TO_LIST
    # или если вы хотите вернуться на первую страницу списка с пагинацией.
    # Пока используем ваш вариант:
    markup.add(InlineKeyboardButton(
        const.BTN_TEXT_BACK,  # "⬅️ Назад" (если текст общий) или "Назад к списку"
        callback_data=const.CB_ACTION_CANCEL + "manage_user_list"  # Этот callback должен быть обработан!
    ))

    return markup

def generate_extend_time_keyboard(booking_id: int, max_duration: Optional[timedelta] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени продления."""
    markup = InlineKeyboardMarkup(row_width=3); buttons = []; current_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    limit_duration = max_duration if max_duration is not None else timedelta(hours=const.MAX_BOOKING_DURATION_HOURS); time_step = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    if limit_duration < timedelta(0): limit_duration = timedelta(0)
    while current_delta <= limit_duration and current_delta > timedelta(0):
        h, rem = divmod(current_delta.total_seconds(), 3600); m, _ = divmod(rem, 60); ext_str = f"{int(h):d}:{int(m):02d}"
        callback = f"{const.CB_EXTEND_SELECT_TIME}{booking_id}_{ext_str}"; buttons.append(InlineKeyboardButton(text=f"+ {ext_str}", callback_data=callback)); current_delta += time_step
    if not buttons: markup.add(InlineKeyboardButton("Продление не доступно", callback_data=const.CB_IGNORE)); return markup
    row = [];
    for btn in buttons:
        row.append(btn);
        if len(row) == markup.row_width: markup.row(*row); row = []
    if row: markup.row(*row)
    cancel_context = const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1); markup.add(InlineKeyboardButton("❌ Отмена", callback_data=const.CB_ACTION_CANCEL + cancel_context)); return markup

def generate_extend_prompt_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления: Продлить / Нет."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("➕ Продлить", callback_data=f"{const.CB_NOTIFY_EXTEND_PROMPT}{booking_id}"), InlineKeyboardButton("🚫 Нет, спасибо", callback_data=f"{const.CB_NOTIFY_DECLINE_EXT}{booking_id}")); return markup


def generate_admin_cancel_inline_keyboard(bookings: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Генерирует Inline клавиатуру для админа для отмены броней.
    Каждая кнопка соответствует одной брони.
    """
    markup = InlineKeyboardMarkup(row_width=1)  # Каждая кнопка на новой строке

    if not bookings:  # На всякий случай, хотя проверка должна быть выше
        return markup

    for booking in bookings:
        booking_id = booking.get('id')
        if booking_id is None:  # Пропускаем, если у брони нет ID (маловероятно)
            continue

        # Текст кнопки: короткий, с ID
        button_text = f"🗑️ Отменить бронь ID: {booking_id}"

        # Callback data для обработчика
        callback_data = f"{const.CB_ADMIN_CANCEL_SELECT}{booking_id}"

        markup.add(InlineKeyboardButton(text=button_text, callback_data=callback_data))

    return markup