# --- START OF FILE handlers/registration.py ---

# handlers/registration.py
import telebot
from telebot import types
from telebot.types import Message
from typing import Optional, Dict, Any, List, Tuple # Добавлен List, Tuple
from database import Database
from logger import logger
from utils import keyboards
import constants as const
from services import user_service, registration_notification_service # Добавлен registration_notification_service


# Передаем только bot и db
def register_reg_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики, связанные с регистрацией и командой /start."""

    @bot.message_handler(commands=['start'])
    def handle_start(message: Message):
        """Обрабатывает команду /start."""
        user_id: int = message.from_user.id
        username: str = message.from_user.username or ""
        first_name_tg: str = message.from_user.first_name or ""
        last_name_tg: str = message.from_user.last_name or ""
        chat_id: int = message.chat.id

        logger.info(f"Получена команда /start от user_id: {user_id} (username: {username})")

        try:
            is_pending: bool = False
            user_info: Optional[Dict[str, Any]] = None
            is_pending, user_info = user_service.find_or_register_user(db, user_id, username, first_name_tg,
                                                                       last_name_tg)

            if not is_pending and user_info:
                if user_info.get('is_blocked'):
                    logger.warning(f"Заблокированный пользователь {user_id} попытался использовать /start.")
                    bot.reply_to(message, const.MSG_ERROR_ACCOUNT_INACTIVE, reply_markup=types.ReplyKeyboardRemove())
                else:
                    fi_from_db: Optional[str] = user_info.get('fi')
                    user_name: str = fi_from_db or first_name_tg or username or f"User {user_id}"
                    is_admin: bool = user_info.get('is_admin', False)
                    logger.info(
                        f"Пользователь {user_id} ({user_name}) уже зарегистрирован и активен (is_admin: {is_admin}).")
                    reply_markup = keyboards.create_admin_reply_keyboard() if is_admin else keyboards.create_user_reply_keyboard()
                    welcome_msg: str = const.MSG_WELCOME.format(name=user_name)
                    bot.reply_to(message, welcome_msg, reply_markup=reply_markup)
                    if is_admin:
                        bot.send_message(chat_id, "Как администратору, вам доступны доп. команды (/adminhelp).")

            elif is_pending:
                temp_user_exists: bool = False
                try:
                    temp_user_exists = bool(user_service.find_temp_user(db, user_id))
                except Exception as e_find_temp:
                    logger.error(f"Ошибка проверки temp_user для {user_id} в /start: {e_find_temp}",
                                 exc_info=True)  # Добавлено exc_info

                if temp_user_exists:
                    logger.info(f"Пользователь {user_id} уже ожидает подтверждения регистрации.")
                    bot.reply_to(message, const.MSG_REGISTRATION_PENDING, reply_markup=types.ReplyKeyboardRemove())
                else:
                    logger.info(f"Пользователю {user_id} предложено ввести ФИО для регистрации.")
                    msg_text: str = ("Добро пожаловать! 👋\n"
                                     "Для использования бота, пожалуйста, представьтесь.\n"
                                     "**Отправьте свою Фамилию, Имя и Отчество в одном сообщении** (через пробел, например: Петров Иван Сидорович).")
                    sent_msg: Optional[Message] = None
                    try:
                        # --- Блок try для отправки и регистрации ---
                        sent_msg = bot.reply_to(message, msg_text, reply_markup=types.ReplyKeyboardRemove(),
                                                parse_mode="Markdown")
                        if sent_msg:
                            logger.debug(
                                f"Сообщение с запросом ФИО отправлено user {user_id}, msg_id={sent_msg.message_id}")
                            bot.register_next_step_handler(sent_msg, process_fio_input, db, bot)
                            logger.debug(
                                f"register_next_step_handler для process_fio_input зарегистрирован для user {user_id}")
                        else:
                            # Если reply_to не вернул сообщение
                            logger.error(
                                f"Не удалось отправить сообщение для запроса ФИО пользователю {user_id} (reply_to вернул None)")
                            bot.reply_to(message, const.MSG_ERROR_GENERAL)  # Сообщаем об ошибке
                        # --- Конец блока try ---
                    except Exception as e_reg_step:
                        # Ловим ошибку конкретно на этапе запроса ФИО
                        logger.error(
                            f"Ошибка при отправке запроса ФИО или регистрации шага для user {user_id}: {e_reg_step}",
                            exc_info=True)
                        bot.reply_to(message, const.MSG_ERROR_GENERAL)

            else:  # is_pending is False and user_info is None
                logger.error(
                    f"Ошибка при поиске/регистрации пользователя {user_id} в find_or_register_user (вернул False, None).")
                bot.reply_to(message, const.MSG_ERROR_GENERAL)

        except Exception as e:
            # Ловим все остальные ошибки в handle_start
            # --- УЛУЧШЕННОЕ ЛОГИРОВАНИЕ ---
            logger.error(f"Ошибка в обработчике /start (registration) для пользователя {user_id}", exc_info=True)
            # -----------------------------
            bot.reply_to(message, const.MSG_ERROR_GENERAL)


    # --- Внутренние функции и обработчики шагов ---
    def process_fio_input(message: Message, db_conn: Database, current_bot: telebot.TeleBot):
        """Обрабатывает введенное Фамилию, Имя и Отчество."""
        user_id: int = message.from_user.id
        user_input: str = ""
        if message.text:
            user_input = message.text.strip()

        logger.debug(f"Получено ФИО '{user_input}' от пользователя {user_id} для регистрации.")

        reply_markup: types.ReplyKeyboardRemove = types.ReplyKeyboardRemove()

        try:
            # Разделяем ввод на части по пробелам
            parts: List[str] = user_input.split()
            # Ожидаем ровно три части: Фамилия Имя Отчество
            if len(parts) == 3:
                 # Извлекаем части, удаляем лишние пробелы и капитализируем
                 last_name_input: str = parts[0].strip().capitalize()
                 first_name_input: str = parts[1].strip().capitalize()
                 middle_name_input: str = parts[2].strip().capitalize()

                 # Проверяем, что все части не пустые
                 if last_name_input and first_name_input and middle_name_input:
                    # Формируем данные для БД
                    # В first_name записываем Имя + Отчество
                    first_name_db: str = f"{first_name_input} {middle_name_input}"
                    # В last_name записываем Фамилию
                    last_name_db: str = last_name_input
                    # В fi записываем Фамилия Имя Отчество
                    full_name_db: str = f"{last_name_db} {first_name_input} {middle_name_input}"

                    # Регистрируем во временную таблицу
                    reg_success: bool = False
                    reg_success = user_service.register_temporary_user(db_conn, user_id, first_name_db, last_name_db, full_name_db)

                    if reg_success:
                        # Сообщаем пользователю и уведомляем админов
                        bot.reply_to(message, const.MSG_REGISTRATION_SENT, reply_markup=reply_markup)
                        logger.info(f"Заявка на регистрацию для {user_id} ({full_name_db}) отправлена администраторам.")
                        # Уведомляем админов, передавая все три части ФИО
                        notify_admins_for_confirmation(current_bot, db_conn, user_id, first_name_input, middle_name_input, last_name_input, full_name_db)
                    else:
                        # Если не удалось записать во временную таблицу
                        bot.reply_to(message, const.MSG_ERROR_REGISTRATION_FAILED, reply_markup=reply_markup)
                 else:
                      # Если какая-то часть оказалась пустой после strip()
                      raise ValueError("Фамилия, имя или отчество не могут быть пустыми.")
            else:
                # Если введено не три слова
                raise ValueError("Некорректный формат ввода ФИО (требуется 3 слова).")

        except ValueError as ve:
            # Ошибка формата ввода
            logger.warning(f"Пользователь {user_id} ввел некорректное ФИО: '{user_input}'. Ошибка: {ve}")
            # --- ИЗМЕНЕНИЕ: Текст ошибки формата ---
            msg_text: str = "❌ Пожалуйста, введите **Фамилию, Имя и Отчество** через пробел (например: Петров Иван Сидорович).\nПопробуйте еще раз:"
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
            sent_msg: Optional[Message] = None
            sent_msg = bot.reply_to(message, msg_text, parse_mode="Markdown", reply_markup=reply_markup)
            # Повторно регистрируем обработчик для следующего сообщения
            if sent_msg:
                current_bot.register_next_step_handler(sent_msg, process_fio_input, db_conn, current_bot)
            else:
                 logger.error(f"Не удалось отправить сообщение для повторного ввода ФИО пользователю {user_id}")
        except Exception as e:
             # Другие непредвиденные ошибки
             logger.error(f"Неожиданная ошибка при обработке ФИО пользователя {user_id}: {e}", exc_info=True)
             bot.reply_to(message, const.MSG_ERROR_GENERAL, reply_markup=reply_markup)

    # --- ИЗМЕНЕНИЕ: Уведомление админов ---
    def notify_admins_for_confirmation(
            bot_instance: telebot.TeleBot, db_conn: Database, temp_user_id: int,
            first_name_in: str, middle_name_in: str, last_name_in: str,  # Принимаем три части
            full_name_db: str  # Принимаем полное ФИО для логов
    ):
        """Отправляет уведомление всем администраторам о новой заявке и сохраняет message_id."""  # Изменен docstring
        try:
            admin_ids: List[int] = user_service.get_admin_ids(db_conn)
            if not admin_ids:
                logger.error("Нет админов для уведомления о новой регистрации!")
                return

            markup: types.InlineKeyboardMarkup = keyboards.generate_registration_confirmation_keyboard(temp_user_id)
            text: str = (f"🔔 Новая заявка на регистрацию:\n"
                         f"User ID: `{temp_user_id}`\n"
                         f"Фамилия: {last_name_in}\n"
                         f"Имя: {first_name_in}\n"
                         f"Отчество: {middle_name_in}\n\n"
                         f"Подтвердить регистрацию?")

            sent_count: int = 0
            for admin_id in admin_ids:
                try:
                    # Отправляем сообщение
                    sent_message: Optional[Message] = None
                    sent_message = bot_instance.send_message(admin_id, text, reply_markup=markup, parse_mode="Markdown")
                    sent_count += 1
                    # --- ИЗМЕНЕНИЕ: Сохранение message_id через новый сервис ---
                    if sent_message:
                        # Вызываем функцию из НОВОГО сервиса
                        registration_notification_service.add_admin_reg_notification(
                            db=db_conn,
                            temp_user_id=temp_user_id,
                            admin_id=admin_id,
                            chat_id=sent_message.chat.id,
                            message_id=sent_message.message_id
                        )
                    else:
                        logger.error(
                            f"Не удалось получить sent_message для админа {admin_id} при уведомлении о {temp_user_id}")
                    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                except Exception as e_send:
                    logger.error(
                        f"Не удалось отправить уведомление админу {admin_id} о регистрации {temp_user_id}: {e_send}")
            if sent_count > 0:
                logger.info(
                    f"Уведомление о регистрации {temp_user_id} ({full_name_db}) отправлено {sent_count} админам.")
            else:
                logger.error(f"Не удалось отправить уведомление о регистрации {temp_user_id} ни одному админу.")
        except Exception as e:
            logger.error(f"Общая ошибка при уведомлении админов о регистрации {temp_user_id}: {e}", exc_info=True)

    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    logger.info("Обработчики регистрации (/start) зарегистрированы.")

# --- END OF FILE handlers/registration.py ---