# handlers/registration.py (ЕДИНСТВЕННЫЙ ОБРАБОТЧИК /start)
import telebot
from telebot import types
from telebot.types import Message
from database import Database
from logger import logger
from services import user_service
from utils import keyboards
import constants as const
from typing import Optional, Dict, Any # Добавили

# Передаем только bot и db
def register_reg_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики, связанные с регистрацией и командой /start."""

    @bot.message_handler(commands=['start'])
    def handle_start(message: Message):
        user_id = message.from_user.id
        username = message.from_user.username or ""
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        chat_id = message.chat.id

        logger.info(f"Получена команда /start от user_id: {user_id} (username: {username})")

        try:
            # Используем единую функцию для определения статуса
            is_pending, user_info = user_service.find_or_register_user(db, user_id, username, first_name, last_name)

            if not is_pending and user_info: # Пользователь найден в users
                # Проверяем активность
                if user_info.get('is_blocked'):
                    logger.warning(f"Заблокированный пользователь {user_id} попытался использовать /start.")
                    bot.reply_to(message, const.MSG_ERROR_ACCOUNT_INACTIVE, reply_markup=types.ReplyKeyboardRemove())
                else:
                    # Активный пользователь (админ или обычный)
                    fi_from_db = user_info.get('fi')
                    logger.debug(f"Обработка /start для user {user_id}. fi из БД: '{fi_from_db}'. first_name из TG: '{first_name}'")
                    user_name = fi_from_db or first_name or username or f"User {user_id}" # Приоритет у fi
                    logger.debug(f"Итоговое user_name для приветствия: '{user_name}'")
                    is_admin = user_info.get('is_admin', False)

                    logger.info(f"Пользователь {user_id} ({user_name}) уже зарегистрирован и активен (is_admin: {is_admin}).")
                    reply_markup = keyboards.create_admin_reply_keyboard() if is_admin else keyboards.create_user_reply_keyboard()
                    welcome_msg = const.MSG_WELCOME.format(name=user_name)
                    bot.reply_to(message, welcome_msg, reply_markup=reply_markup)
                    if is_admin:
                         bot.send_message(chat_id, "Как администратору, вам доступны доп. команды (/adminhelp).")

            elif is_pending: # Пользователь либо в temp, либо его нет нигде
                if user_service.find_temp_user(db, user_id): # Проверяем, ждет ли уже
                    logger.info(f"Пользователь {user_id} уже ожидает подтверждения регистрации.")
                    bot.reply_to(message, const.MSG_REGISTRATION_PENDING, reply_markup=types.ReplyKeyboardRemove())
                else: # Точно новый, предлагаем ввести имя
                    logger.info(f"Пользователю {user_id} предложено ввести имя для регистрации.")
                    msg_text = ("Добро пожаловать! 👋\n"
                                "Для использования бота, пожалуйста, представьтесь.\n"
                                "**Отправьте своё Имя и Фамилию в одном сообщении** (например: Иван Петров).")
                    sent_msg = bot.reply_to(message, msg_text, reply_markup=types.ReplyKeyboardRemove(), parse_mode="Markdown")
                    bot.register_next_step_handler(sent_msg, process_name_input, db, bot) # Передаем только db и bot

            else: # find_or_register_user вернул (False, None) - ошибка
                 logger.error(f"Ошибка при поиске/регистрации пользователя {user_id} в find_or_register_user.")
                 bot.reply_to(message, const.MSG_ERROR_GENERAL)


        except Exception as e:
            logger.error(f"Ошибка в обработчике /start (registration) для пользователя {user_id}: {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)


    # --- Внутренние функции и обработчики шагов ---
    # Убран параметр admin_id
    def process_name_input(message: Message, db_conn: Database, current_bot: telebot.TeleBot):
        """Обрабатывает введенное имя и фамилию."""
        user_id = message.from_user.id
        user_input = message.text.strip()
        logger.debug(f"Получено имя '{user_input}' от пользователя {user_id} для регистрации.")

        reply_markup = types.ReplyKeyboardRemove() # Убираем клавиатуру после ввода

        try:
            parts = user_input.split(maxsplit=1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                first_name = parts[0].strip().capitalize()
                last_name = parts[1].strip().capitalize()
                full_name = f"{first_name} {last_name}"

                if user_service.register_temporary_user(db_conn, user_id, first_name, last_name, full_name):
                    bot.reply_to(message, const.MSG_REGISTRATION_SENT, reply_markup=reply_markup)
                    logger.info(f"Заявка на регистрацию для {user_id} ({full_name}) отправлена администраторам.")
                    notify_admins_for_confirmation(current_bot, db_conn, user_id, first_name, last_name, full_name)
                else:
                    bot.reply_to(message, const.MSG_ERROR_REGISTRATION_FAILED, reply_markup=reply_markup)
            else:
                raise ValueError("Некорректный формат ввода имени и фамилии.")

        except ValueError:
            logger.warning(f"Пользователь {user_id} ввел некорректное имя/фамилию: '{user_input}'")
            msg_text = "❌ Пожалуйста, введите **Имя и Фамилию** через пробел (например: Иван Петров).\nПопробуйте еще раз:"
            sent_msg = bot.reply_to(message, msg_text, parse_mode="Markdown", reply_markup=reply_markup)
            current_bot.register_next_step_handler(sent_msg, process_name_input, db_conn, current_bot)
        except Exception as e:
             logger.error(f"Неожиданная ошибка при обработке имени пользователя {user_id}: {e}", exc_info=True)
             bot.reply_to(message, const.MSG_ERROR_GENERAL, reply_markup=reply_markup)


    def notify_admins_for_confirmation(
        bot_instance: telebot.TeleBot, db_conn: Database, temp_user_id: int,
        first_name: str, last_name: str, full_name: str
    ):
        """Отправляет уведомление всем администраторам."""
        try:
            admin_ids = user_service.get_admin_ids(db_conn)
            if not admin_ids: logger.error("Нет админов для уведомления!"); return

            markup = keyboards.generate_registration_confirmation_keyboard(temp_user_id)
            text = (f"🔔 Новая заявка на регистрацию:\n"
                    f"User ID: `{temp_user_id}`\n"
                    f"Имя: {first_name}\n"
                    f"Фамилия: {last_name}\n"
                    f"ФИ: {full_name}\n\n"
                    f"Подтвердить регистрацию?")

            sent_count = 0
            for admin_id in admin_ids:
                try:
                    bot_instance.send_message(admin_id, text, reply_markup=markup, parse_mode="Markdown")
                    sent_count += 1
                except Exception as e_send: logger.error(f"Не отправить уведомление админу {admin_id} о {temp_user_id}: {e_send}")
            if sent_count > 0: logger.info(f"Уведомление о {temp_user_id} ({full_name}) отправлено {sent_count} админам.")
            else: logger.error(f"Не отправить уведомление о {temp_user_id} ни одному админу.")
        except Exception as e: logger.error(f"Ошибка уведомления админов о {temp_user_id}: {e}", exc_info=True)

    logger.info("Обработчики регистрации (/start) зарегистрированы.")