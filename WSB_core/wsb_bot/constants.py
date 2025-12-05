# constants_wsb.py
from datetime import time

# Версия программы
APP_VERSION = "WSB v.6.0.2"
"""
Модуль для хранения констант, таких как префиксы callback_data,
магические числа и строки для бота бронирования рабочих мест.
"""

# --- Команды Бота (для регистрации в меню и обработчиков) ---
# Пользовательские команды
CMD_START = "start"
CMD_BOOKING = "booking"
CMD_MY_BOOKINGS = "mybookings"
CMD_FINISH_BOOKING = "finish"
CMD_CANCEL_BOOKING = "cancel"
CMD_EXTEND_BOOKING = "extend"
CMD_WORKSPACE_BOOKINGS = "workspacebookings"
CMD_DATE_BOOKINGS = "datebookings"
CMD_HELP = "help"

# Админские команды
CMD_ADD_EQUIPMENT = "add_equipment"
CMD_MANAGE_EQUIPMENT = "manage_equipment"
CMD_ADMIN_HELP = "adminhelp"
CMD_ADMIN_CANCEL_BOOKING = "admin_cancel"
CMD_ALL_BOOKINGS = "all" # Общий отчет, может быть такой же, как у пользователя, или с доп. фильтрами
CMD_BROADCAST = "broadcast"
CMD_USERS_LIST = "users"
CMD_MANAGE_USER = "manage_user"
CMD_SCHEDULE_UPDATE = "schedule"


# --- Префиксы Callback Data ---
# cb - callback, s - select, c - confirm, a - action, d - decline, p - prompt
# book - booking process (cat - category, equip - equipment, date, time, dur)
# reg - registration
# manage - user management
# filter - /all_wsb filter
# wspb - workspace bookings (просмотр по оборудованию)
# dateb - date bookings (просмотр по дате)
# notify - notification buttons
# ext - extend
# fin - finish (завершение)
# canc - cancel (отмена)
# admin_add_equip - admin add equipment process (включает создание категории)
# admin_manage_equip - admin manage equipment process (включает удаление категории)

# Импортируем константы из общего ядра wsb_core
try:
    from wsb_core.constants import (
        WORKING_HOURS_START,
        WORKING_HOURS_END,
        BOOKING_TIME_STEP_MINUTES,
        MAX_BOOKING_DURATION_HOURS
    )
except ImportError:
    # Fallback на локальные значения, если wsb_core недоступен
    BOOKING_TIME_STEP_MINUTES = 30
    MAX_BOOKING_DURATION_HOURS = 8
    WORKING_HOURS_START = time(8, 0)
    WORKING_HOURS_END = time(20, 0)

# Бронирование (Пользователь)
CB_BOOK_ACTION = "cb_book_a_"
CB_BOOK_SELECT_CATEGORY = f"{CB_BOOK_ACTION}s_cat_"
CB_BOOK_SELECT_EQUIPMENT = f"{CB_BOOK_ACTION}s_equip_"
CB_BOOK_SELECT_DATE = f"{CB_BOOK_ACTION}s_date_"
CB_BOOK_SELECT_SLOT = f"{CB_BOOK_ACTION}s_slot_"
CB_BOOK_SELECT_TIME = f"{CB_BOOK_ACTION}s_time_"
CB_BOOK_SELECT_DURATION = f"{CB_BOOK_ACTION}s_dur_"
CB_BOOK_CONFIRM_FINAL = f"{CB_BOOK_ACTION}c_final"
CB_BOOK_CANCEL_PROCESS = f"{CB_BOOK_ACTION}cancel" # Отмена в процессе бронирования

# Подтверждение начала брони (из уведомления)
CB_BOOK_CONFIRM_START = "cb_book_c_start_"

# Отмена существующей брони (Пользователь/Админ)
CB_CANCEL_SELECT_BOOKING = "cb_canc_s_book_" # Пользователь выбирает свою бронь
CB_ADMIN_CANCEL_SELECT = "cb_admin_canc_s_book_" # Админ выбирает любую бронь
CB_ADMIN_CANCEL_CONFIRM = "cb_admin_canc_c_book_" # Админ подтверждает отмену

