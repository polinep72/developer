# --- START OF FILE constants.py ---

# constants.py
from datetime import time
"""
Модуль для хранения констант, таких как префиксы callback_data,
магические числа и строки.
"""

# --- Префиксы Callback Data ---
# cb - callback, s - select, c - confirm, a - action, d - decline, p - prompt
# book, cat, eq, date, time, dur - booking process
# reg - registration
# manage - user management
# filter - /all filter
# ws - workspace bookings
# dateb - date bookings
# notify - notification buttons
# ext - extend
# del - delete
# admin_add_eq - admin add equipment process

# Шаг времени для бронирования (в минутах)
BOOKING_TIME_STEP_MINUTES = 30

# Максимальная длительность одного бронирования (в часах)
MAX_BOOKING_DURATION_HOURS = 13 # <<< УБЕДИТЕСЬ, ЧТО ЭТО ПРАВИЛЬНО

# Рабочие часы (начало и конец)
WORKING_HOURS_START = time(7, 0)
WORKING_HOURS_END = time(21, 0) # <<< УБЕДИТЕСЬ, ЧТО ЭТО ПРАВИЛЬНО

# Бронирование (Новый флоу)
CB_BOOK_ACTION = "cb_book_a_"
CB_BOOK_SELECT_CATEGORY = f"{CB_BOOK_ACTION}s_cat_"
CB_BOOK_SELECT_EQUIPMENT = f"{CB_BOOK_ACTION}s_eq_"
CB_BOOK_SELECT_DATE = f"{CB_BOOK_ACTION}s_date_"
CB_BOOK_SELECT_SLOT = f"{CB_BOOK_ACTION}s_slot_"
CB_BOOK_SELECT_TIME = f"{CB_BOOK_ACTION}s_time_"
CB_BOOK_SELECT_DURATION = f"{CB_BOOK_ACTION}s_dur_"
CB_BOOK_CONFIRM_FINAL = f"{CB_BOOK_ACTION}c_final"
CB_BOOK_CANCEL_PROCESS = f"{CB_BOOK_ACTION}cancel"

# Подтверждение начала брони (из уведомления)
CB_BOOK_CONFIRM_START = "cb_book_c_start_"

# Отмена (существующей брони)
CB_CANCEL_SELECT_BOOKING = "cb_cancel_s_book_"
CB_ADMIN_CANCEL_SELECT = "cb_admin_cancel_s_book_"
CB_ADMIN_CANCEL_CONFIRM = "cb_admin_cancel_c_book_"

# Общая кнопка отмены действия (вне процесса бронирования)
CB_ACTION_CANCEL = "cb_a_cancel_"
CB_IGNORE = "cb_ignore"

# Завершение
CB_FINISH_SELECT_BOOKING = "cb_finish_s_book_"

# Продление
CB_EXTEND_SELECT_BOOKING = "cb_extend_s_book_"
CB_EXTEND_SELECT_TIME = "cb_extend_s_time_"

# Уведомление об окончании
CB_NOTIFY_EXTEND_PROMPT = "cb_notify_ext_p_"
CB_NOTIFY_DECLINE_EXT = "cb_notify_dec_e_"

# Просмотр (/workspacebookings)
CB_WSB_SELECT_CATEGORY = "cb_wsb_s_cat_"
CB_WSB_SELECT_EQUIPMENT = "cb_wsb_s_eq_"

# Просмотр (/datebookings)
CB_DATEB_SELECT_DATE = "cb_dateb_s_date_"

# Регистрация (Админ)
CB_REG_CONFIRM_USER = "cb_reg_c_user_"
CB_REG_DECLINE_USER = "cb_reg_d_user_"

# Управление пользователями (Админ)
CB_MANAGE_SELECT_USER = "cb_manage_s_user_"
CB_MANAGE_BLOCK_USER = "cb_manage_a_block_"
CB_MANAGE_UNBLOCK_USER = "cb_manage_a_unblock_"

# Фильтр /all (Админ)
CB_FILTER_BY_TYPE = "cb_filter_by_"
CB_FILTER_SELECT_USER = "cb_filter_s_user_"
CB_FILTER_SELECT_EQUIPMENT = "cb_filter_s_eq_"
CB_FILTER_SELECT_DATE = "cb_filter_s_date_"

# Удаление оборудования (Админ)
CB_EQUIP_DELETE_SELECT = "cb_eq_del_s_"
CB_EQUIP_DELETE_CONFIRM = "cb_eq_del_c_"

# Добавление оборудования (Админ) - НОВОЕ
CB_ADMIN_ADD_EQUIP_SELECT_CAT_ = "cb_admin_add_eq_cat_" # Префикс + ID категории
CB_ADMIN_ADD_EQUIP_NEW_CAT = "cb_admin_add_eq_new_cat"
CB_ADMIN_ADD_EQUIP_CANCEL = "cb_admin_add_eq_cancel" # Отмена на шаге выбора категории


