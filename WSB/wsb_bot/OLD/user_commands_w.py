# handlers/user_commands.py
import telebot
from telebot import types # Импортируем types
from telebot.types import Message
from database import Database
from logger import logger
# import config # config больше не нужен напрямую
from services import user_service, booking_service, equipment_service
# --- Импортируем клавиатуры из utils ---
from utils import keyboards
# --------------------------------------
import constants as const
from datetime import datetime, date
import os

# --- Текст помощи для пользователя ---
USER_HELP_TEXT = (
    "🤖 **Команды бота:**\n\n"
    "`/start` - Начало работы, показ клавиатуры\n"
    "`/booking` - Забронировать оборудование\n"
    "`/mybookings` - Просмотр ваших активных бронирований\n"
    "`/finish` - Завершить текущее использование\n"
    "`/cancel` - Отменить будущее бронирование\n"
    "`/продлить` - Продлить текущее бронирование\n"
    "`/workspacebookings` - Бронирования по месту\n"
    "`/datebookings` - Бронирования по дате\n"
    "`/help` - Показать это сообщение\n"
)

def register_user_command_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики команд для обычных пользователей."""

    # --- Команды Помощи ---
    # @bot.message_handler(commands=['start'])
    # def handle_start(message: Message):
    #     user_id = message.from_user.id
    #     username = message.from_user.username
    #     first_name = message.from_user.first_name
    #     last_name = message.from_user.last_name
    #     fi = message.from_user.fi
    #     chat_id = message.chat.id
    #
    #     logger.info(f"Получена команда /start от user_id: {user_id}, username: {username}")
    #
    #     # Логика регистрации пользователя...
    #     is_new, user_info = user_service.find_or_register_user(db, user_id, username, first_name, last_name)
    #
    #     # Определяем сообщение и клавиатуру по умолчанию
    #     reply_markup = types.ReplyKeyboardRemove()
    #     response_message = ""
    #     is_active_admin = False # Флаг для показа админской клавиатуры
    #
    #     if user_info:
    #         is_active = user_service.is_user_registered_and_active(db, user_id)
    #         is_admin = user_service.is_admin(db, user_id)
    #         if is_active:
    #             response_message = const.MSG_WELCOME.format(name=first_name or username)
    #             # Показываем соответствующую Reply клавиатуру
    #             if is_admin:
    #                 reply_markup = keyboards.create_admin_reply_keyboard() # Админская клавиатура
    #                 is_active_admin = True
    #             else:
    #                 reply_markup = keyboards.create_user_reply_keyboard() # Обычная клавиатура
    #         else:
    #             response_message = const.MSG_ERROR_ACCOUNT_INACTIVE
    #     elif is_new is False and user_info is None:
    #          response_message = const.MSG_ERROR_REGISTRATION_FAILED
    #     elif is_new is True:
    #          response_message = const.MSG_REGISTRATION_PENDING
    #
    #     # Отправляем сообщение
    #     bot.send_message(chat_id, response_message, reply_markup=reply_markup)
    #
    #     # Если пользователь - активный админ, можно дополнительно отправить /adminhelp
    #     if is_active_admin:
    #          bot.send_message(chat_id, "Как администратору, вам доступны доп. команды. Используйте /adminhelp для их просмотра.")


    @bot.message_handler(commands=['help'])
    def help_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"Пользователь {user_id} запросил /help")

        # Проверка статуса
        if not user_service.is_user_registered_and_active(db, user_id):
             bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
             return

        # Используем USER_HELP_TEXT, определенный выше
        help_text_to_send = USER_HELP_TEXT
        is_admin = user_service.is_admin(db, user_id)

        # Добавляем информацию об админских командах, если это админ
        if is_admin:
             admin_help_preview = "\n👑 *Доступны команды администратора* (/adminhelp)"
             help_text_to_send += admin_help_preview
             # Показываем админскую клавиатуру
             reply_markup = keyboards.create_admin_reply_keyboard()
        else:
             # Показываем обычную клавиатуру
             reply_markup = keyboards.create_user_reply_keyboard()

        bot.reply_to(message, help_text_to_send, parse_mode="Markdown", reply_markup=reply_markup)

    # --- Команды Бронирования ---
    @bot.message_handler(commands=['booking']) # Убедитесь, что команда совпадает с кнопкой и меню
    def booking_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"Пользователь {user_id} инициировал бронирование (/booking)")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            logger.warning(f"Неавторизованный пользователь {user_id} попытался использовать /booking.")
            return

        try:
            categories = equipment_service.get_all_categories(db)
            if not categories:
                bot.reply_to(message, "В системе пока нет категорий оборудования для бронирования.")
                return
            # Используем Inline клавиатуру для выбора категории
            markup = keyboards.generate_equipment_category_keyboard(categories, const.CB_BOOK_SELECT_CATEGORY)
            bot.send_message(message.chat.id, "Шаг 1: Выберите категорию оборудования:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка при получении категорий для бронирования /booking (user {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Просмотр Бронирований ---
    @bot.message_handler(commands=['mybookings'])
    def my_bookings_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"Пользователь {user_id} запросил /mybookings")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return

        try:
            # Получаем текст активных броней пользователя
            bookings_text = booking_service.get_user_active_bookings_text(db, user_id)
            # Отправляем как есть, Telegram сам разобьет, если нужно, или используем пагинацию
            bot.send_message(message.chat.id, bookings_text, parse_mode="Markdown") # Используем Markdown, если сервис его возвращает
        except Exception as e:
            logger.error(f"Ошибка при получении /mybookings для user {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # @bot.message_handler(commands=['allbookings']) # Эта команда больше для админов (/all)
    # def all_bookings_handler(message: Message):
    #     # ... (код закомментирован, т.к. есть /all у админа) ...

    @bot.message_handler(commands=['datebookings'])
    def datebookings_start_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"Пользователь {user_id} запросил /datebookings")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return

        try:
             # Генерируем Inline клавиатуру для выбора даты
             markup = keyboards.generate_date_keyboard(
                 equipment_id=0, # ID оборудования не важен для этого колбэка
                 callback_prefix=const.CB_DATEB_SELECT_DATE,
                 single_column=True # Даты в один столбец
             )
             bot.send_message(message.chat.id, "Выберите дату для просмотра бронирований:", reply_markup=markup)
        except Exception as e:
             logger.error(f"Ошибка при генерации клавиатуры дат для /datebookings (user {user_id}): {e}", exc_info=True)
             bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['workspacebookings'])
    def workspacebookings_start_handler(message: Message):
        user_id = message.from_user.id
        logger.debug(f"Пользователь {user_id} запросил /workspacebookings")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return

        try:
            categories = equipment_service.get_all_categories(db)
            if not categories:
                bot.reply_to(message, "В системе пока нет категорий оборудования.")
                return
            # Используем Inline клавиатуру для выбора категории
            markup = keyboards.generate_equipment_category_keyboard(categories, const.CB_WSB_SELECT_CATEGORY)
            bot.send_message(message.chat.id, "Выберите категорию оборудования для просмотра бронирований:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка при получении категорий для /workspacebookings (user {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)


    # --- Управление Бронированием (Отмена, Завершение, Продление) ---
    @bot.message_handler(commands=['cancel'])
    def cancel_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"Пользователь {user_id} инициировал отмену бронирования (/cancel)")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return

        try:
            # Получаем брони, которые можно отменить (будущие или начавшиеся недавно)
            # Функция должна возвращать список словарей
            user_bookings = booking_service.get_user_bookings_for_cancel(db, user_id)
            if not user_bookings:
                bot.reply_to(message, "У вас нет будущих бронирований, которые можно отменить.")
                return

            # Генерируем Inline клавиатуру для выбора
            markup = keyboards.generate_user_bookings_keyboard(user_bookings, const.CB_CANCEL_SELECT_BOOKING)
            bot.send_message(message.chat.id, "Выберите бронирование для отмены:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка при получении броней для /cancel (user {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)


    @bot.message_handler(commands=['finish'])
    def finish_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"Пользователь {user_id} инициировал завершение работы (/finish)")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return

        try:
            # Получаем текущие активные брони пользователя
            # Функция должна возвращать список словарей
            current_bookings = booking_service.get_user_current_bookings(db, user_id)
            if not current_bookings:
                bot.reply_to(message, "У вас нет активных бронирований в данный момент, которые можно завершить.")
                return

            # Если только одна активная бронь, завершаем ее сразу
            if len(current_bookings) == 1:
                 booking_id_to_finish = current_bookings[0].get('id')
                 if booking_id_to_finish:
                     logger.debug(f"User {user_id} имеет одну активную бронь {booking_id_to_finish}, завершаем ее.")
                     # Сервис finish_booking должен сам чистить уведомления и таймеры
                     success, msg = booking_service.finish_booking(db, booking_id_to_finish, user_id)
                     bot.reply_to(message, msg)
                 else:
                      logger.error(f"Не найден ID в единственной активной брони для user {user_id} при /finish")
                      bot.reply_to(message, const.MSG_ERROR_GENERAL)
                 return

            # Если несколько активных броней, предлагаем выбор
            logger.debug(f"User {user_id} имеет несколько активных броней, предлагаем выбор для /finish.")
            markup = keyboards.generate_user_bookings_keyboard(current_bookings, const.CB_FINISH_SELECT_BOOKING)
            bot.send_message(message.chat.id, "У вас несколько активных бронирований. Выберите, какое завершить:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка при получении броней для завершения /finish (user {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)


    @bot.message_handler(commands=['extend'])
    def extend_start_handler(message: Message):
        user_id = message.from_user.id
        logger.info(f"Пользователь {user_id} инициировал продление (/extend)")

        if not user_service.is_user_registered_and_active(db, user_id):
            bot.reply_to(message, const.MSG_ERROR_NOT_REGISTERED)
            return

        try:
             # Получаем текущие активные брони пользователя
             current_bookings = booking_service.get_user_current_bookings(db, user_id)
             if not current_bookings:
                  bot.reply_to(message, "У вас нет активных бронирований в данный момент, которые можно продлить.")
                  return

             # Если только одна активная бронь
             if len(current_bookings) == 1:
                  booking_id_to_extend = current_bookings[0].get('id')
                  if booking_id_to_extend:
                      logger.debug(f"User {user_id} имеет одну активную бронь {booking_id_to_extend}, предлагаем продление.")
                      # Генерируем Inline клавиатуру с вариантами времени продления
                      # Эта функция должна сама рассчитать max_duration
                      markup = keyboards.generate_extend_time_keyboard(booking_id_to_extend) # <-- Передаем только ID
                      bot.send_message(message.chat.id, "На сколько продлить бронирование:", reply_markup=markup)
                  else:
                       logger.error(f"Не найден ID в единственной активной брони для user {user_id} при /продлить")
                       bot.reply_to(message, const.MSG_ERROR_GENERAL)
                  return

             # Если несколько активных броней, предлагаем выбор
             logger.debug(f"User {user_id} имеет несколько активных броней, предлагаем выбор для /продлить.")
             markup = keyboards.generate_user_bookings_keyboard(current_bookings, const.CB_EXTEND_SELECT_BOOKING)
             bot.send_message(message.chat.id, "У вас несколько активных бронирований. Выберите, какое продлить:", reply_markup=markup)
        except Exception as e:
             logger.error(f"Ошибка при получении броней для продления /продлить (user {user_id}): {e}", exc_info=True)
             bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Обработчик для текста, не являющегося командой ---
    @bot.message_handler(func=lambda message: not message.text.startswith('/'))
    def handle_text(message: Message):
        # Игнорируем обычный текст или отвечаем вежливо
        # logger.debug(f"Получен текст '{message.text}' от user {message.from_user.id}")
        # bot.reply_to(message, "Пожалуйста, используйте команды из меню или кнопки.")
        pass # Игнорируем

    logger.info("Обработчики команд пользователя зарегистрированы.")