# Общая кнопка отмены действия (вне процесса бронирования, для FSM и т.п.)
CB_ACTION_CANCEL = "cb_a_cancel_"
CB_IGNORE = "cb_ignore" # Для кнопок-пустышек

# Завершение брони (Пользователь)
CB_FINISH_SELECT_BOOKING = "cb_fin_s_book_"

# Продление брони (Пользователь)
CB_EXTEND_SELECT_BOOKING = "cb_ext_s_book_"
CB_EXTEND_SELECT_TIME = "cb_ext_s_time_"

# Уведомление об окончании (Пользователь)
CB_NOTIFY_EXTEND_PROMPT = "cb_notify_ext_p_"
CB_NOTIFY_DECLINE_EXT = "cb_notify_dec_e_"

# Просмотр броней по рабочим местам (/workspacebookings) (Пользователь)
CB_WSPB_SELECT_CATEGORY = "cb_wspb_s_cat_"
CB_WSPB_SELECT_EQUIPMENT = "cb_wspb_s_equip_"

# Просмотр броней по дате (/datebookings) (Пользователь)
CB_DATEB_SELECT_DATE = "cb_dateb_s_date_"

# Регистрация (Админ)
CB_REG_CONFIRM_USER = "cb_reg_c_user_"
CB_REG_DECLINE_USER = "cb_reg_d_user_"

# Управление пользователями (Админ)
CB_MANAGE_USER_SELECT = "cb_manage_s_user_" # Изменено с CB_MANAGE_SELECT_USER для единообразия
CB_MANAGE_USER_ACTION_BLOCK = "cb_manage_a_block_"
CB_MANAGE_USER_ACTION_UNBLOCK = "cb_manage_a_unblock_"
CB_MANAGE_USER_ACTION_MAKE_ADMIN = "cb_manage_a_mkadmin_"
CB_MANAGE_USER_ACTION_REMOVE_ADMIN = "cb_manage_a_rmadmin_"


# Фильтр /all (Админ)
CB_FILTER_BY_TYPE = "cb_filter_by_" # Например, filter_by_user, filter_by_equip
CB_FILTER_SELECT_USER = "cb_filter_s_user_"
CB_FILTER_SELECT_CATEGORY = "cb_filter_s_cat_"
CB_FILTER_SELECT_EQUIPMENT = "cb_filter_s_equip_"
CB_FILTER_SELECT_DATE = "cb_filter_s_date_"

# Добавление оборудования (Админ, многошаговый процесс)
CB_ADMIN_ADD_EQUIP_SELECT_CAT = "cb_adm_add_eq_s_cat_"  # Выбор существующей категории
CB_ADMIN_ADD_EQUIP_NEW_CAT_PROMPT = "cb_adm_add_eq_new_cat_p" # Кнопка "Добавить новую категорию"
CB_ADMIN_ADD_EQUIP_CANCEL_PROCESS = "cb_adm_add_eq_cancel_p" # Отмена процесса добавления

# Управление (удаление) оборудованием (Админ, многошаговый процесс)
CB_ADMIN_MANAGE_EQUIP_SELECT_CAT = "cb_adm_man_eq_s_cat_" # Выбор категории для управления
CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP = "cb_adm_man_eq_s_equip_" # Выбор оборудования для удаления
CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE = "cb_adm_man_eq_c_del_" # Подтверждение удаления оборудования
CB_ADMIN_MANAGE_EQUIP_CANCEL_PROCESS = "cb_adm_man_eq_cancel_p" # Отмена процесса управления

# Рассылка (Админ)
CB_ADMIN_BROADCAST_CONFIRM = "cb_admin_bc_confirm"
CB_ADMIN_BROADCAST_CANCEL = "cb_admin_bc_cancel"