# Состояния для процесса бронирования пользователя
STATE_BOOKING_IDLE = 0
STATE_BOOKING_CATEGORY = 1
STATE_BOOKING_EQUIPMENT = 2
STATE_BOOKING_DATE = 3
STATE_BOOKING_SLOT = 4
STATE_BOOKING_START_TIME = 5
STATE_BOOKING_DURATION = 6
STATE_BOOKING_CONFIRM = 7

# Состояния для процесса добавления оборудования админом - НОВОЕ
ADMIN_STATE_ADD_EQUIP_NEW_CAT_NAME = "awaiting_new_cat_name"
ADMIN_STATE_ADD_EQUIP_NAME = "awaiting_equip_name"
ADMIN_STATE_ADD_EQUIP_NOTE = "awaiting_equip_note"


# --- Числовые Константы ---
BOOKING_CONFIRMATION_TIMEOUT_SECONDS = 300 # 5 минут
NOTIFICATION_BEFORE_START_MINUTES = 10
NOTIFICATION_BEFORE_END_MINUTES = 10
MAX_MESSAGE_LENGTH = 4096
# START_OF_WORKDAY_HOUR / END_OF_WORKDAY_HOUR / MINUTE берутся из WORKING_HOURS_*


# --- Константы Планировщика ---
JOB_TYPE_NOTIFY_START = "notify_start"
JOB_TYPE_NOTIFY_END = "notify_end"
JOB_TYPE_CONFIRM_TIMEOUT = "confirm_timeout" # <<< Добавлено для отслеживания таймаута подтверждения
# --- ИСПРАВЛЕНИЕ: Добавляем или проверяем наличие этой константы ---
JOB_TYPE_FINAL_END_NOTICE = "final_end_notice" # Для сообщения о фактическом окончании
JOB_TYPE_END_MSG_CLEANUP = "end_msg_cleanup" # <<< Добавлено для очистки сообщения после окончания брони


# --- Текстовые Константы ---

# Общие сообщения
MSG_ERROR_GENERAL = "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
MSG_ERROR_NO_PERMISSION = "У вас нет прав для выполнения этой команды."
MSG_ACTION_CANCELLED = "Действие отменено."
MSG_WELCOME = "Добро пожаловать, {name}! 👋\nИспользуйте команды или кнопки для взаимодействия."
MSG_HELP_USER = (
    "🤖 **Команды бота:**\n\n"
    "`/start` - Старт/Перезапуск\n"
    "`/booking` - Бронировать\n"
    "`/mybookings` - Мои брони\n"
    "`/finish` - Завершить\n"
    "`/cancel` - Отменить бронь\n"
    "`/extend` - Продлить бронь\n"
    "`/workspacebookings` - Брони по месту\n"
    "`/datebookings` - Брони по дате\n"
    "`/help` - Помощь\n"
)
MSG_HELP_ADMIN_ADDON = "\n👑 *Доступны команды администратора* (/adminhelp)"

# Регистрация и статус пользователя
MSG_ERROR_NOT_REGISTERED = "Вы не зарегистрированы или ваш аккаунт неактивен. Обратитесь к администратору или используйте /start."
MSG_ERROR_ACCOUNT_INACTIVE = "Ваш аккаунт неактивен. Обратитесь к администратору."
MSG_REGISTRATION_SENT = "✅ Заявка на регистрацию отправлена администратору."
MSG_REGISTRATION_PENDING = "⏳ Ваша заявка на рассмотрении."
MSG_REGISTRATION_APPROVED = "🎉 Ваша регистрация подтверждена."
MSG_REGISTRATION_DECLINED = "🚫 Ваша заявка на регистрацию отклонена."
MSG_ERROR_REGISTRATION_FAILED = "❌ Ошибка регистрации. Попробуйте /start позже."
MSG_USER_BLOCKED = "🔴 Пользователь заблокирован."
MSG_USER_UNBLOCKED = "🟢 Пользователь разблокирован."

