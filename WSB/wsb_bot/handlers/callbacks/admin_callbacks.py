# handlers/callbacks/admin_callbacks.py
import telebot
from telebot.types import CallbackQuery, Message  # Message для register_next_step_handler
from bot_app import bot as bot_instance_global, db_connection as db_connection_global, scheduler, \
    scheduled_jobs_registry
from logger import logger
from services import user_service, equipment_service, booking_service, admin_service, notification_service, \
    registration_notification_service
from utils import keyboards
import constants as const
from wsb_bot.handlers.admin_commands import admin_step_cache, clear_admin_step_cache  # Импортируем кэш и функцию очистки
from typing import Dict, Any, Optional, Set, Tuple, List

# Используем глобальные экземпляры
bot: telebot.TeleBot = bot_instance_global
db_connection = db_connection_global


# --- Вспомогательная функция для редактирования или отправки сообщения ---
def _edit_or_send_message(chat_id: int, message_id: Optional[int], text: str, reply_markup=None, parse_mode=None):
    """Пытается отредактировать сообщение, если message_id есть, иначе отправляет новое."""
    try:
        if message_id:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup,
                                  parse_mode=parse_mode)
        else:
            bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except telebot.apihelper.ApiTelegramException as e:
        if "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
            # Если сообщение не найдено для редактирования или не изменено, отправляем новое
            logger.warning(f"Сообщение {message_id} не найдено/не изменено, отправка нового. Ошибка: {e}")
            bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif "message can't be edited" in str(e).lower():
            logger.warning(f"Сообщение {message_id} не может быть отредактировано, отправка нового. Ошибка: {e}")
            bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            logger.error(
                f"Ошибка API при редактировании/отправке сообщения (chat_id: {chat_id}, msg_id: {message_id}): {e}")
            # В крайнем случае, если даже отправка нового не удалась (например, бот заблокирован)
            # можно просто залогировать и не падать
    except Exception as e_gen:
        logger.error(
            f"Общая ошибка при редактировании/отправке сообщения (chat_id: {chat_id}, msg_id: {message_id}): {e_gen}",
            exc_info=True)