# Состояния для процесса бронирования пользователя (FSM)
STATE_BOOKING_IDLE = 0 # Может не понадобиться без FSM
STATE_BOOKING_CATEGORY = 1
STATE_BOOKING_EQUIPMENT = 2
STATE_BOOKING_DATE = 3
STATE_BOOKING_SLOT = 4 # или STATE_BOOKING_START_TIME, если слоты не используются
STATE_BOOKING_START_TIME = 5
STATE_BOOKING_DURATION = 6
STATE_BOOKING_CONFIRM = 7

# Состояния для процесса добавления оборудования админом (FSM или next_step_handler)
ADMIN_STATE_ADD_EQUIP_SELECT_OR_CREATE_CATEGORY = "admin_add_equip_select_or_create_cat"
ADMIN_STATE_PROMPT_NEW_CAT_NAME = "admin_add_equip_prompt_new_cat_name"
ADMIN_STATE_ADD_EQUIP_GET_NAME = "admin_add_equip_get_name"
ADMIN_STATE_ADD_EQUIP_GET_NOTE = "admin_add_equip_get_note"

# Состояния для процесса управления (удаления) оборудованием админом (FSM или next_step_handler)
ADMIN_STATE_MANAGE_EQUIP_SELECT_CAT = "admin_manage_equip_select_cat"
ADMIN_STATE_MANAGE_EQUIP_SELECT_EQUIP = "admin_manage_equip_select_equip"
# ADMIN_STATE_MANAGE_EQUIP_CONFIRM_DELETE - обычно решается кнопкой с callback, состояние не нужно

# Состояние для рассылки (Админ)
ADMIN_STATE_BROADCAST_GET_MESSAGE = "admin_broadcast_get_message"
# ADMIN_STATE_BROADCAST_CONFIRM - обычно решается кнопкой с callback

# --- Числовые Константы ---
BOOKING_CONFIRMATION_TIMEOUT_SECONDS = 540 # 9 минут до автоотмены неподтвержденной брони
NOTIFICATION_BEFORE_START_MINUTES = 10
NOTIFICATION_BEFORE_END_MINUTES = 10
MAX_MESSAGE_LENGTH = 4096

# --- Константы Планировщика ---
JOB_TYPE_NOTIFY_START = "notify_start"
JOB_TYPE_NOTIFY_END = "notify_end"
JOB_TYPE_CONFIRM_TIMEOUT = "confirm_timeout" # Для автоотмены неподтвержденных броней
JOB_TYPE_AUTO_FINISH = "auto_finish" # Новая задача для автозавершения
# JOB_TYPE_END_MSG_CLEANUP = "end_msg_cleanup" # Опционально, если нужно удалять сообщения

# --- Текстовые Константы ---

# Общие сообщения
MSG_ERROR_GENERAL = "Произошла непредвиденная ошибка. Пожалуйста, попробуйте позже."
MSG_ERROR_NO_PERMISSION = "У вас нет прав для выполнения этой команды."
MSG_ACTION_CANCELLED = "Действие отменено."
MSG_WELCOME = f"Добро пожаловать, {{name}}! 👋\nБот для бронирования рабочих мест (WSB).\nИспользуйте команды или кнопки для взаимодействия.\nВерсия: {APP_VERSION}"
MSG_HELP_USER = (
    "🤖 **Команды бота WSB:**\n\n"
    f"`/{CMD_START}` - Старт/Перезапуск\n"
    f"`/{CMD_BOOKING}` - Бронировать рабочее место\n"
    f"`/{CMD_MY_BOOKINGS}` - Мои бронирования\n"
    f"`/{CMD_FINISH_BOOKING}` - Завершить бронь\n"
    f"`/{CMD_CANCEL_BOOKING}` - Отменить бронь\n"
    f"`/{CMD_EXTEND_BOOKING}` - Продлить бронь\n"
    f"`/{CMD_WORKSPACE_BOOKINGS}` - Брони по рабочим местам\n"
    f"`/{CMD_DATE_BOOKINGS}` - Брони по дате\n"
    f"`/{CMD_HELP}` - Помощь\n"
    f"_Версия: {APP_VERSION}_"
)
MSG_HELP_ADMIN_ADDON = f"\n👑 *Доступны команды администратора* (/{CMD_ADMIN_HELP})"

