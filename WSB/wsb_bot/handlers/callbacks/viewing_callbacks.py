# handlers/callbacks/viewing_callbacks.py (WSB - переработанный в стиле CRB)
"""
Обработчики callback-запросов, связанных с просмотром информации о бронированиях в WSB.
"""
import telebot  # Только для аннотации типов, если где-то нужно
from telebot.types import CallbackQuery
from telebot import apihelper
from typing import Dict, Any, Optional  # Убрал неиспользуемые
from datetime import datetime, date  # date нужен для strptime
import html  # Для экранирования

# --- Импортируем глобальные объекты из bot_app ---
try:
    from bot_app import bot as global_bot_instance
    # global_db_connection будет использоваться сервисами
except ImportError:
    critical_error_msg_vcb = "КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать global_bot_instance из bot_app.py (WSB ViewingCallbacks)."
    try:
        from logger import logger; logger.critical(critical_error_msg_vcb)
    except ImportError:
        import sys; sys.stderr.write(f"CRITICAL: {critical_error_msg_vcb}\n")
    global_bot_instance = None

from logger import logger
import constants as const
# Сервисы используют global_db_connection
import services.booking_service as bookingService
import services.equipment_service as equipmentService
from utils import keyboards as keyboards_wsb  # Используем ваш файл клавиатур
from utils.message_utils import edit_or_send_message


# utils.time_utils если нужны (bookingService уже должен их использовать)
# from utils.time_utils import format_date

# --- Обработчики /datebookings ---

def handle_datebookings_select_date_wsb(call: CallbackQuery):  # Имя функции изменено для ясности
    """Обрабатывает выбор даты в /datebookings для WSB."""
    if not global_bot_instance:
        logger.error("global_bot_instance не инициализирован в handle_datebookings_select_date_wsb.")
        return

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    selected_date_str_from_cb = call.data[len(const.CB_DATEB_SELECT_DATE):]  # Формат YYYY-MM-DD из клавиатуры
    logger.debug(
        f"User {user_id} запросил бронирования на дату {selected_date_str_from_cb} (callback /datebookings, WSB)")

    kwargs_edit: Dict[str, Any] = {'reply_markup': None, 'parse_mode': "HTML", 'disable_web_page_preview': True}
    date_obj_selected: Optional[date] = None
    text_response: str

    try:
        # Преобразуем YYYY-MM-DD в datetime.date
        date_obj_selected = datetime.strptime(selected_date_str_from_cb, '%Y-%m-%d').date()

        try:
            global_bot_instance.answer_callback_query(call.id,
                                                      f"Загружаю бронирования на {date_obj_selected.strftime('%d-%m-%Y')}...")
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")

        # bookingService.get_bookings_by_date_text использует global_db и возвращает HTML
        text_response = bookingService.get_bookings_by_date_text(date_obj_selected)
        edit_or_send_message(global_bot_instance, chat_id, message_id, text_response, **kwargs_edit)

    except ValueError:
        logger.warning(f"Неверный формат даты '{selected_date_str_from_cb}' в /datebookings от user {user_id} (WSB)")
        try:
            global_bot_instance.answer_callback_query(call.id, "Ошибка формата даты.", show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        edit_or_send_message(global_bot_instance, chat_id, message_id, "<b>Ошибка:</b> Неверный формат даты.",
                             **kwargs_edit)
    except Exception as e_get_bookings_date:
        logger.error(
            f"Ошибка при получении броней на {selected_date_str_from_cb} для user {user_id} (WSB): {e_get_bookings_date}",
            exc_info=True)
        try:
            global_bot_instance.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)


# --- Обработчики /workspacebookings ---

