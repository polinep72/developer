# handlers/callbacks/common_callbacks.py
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery, InlineKeyboardButton  # <--- ИСПРАВЛЕНО: Добавлен InlineKeyboardButton
from typing import Dict, Any, Optional, Set, Tuple, List
from datetime import datetime  # <--- ИСПРАВЛЕНО: Добавлен datetime (если нужен для парсинга sub_context_data)
from services import user_service
from database import Database
from logger import logger
import constants as const
from utils import keyboards


# Вспомогательная функция для редактирования/отправки
def _edit_or_send_message(bot_instance: telebot.TeleBot, chat_id: int, message_id: Optional[int], text: str,
                          reply_markup=None, parse_mode=None):
    try:
        if message_id:
            bot_instance.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup,
                                           parse_mode=parse_mode)
        else:
            bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except telebot.apihelper.ApiTelegramException as e:
        if "message to edit not found" in str(e).lower() or \
                "message is not modified" in str(e).lower() or \
                "message can't be edited" in str(e).lower():
            logger.warning(
                f"Сообщение {message_id} не найдено/не изменено/не может быть отредактировано, отправка нового. Ошибка: {e}")
            try:
                bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception as e_send_new:
                logger.error(
                    f"Не удалось отправить новое сообщение после ошибки редактирования (chat_id: {chat_id}): {e_send_new}")
        else:
            logger.error(
                f"Ошибка API при редактировании/отправке сообщения (chat_id: {chat_id}, msg_id: {message_id}): {e}")
    except Exception as e_gen:
        logger.error(
            f"Общая ошибка при редактировании/отправке сообщения (chat_id: {chat_id}, msg_id: {message_id}): {e_gen}",
            exc_info=True)


# Для пользовательского процесса бронирования
from states import user_booking_states, clear_user_state
from services import equipment_service, booking_service

# Для админских процессов (импортируем кэш и функцию очистки, если они используются для определения контекста)
# Специфичные функции полной отмены админских процессов (типа admin_cancel_add_equip) должны быть в admin_callbacks.py
# и вызываться по своим префиксам (CB_ADMIN_..._CANCEL_PROCESS)
from wsb_bot.handlers.admin_commands import admin_step_cache, clear_admin_step_cache