# Регистрация и статус пользователя
MSG_ERROR_NOT_REGISTERED = f"Вы не зарегистрированы или ваш аккаунт неактивен. Обратитесь к администратору или используйте /{CMD_START}."
MSG_ERROR_ACCOUNT_INACTIVE = "Ваш аккаунт неактивен. Обратитесь к администратору."
MSG_REGISTRATION_SENT = "✅ Заявка на регистрацию отправлена администратору."
MSG_REGISTRATION_PENDING = "⏳ Ваша заявка на рассмотрении."
MSG_REGISTRATION_APPROVED = "🎉 Ваша регистрация подтверждена."
MSG_REGISTRATION_DECLINED = "🚫 Ваша заявка на регистрацию отклонена."
MSG_ERROR_REGISTRATION_FAILED = f"❌ Ошибка регистрации. Попробуйте /{CMD_START} позже."
MSG_USER_BLOCKED = "🔴 Пользователь заблокирован."
MSG_USER_UNBLOCKED = "🟢 Пользователь разблокирован."
MSG_USER_MADE_ADMIN = "👑 Пользователю предоставлены права администратора."
MSG_USER_REMOVED_ADMIN = "👤 У пользователя отозваны права администратора."

# Сообщения для флоу бронирования WSB (Пользователь)
MSG_BOOKING_STEP_1_CATEGORY = "Шаг 1: Выберите категорию оборудования:"
MSG_BOOKING_STEP_2_EQUIPMENT = "Шаг 2: Выберите оборудование из категории '{category_name}':"
MSG_BOOKING_STEP_3_DATE = "Шаг 3: Выберите дату:"
MSG_BOOKING_STEP_4_SLOT = "Шаг 4: Выберите доступный интервал:" # Если используются слоты
MSG_BOOKING_STEP_5_START_TIME = "Шаг 5: Выберите время начала:"
MSG_BOOKING_STEP_6_DURATION = "Шаг 6: Выберите длительность:"
MSG_BOOKING_STEP_7_CONFIRM = "Шаг 7: Подтвердите бронь:"
MSG_BOOKING_PROMPT_START_TIME_IN_SLOT = "Шаг 5: Выберите время начала в интервале {start_slot} - {end_slot}:"
MSG_BOOKING_PROMPT_DURATION_IN_SLOT = "Шаг 6: Выберите длительность (окончание не позднее {end_slot}):"
MSG_BOOKING_CONFIRM_DETAILS = "Проверьте детали:\nКатегория: *{category_name}*\nОборудование: *{equip_name}*\nДата: {date}\nВремя: {start_time} - {end_time} ({duration})"
MSG_NO_CATEGORIES_AVAILABLE = "❌ Нет доступных категорий оборудования для бронирования."
MSG_CAT_CREATE_FAIL = "❌ Не удалось создать категорию оборудования."
MSG_EQUIP_ADD_FAIL_EXISTS = "❌ Оборудование с таким именем уже существует."
MSG_NO_EQUIPMENT_IN_CATEGORY = "❌ Нет доступного оборудования в выбранной категории '{category_name}'."
MSG_NO_SLOTS_AVAILABLE = "❌ Нет свободных интервалов на эту дату для выбранного оборудования."
MSG_BOOKING_FAIL_OUTSIDE_WORK_HOURS = f"❌ Время начала вне рабочих часов ({time.strftime(WORKING_HOURS_START, '%H:%M')} - {time.strftime(WORKING_HOURS_END, '%H:%M')})."
MSG_BOOKING_FAIL_ENDS_OUTSIDE_WORK_HOURS = f"❌ Бронь выходит за рамки рабочего дня (до {time.strftime(WORKING_HOURS_END, '%H:%M')})."
MSG_BOOKING_PROCESS_CANCELLED = f"🚫 Бронирование отменено. Начните заново /{CMD_BOOKING}."
MSG_BOOKING_ERROR_STATE = f"❌ Ошибка состояния процесса бронирования. Начните заново /{CMD_BOOKING}."
MSG_BOOKING_CONFIRM_TIMEOUT_USER_MSG = f"⏳ Время подтверждения бронирования истекло. Ваша бронь была автоматически отменена. Для создания новой брони, пожалуйста, начните процесс заново с команды /{CMD_BOOKING}."
MSG_BOOKING_NEEDS_CONFIRMATION = "✅ Бронь создана и ожидает вашего подтверждения в течение {timeout_min} минут. Подтвердите её через уведомление или в разделе 'Мои бронирования'."
MSG_BOOKING_ENDED_NO_ACTION_WSB = "Ваше время использования оборудования '{equip_name}' (категория: '{category_name}') окончено."