# Сообщения для нового флоу бронирования
MSG_BOOKING_STEP_1_CATEGORY = "Шаг 1: Выберите категорию:"
MSG_BOOKING_STEP_2_EQUIPMENT = "Шаг 2: Выберите оборудование:"
MSG_BOOKING_STEP_3_DATE = "Шаг 3: Выберите дату:"
MSG_BOOKING_STEP_4_SLOT = "Шаг 4: Выберите интервал:"
MSG_BOOKING_STEP_5_START_TIME = "Шаг 5: Выберите время начала:"
MSG_BOOKING_STEP_6_DURATION = "Шаг 6: Выберите длительность:"
MSG_BOOKING_STEP_7_CONFIRM = "Шаг 7: Подтвердите бронь:"
MSG_BOOKING_PROMPT_START_TIME_IN_SLOT = "Шаг 5: Выберите время начала в интервале {start_slot} - {end_slot}:"
MSG_BOOKING_PROMPT_DURATION_IN_SLOT = "Шаг 6: Выберите длительность (окончание не позднее {end_slot}):"
MSG_BOOKING_CONFIRM_DETAILS = "Проверьте детали:\nОборудование: *{equip_name}*\nДата: {date}\nВремя: {start_time} - {end_time} ({duration})"
MSG_NO_SLOTS_AVAILABLE = "❌ Нет свободных интервалов на эту дату."
MSG_BOOKING_FAIL_OUTSIDE_WORK_HOURS = "❌ Время начала вне рабочих часов ({start_work} - {end_work})."
MSG_BOOKING_FAIL_ENDS_OUTSIDE_WORK_HOURS = "❌ Бронь выходит за рамки рабочего дня ({end_work})."
MSG_BOOKING_PROCESS_CANCELLED = "🚫 Бронирование отменено."
MSG_BOOKING_ERROR_STATE = "❌ Ошибка состояния. Начните заново /booking."
MSG_BOOKING_CONFIRM_TIMEOUT = "⏳ Время подтверждения бронирования истекло. Ваша бронь отменена."
MSG_BOOKING_ENDED_NO_ACTION = "Ваша работа на оборудовании {equipment_name} окончена."

# Бронирование (результаты, ошибки)
MSG_BOOKING_SUCCESS = "✅ Бронирование успешно создано!"
MSG_BOOKING_FAIL_GENERAL = "❌ Ошибка создания бронирования."
MSG_BOOKING_FAIL_OVERLAP = "❌ Время пересекается с другой бронью."
MSG_BOOKING_FAIL_LIMIT_EXCEEDED = f"❌ Макс. длительность: {MAX_BOOKING_DURATION_HOURS} ч."
MSG_BOOKING_FAIL_TIME_IN_PAST = "❌ Нельзя бронировать в прошлом."
MSG_BOOKING_FAIL_INVALID_TIME = "❌ Некорректное время/длительность."
MSG_BOOKING_CANCELLED = "🗑️ Бронь отменена."
MSG_BOOKING_FINISHED = "🏁 Работа завершена."
MSG_BOOKING_EXTENDED = "➕ Бронь продлена."
MSG_BOOKING_CONFIRMED = "👍 Бронь подтверждена."
MSG_EXTEND_DECLINED = "Понятно, бронь завершится по расписанию."
MSG_EXTEND_FAIL_NO_TIME = "❌ Продление невозможно: нет времени."
MSG_EXTEND_FAIL_NOT_ACTIVE = "❌ Не продлить: бронь неактивна."
MSG_FINISH_FAIL_NOT_ACTIVE = "❌ Не завершить: бронь неактивна."
MSG_CANCEL_FAIL_NOT_FOUND = "❌ Не отменить: бронь не найдена/неактивна."
MSG_CANCEL_FAIL_TOO_LATE = "❌ Не отменить: бронь уже началась."

# Добавлены сообщения для таймаутов
MSG_BOOKING_CONFIRM_TIMEOUT = "⏳ Время подтверждения бронирования истекло. Ваша бронь отменена."
MSG_BOOKING_ENDED_NO_ACTION = "Ваша работа на оборудовании {equipment_name} окончена."

# Оборудование (Админ)
MSG_EQUIP_DELETE_SUCCESS = "✅ Оборудование '{equipment_name}' удалено."
MSG_EQUIP_DELETE_SUCCESS_CAT = "✅ Оборудование '{equipment_name}' и категория удалены."
MSG_EQUIP_DELETE_FAIL_USED = "❌ Не удалить: '{equipment_name}' используется."
MSG_EQUIP_DELETE_FAIL_NOT_FOUND = "❌ Оборудование не найдено."
MSG_EQUIP_DELETE_FAIL_DB = "❌ Ошибка БД при удалении."
MSG_EQUIP_ADD_SUCCESS = "✅ Оборудование '{equipment_name}' добавлено в '{category_name}'."
MSG_EQUIP_ADD_FAIL = "❌ Не удалось добавить '{equipment_name}'."
MSG_EQUIP_ADD_FAIL_EXISTS = "❌ '{equipment_name}' уже есть в '{category_name}'."
MSG_CAT_CREATE_SUCCESS = "Создана категория '{category_name}' (ID: {category_id})."
MSG_CAT_CREATE_FAIL = "Не удалось создать/найти '{category_name}'."

# Текст помощи Админу
MSG_ADMIN_HELP = """
*Команды администратора:*
`/add_equipment` - Добавить оборудование
`/view_equipment` - Просмотр/удаление оборудования
`/admin_cancel` - Отменить бронь
`/all` - Отчет по всем броням
`/broadcast` - Рассылка
`/users` - Список пользователей
`/manage_user` - Блок/разблок пользователей
`/schedule` - Обновить уведомления
`/adminhelp` - Эта справка
"""

# --- END OF FILE constants.py ---