def register_common_callback_handlers(
        bot: telebot.TeleBot,
        db: Database
):
    """Регистрирует обработчики общих колбэков."""

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_ACTION_CANCEL_PREFIX))
    def handle_general_cancel_or_back_action(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        raw_context_data = call.data[len(const.CB_ACTION_CANCEL_PREFIX):]
        context_parts = raw_context_data.split('_')
        main_context = context_parts[0]
        sub_context_data_str = "_".join(context_parts[1:]) if len(context_parts) > 1 else None

        logger.info(
            f"User {user_id} нажал Отмена/Назад. Контекст: '{main_context}', доп. данные: {sub_context_data_str}. Сообщение: {message_id}")
        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)

        # === Логика возврата для пользовательского процесса бронирования ===
        if user_id in user_booking_states:
            current_booking_step = user_booking_states[user_id].get('step')
            message_to_edit_user = user_booking_states[user_id].get('message_id',
                                                                    message_id)  # Используем сохраненный ID

            if main_context == "select_category":
                if current_booking_step == const.STATE_BOOKING_SELECT_EQUIPMENT:
                    user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_CATEGORY
                    user_booking_states[user_id]['data'] = {}
                    categories = equipment_service.get_all_categories(db)
                    markup = keyboards.generate_category_keyboard_for_booking(categories)
                    _edit_or_send_message(bot, chat_id, message_to_edit_user, const.MSG_BOOKING_STEP_1_SELECT_CATEGORY,
                                          reply_markup=markup)
                    return
            elif main_context == "select_equipment":
                if current_booking_step == const.STATE_BOOKING_SELECT_DATE:
                    user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_EQUIPMENT
                    category_id = user_booking_states[user_id]['data'].get('category_id')
                    category_name = user_booking_states[user_id]['data'].get('category_name', 'выбранной категории')
                    user_booking_states[user_id]['data'].pop('selected_date', None)
                    user_booking_states[user_id]['data'].pop('selected_date_str_for_service', None)
                    if category_id:
                        equipments = equipment_service.get_equipment_by_category(db, category_id)
                        markup = keyboards.generate_equipment_keyboard_for_booking(equipments, category_name)
                        prompt_text = const.MSG_BOOKING_STEP_2_SELECT_EQUIPMENT.format(category_name=category_name)
                        _edit_or_send_message(bot, chat_id, message_to_edit_user, prompt_text, reply_markup=markup,
                                              parse_mode='Markdown')
                    else:
                        user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_CATEGORY
                        categories = equipment_service.get_all_categories(db)
                        markup_cat = keyboards.generate_category_keyboard_for_booking(categories)
                        _edit_or_send_message(bot, chat_id, message_to_edit_user,
                                              const.MSG_BOOKING_STEP_1_SELECT_CATEGORY, reply_markup=markup_cat)
                    return
            elif main_context == "select_date":
                if current_booking_step == const.STATE_BOOKING_SELECT_SLOT:
                    user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_DATE
                    user_booking_states[user_id]['data'].pop('selected_slot_index', None)
                    user_booking_states[user_id]['data'].pop('selected_slot_times', None)
                    markup = keyboards.generate_date_keyboard_for_booking()
                    _edit_or_send_message(bot, chat_id, message_to_edit_user, const.MSG_BOOKING_STEP_3_SELECT_DATE,
                                          reply_markup=markup, parse_mode='Markdown')
                    return
            elif main_context == "select_slot":
                if current_booking_step == const.STATE_BOOKING_SELECT_START_TIME:
                    user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_SLOT
                    user_booking_states[user_id]['data'].pop('selected_start_time_str', None)
                    user_booking_states[user_id]['data'].pop('selected_start_time_obj', None)
                    equip_id = user_booking_states[user_id]['data'].get('equip_id')
                    selected_date_obj = user_booking_states[user_id]['data'].get('selected_date')
                    if equip_id and selected_date_obj:
                        available_slots = booking_service.calculate_available_slots(db, equip_id, selected_date_obj)
                        markup = keyboards.generate_available_slots_keyboard_for_booking(available_slots)
                        _edit_or_send_message(bot, chat_id, message_to_edit_user, const.MSG_BOOKING_STEP_4_SELECT_SLOT,
                                              reply_markup=markup, parse_mode='Markdown')
                    else:
                        clear_user_state(user_id)
                        _edit_or_send_message(bot, chat_id, message_to_edit_user, const.MSG_BOOKING_ERROR_INVALID_STATE,
                                              reply_markup=None)
                    return
            elif main_context == "select_start_time":
                if current_booking_step == const.STATE_BOOKING_SELECT_DURATION:
                    user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_START_TIME
                    user_booking_states[user_id]['data'].pop('selected_duration_str_for_service', None)
                    selected_slot_idx = user_booking_states[user_id]['data'].get('selected_slot_index')
                    selected_slot_times = user_booking_states[user_id]['data'].get('selected_slot_times')
                    selected_date_obj = user_booking_states[user_id]['data'].get('selected_date')
                    if isinstance(selected_slot_idx, int) and selected_slot_times and selected_date_obj:
                        available_start_times = booking_service.get_start_times_in_slot(selected_slot_times,
                                                                                        selected_date_obj)
                        markup = keyboards.generate_start_time_keyboard_for_booking(selected_slot_idx,
                                                                                    available_start_times)
                        prompt_text = const.MSG_BOOKING_STEP_5_SELECT_START_TIME.format(
                            start_slot=booking_service._format_time(selected_slot_times[0]),
                            end_slot=booking_service._format_time(selected_slot_times[1])
                        )
                        _edit_or_send_message(bot, chat_id, message_to_edit_user, prompt_text, reply_markup=markup,
                                              parse_mode='Markdown')
                    else:
                        clear_user_state(user_id)
                        _edit_or_send_message(bot, chat_id, message_to_edit_user, const.MSG_BOOKING_ERROR_INVALID_STATE,
                                              reply_markup=None)
                    return

        # === Логика отмены/возврата для админских процессов ===
        if user_id in admin_step_cache:
            current_admin_state_info = admin_step_cache.get(user_id)
            current_admin_state = current_admin_state_info.get('state') if current_admin_state_info else None
            admin_message_id_to_edit = current_admin_state_info.get('message_to_edit_id', message_id)

            # Назад к выбору категории при добавлении оборудования
            if main_context == "add_equip" and sub_context_data_str == "select_cat":
                if current_admin_state in [const.ADMIN_STATE_ADD_EQUIP_NEW_CATEGORY_NAME,
                                           const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NAME,
                                           const.ADMIN_STATE_ADD_EQUIP_EQUIPMENT_NOTE]:
                    admin_step_cache[user_id]['state'] = const.ADMIN_STATE_ADD_EQUIP_CHOOSE_CATEGORY
                    admin_step_cache[user_id]['data'] = {}
                    categories = equipment_service.get_all_categories(db)
                    markup = keyboards.generate_admin_select_category_for_add_equip_keyboard(categories)
                    _edit_or_send_message(bot, chat_id, admin_message_id_to_edit,
                                          const.MSG_ADMIN_ADD_EQUIP_CHOOSE_CAT_TEXT, reply_markup=markup,
                                          parse_mode='Markdown')
                    return

            # Назад к выбору категории при управлении оборудованием
            if main_context == "manage_equip" and sub_context_data_str and sub_context_data_str.startswith(
                    "select_cat"):
                # sub_context_data_str может быть "select_cat" или "select_cat_CATEGORYID"
                if current_admin_state == const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_EQUIPMENT:
                    admin_step_cache[user_id]['state'] = const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_CATEGORY
                    admin_step_cache[user_id]['data'] = {}
                    categories = equipment_service.get_all_categories(db)
                    markup = keyboards.generate_admin_select_category_for_manage_equip_keyboard(categories)
                    _edit_or_send_message(bot, chat_id, admin_message_id_to_edit,
                                          const.MSG_ADMIN_MANAGE_EQUIP_CHOOSE_CAT_TEXT, reply_markup=markup,
                                          parse_mode='Markdown')
                    return

            # Назад к выбору оборудования при отмене подтверждения удаления
            if main_context == "manage_equip" and sub_context_data_str and sub_context_data_str.startswith(
                    "confirm_del"):
                # sub_context_data_str будет 'confirm_del_EQUIPID'
                if current_admin_state is not None and 'category_id' in admin_step_cache[user_id][
                    'data']:  # Проверяем, что мы были на шаге подтверждения
                    cat_id_cached = admin_step_cache[user_id]['data']['category_id']
                    cat_name_cached = admin_step_cache[user_id]['data'].get('category_name', 'выбранной категории')
                    admin_step_cache[user_id]['state'] = const.ADMIN_STATE_MANAGE_EQUIP_CHOOSE_EQUIPMENT
                    # Данные о equip_id_to_delete и equip_name_to_delete остаются, это не страшно

                    equipments_in_cat = equipment_service.get_equipment_by_category(db, cat_id_cached)
                    markup = keyboards.generate_admin_select_equipment_to_delete_keyboard(equipments_in_cat,
                                                                                          cat_id_cached)
                    _edit_or_send_message(bot, chat_id, admin_message_id_to_edit,
                                          const.MSG_ADMIN_MANAGE_EQUIP_CHOOSE_EQUIP_TEXT.format(
                                              category_name=cat_name_cached),
                                          reply_markup=markup, parse_mode='Markdown')
                    return

            # Для отчета /all - возврат к выбору типа фильтра
            if main_context == "report_filter_type" or main_context == "report_filter_value":
                if user_id in admin_step_cache: admin_step_cache[user_id]['state'] = 'admin_report_filter_type'
                markup = keyboards.generate_admin_report_filter_type_keyboard()
                _edit_or_send_message(bot, chat_id, admin_message_id_to_edit or message_id,
                                      "Отмена. Выберите тип фильтра для отчета:", reply_markup=markup)
                return

            # Для управления пользователями - возврат к списку пользователей
            if main_context == "manage_user_select" or main_context == "manage_user_list":
                if user_id in admin_step_cache: admin_step_cache[user_id]['state'] = 'admin_manage_user_select'
                all_users = user_service.get_all_users_info(db)
                markup = keyboards.generate_admin_manage_user_select_keyboard(all_users)
                _edit_or_send_message(bot, chat_id, admin_message_id_to_edit or message_id,
                                      "Отмена. Выберите пользователя для управления:", reply_markup=markup)
                return

            # Для админской отмены брони - возврат к списку броней
            if main_context == "admin_cancel_booking_list" or (
                    main_context == "admin_cancel_booking" and sub_context_data_str and sub_context_data_str.startswith(
                    "confirm")):
                active_bookings = booking_service.get_all_active_bookings_for_admin_keyboard(db)
                markup = keyboards.generate_admin_cancel_booking_selection_keyboard(active_bookings)
                _edit_or_send_message(bot, chat_id, admin_message_id_to_edit or message_id,
                                      "Отмена действия. Выберите бронь для принудительной отмены:", reply_markup=markup)
                return

        # Отмена просмотра броней по рабочим местам
        if main_context == "view_workspace":  # Отмена всего процесса /workspacebookings
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None)
            return
        if main_context == "view_category" and sub_context_data_str:  # Назад к списку категорий при просмотре оборудования
            # sub_context_data_str здесь может быть category_id, но он не используется для генерации списка всех категорий
            categories = equipment_service.get_all_categories(db)
            markup = keyboards.generate_category_keyboard_for_viewing(categories)
            _edit_or_send_message(bot, chat_id, message_id,
                                  "Выберите категорию для просмотра бронирований оборудования:", reply_markup=markup)
            return
        if main_context == "view_equipment" and sub_context_data_str:  # Назад к списку оборудования в категории
            try:
                category_id_for_back = int(sub_context_data_str)
                category_info = equipment_service.get_category_by_id(db, category_id_for_back)
                category_name_for_back = category_info.get('name_cat',
                                                           'выбранной категории') if category_info else 'выбранной категории'
                equipments = equipment_service.get_equipment_by_category(db, category_id_for_back)
                markup = keyboards.generate_equipment_keyboard_for_viewing(equipments, category_id_for_back)
                _edit_or_send_message(bot, chat_id, message_id, f"Оборудование в категории '{category_name_for_back}':",
                                      reply_markup=markup)
            except ValueError:
                logger.error(
                    f"Некорректный category_id в sub_context_data_str для view_equipment: {sub_context_data_str}")
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)
            return

        # Отмена просмотра броней по дате
        if main_context == "view_date_list":  # Назад к выбору даты из отчета по дате
            markup = keyboards.generate_date_keyboard_for_viewing()
            _edit_or_send_message(bot, chat_id, message_id,
                                  "Выберите дату для просмотра всех бронирований рабочих мест:", reply_markup=markup)
            return
        if main_context == "view_date":  # Отмена всего процесса /datebookings
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None)
            return

        # Общая отмена, если ни один из контекстов не подошел
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None)
        if user_id in user_booking_states: clear_user_state(user_id)
        if user_id in admin_step_cache: clear_admin_step_cache(user_id)

    @bot.callback_query_handler(func=lambda call: call.data == const.CB_IGNORE)
    def handle_ignore_callback(call: CallbackQuery):
        user_id = call.from_user.id
        logger.debug(f"User {user_id} нажал кнопку 'Игнорировать'. Callback: {call.data}")
        try:
            bot.answer_callback_query(call.id)
        except Exception as e_ans_ignore:
            logger.warning(f"Не удалось ответить на callback CB_IGNORE: {e_ans_ignore}")

    logger.info("Обработчики общих колбэков WSB зарегистрированы.")