def handle_wsb_select_category_wsb(call: CallbackQuery):
    """Обрабатывает выбор категории в /workspacebookings (WSB)."""
    if not global_bot_instance:
        logger.error("global_bot_instance не инициализирован в handle_wsb_select_category_wsb.")
        return

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    category_id_str = call.data[len(const.CB_WSPB_SELECT_CATEGORY):]
    category_id: Optional[int] = None
    try:
        category_id = int(category_id_str)
    except ValueError:
        logger.error(f"Неверный category_id '{category_id_str}' в CB_WSPB_SELECT_CATEGORY от user {user_id} (WSB)")
        try:
            global_bot_instance.answer_callback_query(call.id, "Ошибка ID категории.", show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        return

    logger.debug(f"User {user_id} выбрал категорию {category_id} для /workspacebookings (WSB)")
    try:
        global_bot_instance.answer_callback_query(call.id)
    except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
        logger.debug(f"Не удалось ответить на callback query: {e}")

    kwargs_edit_wsb: Dict[str, Any] = {'parse_mode': "HTML"}  # user_id_for_state_update не нужен

    equipment_list_in_cat = None
    category_name_val = None
    try:
        # equipmentService использует global_db
        equipment_list_in_cat = equipmentService.get_equipment_by_category(category_id)
        category_name_val = equipmentService.get_category_name_by_id(category_id) or f"ID {category_id}"
    except Exception as e_get_equip_list:
        logger.error(
            f"Ошибка получения оборудования для категории {category_id} (wsb, user {user_id}): {e_get_equip_list}",
            exc_info=True)
        edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None,
                             **kwargs_edit_wsb)
        return

    if not equipment_list_in_cat:
        logger.warning(
            f"В категории {category_id} ('{html.escape(category_name_val)}') нет оборудования (wsb, user {user_id}).")
        # Используем константу MSG_NO_EQUIPMENT_IN_CATEGORY
        msg_no_equip_text = const.MSG_NO_EQUIPMENT_IN_CATEGORY.format(category_name=html.escape(category_name_val))
        edit_or_send_message(global_bot_instance, chat_id, message_id, msg_no_equip_text, reply_markup=None,
                             **kwargs_edit_wsb)
        return

    # keyboards_wsb.generate_equipment_keyboard ожидает (list, prefix, category_name - опционально для кнопки "назад")
    markup_equip_select = keyboards_wsb.generate_equipment_keyboard(
        equipment_list_in_cat,
        const.CB_WSPB_SELECT_EQUIPMENT,
        category_name_val  # Для кнопки "Назад к категориям"
    )
    edit_or_send_message(global_bot_instance, chat_id, message_id,
                        f"Оборудование в категории '<b>{html.escape(category_name_val)}</b>'. Выберите для просмотра:",
                        reply_markup=markup_equip_select, **kwargs_edit_wsb)


def handle_wsb_select_equipment_wsb(call: CallbackQuery):
    """Обрабатывает выбор оборудования в /workspacebookings для WSB."""
    if not global_bot_instance:
        logger.error("global_bot_instance не инициализирован в handle_wsb_select_equipment_wsb.")
        return

    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    equip_id_str = call.data[len(const.CB_WSPB_SELECT_EQUIPMENT):]
    equip_id: Optional[int] = None
    try:
        equip_id = int(equip_id_str)
    except ValueError:
        logger.error(f"Неверный equipment_id '{equip_id_str}' в CB_WSB_SELECT_EQUIPMENT от user {user_id} (WSB)")
        try:
            global_bot_instance.answer_callback_query(call.id, "Ошибка ID оборудования.", show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        return

    logger.debug(f"User {user_id} выбрал оборудование {equip_id} для просмотра (/workspacebookings, WSB)")
    try:
        global_bot_instance.answer_callback_query(call.id, "Загружаю информацию о бронированиях...")
    except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
        logger.debug(f"Не удалось ответить на callback query: {e}")

    kwargs_edit_wsb_equip: Dict[str, Any] = {'reply_markup': None, 'parse_mode': "HTML",
                                            'disable_web_page_preview': True}
    equipment_name_val: Optional[str] = None
    text_response_bookings: str

    try:
        equipment_name_val = equipmentService.get_equipment_name_by_id(equip_id)
        if not equipment_name_val:
            logger.warning(f"Не найдено имя для оборудования {equip_id} (wsb, user {user_id})")
            edit_or_send_message(global_bot_instance, chat_id, message_id,
                                "Не удалось найти информацию о выбранном оборудовании.",
                                 **kwargs_edit_wsb_equip)
            return

        # bookingService.get_bookings_by_workspace_text использует global_db и возвращает HTML
        text_response_bookings = bookingService.get_bookings_by_workspace_text(equip_id, equipment_name_val)
        edit_or_send_message(global_bot_instance, chat_id, message_id, text_response_bookings, **kwargs_edit_wsb_equip)
    except Exception as e_get_bookings_equip:
        logger.error(
            f"Ошибка при получении броней для оборудования {equip_id} (wsb, user {user_id}): {e_get_bookings_equip}",
            exc_info=True)
        edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit_wsb_equip)

# --- END OF FILE handlers/callbacks/viewing_callbacks.py (WSB - переработанный в стиле CRB) ---