# --- Регистрация всех обработчиков колбэков для админа ---
def register_admin_callback_handlers(bot_param: telebot.TeleBot, db_param, scheduler_param, registry_param):
    # Используем глобальные экземпляры
    pass

    # === Обработчики для процесса добавления оборудования (/add_equipment) ===

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_ADMIN_ADD_EQUIP_SELECT_CAT))
    def handle_add_equip_select_category(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if admin_id not in admin_step_cache or admin_step_cache[admin_id].get(
                'state') != const.ADMIN_STATE_ADD_EQUIP_CHOOSE_CATEGORY:
            bot.answer_callback_query(call.id, "Сессия добавления оборудования истекла или неверна. Начните заново.",
                                      show_alert=True)
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE,
                                  reply_markup=None)  # Общее сообщение об ошибке состояния
            return

        try:
            category_id = int(call.data[len(const.CB_ADMIN_ADD_EQUIP_SELECT_CAT):])
        except ValueError:
            logger.error(f"Ошибка парсинга category_id из callback: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка данных. Попробуйте снова.", show_alert=True)
            return

        category_info = equipment_service.get_category_by_id(db_connection, category_id)
        if not category_info:
            bot.answer_callback_query(call.id, "Выбранная категория не найдена.", show_alert=True)
            _edit_or_send_message(chat_id, message_id, "Ошибка: категория не найдена. Процесс прерван.",
                                  reply_markup=None)
            clear_admin_step_cache(admin_id)
            return

        bot.answer_callback_query(call.id, f"Категория '{category_info['name_cat']}' выбрана.")
        admin_step_cache[admin_id]['data']['category_id'] = category_id
        admin_step_cache[admin_id]['data']['category_name'] = category_info['name_cat']
        admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NAME

        prompt_text = const.MSG_ADMIN_PROMPT_EQUIP_NAME_TEXT.format(name_cat=category_info['name_cat'])
        _edit_or_send_message(chat_id, message_id, prompt_text, reply_markup=None, parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_name_input, admin_id_for_cache=admin_id)

    @bot.callback_query_handler(func=lambda call: call.data == const.CB_ADMIN_ADD_EQUIP_CREATE_NEW_CAT_PROMPT)
    def handle_add_equip_prompt_new_category(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if admin_id not in admin_step_cache or admin_step_cache[admin_id].get(
                'state') != const.ADMIN_STATE_ADD_EQUIP_CHOOSE_CATEGORY:
            bot.answer_callback_query(call.id, "Сессия добавления оборудования истекла. Начните заново.",
                                      show_alert=True)
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        bot.answer_callback_query(call.id)
        admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_ADD_EQUIP_NEW_CATEGORY_NAME
        _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_PROMPT_NEW_CAT_NAME_TEXT, reply_markup=None,
                              parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_new_category_name_input,
                                                  admin_id_for_cache=admin_id)

    @bot.callback_query_handler(func=lambda call: call.data == const.CB_ADMIN_ADD_EQUIP_CANCEL_PROCESS)
    def handle_add_equip_cancel_process(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
        _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_ADD_EQUIP_PROCESS_CANCELLED_TEXT, reply_markup=None)
        clear_admin_step_cache(admin_id)

    # === Обработчики для процесса управления/удаления оборудования (/manage_equipment) ===

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_ADMIN_MANAGE_EQUIP_SELECT_CAT))
    def handle_manage_equip_select_category(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if admin_id not in admin_step_cache or admin_step_cache[admin_id].get(
                'state') != const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_CATEGORY:
            bot.answer_callback_query(call.id, "Сессия управления оборудованием истекла. Начните заново.",
                                      show_alert=True)
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        try:
            category_id = int(call.data[len(const.CB_ADMIN_MANAGE_EQUIP_SELECT_CAT):])
        except ValueError:
            logger.error(f"Ошибка парсинга category_id из callback: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка данных. Попробуйте снова.", show_alert=True)
            return

        category_info = equipment_service.get_category_by_id(db_connection, category_id)
        if not category_info:
            bot.answer_callback_query(call.id, "Выбранная категория не найдена.", show_alert=True)
            _edit_or_send_message(chat_id, message_id, "Ошибка: категория не найдена. Процесс прерван.",
                                  reply_markup=None)
            clear_admin_step_cache(admin_id)
            return

        bot.answer_callback_query(call.id, f"Категория '{category_info['name_cat']}' выбрана.")
        admin_step_cache[admin_id]['data']['category_id'] = category_id
        admin_step_cache[admin_id]['data']['category_name'] = category_info['name_cat']
        admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_EQUIPMENT

        equipments_in_category = equipment_service.get_equipment_by_category(db_connection, category_id)
        if not equipments_in_category:
            _edit_or_send_message(chat_id, message_id,
                                  const.MSG_ADMIN_MANAGE_EQUIP_NO_EQUIP_IN_CAT_TEXT.format(
                                      category_name=category_info['name_cat']),
                                  reply_markup=keyboards.generate_admin_select_equipment_to_delete_keyboard([],
                                                                                                            category_id),
                                  # Пустая клавиатура с кнопкой назад
                                  parse_mode='Markdown')
            return

        markup = keyboards.generate_admin_select_equipment_to_delete_keyboard(equipments_in_category, category_id)
        _edit_or_send_message(chat_id, message_id,
                              const.MSG_ADMIN_MANAGE_EQUIP_CHOOSE_EQUIP_TEXT.format(
                                  category_name=category_info['name_cat']),
                              reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP_TO_DELETE))
    def handle_manage_equip_select_equipment_to_delete(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if admin_id not in admin_step_cache or admin_step_cache[admin_id].get(
                'state') != const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_EQUIPMENT:
            bot.answer_callback_query(call.id, "Сессия управления оборудованием истекла. Начните заново.",
                                      show_alert=True)
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        try:
            equip_id = int(call.data[len(const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP_TO_DELETE):])
        except ValueError:
            logger.error(f"Ошибка парсинга equip_id из callback: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка данных. Попробуйте снова.", show_alert=True)
            return

        equip_details = equipment_service.get_equipment_details_by_id(db_connection, equip_id)
        if not equip_details:
            bot.answer_callback_query(call.id, "Выбранное оборудование не найдено.", show_alert=True)
            _edit_or_send_message(chat_id, message_id, "Ошибка: оборудование не найдено. Процесс прерван.",
                                  reply_markup=None)
            # Можно вернуть на шаг выбора категории или очистить состояние
            return

        bot.answer_callback_query(call.id)
        admin_step_cache[admin_id]['data']['equip_id_to_delete'] = equip_id
        admin_step_cache[admin_id]['data']['equip_name_to_delete'] = equip_details['name_equip']
        # Состояние можно не менять, т.к. следующий шаг - подтверждение по кнопке

        markup = keyboards.generate_admin_confirm_delete_equipment_keyboard(equip_id)
        confirm_text = const.MSG_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE_TEXT.format(
            equip_name=equip_details['name_equip'],
            category_name=admin_step_cache[admin_id]['data']['category_name']
        )
        _edit_or_send_message(chat_id, message_id, confirm_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(const.CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE_EQUIP))
    def handle_manage_equip_confirm_delete(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Проверка состояния не так важна, если equip_id есть в callback_data

        try:
            equip_id = int(call.data[len(const.CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE_EQUIP):])
        except ValueError:
            logger.error(f"Ошибка парсинга equip_id из callback: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка данных. Попробуйте снова.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "Удаляю оборудование...")

        success, message_key, details = equipment_service.delete_equipment(db_connection, equip_id)

        final_message = ""
        if success:
            if message_key == "EQUIPMENT_DELETE_SUCCESS":
                final_message = const.MSG_ADMIN_EQUIP_DELETE_SUCCESS_TEXT.format(
                    name_equip=details.get('equip_name', 'N/A'),
                    name_cat=details.get('category_name', 'N/A')
                )
                if details.get('category_auto_deleted'):
                    final_message += "\n" + const.MSG_ADMIN_CAT_AUTO_DELETE_SUCCESS_TEXT.format(
                        name_cat=details.get('category_name', 'N/A'))
            # Добавить обработку других message_key от equipment_service.delete_equipment при необходимости
        else:
            if message_key == "EQUIPMENT_HAS_BOOKING_HISTORY":
                final_message = const.MSG_ADMIN_EQUIP_DELETE_FAIL_HAS_BOOKING_HISTORY_TEXT.format(
                    name_equip=details.get('equip_name', 'N/A'))
            elif message_key == "EQUIPMENT_NOT_FOUND":
                final_message = const.MSG_ADMIN_EQUIP_DELETE_FAIL_NOT_FOUND_TEXT
            else:  # DB_ERROR_DELETING_EQUIPMENT или другая ошибка
                final_message = const.MSG_ADMIN_EQUIP_DELETE_FAIL_DB_ERROR_TEXT

        _edit_or_send_message(chat_id, message_id, final_message, reply_markup=None, parse_mode='Markdown')
        clear_admin_step_cache(admin_id)  # Очищаем состояние после завершения операции

    @bot.callback_query_handler(func=lambda call: call.data == const.CB_ADMIN_MANAGE_EQUIP_CANCEL_PROCESS)
    def handle_manage_equip_cancel_process(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
        _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_MANAGE_EQUIP_PROCESS_CANCELLED_TEXT,
                              reply_markup=None)
        clear_admin_step_cache(admin_id)

    # === Обработчики для отчета /all ===
    # (скопированы из вашего CRB admin_callbacks.py и адаптированы)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_FILTER_BY_TYPE))
    def handle_admin_report_filter_type_select(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if admin_id not in admin_step_cache or admin_step_cache[admin_id].get('state') != 'admin_report_filter_type':
            bot.answer_callback_query(call.id, "Сессия выбора фильтра истекла. Начните заново.", show_alert=True)
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        filter_type_selected = call.data[len(const.CB_FILTER_BY_TYPE):]  # "user", "equipment", "date"
        bot.answer_callback_query(call.id)

        options: List[Tuple[Any, Any]] = []
        prompt_text = ""

        if filter_type_selected == "user":
            all_users = user_service.get_all_users_info(db_connection)
            options = [(f"{u.get('fi', 'N/A')} (ID: {u.get('users_id')})", u.get('users_id')) for u in all_users if
                       u.get('users_id')]
            options.sort(key=lambda x: x[0])  # Сортировка по имени
            prompt_text = "Выберите пользователя для отчета:"
        elif filter_type_selected == "equipment":
            all_equipment = equipment_service.get_all_equipment_with_category_info(db_connection)  # Нужна такая функция
            options = [
                (f"{eq.get('name_equip', 'N/A')} (Кат: {eq.get('name_cat', 'N/A')}, ID: {eq.get('id')})", eq.get('id'))
                for eq in all_equipment if eq.get('id')]
            options.sort(key=lambda x: x[0])
            prompt_text = "Выберите оборудование для отчета:"
        elif filter_type_selected == "date":
            # Получаем список месяцев, за которые есть бронирования
            query_months = "SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month_year FROM bookings WHERE date IS NOT NULL ORDER BY month_year DESC;"
            months_result = db_connection.execute_query(query_months, fetch_results=True)
            if months_result:
                options = [(m.get('month_year'), m.get('month_year')) for m in months_result if m.get('month_year')]
            prompt_text = "Выберите месяц (ГГГГ-ММ) для отчета:"
        else:
            logger.warning(f"Неизвестный тип фильтра '{filter_type_selected}' от админа {admin_id}")
            _edit_or_send_message(chat_id, message_id, "Неизвестный тип фильтра.", reply_markup=None)
            return

        if not options:
            _edit_or_send_message(chat_id, message_id, f"Нет данных для фильтрации по типу '{filter_type_selected}'.",
                                  reply_markup=None)
            # Можно вернуть на шаг выбора типа фильтра или очистить состояние
            # admin_step_cache[admin_id]['state'] = 'admin_report_filter_type' # Вернуть
            # markup = keyboards.generate_admin_report_filter_type_keyboard()
            # _edit_or_send_message(chat_id, message_id, "Нет данных. Выберите другой тип фильтра:", reply_markup=markup)
            return

        admin_step_cache[admin_id]['state'] = f'admin_report_filter_value_{filter_type_selected}'
        markup = keyboards.generate_admin_report_filter_value_selection_keyboard(options, filter_type_selected,
                                                                                 back_context="report_filter_type")
        _edit_or_send_message(chat_id, message_id, prompt_text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_FILTER_SELECT_USER) or \
                                                  call.data.startswith(const.CB_FILTER_SELECT_EQUIPMENT) or \
                                                  call.data.startswith(const.CB_FILTER_SELECT_DATE))
    def handle_admin_report_filter_value_select(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        filter_type = ""
        filter_value_str = ""
        filter_value_for_service: Any = None
        filter_details_for_report = ""

        if call.data.startswith(const.CB_FILTER_SELECT_USER):
            filter_type = "user"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_USER):]
            filter_value_for_service = int(filter_value_str)
            user_info = user_service.get_user_info(db_connection, filter_value_for_service)
            filter_details_for_report = f"Пользователь: {user_info.get('fi', 'N/A') if user_info else filter_value_str}"
        elif call.data.startswith(const.CB_FILTER_SELECT_EQUIPMENT):
            filter_type = "equipment"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_EQUIPMENT):]
            filter_value_for_service = int(filter_value_str)
            equip_info = equipment_service.get_equipment_details_by_id(db_connection, filter_value_for_service)
            filter_details_for_report = f"Оборудование: {equip_info.get('name_equip', 'N/A') if equip_info else filter_value_str}"
        elif call.data.startswith(const.CB_FILTER_SELECT_DATE):
            filter_type = "date"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_DATE):]
            filter_value_for_service = filter_value_str  # 'YYYY-MM'
            filter_details_for_report = f"Месяц: {filter_value_str}"
        else:
            bot.answer_callback_query(call.id, "Неизвестный фильтр.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "Формирую отчет...")
        _edit_or_send_message(chat_id, message_id, f"⏳ Формируется отчет... ({filter_details_for_report})",
                              reply_markup=None)

        bookings_data = admin_service.get_filtered_bookings(db_connection, filter_type, filter_value_for_service)
        if not bookings_data:
            _edit_or_send_message(chat_id, message_id,
                                  f"По фильтру '{filter_details_for_report}' бронирований не найдено.",
                                  reply_markup=None)
            clear_admin_step_cache(admin_id)
            return

        report_file_path = admin_service.create_bookings_report_file(bookings_data, filter_details_for_report)
        if report_file_path:
            try:
                with open(report_file_path, 'rb') as f:
                    bot.send_document(chat_id, f, caption=f"Отчет: {filter_details_for_report}")
                # Удаляем "пожалуйста подождите" сообщение
                bot.delete_message(chat_id, message_id)
            except Exception as e_send_doc:
                logger.error(f"Ошибка отправки файла отчета {report_file_path}: {e_send_doc}")
                _edit_or_send_message(chat_id, message_id, "Ошибка при отправке файла отчета.", reply_markup=None)
            finally:
                if os.path.exists(report_file_path): os.remove(report_file_path)
        else:
            _edit_or_send_message(chat_id, message_id, "Не удалось создать файл отчета.", reply_markup=None)

        clear_admin_step_cache(admin_id)

    # === Обработчики для управления пользователями ===
    # (В основном, логика из CRB admin_callbacks.py, адаптирована под новые константы)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_MANAGE_USER_SELECT))
    def handle_admin_manage_user_select_action(call: CallbackQuery):  # Переименовано для ясности
        # ... (Логика из handle_manage_user_select вашего CRB файла, адаптированная под WSB)
        # Показывает кнопки Block/Unblock, Make Admin/Remove Admin для выбранного пользователя
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Очистка состояния предыдущего шага, если мы перешли с выбора пользователя
        if admin_id in admin_step_cache and admin_step_cache[admin_id].get('state') == 'admin_manage_user_select':
            admin_step_cache[admin_id]['state'] = 'admin_manage_user_actions'  # Новое состояние
        elif admin_id not in admin_step_cache:  # Если пришли сюда напрямую без состояния
            admin_step_cache[admin_id] = {'state': 'admin_manage_user_actions', 'data': {}, 'chat_id': chat_id,
                                          'message_to_edit_id': message_id}
        else:  # Если состояние другое, возможно, ошибка или другой процесс
            pass  # Можно просто продолжить или обработать как ошибку

        try:
            target_user_id = int(call.data[len(const.CB_MANAGE_USER_SELECT):])
        except ValueError:
            logger.error(f"Ошибка парсинга user_id из CB_MANAGE_USER_SELECT: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        admin_step_cache[admin_id]['data']['target_user_id'] = target_user_id

        user_info = user_service.get_user_info(db_connection,
                                               target_user_id)  # Нужна функция, возвращающая is_blocked и is_admin
        if not user_info:
            _edit_or_send_message(chat_id, message_id, "Пользователь не найден.", reply_markup=None)
            return

        is_blocked = user_info.get('is_blocked', False)
        is_admin = user_info.get('is_admin', False)
        user_fi = user_info.get('fi', f"ID {target_user_id}")

        text = (f"Управление пользователем: *{user_fi}*\n"
                f"ID: `{target_user_id}`\n"
                f"Статус: {'🔴 Заблокирован' if is_blocked else '🟢 Активен'}\n"
                f"Права: {'👑 Администратор' if is_admin else '👤 Пользователь'}\n\n"
                "Выберите действие:")
        markup = keyboards.generate_admin_user_actions_keyboard(target_user_id, is_blocked, is_admin)
        _edit_or_send_message(chat_id, message_id, text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_MANAGE_USER_ACTION_BLOCK) or \
                                                  call.data.startswith(const.CB_MANAGE_USER_ACTION_UNBLOCK) or \
                                                  call.data.startswith(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN) or \
                                                  call.data.startswith(const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN))
    def handle_admin_manage_user_perform_action(call: CallbackQuery):  # Переименовано
        # ... (Логика из handle_manage_user_action вашего CRB файла, адаптированная под WSB)
        # Выполняет выбранное действие (блок/разблок, админ/не админ)
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        # Проверка состояния не так критична, если вся информация в callback_data

        action_type = ""
        target_user_id = 0

        try:
            if call.data.startswith(const.CB_MANAGE_USER_ACTION_BLOCK):
                action_type = "block"
                target_user_id = int(call.data[len(const.CB_MANAGE_USER_ACTION_BLOCK):])
            elif call.data.startswith(const.CB_MANAGE_USER_ACTION_UNBLOCK):
                action_type = "unblock"
                target_user_id = int(call.data[len(const.CB_MANAGE_USER_ACTION_UNBLOCK):])
            elif call.data.startswith(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN):
                action_type = "make_admin"
                target_user_id = int(call.data[len(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN):])
            elif call.data.startswith(const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN):
                action_type = "remove_admin"
                target_user_id = int(call.data[len(const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN):])
            else:
                raise ValueError("Unknown action prefix")
        except ValueError:
            logger.error(f"Ошибка парсинга user_id/action из callback: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка данных действия.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "Выполняю действие...")

        success = False
        result_message = const.MSG_ERROR_GENERAL

        if action_type == "block":
            success = user_service.update_user_block_status(db_connection, target_user_id, block=True)
            result_message = const.MSG_USER_BLOCKED if success else "Не удалось заблокировать пользователя."
        elif action_type == "unblock":
            success = user_service.update_user_block_status(db_connection, target_user_id, block=False)
            result_message = const.MSG_USER_UNBLOCKED if success else "Не удалось разблокировать пользователя."
        elif action_type == "make_admin":
            success = user_service.update_user_admin_status(db_connection, target_user_id, is_admin=True)
            result_message = const.MSG_USER_MADE_ADMIN if success else "Не удалось назначить администратором."
        elif action_type == "remove_admin":
            success = user_service.update_user_admin_status(db_connection, target_user_id, is_admin=False)
            result_message = const.MSG_USER_REMOVED_ADMIN if success else "Не удалось отозвать права администратора."

        # Обновляем информацию и клавиатуру
        user_info_after = user_service.get_user_info(db_connection, target_user_id)
        if not user_info_after:
            _edit_or_send_message(chat_id, message_id, "Ошибка: пользователь не найден после действия.",
                                  reply_markup=None)
            return

        is_blocked_after = user_info_after.get('is_blocked', False)
        is_admin_after = user_info_after.get('is_admin', False)
        user_fi_after = user_info_after.get('fi', f"ID {target_user_id}")

        text_after = (f"Управление пользователем: *{user_fi_after}*\n"
                      f"ID: `{target_user_id}`\n"
                      f"Статус: {'🔴 Заблокирован' if is_blocked_after else '🟢 Активен'}\n"
                      f"Права: {'👑 Администратор' if is_admin_after else '👤 Пользователь'}\n\n"
                      f"{'✅ ' if success else '❌ '}{result_message}\n\n"
                      "Выберите следующее действие:")
        markup_after = keyboards.generate_admin_user_actions_keyboard(target_user_id, is_blocked_after, is_admin_after)
        _edit_or_send_message(chat_id, message_id, text_after, reply_markup=markup_after, parse_mode='Markdown')

    # === Обработчики регистрации (копипаст из вашего CRB admin_callbacks.py, без изменений в логике, только ссылки на константы) ===
    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_REG_CONFIRM_USER))
    def handle_registration_confirm_callback(
            call: CallbackQuery):  # Переименовал, чтобы не конфликтовать с функцией из CRB, если она импортируется
        # ... (логика из handle_registration_confirm вашего CRB файла)
        # Использует registration_notification_service, userService
        # Адаптировать тексты сообщений на константы WSB
        # Пример: bot.send_message(temp_user_id, const.MSG_REGISTRATION_APPROVED)
        admin_user_id: int = call.from_user.id
        cb_data: str = call.data
        temp_user_id_str: str = cb_data[len(const.CB_REG_CONFIRM_USER):]
        try:
            temp_user_id = int(temp_user_id_str)
        except ValueError:
            return logger.error(f"Invalid user_id in CB_REG_CONFIRM_USER: {temp_user_id_str}")

        logger.info(f"Admin {admin_user_id} confirms registration for temp_user_id {temp_user_id}")
        bot.answer_callback_query(call.id, "Обработка...")

        success, user_info = user_service.confirm_registration(db_connection, temp_user_id)

        admin_display_name = user_service.get_user_display_name(db_connection, admin_user_id)

        if success and user_info:
            user_display_name = user_info.get('fi', f"ID {temp_user_id}")
            try:
                bot.send_message(temp_user_id, const.MSG_REGISTRATION_APPROVED)
            except Exception as e_notify:
                logger.error(f"Failed to notify user {temp_user_id} about registration approval: {e_notify}")

            final_text = f"✅ Заявка пользователя {user_display_name} (ID: `{temp_user_id}`) была **подтверждена** администратором {admin_display_name}."
            registration_notification_service.update_admin_notifications_after_processing(db_connection, bot,
                                                                                          temp_user_id, final_text)
        elif success and not user_info:  # Случай, когда confirm_registration вернул True, но без user_info (маловероятно)
            logger.warning(f"Registration for {temp_user_id} confirmed but no user_info returned.")
            final_text = f"✅ Заявка пользователя ID `{temp_user_id}` была **подтверждена** администратором {admin_display_name} (детали пользователя не получены)."
            registration_notification_service.update_admin_notifications_after_processing(db_connection, bot,
                                                                                          temp_user_id, final_text)
        else:  # Заявка уже обработана или ошибка
            error_text = f"ℹ️ Заявка пользователя ID `{temp_user_id}` уже была обработана ранее или произошла ошибка при подтверждении."
            _edit_or_send_message(call.message.chat.id, call.message.message_id, error_text, reply_markup=None,
                                  parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_REG_DECLINE_USER))
    def handle_registration_decline_callback(call: CallbackQuery):  # Переименовал
        # ... (логика из handle_registration_decline вашего CRB файла)
        admin_user_id: int = call.from_user.id
        cb_data: str = call.data
        temp_user_id_str: str = cb_data[len(const.CB_REG_DECLINE_USER):]
        try:
            temp_user_id = int(temp_user_id_str)
        except ValueError:
            return logger.error(f"Invalid user_id in CB_REG_DECLINE_USER: {temp_user_id_str}")

        logger.info(f"Admin {admin_user_id} declines registration for temp_user_id {temp_user_id}")
        bot.answer_callback_query(call.id, "Обработка...")

        temp_user_details = user_service.find_temp_user(db_connection, temp_user_id)  # Получаем детали до удаления
        success = user_service.decline_registration(db_connection, temp_user_id)

        admin_display_name = user_service.get_user_display_name(db_connection, admin_user_id)
        user_display_name_temp = temp_user_details.get('fi',
                                                       f"ID {temp_user_id}") if temp_user_details else f"ID {temp_user_id}"

        if success:
            try:
                bot.send_message(temp_user_id, const.MSG_REGISTRATION_DECLINED)
            except Exception as e_notify:
                logger.warning(f"Failed to notify user {temp_user_id} about registration decline: {e_notify}")

            final_text = f"🚫 Заявка пользователя {user_display_name_temp} (ID: `{temp_user_id}`) была **отклонена** администратором {admin_display_name}."
            registration_notification_service.update_admin_notifications_after_processing(db_connection, bot,
                                                                                          temp_user_id, final_text)
        else:  # Заявка уже обработана или ошибка
            error_text = f"ℹ️ Заявка пользователя ID `{temp_user_id}` уже была обработана ранее или произошла ошибка при отклонении."
            _edit_or_send_message(call.message.chat.id, call.message.message_id, error_text, reply_markup=None,
                                  parse_mode="Markdown")

    # === Обработчик подтверждения/отмены рассылки ===
    @bot.callback_query_handler(func=lambda
            call: call.data == const.CB_ADMIN_BROADCAST_CONFIRM_SEND or call.data == const.CB_ADMIN_BROADCAST_CANCEL_SEND)
    def handle_admin_broadcast_confirmation(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id  # ID сообщения с кнопками Да/Нет

        if admin_id not in admin_step_cache or \
                'broadcast_message' not in admin_step_cache[admin_id].get('data', {}):
            bot.answer_callback_query(call.id, "Сессия рассылки истекла. Начните заново.", show_alert=True)
            _edit_or_send_message(chat_id, message_id, "Ошибка: не найдено сообщение для рассылки. Начните заново.",
                                  reply_markup=None)
            clear_admin_step_cache(admin_id)
            return

        if call.data == const.CB_ADMIN_BROADCAST_CONFIRM_SEND:
            bot.answer_callback_query(call.id, "Начинаю рассылку...")
            broadcast_text = admin_step_cache[admin_id]['data']['broadcast_message']
            # Удаляем сообщение с кнопками подтверждения
            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass

            # Запускаем саму рассылку (она может быть долгой, поэтому результат отправляется отдельно)
            # Эта функция сама отправит админу отчет о результатах
            admin_service.broadcast_message_to_users(db_connection, bot, broadcast_text,
                                                     admin_id)  # Передаем admin_id для отчета

        elif call.data == const.CB_ADMIN_BROADCAST_CANCEL_SEND:
            bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
            _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_BROADCAST_CANCELLED_TEXT, reply_markup=None)

        clear_admin_step_cache(admin_id)  # Очищаем состояние в любом случае

    # === Обработчики для админской отмены бронирований ===
    # (Адаптировано из вашего CRB admin_callbacks.py)
    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_ADMIN_CANCEL_SELECT_BOOKING))
    def handle_admin_cancel_select_booking_callback(call: CallbackQuery):
        # ... (Логика из handle_admin_cancel_select вашего CRB файла)
        # Показывает подтверждение отмены для выбранной брони
        # Использует booking_service.find_booking_by_id
        # keyboards.generate_admin_booking_cancel_confirmation_keyboard
        # Тексты сообщений адаптированы под WSB
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        try:
            booking_id = int(call.data[len(const.CB_ADMIN_CANCEL_SELECT_BOOKING):])
        except ValueError:
            return logger.error(f"Invalid booking_id in CB_ADMIN_CANCEL_SELECT_BOOKING: {call.data}")

        logger.info(f"Admin {admin_id} selected booking {booking_id} for admin cancellation.")
        bot.answer_callback_query(call.id)

        booking_info = booking_service.find_booking_by_id(db_connection,
                                                          booking_id)  # Используем find_booking_by_id WSB
        if not booking_info:
            _edit_or_send_message(chat_id, message_id, "Бронь не найдена.", reply_markup=None)
            return

        status = booking_info.get('status')
        if status == 'cancelled':
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ALREADY_CANCELLED_INFO, reply_markup=None)
            return
        if status == 'finished':
            _edit_or_send_message(chat_id, message_id, const.MSG_BOOKING_ALREADY_FINISHED_INFO, reply_markup=None)
            return

        # Формируем информацию о брони для подтверждения
        equip_name = booking_info.get('name_equip', 'N/A')
        cat_name = booking_info.get('name_cat', 'N/A')
        user_fi = booking_info.get('user_fi', 'N/A')
        b_date = booking_service._format_date(booking_info.get('date'))
        b_time = booking_info.get('time_interval', 'N/A')

        confirm_text = (
            f"❓ Отменить бронирование ID `{booking_id}`?\n\n"
            f"👤 Пользователь: {user_fi}\n"
            f"💻 Оборудование: {equip_name} (Кат: {cat_name})\n"
            f"🗓️ Дата: {b_date}, Время: {b_time}\n\n"
            "Пользователь будет уведомлен."
        )
        markup = keyboards.generate_admin_booking_cancel_confirmation_keyboard(booking_id)
        _edit_or_send_message(chat_id, message_id, confirm_text, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_ADMIN_CANCEL_CONFIRM_BOOKING))
    def handle_admin_cancel_confirm_booking_callback(call: CallbackQuery):
        # ... (Логика из handle_admin_cancel_confirm вашего CRB файла)
        # Выполняет отмену, обновляет задачи, уведомляет пользователя
        # Использует booking_service.cancel_booking, notification_service.cleanup_completed_jobs
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        try:
            booking_id = int(call.data[len(const.CB_ADMIN_CANCEL_CONFIRM_BOOKING):])
        except ValueError:
            return logger.error(f"Invalid booking_id in CB_ADMIN_CANCEL_CONFIRM_BOOKING: {call.data}")

        logger.info(f"Admin {admin_id} confirmed admin cancellation for booking {booking_id}.")
        bot.answer_callback_query(call.id, "Отменяю бронь...")

        booking_info_before = booking_service.find_booking_by_id(db_connection, booking_id)  # Для уведомления

        success, msg, owner_user_id = booking_service.cancel_booking(db_connection, booking_id, user_id=admin_id,
                                                                     is_admin_cancel=True)

        _edit_or_send_message(chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown")

        if success:
            try:
                notification_service.cleanup_booking_notifications(scheduler, scheduled_jobs_registry, booking_id)
            except Exception as e_clean:
                logger.error(f"Error cleaning up notifications for admin-cancelled booking {booking_id}: {e_clean}")

            if owner_user_id and booking_info_before:
                equip_name = booking_info_before.get('name_equip', 'Ваше')
                cat_name = booking_info_before.get('name_cat', '')
                b_date = booking_service._format_date(booking_info_before.get('date'))
                b_time_interval = booking_info_before.get('time_interval', 'N/A')

                user_notify_text = (
                    f"❗️ Ваше бронирование оборудования '{equip_name}' "
                    f"{'(категория: ' + cat_name + ')' if cat_name else ''} "
                    f"на {b_date} ({b_time_interval}) было отменено администратором."
                )
                try:
                    bot.send_message(owner_user_id, user_notify_text)
                except Exception as e_notify:
                    logger.error(
                        f"Failed to notify user {owner_user_id} about admin cancellation of booking {booking_id}: {e_notify}")

    # === Общий обработчик для кнопок "Отмена действия" и "Назад" ===
    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_ACTION_CANCEL_PREFIX))
    def handle_general_cancel_action(call: CallbackQuery):
        admin_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        context_and_data = call.data[len(const.CB_ACTION_CANCEL_PREFIX):]
        parts = context_and_data.split('_')
        context = parts[0]
        context_data = parts[1:] if len(parts) > 1 else []  # Данные после контекста

        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
        logger.info(f"Admin {admin_id} отменил действие в контексте: {context} с данными {context_data}")

        # Логика возврата на предыдущий шаг или отмены процесса
        # Для /add_equipment и /manage_equipment
        if context == "add" and context_data and context_data[0] == "equip":  # Отмена всего процесса /add_equipment
            _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_ADD_EQUIP_PROCESS_CANCELLED_TEXT,
                                  reply_markup=None)
            clear_admin_step_cache(admin_id)
            return
        if context == "manage" and context_data and context_data[
            0] == "equip":  # Отмена всего процесса /manage_equipment
            _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_MANAGE_EQUIP_PROCESS_CANCELLED_TEXT,
                                  reply_markup=None)
            clear_admin_step_cache(admin_id)
            return

        # Возврат к выбору категории при добавлении оборудования (если был шаг ввода имени новой категории или оборудования)
        if context == "add_equip_select_cat" or \
                (admin_id in admin_step_cache and admin_step_cache[admin_id].get('state') in [
                    const.ADMIN_STATE_ADD_EQUIP_NEW_CATEGORY_NAME,
                    const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NAME,
                    const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NOTE
                ]):
            admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_ADD_EQUIP_CHOOSE_CATEGORY
            admin_step_cache[admin_id]['data'] = {}  # Сбрасываем накопленные данные
            categories = equipment_service.get_all_categories(db_connection)
            markup = keyboards.generate_admin_select_category_for_add_equip_keyboard(categories)
            _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_ADD_EQUIP_CHOOSE_CAT_TEXT, reply_markup=markup,
                                  parse_mode='Markdown')
            return

        # Возврат к выбору категории при управлении оборудованием
        if context == "manage_equip_select_cat" or \
                (admin_id in admin_step_cache and admin_step_cache[admin_id].get('state') in [
                    const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_EQUIPMENT
                    # const.ADMIN_STATE_MANAGE_EQUIP_CONFIRM_DELETE - здесь обычно "Нет" возвращает на шаг выше
                ]):
            admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_CATEGORY
            admin_step_cache[admin_id]['data'] = {}
            categories = equipment_service.get_all_categories(db_connection)
            if not categories:  # Дополнительная проверка
                _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_MANAGE_EQUIP_NO_CATEGORIES_TEXT,
                                      reply_markup=None)
                clear_admin_step_cache(admin_id)
                return
            markup = keyboards.generate_admin_select_category_for_manage_equip_keyboard(categories)
            _edit_or_send_message(chat_id, message_id, const.MSG_ADMIN_MANAGE_EQUIP_CHOOSE_CAT_TEXT,
                                  reply_markup=markup, parse_mode='Markdown')
            return

        # Возврат к выбору оборудования при удалении (после кнопки "Нет" на подтверждении)
        if context == "manage_equip_confirm_del" and admin_id in admin_step_cache and \
                'category_id' in admin_step_cache[admin_id]['data'] and 'category_name' in admin_step_cache[admin_id][
            'data']:
            cat_id_cached = admin_step_cache[admin_id]['data']['category_id']
            cat_name_cached = admin_step_cache[admin_id]['data']['category_name']
            admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_EQUIPMENT
            # 'equip_id_to_delete' и 'equip_name_to_delete' остаются в data, это не страшно или можно очистить

            equipments_in_cat = equipment_service.get_equipment_by_category(db_connection, cat_id_cached)
            markup = keyboards.generate_admin_select_equipment_to_delete_keyboard(equipments_in_cat, cat_id_cached)
            _edit_or_send_message(chat_id, message_id,
                                  const.MSG_ADMIN_MANAGE_EQUIP_CHOOSE_EQUIP_TEXT.format(category_name=cat_name_cached),
                                  reply_markup=markup, parse_mode='Markdown')
            return

        # Для отчета /all - возврат к выбору типа фильтра
        if context == "report_filter_type" or context == "report_filter_value":
            if admin_id in admin_step_cache: admin_step_cache[admin_id]['state'] = 'admin_report_filter_type'
            markup = keyboards.generate_admin_report_filter_type_keyboard()
            _edit_or_send_message(chat_id, message_id, "Выберите тип фильтра для отчета:", reply_markup=markup)
            return

        # Для управления пользователями - возврат к списку пользователей
        if context == "manage_user_select" or context == "manage_user_list":  # manage_user_list - для кнопки Назад из user_status_keyboard
            if admin_id in admin_step_cache: admin_step_cache[admin_id]['state'] = 'admin_manage_user_select'
            users = user_service.get_all_users_info(db_connection)
            markup = keyboards.generate_admin_manage_user_select_keyboard(users)
            _edit_or_send_message(chat_id, message_id, "Выберите пользователя для управления:", reply_markup=markup)
            return

        # Для админской отмены брони - возврат к списку броней
        if context == "admin_cancel_booking_list" or context.startswith("admin_cancel_booking_confirm"):
            active_bookings = booking_service.get_all_active_bookings_for_admin_keyboard(db_connection)
            markup = keyboards.generate_admin_cancel_booking_selection_keyboard(active_bookings)
            _edit_or_send_message(chat_id, message_id, "Отмена действия. Выберите бронь для отмены:",
                                  reply_markup=markup)
            return

        # Если контекст не распознан или не требует специальной обработки
        _edit_or_send_message(chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None)
        if admin_id in admin_step_cache:  # Очищаем состояние, если оно было для этого админа
            clear_admin_step_cache(admin_id)

    logger.info("Обработчики колбэков администратора WSB зарегистрированы.")


