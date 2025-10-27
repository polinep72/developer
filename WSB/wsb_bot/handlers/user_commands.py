# handlers/user_commands.py
import telebot
from telebot import types
from telebot.types import Message
from database import Database
from logger import logger
from services import user_service, booking_service, equipment_service
from utils import keyboards
import constants as const
from datetime import datetime, date
import os
from .callback_handlers import user_booking_states, clear_user_state
from . import callback_handlers
from telebot import apihelper # Добавим импорт

# <<< Импорт зависимостей из main >>>
try:
    # Используем относительный импорт, если main.py в корне проекта
    from main import scheduler as main_scheduler, active_timers_main, scheduled_jobs_registry_main
except ImportError:
    # Если импорт не удался (например, при тестах), используем заглушки
    logger.warning("Не удалось импортировать scheduler/timers/registry из main. Уведомления могут не работать корректно в fake_call.")
    main_scheduler = None
    active_timers_main = {}
    scheduled_jobs_registry_main = set()


def register_user_command_handlers(bot: telebot.TeleBot, db: Database): # bot и db передаются сюда
    """Регистрирует обработчики команд для обычных пользователей."""
    # --- СПИСОК ВСЕХ ИЗВЕСТНЫХ ТЕКСТОВ REPLY-КНОПОК (включая админские) ---
    # Это нужно для корректной работы последнего обработчика handle_text
    ALL_REPLY_BUTTON_TEXTS = [
        const.BTN_TEXT_HELP, const.BTN_TEXT_BOOKING, const.BTN_TEXT_MYBOOKINGS,
        const.BTN_TEXT_WORKSPACEBOOKINGS, const.BTN_TEXT_DATEBOOKINGS, const.BTN_TEXT_CANCEL,
        const.BTN_TEXT_FINISH, const.BTN_TEXT_EXTEND,
        # Тексты админских кнопок, чтобы handle_text их не перехватывал,
        # если админ нажмет их в обычном чате (хотя они должны обрабатываться в admin_commands.py).
        # Это больше для полноты и предотвращения неожиданного поведения handle_text.
        const.BTN_TEXT_ADMIN_HELP, const.BTN_TEXT_ADD_EQUIPMENT, const.BTN_TEXT_MANAGE_EQUIPMENT,
        const.BTN_TEXT_ADMIN_CANCEL_KB, const.BTN_TEXT_ALL_KB, const.BTN_TEXT_BROADCAST_KB,
        const.BTN_TEXT_MANAGE_USER_KB, const.BTN_TEXT_USERS_KB, const.BTN_TEXT_SCHEDULE_KB
    ]
    # --- КОНЕЦ СПИСКА ---

    #@bot.message_handler(commands=[const.CMD_START])
    def handle_start(message: Message):
        user_id = message.from_user.id; username = message.from_user.username; first_name = message.from_user.first_name; last_name = message.from_user.last_name; chat_id = message.chat.id
        logger.info(f"/start user_id: {user_id}, username: {username}"); clear_user_state(user_id)
        is_new, user_info = user_service.find_or_register_user(db, user_id, username, first_name, last_name)
        reply_markup = types.ReplyKeyboardRemove(); response_message = ""; is_active_admin = False
        if user_info:
            is_active = user_service.is_user_registered_and_active(db, user_id); is_admin = user_service.is_admin(db, user_id)
            if is_active:
                user_name_from_db = user_info.get('fi'); name_to_display = user_name_from_db or first_name or username
                response_message = const.MSG_WELCOME.format(name=name_to_display)
                if is_admin: reply_markup = keyboards.create_admin_reply_keyboard(); is_active_admin = True
                else: reply_markup = keyboards.create_user_reply_keyboard()
            else: response_message = const.MSG_ERROR_ACCOUNT_INACTIVE
        elif is_new is False and user_info is None: response_message = const.MSG_ERROR_REGISTRATION_FAILED
        elif is_new is True and user_info is None: response_message = const.MSG_REGISTRATION_PENDING
        elif is_new is True and user_info: response_message = const.MSG_REGISTRATION_PENDING
        bot.send_message(chat_id, response_message, reply_markup=reply_markup)

    @bot.message_handler(commands=[const.CMD_HELP])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_HELP)  # Обработка текста кнопки
    def help_handler(message: Message):
        user_id = message.from_user.id; logger.debug(f"User {user_id} /help"); clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); return
        help_text_to_send = const.MSG_HELP_USER; is_admin = user_service.is_admin(db, user_id)
        if is_admin: help_text_to_send += const.MSG_HELP_ADMIN_ADDON; reply_markup = keyboards.create_admin_reply_keyboard()
        else: reply_markup = keyboards.create_user_reply_keyboard()
        bot.reply_to(message, help_text_to_send, parse_mode="Markdown", reply_markup=reply_markup)

    @bot.message_handler(commands=[const.CMD_BOOKING])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_BOOKING)  # Обработка текста кнопки
    def booking_start_handler(message: Message):
        user_id = message.from_user.id; chat_id = message.chat.id
        logger.info(f"User {user_id} /booking");
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); logger.warning(f"Неавториз. {user_id} /booking."); return
        clear_user_state(user_id); user_booking_states[user_id] = {'step': const.STATE_BOOKING_CATEGORY, 'chat_id': chat_id, 'message_id': None, 'data': {}}
        logger.debug(f"Состояние {user_id} инициализировано: {user_booking_states[user_id]}")
        try:
            categories = equipment_service.get_all_categories(db)
            if not categories: bot.reply_to(message, "Нет категорий."); clear_user_state(user_id); return
            markup = keyboards.generate_equipment_category_keyboard(categories, const.CB_BOOK_SELECT_CATEGORY)
            sent_message = bot.send_message(chat_id, const.MSG_BOOKING_STEP_1_CATEGORY, reply_markup=markup)
            if user_id in user_booking_states: user_booking_states[user_id]['message_id'] = sent_message.message_id; logger.debug(f"Msg {sent_message.message_id} для категории user {user_id}")
            else: logger.warning(f"Состояние {user_id} исчезло после отпр. сообщ.")
        except Exception as e:
            logger.error(f"Ошибка старта /booking user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)
            clear_user_state(user_id)

    @bot.message_handler(commands=[const.CMD_MY_BOOKINGS])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_MYBOOKINGS)  # Обработка текста кнопки
    def my_bookings_handler(message: Message):
        user_id = message.from_user.id; logger.debug(f"User {user_id} /mybookings"); clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); return
        try:
            bookings_text = booking_service.get_user_active_bookings_text(db, user_id)
            bot.send_message(message.chat.id, bookings_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Ошибка /mybookings user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_DATE_BOOKINGS])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_DATEBOOKINGS)  # Обработка текста кнопки
    def datebookings_start_handler(message: Message):
        user_id = message.from_user.id; logger.debug(f"User {user_id} /datebookings"); clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); return
        try:
            markup = keyboards.generate_date_keyboard(callback_prefix=const.CB_DATEB_SELECT_DATE)
            bot.send_message(message.chat.id, "Выберите дату:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка клв. дат /datebookings user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_WORKSPACE_BOOKINGS])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_WORKSPACEBOOKINGS)  # Обработка текста кнопки
    def workspacebookings_start_handler(message: Message):
        user_id = message.from_user.id; logger.debug(f"User {user_id} /workspacebookings"); clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); return
        try:
            categories = equipment_service.get_all_categories(db)
            if not categories: bot.reply_to(message, "Нет категорий."); return
            markup = keyboards.generate_equipment_category_keyboard(categories, const.CB_WSPB_SELECT_CATEGORY)
            bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка категорий /workspacebookings user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_CANCEL_BOOKING])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_CANCEL)  # Обработка текста кнопки
    def cancel_start_handler(message: Message):
        user_id = message.from_user.id; logger.info(f"User {user_id} /cancel"); clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); return
        try:
            user_bookings = booking_service.get_user_bookings_for_cancel(db, user_id)
            if not user_bookings: bot.reply_to(message, "Нет броней для отмены."); return
            markup = keyboards.generate_user_bookings_keyboard(user_bookings, const.CB_CANCEL_SELECT_BOOKING)
            bot.send_message(message.chat.id, "Выберите бронь для отмены:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /cancel user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_FINISH_BOOKING])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_FINISH)  # Обработка текста кнопки
    def finish_start_handler(message: Message):
        user_id = message.from_user.id; logger.info(f"User {user_id} /finish"); clear_user_state(user_id)
        if not user_service.is_user_registered_and_active(db, user_id): bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED); return
        try:
            current_bookings = booking_service.get_user_current_bookings(db, user_id)
            if not current_bookings: bot.reply_to(message, "Нет активных броней."); return
            if len(current_bookings) == 1:
                booking_id_to_finish = current_bookings[0].get('id')
                if booking_id_to_finish:
                    logger.debug(f"User {user_id} одна бронь {booking_id_to_finish}, завершаем.")
                    success, msg = booking_service.finish_booking(db, booking_id_to_finish, user_id)
                    bot.reply_to(message, msg, parse_mode="Markdown")
                else:
                    logger.error(f"Нет ID в брони user {user_id} при /finish")
                    bot.reply_to(message, const.MSG_ERROR_GENERAL)
                return
            logger.debug(f"User {user_id} неск. броней, выбор /finish.")
            markup = keyboards.generate_user_bookings_keyboard(current_bookings, const.CB_FINISH_SELECT_BOOKING)
            bot.send_message(message.chat.id, "Несколько активных броней. Выберите:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /finish user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_EXTEND_BOOKING])
    @bot.message_handler(func=lambda message: message.text == const.BTN_TEXT_EXTEND)
    def extend_start_handler(message: types.Message):  # Убрали лишние аргументы
        user_id = message.from_user.id
        logger.info(f"User {user_id} нажал '{message.text}' (extend_start_handler)")
        # clear_user_state(user_id) # Раскомментируйте, если функция есть и нужна

        # Теперь используем импортированные bot, db, scheduler и т.д.
        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return
        try:
            current_bookings = booking_service.get_user_current_bookings(db, user_id)
            if not current_bookings:
                bot.reply_to(message, "Нет активных броней для продления.")
                return

            if len(current_bookings) == 1:
                booking_id_to_extend = current_bookings[0].get('id')
                if booking_id_to_extend:
                    logger.debug(
                        f"User {user_id} одна активная бронь ID: {booking_id_to_extend}, имитируем выбор для продления.")

                    fake_call = types.CallbackQuery(
                        id=f"fake_{message.message_id}_{user_id}_extend",
                        from_user=message.from_user,
                        data=f"{const.CB_EXTEND_SELECT_BOOKING}{booking_id_to_extend}",
                        chat_instance=str(message.chat.id),
                        json_string="",
                        message=message
                    )
                    fake_call.is_fake_call = True  # Ваш кастомный атрибут

                    try:
                        # Передаем импортированные экземпляры
                        callback_handlers.handle_callback_query(
                            bot,
                            db,
                            main_scheduler,
                            active_timers_main,
                            scheduled_jobs_registry_main,
                            fake_call,
                            source_command=const.CMD_EXTEND_BOOKING  # Или message.text
                        )
                    except Exception as e_fake_call:
                        logger.error(
                            f"Ошибка вызова handle_callback_query для fake_call (booking_id: {booking_id_to_extend}): {e_fake_call}",
                            exc_info=True)
                        bot.reply_to(message, const.MSG_ERROR_GENERAL)
                else:
                    logger.error(f"Не найден ID в единственной активной брони user {user_id} при /extend")
                    bot.reply_to(message, const.MSG_ERROR_GENERAL)
                return

            logger.debug(
                f"User {user_id} имеет несколько активных броней ({len(current_bookings)}), показываем выбор для /extend.")
            markup = keyboards.generate_user_bookings_keyboard(current_bookings, const.CB_EXTEND_SELECT_BOOKING)
            bot.send_message(message.chat.id,
                            "У вас несколько активных бронирований. Выберите то, которое хотите продлить:",
                            reply_markup=markup)

        except Exception as e:
            logger.error(f"Общая ошибка в /extend для user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # Этот обработчик должен быть ПОСЛЕДНИМ среди message_handler'ов,
    # которые проверяют текст, чтобы он срабатывал только если другие не подошли.
    @bot.message_handler(func=lambda message:
    message.text is not None and
    not message.text.startswith('/') and
    message.text not in ALL_REPLY_BUTTON_TEXTS
                        )
    def handle_unknown_text(message: Message):  # Переименовал для ясности
        user_id = message.from_user.id
        current_state_info = user_booking_states.get(user_id)  # Используем .get для безопасности

        # Проверяем, находится ли пользователь в каком-то многошаговом процессе
        # callback_handlers.STATE_BOOKING_IDLE было бы хорошо определить в constants.py, если его еще там нет
        # Например, const.STATE_IDLE = 0 или "idle"
        is_in_process = current_state_info and current_state_info.get('step') not in [None, const.STATE_BOOKING_IDLE]  # Предполагаем, что STATE_BOOKING_IDLE это маркер конца FSM

        if is_in_process:
            step = current_state_info.get('step')
            logger.debug(
                f"User {user_id} is in state '{step}' and sent text '{message.text}'. Prompting to use buttons."
            )
            try:
                bot.reply_to(message, "Пожалуйста, используйте кнопки для навигации в текущем процессе.")
            except apihelper.ApiTelegramException as e_reply:
                if "reply message not found" in str(e_reply).lower():
                    logger.warning(
                        f"Could not reply to message {message.message_id} (possibly deleted) for user {user_id}."
                    )
                else:
                    logger.warning(f"Telegram API error when replying to user {user_id}: {e_reply}")
            except Exception as e_reply_other:
                logger.warning(f"Other error when replying to user {user_id}: {e_reply_other}")
        else:
            logger.debug(
                f"User {user_id} sent unknown text '{message.text}' outside of an active process. Offering help."
            )
            # Здесь важно убедиться, что отправка клавиатуры не сломает логику, если пользователь сразу нажмет что-то
            # Возможно, просто отправить текст без клавиатуры или с инлайн-кнопкой "Помощь?"
            is_admin = user_service.is_admin(db, user_id)
            reply_kb = keyboards.create_admin_reply_keyboard() if is_admin else keyboards.create_user_reply_keyboard()

            bot.reply_to(message,
                        f"Неизвестная команда или текст. Воспользуйтесь кнопками меню или введите /help для получения списка доступных действий.",
                        reply_markup=reply_kb)

        logger.info("Обработчики команд пользователя успешно зарегистрированы.")