# Бронирование (результаты, ошибки - общие для пользователя и системы)
MSG_BOOKING_SUCCESS = "✅ Бронирование успешно создано и подтверждено!"
MSG_BOOKING_FAIL_GENERAL = "❌ Ошибка создания бронирования."
MSG_BOOKING_FAIL_OVERLAP = "❌ Выбранное время пересекается с другой бронью для этого оборудования."
MSG_BOOKING_FAIL_LIMIT_EXCEEDED = f"❌ Макс. длительность бронирования: {MAX_BOOKING_DURATION_HOURS} ч."
MSG_BOOKING_FAIL_TIME_IN_PAST = "❌ Нельзя бронировать на прошедшее время."
MSG_BOOKING_FAIL_INVALID_TIME = "❌ Некорректное время или длительность."
MSG_BOOKING_CANCELLED_SUCCESS = "🗑️ Бронь успешно отменена."
MSG_BOOKING_ALREADY_CANCELLED = "Бронь уже была отменена ранее."
MSG_BOOKING_ALREADY_FINISHED = "Бронь уже была завершена ранее."
MSG_BOOKING_WAS_CANCELLED = "Эта бронь была отменена."
MSG_BOOKING_FINISHED_WSB = "🏁 Бронь завершена."
MSG_BOOKING_EXTENDED_WSB = "➕ Бронь продлена."
MSG_BOOKING_CONFIRMED = "👍 Бронь подтверждена и активна."
MSG_EXTEND_DECLINED = "Понятно, бронь завершится по расписанию."
MSG_EXTEND_FAIL_NO_TIME = "❌ Продление невозможно: нет свободного времени или достигнут лимит."
MSG_EXTEND_FAIL_NOT_ACTIVE = "❌ Нельзя продлить: бронь не активна."
MSG_EXTEND_FAIL_NOT_FOUND = "❌ Бронь для продления не найдена."
MSG_EXTEND_FAIL_NOT_YOURS = "❌ Это не ваше бронирование."
MSG_EXTEND_FAIL_ALREADY_ENDED = "❌ Бронирование уже завершилось, продление невозможно."
MSG_FINISH_FAIL_NOT_ACTIVE = "❌ Нельзя завершить: бронь не активна."
MSG_FINISH_FAIL_NOT_YOURS = "❌ Это не ваше бронирование."
MSG_CANCEL_FAIL_NOT_FOUND = "❌ Бронь для отмены не найдена."
MSG_CANCEL_FAIL_NOT_YOURS = "❌ Это не ваше бронирование."
MSG_CANCEL_FAIL_TOO_LATE = "❌ Нельзя отменить: бронь уже началась или завершена."
MSG_CANCEL_FAIL_CANNOT_CANCEL_ACTIVE = "❌ Активную бронь нельзя отменить, только завершить."