# --- Функции, вызываемые через register_next_step_handler ---

def process_add_equip_new_category_name_input(message: Message, admin_id_for_cache: int):
    admin_id = message.from_user.id  # message.from_user.id может отличаться от admin_id_for_cache, если кто-то другой ответил
    chat_id = message.chat.id

    if admin_id != admin_id_for_cache:  # Проверка, что отвечает тот же админ
        logger.warning(f"Попытка ввода имени категории от другого пользователя {admin_id} вместо {admin_id_for_cache}")
        return

    if admin_id not in admin_step_cache or \
            admin_step_cache[admin_id].get('state') != const.ADMIN_STATE_ADD_EQUIP_NEW_CATEGORY_NAME:
        logger.warning(f"Получен ввод имени новой категории от админа {admin_id} вне ожидаемого состояния.")
        # Можно отправить сообщение об ошибке или просто проигнорировать
        return

    message_to_edit_id = admin_step_cache[admin_id].get('message_to_edit_id')
    new_category_name = message.text.strip()

    if not new_category_name:
        _edit_or_send_message(chat_id, message_to_edit_id,
                              const.MSG_ADMIN_PROMPT_NEW_CAT_NAME_TEXT + "\n\n⚠️ Название категории не может быть пустым. Пожалуйста, введите название:",
                              reply_markup=None, parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_new_category_name_input,
                                                  admin_id_for_cache=admin_id)
        return

    success, msg_key, new_category_id = equipment_service.add_category(db_connection, new_category_name)

    if success and new_category_id is not None:
        bot.send_message(chat_id, const.MSG_ADMIN_CAT_ADD_SUCCESS_TEXT.format(name_cat=new_category_name),
                         parse_mode='Markdown')
        admin_step_cache[admin_id]['data']['category_id'] = new_category_id
        admin_step_cache[admin_id]['data']['category_name'] = new_category_name
        admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NAME

        prompt_text = const.MSG_ADMIN_PROMPT_EQUIP_NAME_TEXT.format(name_cat=new_category_name)
        # Отправляем новое сообщение, так как предыдущее было текстовым вводом
        sent_msg = bot.send_message(chat_id, prompt_text, parse_mode='Markdown')
        admin_step_cache[admin_id]['message_to_edit_id'] = sent_msg.message_id  # Обновляем ID для редактирования
        bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_name_input, admin_id_for_cache=admin_id)
    else:
        error_message = ""
        if msg_key == "CATEGORY_ALREADY_EXISTS":
            error_message = const.MSG_ADMIN_CAT_ADD_FAIL_ALREADY_EXISTS_TEXT.format(name_cat=new_category_name)
        else:  # DB_ERROR_ADDING_CATEGORY или INTERNAL_ERROR_ADDING_CATEGORY
            error_message = const.MSG_ADMIN_CAT_ADD_FAIL_GENERAL_ERROR_TEXT.format(name_cat=new_category_name)

        _edit_or_send_message(chat_id, message_to_edit_id,
                              error_message + "\n\n" + const.MSG_ADMIN_PROMPT_NEW_CAT_NAME_TEXT,
                              reply_markup=None, parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_new_category_name_input,
                                                  admin_id_for_cache=admin_id)  # Повторный запрос


