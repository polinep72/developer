from telebot import types
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
)
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timedelta, date, time
import constants as const
from logger import logger
import config
from services.booking_service import _format_time

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


def create_user_reply_keyboard() -> ReplyKeyboardMarkup:
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


def _add_cancel_booking_button(markup: InlineKeyboardMarkup) -> None:
    markup.add(
        InlineKeyboardButton(
            "❌ Отменить бронирование", callback_data=const.CB_BOOK_CANCEL_PROCESS
        )
    )


def generate_equipment_category_keyboard(
    categories: List[Dict[str, Any]], callback_prefix: str
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not categories:
        markup.add(InlineKeyboardButton("Нет категорий", callback_data=const.CB_IGNORE))
        return markup
    for category in categories:
        cat_id = category.get("id")
        name = category.get("name_cat", "Без имени")
        if cat_id is not None:
            markup.add(
                InlineKeyboardButton(
                    text=name, callback_data=f"{callback_prefix}{cat_id}"
                )
            )
        else:
            logger.warning(f"Категория без ID: {category}")
    _add_cancel_booking_button(markup)
    return markup


def generate_equipment_keyboard(
    equipment: List[Dict[str, Any]], callback_prefix: str
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not equipment:
        markup.add(InlineKeyboardButton("Нет оборудования", callback_data=const.CB_IGNORE))
        return markup
    for item in equipment:
        eq_id = item.get("id")
        name = item.get("name_equip", "Без имени")
        if eq_id is not None:
            markup.add(
                InlineKeyboardButton(
                    text=name, callback_data=f"{callback_prefix}{eq_id}"
                )
            )
        else:
            logger.warning(f"Оборудование без ID: {item}")
    _add_cancel_booking_button(markup)
    return markup


def generate_date_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    now = datetime.now().date()
    buttons = []
    for i in range(7):
        day = now + timedelta(days=i)
        day_str = day.strftime("%d-%m-%Y")
        callback = f"{callback_prefix}{day_str}"
        buttons.append(InlineKeyboardButton(text=day_str, callback_data=callback))
    if not buttons:
        markup.add(InlineKeyboardButton("Нет дат", callback_data=const.CB_IGNORE))
        return markup
    for btn in buttons:
        markup.add(btn)
    _add_cancel_booking_button(markup)
    return markup


def generate_available_slots_keyboard(
    slots: List[Tuple[time, time]], callback_prefix: str
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    if not slots:
        markup.add(InlineKeyboardButton("Нет слотов", callback_data=const.CB_IGNORE))
        return markup
    for i, slot in enumerate(slots):
        start_str = _format_time(slot[0])
        end_str = _format_time(slot[1])
        callback = f"{callback_prefix}{i}"
        markup.add(
            InlineKeyboardButton(
                f"{start_str} - {end_str}", callback_data=callback
            )
        )
    _add_cancel_booking_button(markup)
    return markup


def generate_time_keyboard_in_slot(
    selected_slot: Tuple[time, time], selected_date: date, callback_prefix: str
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=4)
    buttons: List[InlineKeyboardButton] = []
    slot_start = selected_slot[0]
    slot_end = selected_slot[1]
    time_step = const.BOOKING_TIME_STEP_MINUTES
    today = datetime.now().date()
    is_today = selected_date == today
    now_dt = datetime.now()
    earliest_start_time = time(0, 0)
    if is_today:
        minutes_to_add = (
            time_step - (now_dt.minute % time_step)
            if now_dt.minute % time_step != 0
            else 0
        )
        earliest_start_dt = now_dt + timedelta(minutes=minutes_to_add)
        earliest_start_time = earliest_start_dt.time().replace(second=0, microsecond=0)
    current_time_dt = datetime.combine(selected_date, slot_start)
    slot_end_dt = datetime.combine(selected_date, slot_end)
    while current_time_dt < slot_end_dt:
        current_time = current_time_dt.time()
        potential_end_dt = current_time_dt + timedelta(minutes=time_step)
        if (
            current_time >= slot_start
            and (not is_today or current_time >= earliest_start_time)
            and potential_end_dt <= slot_end_dt
        ):
            t_str = current_time.strftime("%H:%M")
            callback = f"{callback_prefix}{t_str}"
            buttons.append(InlineKeyboardButton(text=t_str, callback_data=callback))
        current_time_dt += timedelta(minutes=time_step)
    if not buttons:
        markup.add(InlineKeyboardButton("Нет времени", callback_data=const.CB_IGNORE))
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


def generate_duration_keyboard_in_slot(
    start_time: time, selected_date: date, slot_end_time: time, callback_prefix: str
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=3)
    buttons: List[InlineKeyboardButton] = []
    time_step_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    max_overall_duration = timedelta(hours=const.MAX_BOOKING_DURATION_HOURS)
    start_dt = datetime.combine(selected_date, start_time)
    slot_end_dt = datetime.combine(selected_date, slot_end_time)
    current_duration = time_step_delta
    while True:
        potential_end_dt = start_dt + current_duration
        if current_duration > max_overall_duration:
            break
        if potential_end_dt > slot_end_dt:
            break
        if current_duration <= timedelta(0):
            current_duration += time_step_delta
            continue
        h, rem = divmod(current_duration.total_seconds(), 3600)
        m, _ = divmod(rem, 60)
        dur_str = f"{int(h):d}:{int(m):02d}"
        callback = f"{callback_prefix}{dur_str}"
        buttons.append(InlineKeyboardButton(text=dur_str, callback_data=callback))
        current_duration += time_step_delta
    if not buttons:
        markup.add(InlineKeyboardButton("Нет длит.", callback_data=const.CB_IGNORE))
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
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            "✅ Подтвердить", callback_data=const.CB_BOOK_CONFIRM_FINAL
        ),
        InlineKeyboardButton("❌ Отмена", callback_data=const.CB_BOOK_CANCEL_PROCESS),
    )
    return markup


def generate_start_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """
    Кнопка подтверждения начала брони из уведомления.
    Совместима с боевой реализацией notification_service.
    """
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(
            "✅ Подтвердить начало",
            callback_data=f"{const.CB_BOOK_CONFIRM_START}{booking_id}",
        )
    )
    return markup


