# --- START OF FILE handlers/callbacks/viewing_callbacks.py ---
"""
Обработчики callback-запросов, связанных с просмотром информации о бронированиях.

Отвечает за:
- Обработку выбора даты в /datebookings.
- Обработку выбора переговорной комнаты в /roombookings.
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime

from database import Database
from logger import logger
import constants as const # Используем обновленные константы
import services.booking_service as bookingService # Уже адаптирован
# --- ИЗМЕНЕНИЕ: Импорт сервиса комнат ---
import services.conference_room_service as room_service
# --- КОНЕЦ ИЗМЕНЕНИЯ ---
from utils import keyboards # Уже адаптирован

# Импортируем хелпер для редактирования/отправки сообщений
try:
    from utils.message_utils import edit_or_send_message
except ImportError:
    from ..utils.message_utils import edit_or_send_message
except ImportError:
    logger.error("Не удалось импортировать edit_or_send_message.")
    # Заглушка
    def edit_or_send_message(bot, chat_id, message_id, text, **kwargs):
        logger.warning(f"Вызвана заглушка edit_or_send_message для chat_id {chat_id}")
        reply_markup = kwargs.get('reply_markup')
        parse_mode = kwargs.get('parse_mode')
        try:
            if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode=parse_mode)
            else: bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e: logger.error(f"Ошибка в заглушке edit_or_send_message: {e}")

# --- Обработчики /datebookings (без изменений) ---

def handle_datebookings_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    """Обрабатывает выбор даты в /datebookings."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    data_part = cb_data[len(const.CB_DATEB_SELECT_DATE):]
    selected_date_str = data_part
    logger.debug(f"User {user_id} запросил бронирования на дату {selected_date_str} (callback /datebookings)")

    kwargs_edit = {'reply_markup': None, 'parse_mode': "HTML"} # user_id_for_state_update не нужен здесь
    date_obj = None
    try:
        date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        text = bookingService.get_bookings_by_date_text(db, date_obj)  # Эта функция теперь возвращает HTML
        edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)
        try: bot.answer_callback_query(call.id, f"Загружаю бронирования на {selected_date_str}...")
        except Exception: pass # Игнорируем ошибку ответа

        # Вызываем адаптированную функцию из booking_service
        text = bookingService.get_bookings_by_date_text(db, date_obj)
        edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)

    except ValueError:
        logger.warning(f"Неверный формат даты '{selected_date_str}' в callback /datebookings от user {user_id}")
        try: bot.answer_callback_query(call.id, "Ошибка формата даты.", show_alert=True)
        except Exception: pass
    except Exception as e:
        logger.error(f"Ошибка при получении бронирований на дату {selected_date_str} для user {user_id}: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)


# --- Обработчики /roombookings (ранее /workspacebookings) ---

# --- ИЗМЕНЕНО: Функция удалена, т.к. нет выбора категории ---
# def handle_wsb_category_select(...) - УДАЛЕНО
# --- КОНЕЦ ИЗМЕНЕНИЯ ---


# --- ИЗМЕНЕНО: Переименовано и адаптировано для комнат ---
def handle_roomb_select( # <-- Переименовано
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    """Обрабатывает выбор комнаты в /roombookings."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data

    cr_id_str = cb_data[len(const.CB_ROOMB_SELECT_CR):] # <-- Префикс для комнат
    cr_id = None
    try:
        cr_id = int(cr_id_str)
    except ValueError:
        logger.error(f"Неверный cr_id '{cr_id_str}' в CB_ROOMB_SELECT_CR от user {user_id}") # <-- Лог для комнат
        try: bot.answer_callback_query(call.id, "Ошибка ID комнаты.", show_alert=True)
        except Exception: pass
        return

    logger.debug(f"User {user_id} выбрал комнату {cr_id} для просмотра бронирований (/roombookings)")
    try: bot.answer_callback_query(call.id, "Загружаю информацию о бронированиях...")
    except Exception: pass

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown"}
    name = None
    text = ""
    try:
        # Получаем имя комнаты
        name = room_service.get_conference_room_name_by_id(db, cr_id)
        if not name:
            logger.warning(f"Не найдено имя для комнаты {cr_id} (roombookings, user {user_id})")
            edit_or_send_message(bot, chat_id, message_id, "Не удалось найти информацию о выбранной комнате.", **kwargs_edit)
            return
        # Получаем текст с бронированиями для комнаты
        text = bookingService.get_bookings_by_conference_room_text(db, cr_id, name) # <-- Функция для комнат
        edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при получении бронирований для комнаты {cr_id} (roombookings, user {user_id}): {e}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)
# --- КОНЕЦ ИЗМЕНЕНИЯ ---

# --- END OF FILE handlers/callbacks/viewing_callbacks.py ---