def process_add_equip_name_input(message: Message, admin_id_for_cache: int):
    admin_id = message.from_user.id
    chat_id = message.chat.id

    if admin_id != admin_id_for_cache: return
    if admin_id not in admin_step_cache or \
            admin_step_cache[admin_id].get('state') != const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NAME:
        return  # Игнорируем

    message_to_edit_id = admin_step_cache[admin_id].get('message_to_edit_id')
    equip_name = message.text.strip()
    category_name = admin_step_cache[admin_id]['data'].get('category_name', 'выбранной категории')

    if not equip_name:
        _edit_or_send_message(chat_id, message_to_edit_id,
                              const.MSG_ADMIN_PROMPT_EQUIP_NAME_TEXT.format(
                                  name_cat=category_name) + "\n\n⚠️ Название оборудования не может быть пустым. Введите название:",
                              reply_markup=None, parse_mode='Markdown')
        bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_name_input, admin_id_for_cache=admin_id)
        return

    admin_step_cache[admin_id]['data']['equip_name'] = equip_name
    admin_step_cache[admin_id]['state'] = const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NOTE

    prompt_text = const.MSG_ADMIN_PROMPT_EQUIP_NOTE_TEXT.format(name_equip=equip_name)
    # Если предыдущее сообщение было запросом имени, редактируем его
    if message_to_edit_id:
        _edit_or_send_message(chat_id, message_to_edit_id, prompt_text, reply_markup=None, parse_mode='Markdown')
    else:  # Если это было новое сообщение после создания категории, message_to_edit_id уже обновлен
        sent_msg = bot.send_message(chat_id, prompt_text, parse_mode='Markdown')
        admin_step_cache[admin_id]['message_to_edit_id'] = sent_msg.message_id

    bot.register_next_step_handler_by_chat_id(chat_id, process_add_equip_note_input, admin_id_for_cache=admin_id)