def generate_extend_time_keyboard(
    booking_id: int, max_duration: Optional[timedelta] = None
) -> InlineKeyboardMarkup:
    """Клавиатура выбора времени продления (аналог боевой реализации)."""
    markup = InlineKeyboardMarkup(row_width=3)
    buttons: List[InlineKeyboardButton] = []

    current_delta = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)
    limit_duration = (
        max_duration
        if max_duration is not None
        else timedelta(hours=const.MAX_BOOKING_DURATION_HOURS)
    )
    time_step = timedelta(minutes=const.BOOKING_TIME_STEP_MINUTES)

    if limit_duration < timedelta(0):
        limit_duration = timedelta(0)

    while current_delta <= limit_duration and current_delta > timedelta(0):
        h, rem = divmod(current_delta.total_seconds(), 3600)
        m, _ = divmod(rem, 60)
        ext_str = f"{int(h):d}:{int(m):02d}"
        callback = f"{const.CB_EXTEND_SELECT_TIME}{booking_id}_{ext_str}"
        buttons.append(
            InlineKeyboardButton(text=f"+ {ext_str}", callback_data=callback)
        )
        current_delta += time_step

    if not buttons:
        markup.add(
            InlineKeyboardButton("Продление не доступно", callback_data=const.CB_IGNORE)
        )
        return markup

    row: List[InlineKeyboardButton] = []
    for btn in buttons:
        row.append(btn)
        if len(row) == markup.row_width:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)

    cancel_context = const.CB_EXTEND_SELECT_BOOKING.replace("cb_", "", 1)
    markup.add(
        InlineKeyboardButton(
            "❌ Отмена", callback_data=f"{const.CB_ACTION_CANCEL}{cancel_context}"
        )
    )
    return markup


def generate_extend_prompt_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для уведомления: Продлить / Нет."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            "➕ Продлить",
            callback_data=f"{const.CB_NOTIFY_EXTEND_PROMPT}{booking_id}",
        ),
        InlineKeyboardButton(
            "🚫 Нет, спасибо",
            callback_data=f"{const.CB_NOTIFY_DECLINE_EXT}{booking_id}",
        ),
    )
    return markup