# Администрирование оборудования и категорий
MSG_ADMIN_ADD_EQUIP_CHOOSE_CAT = "Выберите категорию для добавления оборудования или создайте новую:"
MSG_ADMIN_PROMPT_NEW_CAT_NAME = "Введите название новой категории оборудования (например, 'Ноутбуки', 'Мониторы'):"
MSG_ADMIN_CAT_ADD_SUCCESS = "✅ Категория оборудования '{name_cat}' успешно добавлена."
MSG_ADMIN_CAT_ADD_FAIL_EXISTS = "❌ Категория оборудования с именем '{name_cat}' уже существует. Попробуйте другое имя или выберите эту категорию из списка."
MSG_ADMIN_CAT_ADD_FAIL_GENERAL = "❌ Не удалось добавить категорию оборудования '{name_cat}'."
MSG_ADMIN_PROMPT_EQUIP_NAME = "Введите название нового оборудования для категории '{name_cat}' (например, 'HP ProBook G7', 'Dell 24inch'):"
MSG_ADMIN_PROMPT_EQUIP_NOTE = "Введите примечание для оборудования '{name_equip}' (опционально, например, 'S/N: 12345XYZ', 'С HDMI'. Нажмите /skip, чтобы пропустить):"
MSG_ADMIN_EQUIP_ADD_SUCCESS = "✅ Оборудование '{name_equip}' успешно добавлено в категорию '{name_cat}'."
MSG_ADMIN_EQUIP_ADD_FAIL_CAT_NOT_FOUND = "❌ Категория для добавления оборудования не найдена. Процесс прерван."
MSG_ADMIN_EQUIP_ADD_FAIL_EXISTS = "❌ Оборудование с именем '{name_equip}' уже существует в категории '{name_cat}'."
MSG_ADMIN_EQUIP_ADD_FAIL_GENERAL = "❌ Не удалось добавить оборудование '{name_equip}'."
MSG_ADMIN_ADD_EQUIP_PROCESS_CANCELLED = f"🚫 Процесс добавления оборудования отменен. Начните заново /{CMD_ADD_EQUIPMENT}."

MSG_ADMIN_MANAGE_EQUIP_CHOOSE_CAT = "Выберите категорию для просмотра и удаления оборудования:"
MSG_ADMIN_MANAGE_EQUIP_NO_CATEGORIES = "Нет категорий для управления оборудованием."
MSG_ADMIN_MANAGE_EQUIP_CHOOSE_EQUIP = "Выберите оборудование для удаления из категории '{category_name}':"
MSG_ADMIN_MANAGE_EQUIP_NO_EQUIP_IN_CAT = "В категории '{category_name}' нет оборудования для удаления."
MSG_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE = "Вы уверены, что хотите удалить оборудование '{equip_name}' из категории '{category_name}'?"
MSG_ADMIN_EQUIP_DELETE_SUCCESS = "✅ Оборудование '{name_equip}' (категория: '{name_cat}') удалено."
MSG_ADMIN_CAT_AUTO_DELETE_SUCCESS = "✅ Категория '{name_cat}' была пуста и автоматически удалена."
MSG_ADMIN_EQUIP_DELETE_FAIL_HAS_HISTORY = "❌ Оборудование '{name_equip}' не может быть удалено, так как оно использовалось в бронированиях."
MSG_ADMIN_EQUIP_DELETE_FAIL_NOT_FOUND = "❌ Оборудование не найдено для удаления."
MSG_ADMIN_EQUIP_DELETE_FAIL_DB = "❌ Ошибка БД при удалении оборудования."
MSG_ADMIN_CAT_AUTO_DELETE_FAIL = "⚠️ Не удалось автоматически удалить пустую категорию '{name_cat}' после удаления оборудования."
MSG_ADMIN_MANAGE_EQUIP_PROCESS_CANCELLED = f"🚫 Процесс управления оборудованием отменен. Начните заново /{CMD_MANAGE_EQUIPMENT}."