def process_add_equip_note_input(message: Message, admin_id_for_cache: int):
    admin_id = message.from_user.id
    chat_id = message.chat.id

    if admin_id != admin_id_for_cache: return
    if admin_id not in admin_step_cache or \
            admin_step_cache[admin_id].get('state') != const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NOTE:
        return

    message_to_edit_id = admin_step_cache[admin_id].get('message_to_edit_id')
    equip_note = None
    if message.text and message.text.strip().lower() not in ['/skip', 'skip', 'пропустить']:
        equip_note = message.text.strip()

    category_id = admin_step_cache[admin_id]['data']['category_id']
    category_name = admin_step_cache[admin_id]['data']['category_name']
    equip_name = admin_step_cache[admin_id]['data']['equip_name']

    success, msg_key, new_equip_id = equipment_service.add_equipment(
        db_connection, category_id, equip_name, equip_note
    )

    final_user_message = ""
    if success:
        final_user_message = const.MSG_ADMIN_EQUIP_ADD_SUCCESS_TEXT.format(name_equip=equip_name,
                                                                           name_cat=category_name)
    else:
        if msg_key == "EQUIPMENT_ALREADY_EXISTS_IN_CATEGORY":
            final_user_message = const.MSG_ADMIN_EQUIP_ADD_FAIL_ALREADY_EXISTS_TEXT.format(name_equip=equip_name,
                                                                                           name_cat=category_name)
        else:  # Другие ошибки
            final_user_message = const.MSG_ADMIN_EQUIP_ADD_FAIL_GENERAL_ERROR_TEXT.format(name_equip=equip_name)

    _edit_or_send_message(chat_id, message_to_edit_id, final_user_message, reply_markup=None, parse_mode='Markdown')
    clear_admin_step_cache(admin_id)