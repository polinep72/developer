import os
from datetime import datetime, date

import telebot
from telebot import types, apihelper
from telebot.types import Message

from database import Database
from logger import logger
from services import user_service, booking_service, equipment_service
from utils import keyboards
import constants as const
from .callback_handlers import user_booking_states, clear_user_state
from . import callback_handlers

try:
    from main import (
        scheduler as main_scheduler,
        active_timers_main,
        scheduled_jobs_registry_main,
    )
except ImportError:
    logger.warning(
        "Не удалось импортировать scheduler/timers/registry из main. "
        "Уведомления могут не работать корректно в fake_call."
    )
    main_scheduler = None
    active_timers_main = {}
    scheduled_jobs_registry_main = set()


def register_user_command_handlers(bot: telebot.TeleBot, db: Database) -> None:
    """Регистрирует обработчики команд для обычных пользователей."""

    all_reply_button_texts = [
        const.BTN_TEXT_HELP,
        const.BTN_TEXT_BOOKING,
        const.BTN_TEXT_MYBOOKINGS,
        const.BTN_TEXT_WORKSPACEBOOKINGS,
        const.BTN_TEXT_DATEBOOKINGS,
        const.BTN_TEXT_CANCEL,
        const.BTN_TEXT_FINISH,
        const.BTN_TEXT_EXTEND,
        const.BTN_TEXT_ADMIN_HELP,
        const.BTN_TEXT_ADD_EQUIPMENT,
        const.BTN_TEXT_MANAGE_EQUIPMENT,
        const.BTN_TEXT_ADMIN_CANCEL_KB,
        const.BTN_TEXT_ALL_KB,
        const.BTN_TEXT_BROADCAST_KB,
        const.BTN_TEXT_MANAGE_USER_KB,
        const.BTN_TEXT_USERS_KB,
        const.BTN_TEXT_SCHEDULE_KB,
    ]

    @bot.message_handler(commands=[const.CMD_START])
    def handle_start(message: Message) -> None:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        chat_id = message.chat.id

        logger.info(f"/start user_id: {user_id}, username: {username}")
        clear_user_state(user_id)

        is_new, user_info = user_service.find_or_register_user(
            db, user_id, username, first_name, last_name
        )
        reply_markup: types.ReplyKeyboardRemove | types.ReplyKeyboardMarkup = (
            types.ReplyKeyboardRemove()
        )
        response_message = ""

        if user_info:
            is_active = user_service.is_user_registered_and_active(db, user_id)
            is_admin = user_service.is_admin(db, user_id)
            if is_active:
                user_name_from_db = user_info.get("fi")
                name_to_display = user_name_from_db or first_name or username
                response_message = const.MSG_WELCOME.format(name=name_to_display)
                if is_admin:
                    reply_markup = keyboards.create_admin_reply_keyboard()
                else:
                    reply_markup = keyboards.create_user_reply_keyboard()
            else:
                response_message = const.MSG_ERROR_ACCOUNT_INACTIVE
        elif is_new is False and user_info is None:
            response_message = const.MSG_ERROR_REGISTRATION_FAILED
        elif is_new is True and user_info is None:
            response_message = const.MSG_REGISTRATION_PENDING
        elif is_new is True and user_info:
            response_message = const.MSG_REGISTRATION_PENDING

        bot.send_message(chat_id, response_message, reply_markup=reply_markup)

    @bot.message_handler(commands=[const.CMD_HELP])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_HELP)
    def help_handler(message: Message) -> None:
        user_id = message.from_user.id
        logger.debug(f"User {user_id} /help")
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

        bot.reply_to(
            message,
            help_text_to_send,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

    @bot.message_handler(commands=[const.CMD_BOOKING])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_BOOKING)
    def booking_start_handler(message: Message) -> None:
        user_id = message.from_user.id
        chat_id = message.chat.id
        logger.info(f"User {user_id} /booking")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            logger.warning(f"Неавториз. {user_id} /booking.")
            return

        clear_user_state(user_id)
        user_booking_states[user_id] = {
            "step": const.STATE_BOOKING_CATEGORY,
            "chat_id": chat_id,
            "message_id": None,
            "data": {},
        }

        try:
            categories = equipment_service.get_all_categories(db)
            if not categories:
                bot.reply_to(message, "Нет категорий.")
                clear_user_state(user_id)
                return
            markup = keyboards.generate_equipment_category_keyboard(
                categories, const.CB_BOOK_SELECT_CATEGORY
            )
            sent_message = bot.send_message(
                chat_id, const.MSG_BOOKING_STEP_1_CATEGORY, reply_markup=markup
            )
            if user_id in user_booking_states:
                user_booking_states[user_id]["message_id"] = sent_message.message_id
            else:
                logger.warning(f"Состояние {user_id} исчезло после отпр. сообщ.")
        except Exception as exc:
            logger.error(f"Ошибка старта /booking user {user_id}: {exc}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)
            clear_user_state(user_id)

    @bot.message_handler(commands=[const.CMD_MY_BOOKINGS])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_MYBOOKINGS)
    def my_bookings_handler(message: Message) -> None:
        user_id = message.from_user.id
        logger.debug(f"User {user_id} /mybookings")
        clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            bookings_text = booking_service.get_user_active_bookings_text(db, user_id)
            bot.send_message(message.chat.id, bookings_text, parse_mode="Markdown")
        except Exception as exc:
            logger.error(f"Ошибка /mybookings user {user_id}: {exc}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)