# Рассылка (Админ)
MSG_ADMIN_BROADCAST_PROMPT = "Введите сообщение для рассылки всем активным пользователям:"
MSG_ADMIN_BROADCAST_CONFIRM_PROMPT = "Вы уверены, что хотите разослать следующее сообщение?\n\n---\n{broadcast_message}\n---"
MSG_ADMIN_BROADCAST_SENT_SUCCESS = "✅ Рассылка успешно отправлена {count_success} пользователям."
MSG_ADMIN_BROADCAST_SENT_PARTIAL = "⚠️ Рассылка отправлена {count_success} пользователям, но для {count_fail} пользователей произошла ошибка."
MSG_ADMIN_BROADCAST_SENT_FAIL = "❌ Не удалось отправить рассылку ни одному пользователю."
MSG_ADMIN_BROADCAST_NO_USERS = "Нет активных пользователей для рассылки."

# Текст помощи Админу для WSB
MSG_ADMIN_HELP = (
    "*Команды администратора WSB:*\n"
    f"`/{CMD_ADD_EQUIPMENT}` - Добавить оборудование (включая создание категорий)\n"
    f"`/{CMD_MANAGE_EQUIPMENT}` - Удаление оборудования (включая удаление пустых категорий)\n"
    f"`/{CMD_ADMIN_CANCEL_BOOKING}` - Отменить любую бронь\n"
    f"`/{CMD_ALL_BOOKINGS}` - Отчет по всем броням\n"
    f"`/{CMD_BROADCAST}` - Рассылка сообщений\n"
    f"`/{CMD_USERS_LIST}` - Список пользователей\n"
    f"`/{CMD_MANAGE_USER}` - Управление пользователями\n"
    f"`/{CMD_SCHEDULE_UPDATE}` - Обновить уведомления (вручную)\n"
    f"`/{CMD_ADMIN_HELP}` - Эта справка\n"
    f"_Версия: {APP_VERSION}_"
)

# Тексты для Reply Keyboard кнопок (WSB) - Главное меню пользователя
BTN_TEXT_HELP = "❓ Помощь"
BTN_TEXT_BOOKING = "💻 Бронировать место"
BTN_TEXT_CANCEL = "❌ Отменить бронь"
BTN_TEXT_FINISH = "🏁 Завершить бронь"
BTN_TEXT_EXTEND = "⏳ Продлить бронь"
BTN_TEXT_MYBOOKINGS = "📄 Мои бронировния"
BTN_TEXT_WORKSPACEBOOKINGS = "🖥️ Бронь по раб. местам" # Ранее было roombookings
BTN_TEXT_DATEBOOKINGS = "🗓️ Бронь по дате"

# Тексты для Reply Keyboard кнопок (WSB) - Главное меню админа (если отличается)
BTN_TEXT_ADMIN_HELP = "🪄 Помощь админу"
BTN_TEXT_ADD_EQUIPMENT = "💻 Добавить оборудование"
BTN_TEXT_MANAGE_EQUIPMENT = "⚙️ Оборудование (Удал.)"
BTN_TEXT_ADMIN_CANCEL_KB = "🚫 Отменить бронь" # KB для отличия от команды
BTN_TEXT_ALL_KB = "📊 Отчет / Фильтр"
BTN_TEXT_BROADCAST_KB = "📢 Рассылка"
BTN_TEXT_MANAGE_USER_KB = "👤 Упр. польз."
BTN_TEXT_USERS_KB = "👥 Список польз."
BTN_TEXT_SCHEDULE_KB = "⚙️ Обновить график"

# Общие кнопки для инлайн-клавиатур
BTN_TEXT_CONFIRM = "✅ Подтвердить"
BTN_TEXT_DECLINE_GENERIC = "❌ Отклонить"
BTN_TEXT_CANCEL_ACTION = "🚫 Отменить действие"
BTN_TEXT_BACK = "⬅️ Назад"
BTN_TEXT_SKIP = "➡️ Пропустить"
BTN_TEXT_CREATE_NEW_CATEGORY = "➕ Добавить новую категорию"
BTN_TEXT_YES = "Да"
BTN_TEXT_NO = "Нет"