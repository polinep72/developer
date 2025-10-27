# --- START OF FILE handlers/callbacks/viewing_callbacks.py ---
"""
Обработчики callback-запросов, связанных с просмотром информации о бронированиях.

Отвечает за:
- Обработку выбора даты в /datebookings.
- Обработку выбора категории в /workspacebookings.
- Обработку выбора оборудования в /workspacebookings.
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime

from database import Database
from logger import logger
import constants as const
import services.booking_service as bookingService
import services.equipment_service as equipmentService
from utils import keyboards

# Импортируем хелпер для редактирования/отправки сообщений
# Предполагаем, что он останется в основном callback_handlers или будет вынесен в utils
try:
    from utils.message_utils import edit_or_send_message
except ImportError:
    # Заглушка на случай, если основной файл еще не обновлен
    logger.error("Не удалось импортировать edit_or_send_message из callback_handlers")
    def edit_or_send_message(bot, chat_id, message_id, text, **kwargs):
        logger.warning(f"Вызвана заглушка edit_or_send_message для chat_id {chat_id}")
        try:
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, **kwargs)
            else:
                bot.send_message(chat_id, text, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в заглушке edit_or_send_message: {e}")

# --- Обработчики /datebookings ---

def handle_datebookings_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    # user_id, chat_id, message_id извлекаются из call
):
    """Обрабатывает выбор даты в /datebookings."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    data_part = cb_data[len(const.CB_DATEB_SELECT_DATE):]
    selected_date_str = data_part
    logger.debug(f"User {user_id} запросил бронирования на дату {selected_date_str} (callback)")

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}
    date_obj = None
    try:
        date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        try:
            bot.answer_callback_query(call.id, f"Загружаю бронирования на {selected_date_str}...")
        except Exception as e_ans_dateb:
            logger.warning(f"Не удалось ответить на callback /datebookings {selected_date_str}: {e_ans_dateb}")

        text = bookingService.get_bookings_by_date_text(db, date_obj)
        edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)

    except ValueError:
        logger.warning(f"Неверный формат даты '{selected_date_str}' в callback /datebookings от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка формата даты.", show_alert=True)
        except Exception: pass
        # Не редактируем сообщение об ошибке, чтобы пользователь видел исходные кнопки
    except Exception as e:
        logger.error(f"Ошибка при получении бронирований на дату {selected_date_str} для user {user_id}: {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)


# --- Обработчики /workspacebookings ---

def handle_wsb_category_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    # user_id, chat_id, message_id извлекаются из call
):
    """Обрабатывает выбор категории в /workspacebookings."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    cat_id_str = cb_data[len(const.CB_WSB_SELECT_CATEGORY):]
    cat_id = None
    try:
        cat_id = int(cat_id_str)
    except ValueError:
        logger.error(f"Неверный category_id '{cat_id_str}' в CB_WSB_SELECT_CATEGORY от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID категории.", show_alert=True)
        except Exception: pass
        return

    logger.debug(f"User {user_id} выбрал категорию {cat_id} для /workspacebookings")
    try:
        bot.answer_callback_query(call.id)
    except Exception as e_ans_wsb_cat:
        logger.warning(f"Не удалось ответить на callback /workspacebookings category {cat_id}: {e_ans_wsb_cat}")

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'user_id_for_state_update': user_id}
    equipment = None
    try:
        equipment = equipmentService.get_equipment_by_category(db, cat_id)
    except Exception as e_get_eq:
        logger.error(f"Ошибка получения оборудования для кат. {cat_id} (wsb): {e_get_eq}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return

    if not equipment:
        logger.warning(f"В категории {cat_id} нет оборудования (wsb, user {user_id}).")
        edit_or_send_message(bot, chat_id, message_id, "В этой категории нет доступного оборудования.", reply_markup=None, **kwargs_edit)
        return

    markup = keyboards.generate_equipment_keyboard(equipment, const.CB_WSB_SELECT_EQUIPMENT)
    edit_or_send_message(bot, chat_id, message_id, "Выберите конкретное оборудование:", reply_markup=markup, **kwargs_edit)


def handle_wsb_equipment_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    # user_id, chat_id, message_id извлекаются из call
):
    """Обрабатывает выбор оборудования в /workspacebookings."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    equip_id_str = cb_data[len(const.CB_WSB_SELECT_EQUIPMENT):]
    equip_id = None
    try:
        equip_id = int(equip_id_str)
    except ValueError:
        logger.error(f"Неверный equipment_id '{equip_id_str}' в CB_WSB_SELECT_EQUIPMENT от user {user_id}")
        try:
            bot.answer_callback_query(call.id, "Ошибка ID оборудования.", show_alert=True)
        except Exception: pass
        return

    logger.debug(f"User {user_id} выбрал оборудование {equip_id} для просмотра бронирований (/workspacebookings)")
    try:
        bot.answer_callback_query(call.id, "Загружаю информацию о бронированиях...")
    except Exception as e_ans_wsb_eq:
        logger.warning(f"Не удалось ответить на callback /workspacebookings equipment {equip_id}: {e_ans_wsb_eq}")

    # Передаем user_id для обновления message_id в состоянии (на случай, если он был)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}
    name = None
    text = ""
    try:
        name = equipmentService.get_equipment_name_by_id(db, equip_id)
        if not name:
            logger.warning(f"Не найдено имя для оборудования {equip_id} (wsb, user {user_id})")
            edit_or_send_message(bot, chat_id, message_id, "Не удалось найти информацию о выбранном оборудовании.", **kwargs_edit)
            return
        # Получаем текст с бронированиями
        text = bookingService.get_bookings_by_workspace_text(db, equip_id, name)
        edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при получении бронирований для оборудования {equip_id} (wsb, user {user_id}): {e}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)

# --- END OF FILE handlers/callbacks/viewing_callbacks.py ---