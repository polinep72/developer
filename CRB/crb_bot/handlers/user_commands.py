# --- START OF FILE user_commands.py (Исправленная версия с учетом всех текстов кнопок) ---

# handlers/user_commands.py
import telebot
from telebot import types
from telebot.types import Message
from typing import Dict, Any, Optional, Set, Tuple, List
from database import Database
from logger import logger
from services import (
    user_service, booking_service,
    conference_room_service as room_service
)
from utils import keyboards
import constants as const # Импортируем константы для текстов кнопок
from datetime import datetime, date
import os
# Импортируем user_booking_states и clear_user_state из states.py
from states import user_booking_states, clear_user_state
from . import callback_handlers # Для вызова handle_callback_query в /extend
from telebot import apihelper

# Импорт зависимостей из bot_app
try:
    from bot_app import scheduler, active_timers, scheduled_jobs_registry
except ImportError:
    logger.critical("КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать scheduler/timers/registry из bot_app.")
    raise

def register_user_command_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики команд для обычных пользователей."""

    # --- СПИСОК ВСЕХ ИЗВЕСТНЫХ ТЕКСТОВ REPLY-КНОПОК (включая админские) ---
    # Это нужно для корректной работы последнего обработчика handle_text
    ALL_REPLY_BUTTON_TEXTS = [
        const.BTN_TEXT_HELP, const.BTN_TEXT_BOOKING, const.BTN_TEXT_MYBOOKINGS,
        const.BTN_TEXT_ROOMBOOKINGS, const.BTN_TEXT_DATEBOOKINGS, const.BTN_TEXT_CANCEL,
        const.BTN_TEXT_FINISH, const.BTN_TEXT_EXTEND,
        # Тексты админских кнопок, чтобы handle_text их не перехватывал,
        # если админ нажмет их в обычном чате (хотя они должны обрабатываться в admin_commands.py).
        # Это больше для полноты и предотвращения неожиданного поведения handle_text.
        const.BTN_TEXT_ADMIN_HELP, const.BTN_TEXT_ADD_ROOM, const.BTN_TEXT_VIEW_ROOMS,
        const.BTN_TEXT_ADMIN_CANCEL, const.BTN_TEXT_ALL, const.BTN_TEXT_BROADCAST,
        const.BTN_TEXT_MANAGE_USER, const.BTN_TEXT_USERS, const.BTN_TEXT_SCHEDULE
    ]
    # --- КОНЕЦ СПИСКА ---

    # handle_start закомментирован, оставляем так

    @bot.message_handler(commands=['help'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_HELP) # Обработка текста кнопки
    def help_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"User {user_id} запросил /help или нажал кнопку '{const.BTN_TEXT_HELP}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        help_text_to_send = const.MSG_HELP_USER
        is_admin = user_service.is_admin(db, user_id)
        if is_admin:
            help_text_to_send += const.MSG_HELP_ADMIN_ADDON
            reply_markup = keyboards.create_admin_reply_keyboard()
        else:
            reply_markup = keyboards.create_user_reply_keyboard()
        bot.reply_to(message, help_text_to_send, parse_mode="Markdown", reply_markup=reply_markup)

    @bot.message_handler(commands=['booking'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_BOOKING) # Обработка текста кнопки
    def booking_start_handler(message: Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        logger.info(f"User {user_id} инициировал /booking или нажал кнопку '{const.BTN_TEXT_BOOKING}'")
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            logger.warning(f"Неавторизованный пользователь {user_id} попытался выполнить /booking.")
            return
        clear_user_state(user_id)

        try:
            conference_rooms = room_service.get_all_conference_rooms(db)
            if not conference_rooms:
                bot.reply_to(message, "К сожалению, нет доступных переговорных комнат для бронирования.")
                return

            markup = keyboards.generate_conference_room_keyboard(conference_rooms, const.CB_BOOK_SELECT_CR)
            sent_message = bot.send_message(chat_id, const.MSG_BOOKING_STEP_1_SELECT_ROOM, reply_markup=markup)
            logger.debug(f"Отправлено сообщение {sent_message.message_id} для выбора комнаты пользователю {user_id}")

            user_booking_states[user_id] = {
                'step': const.STATE_BOOKING_CONFERENCE_ROOM,
                'chat_id': chat_id,
                'message_id': sent_message.message_id,
                'data': {}
            }
            logger.debug(f"Состояние для user {user_id} инициализировано: {user_booking_states[user_id]}")
        except Exception as e:
            logger.error(f"Ошибка старта /booking для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)
            clear_user_state(user_id)

    @bot.message_handler(commands=['mybookings'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_MYBOOKINGS) # Обработка текста кнопки
    def my_bookings_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"User {user_id} запросил /mybookings или нажал кнопку '{const.BTN_TEXT_MYBOOKINGS}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            bookings_text = booking_service.get_user_active_bookings_text(db, user_id)
            bot.send_message(message.chat.id, bookings_text, parse_mode="HTML") # Используем HTML из-за ссылки на карту
        except Exception as e:
            logger.error(f"Ошибка /mybookings для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['datebookings'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_DATEBOOKINGS) # Обработка текста кнопки
    def datebookings_start_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"User {user_id} запросил /datebookings или нажал кнопку '{const.BTN_TEXT_DATEBOOKINGS}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            markup = keyboards.generate_date_keyboard(callback_prefix=const.CB_DATEB_SELECT_DATE)
            bot.send_message(message.chat.id, "Выберите дату для просмотра бронирований:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка генерации клавиатуры дат для /datebookings user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['roombookings'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_ROOMBOOKINGS) # Обработка текста кнопки
    def roombookings_start_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"User {user_id} запросил /roombookings или нажал кнопку '{const.BTN_TEXT_ROOMBOOKINGS}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            conference_rooms = room_service.get_all_conference_rooms(db)
            if not conference_rooms:
                bot.reply_to(message, "Нет переговорных комнат для просмотра.")
                return
            markup = keyboards.generate_conference_room_keyboard(conference_rooms, const.CB_ROOMB_SELECT_CR)
            bot.send_message(message.chat.id, "Выберите переговорную комнату для просмотра её бронирований:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка старта /roombookings для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['cancel'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_CANCEL) # Обработка текста кнопки
    def cancel_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"User {user_id} инициировал /cancel или нажал кнопку '{const.BTN_TEXT_CANCEL}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            user_bookings = booking_service.get_user_bookings_for_cancel(db, user_id)
            if not user_bookings:
                bot.reply_to(message, "У вас нет предстоящих бронирований, которые можно отменить.")
                return
            markup = keyboards.generate_user_bookings_keyboard(user_bookings, const.CB_CANCEL_SELECT_BOOKING)
            bot.send_message(message.chat.id, "Выберите бронирование для отмены:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /cancel для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['finish'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_FINISH) # Обработка текста кнопки
    def finish_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"User {user_id} инициировал /finish или нажал кнопку '{const.BTN_TEXT_FINISH}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            current_bookings = booking_service.get_user_current_bookings(db, user_id)
            if not current_bookings:
                bot.reply_to(message, "У вас нет активных бронирований, которые можно завершить сейчас.")
                return
            if len(current_bookings) == 1:
                booking_id_to_finish = current_bookings[0].get('id')
                if booking_id_to_finish:
                    logger.debug(f"У пользователя {user_id} только одна активная бронь {booking_id_to_finish}, завершаем её.")
                    success, msg = booking_service.finish_booking(db, booking_id_to_finish, user_id)
                    bot.reply_to(message, msg, parse_mode="Markdown")
                else:
                    logger.error(f"Не найден ID в единственной активной брони пользователя {user_id} при /finish")
                    bot.reply_to(message, const.MSG_ERROR_GENERAL)
                return
            logger.debug(f"У пользователя {user_id} несколько активных броней, предлагаем выбор для /finish.")
            markup = keyboards.generate_user_bookings_keyboard(current_bookings, const.CB_FINISH_SELECT_BOOKING)
            bot.send_message(message.chat.id, "У вас несколько активных бронирований. Выберите то, которое хотите завершить:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /finish для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['extend'])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_EXTEND) # Обработка текста кнопки
    def extend_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"User {user_id} инициировал /extend или нажал кнопку '{const.BTN_TEXT_EXTEND}'")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            current_bookings = booking_service.get_user_current_bookings(db, user_id)
            if not current_bookings:
                bot.reply_to(message, "У вас нет активных бронирований, которые можно продлить.")
                return
            if len(current_bookings) == 1:
                booking_id_to_extend = current_bookings[0].get('id')
                if booking_id_to_extend:
                    logger.debug(f"У пользователя {user_id} только одна активная бронь {booking_id_to_extend}, имитируем нажатие кнопки выбора брони.")
                    fake_call = types.CallbackQuery(
                        id=str(message.message_id)+"_extend_f",
                        from_user=message.from_user,
                        data=f"{const.CB_EXTEND_SELECT_BOOKING}{booking_id_to_extend}",
                        chat_instance=str(message.chat.id),
                        json_string="",
                        message=message
                        )
                    try:
                        callback_handlers.handle_callback_query(
                            bot, db, scheduler, active_timers, scheduled_jobs_registry, fake_call
                            )
                    except Exception as e_fake_call:
                        logger.error(f"Ошибка при вызове handle_callback_query через fake_call для /extend (user {user_id}): {e_fake_call}", exc_info=True)
                        bot.reply_to(message, const.MSG_ERROR_GENERAL)
                else:
                    logger.error(f"Не найден ID в единственной активной брони пользователя {user_id} при /extend")
                    bot.reply_to(message, const.MSG_ERROR_GENERAL)
                return
            logger.debug(f"У пользователя {user_id} несколько активных броней, предлагаем выбор для /extend.")
            markup = keyboards.generate_user_bookings_keyboard(current_bookings, const.CB_EXTEND_SELECT_BOOKING)
            bot.send_message(message.chat.id, "У вас несколько активных бронирований. Выберите то, которое хотите продлить:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /extend для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # Обработчик для текста, который не является командой и не является текстом известной кнопки
    @bot.message_handler(func=lambda message:
                         message.text is not None and
                         not message.text.startswith('/') and
                         message.text not in ALL_REPLY_BUTTON_TEXTS
                        )
    def handle_text(message: Message):
        user_id = message.from_user.id
        # Получаем состояние из общего модуля states.py
        current_state = user_booking_states.get(user_id)
        if current_state and current_state.get('step') not in [None, const.STATE_BOOKING_IDLE]:
            logger.debug(f"Пользователь {user_id} находится в состоянии '{current_state.get('step')}' и отправил текст '{message.text}'. Просим использовать кнопки.")
            try:
                bot.reply_to(message, "Пожалуйста, используйте кнопки для взаимодействия в процессе бронирования.")
            except apihelper.ApiTelegramException as e_reply:
                if "reply message not found" in str(e_reply): logger.warning(f"Не удалось ответить на сообщение {message.message_id} (возможно, удалено) пользователя {user_id}.")
                else: logger.warning(f"Ошибка API Telegram при ответе пользователю {user_id}: {e_reply}")
            except Exception as e_reply_other:
                logger.warning(f"Другая ошибка при ответе пользователю {user_id}: {e_reply_other}")
        else:
            logger.debug(f"Пользователь {user_id} отправил неизвестный текст '{message.text}' вне активного состояния или процесса. Предлагаем помощь.")
            bot.reply_to(message, f"Неизвестная команда или текст. Используйте {const.BTN_TEXT_HELP} или /help для списка доступных действий.")

    logger.info("Обработчики команд пользователя успешно зарегистрированы.")

# --- END OF FILE user_commands.py ---