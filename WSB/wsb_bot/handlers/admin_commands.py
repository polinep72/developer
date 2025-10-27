# handlers/admin_commands.py
import telebot
from telebot.types import Message, ReplyKeyboardRemove # Добавили ReplyKeyboardRemove
from database import Database
from logger import logger
# import config # config не нужен напрямую
from services import (
    user_service, booking_service, equipment_service,
    admin_service, notification_service
)
from utils import keyboards
import constants as const

# Импортируем компоненты из bot_app
from bot_app import bot as bot_instance, scheduler, active_timers, scheduled_jobs_registry

def register_admin_command_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики команд только для администраторов."""

    # Внутренняя функция для проверки прав админа
    def _is_admin_user(user_id: int) -> bool:
        try:
            # Убедитесь, что user_service.is_admin принимает db и user_id
            # и что 'db' здесь - это тот же экземпляр, что и в admin_cancel_start
            is_admin_flag = user_service.is_user_admin(db, user_id)  # Предположим, функция называется is_user_admin
            if not is_admin_flag:
                logger.warning(f"Пользователь {user_id} попытался выполнить админ-команду без прав.")
            return is_admin_flag
        except Exception as e:
            logger.error(f"Ошибка при проверке прав админа для user_id {user_id}: {e}", exc_info=True)
            return False

    # --- Обработчики команд ---

    @bot.message_handler(commands=[const.CMD_ADMIN_HELP])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_ADMIN_HELP)
    def admin_help_handler(message: Message):
        """Обработчик команды /adminhelp для администраторов."""
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return

        logger.debug(f"Admin {user_id} запросил /adminhelp")

        # Используем текст помощи из констант
        help_text = const.MSG_ADMIN_HELP

        # Показываем админскую Reply клавиатуру для удобства
        reply_markup = keyboards.create_admin_reply_keyboard()
        bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=reply_markup)


    # --- Управление Оборудованием ---
    @bot.message_handler(commands=[const.CMD_MANAGE_EQUIPMENT])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_MANAGE_EQUIPMENT)
    def view_equipment_handler(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.debug(f"Админ {user_id} запросил /view_equipment")
        try:
            # Сервис должен возвращать список словарей List[Dict[str, Any]]
            all_equipment = equipment_service.get_all_equipment(db)
            if not all_equipment:
                bot.reply_to(message, "В базе данных нет ни одного оборудования.")
                return
            # Клавиатура ожидает список словарей
            markup = keyboards.generate_equipment_list_with_delete_keyboard(all_equipment)
            bot.send_message(message.chat.id, "Текущее оборудование (нажмите 🗑️ для удаления):", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /view_equipment (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_ADD_EQUIPMENT])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_ADD_EQUIPMENT)
    def add_equipment_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.info(f"Админ {user_id} инициировал добавление оборудования (/add_equipment)")
        try:
            # Сервис возвращает список словарей List[Dict[str, Any]]
            categories = equipment_service.get_all_categories(db)
            # Формируем текст списка категорий
            categories_text = "\n\n*Существующие категории:*\n" + \
                            "\n".join([f"- {cat.get('name_cat', 'Без имени')} (ID: {cat.get('id')})" for cat in categories]) \
                            if categories else "\n\n_(Категорий пока нет)_"

            msg_text = f"Введите название **новой или существующей категории** для оборудования (или /cancel для отмены):{categories_text}"

            # Убираем ReplyKeyboard на время диалога
            sent_msg = bot.reply_to(message, msg_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
            # Передаем bot и db в следующий шаг
            bot.register_next_step_handler(sent_msg, process_category_input, bot, db)
        except Exception as e:
            logger.error(f"Ошибка начала /add_equipment (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Шаги для /add_equipment ---
    def process_category_input(message: Message, bot_i: telebot.TeleBot, db_i: Database):
        admin_id = message.from_user.id
        # Показываем админскую клавиатуру при отмене
        admin_reply_markup = keyboards.create_admin_reply_keyboard()

        if message.text and message.text.startswith('/'):
            if message.text.lower() == '/cancel':
                bot_i.reply_to(message, "Добавление оборудования отменено.", reply_markup=admin_reply_markup)
                logger.info(f"Админ {admin_id} отменил добавление оборудования на шаге категории.")
            else:
                # Игнорируем другие команды во время цепочки
                bot_i.reply_to(message, "Пожалуйста, завершите добавление оборудования или используйте /cancel.", reply_markup=ReplyKeyboardRemove())
                # Повторно регистрируем тот же шаг, ожидая корректный ввод
                bot_i.register_next_step_handler(message, process_category_input, bot_i, db_i)
            return

        category_name = message.text.strip()
        logger.debug(f"Админ {admin_id} ввел категорию: {category_name}")

        if not category_name:
            msg = bot_i.reply_to(message, "Название категории не может быть пустым. Повторите ввод или /cancel:")
            bot_i.register_next_step_handler(msg, process_category_input, bot_i, db_i)
            return

        try:
            category_id = equipment_service.find_or_create_category(db_i, category_name)
            if category_id is None:
                # Используем константу
                bot_i.reply_to(message, const.MSG_CAT_CREATE_FAIL.replace('{category_name}', category_name), reply_markup=admin_reply_markup)
                logger.warning(f"Не удалось найти/создать категорию '{category_name}' для админа {admin_id}.")
                return # Прерываем цепочку при ошибке

            msg_text = f"Категория: '{category_name}' (ID: {category_id}).\nТеперь введите **название** нового оборудования (или /cancel):"
            sent_msg = bot_i.reply_to(message, msg_text, parse_mode="Markdown")
            bot_i.register_next_step_handler(sent_msg, process_equipment_name_input, bot_i, db_i, category_id, category_name)
        except Exception as e:
            logger.error(f"Ошибка обработки категории '{category_name}' (админ {admin_id}): {e}", exc_info=True)
            bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Попробуйте начать /add_equipment заново.", reply_markup=admin_reply_markup)

    def process_equipment_name_input(message: Message, bot_i: telebot.TeleBot, db_i: Database, category_id: int, category_name: str):
        admin_id = message.from_user.id
        admin_reply_markup = keyboards.create_admin_reply_keyboard()

        if message.text and message.text.startswith('/'):
            if message.text.lower() == '/cancel':
                bot_i.reply_to(message, "Добавление оборудования отменено.", reply_markup=admin_reply_markup)
                logger.info(f"Админ {admin_id} отменил добавление оборудования на шаге имени.")
            else:
                bot_i.reply_to(message, "Пожалуйста, завершите добавление оборудования или используйте /cancel.", reply_markup=ReplyKeyboardRemove())
                bot_i.register_next_step_handler(message, process_equipment_name_input, bot_i, db_i, category_id, category_name)
            return

        equipment_name = message.text.strip()
        logger.debug(f"Админ {admin_id} ввел название оборудования: {equipment_name}")

        if not equipment_name:
            msg = bot_i.reply_to(message, "Название оборудования не может быть пустым. Повторите ввод или /cancel:")
            bot_i.register_next_step_handler(msg, process_equipment_name_input, bot_i, db_i, category_id, category_name)
            return

        try:
            # Проверка на дубликат
            if equipment_service.check_equipment_exists(db_i, category_id, equipment_name):
                # Используем константу
                msg_text = const.MSG_EQUIP_ADD_FAIL_EXISTS.replace('{equipment_name}', f"'{equipment_name}'").replace('{category_name}', f"'{category_name}'")
                sent_msg = bot_i.reply_to(message, msg_text + " Введите другое название или /cancel:")
                bot_i.register_next_step_handler(sent_msg, process_equipment_name_input, bot_i, db_i, category_id, category_name)
                return
        except Exception as e:
            logger.error(f"Ошибка при проверке существования оборудования '{equipment_name}' админом {admin_id}: {e}", exc_info=True)
            bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при проверке дубликата.", reply_markup=admin_reply_markup)
            return # Прерываем цепочку

        # Переход к вводу описания
        msg_text = f"Название: '{equipment_name}'.\nВведите **описание** оборудования (можно оставить пустым, просто нажмите Enter, или /cancel):"
        sent_msg = bot_i.reply_to(message, msg_text, parse_mode="Markdown")
        bot_i.register_next_step_handler(sent_msg, process_equipment_note_input, bot_i, db_i, category_id, category_name, equipment_name)

    def process_equipment_note_input(message: Message, bot_i: telebot.TeleBot, db_i: Database, category_id: int, category_name: str, equipment_name: str):
        admin_id = message.from_user.id
        admin_reply_markup = keyboards.create_admin_reply_keyboard()

        if message.text and message.text.startswith('/'):
            if message.text.lower() == '/cancel':
                bot_i.reply_to(message, "Добавление оборудования отменено.", reply_markup=admin_reply_markup)
                logger.info(f"Админ {admin_id} отменил добавление оборудования на шаге описания.")
            else:
                bot_i.reply_to(message, "Пожалуйста, завершите добавление оборудования или используйте /cancel.", reply_markup=ReplyKeyboardRemove())
                bot_i.register_next_step_handler(message, process_equipment_note_input, bot_i, db_i, category_id, category_name, equipment_name)
            return

        note = message.text.strip() if message.text else ""
        logger.debug(f"Админ {admin_id} ввел описание: '{note}' для оборудования '{equipment_name}' в категории '{category_name}'")

        try:
            success = equipment_service.add_equipment(db_i, category_id, equipment_name, note)
            if success:  # `success` должно быть True, судя по вашим предыдущим логам
                # Используем правильное имя константы и правильные плейсхолдеры
                # Константа: MSG_ADMIN_EQUIP_ADD_SUCCESS = "✅ Оборудование '{name_equip}' успешно добавлено в категорию '{name_cat}'."
                msg_text = const.MSG_ADMIN_EQUIP_ADD_SUCCESS.format(
                    name_equip=equipment_name,  # Передаем значение для {name_equip}
                    name_cat=category_name  # Передаем значение для {name_cat}
                )
                # Добавляем parse_mode для корректного отображения эмодзи и форматирования
                bot_i.reply_to(message, msg_text, reply_markup=admin_reply_markup, parse_mode="HTML")

                # Обновленное логгирование без new_equipment_id
                logger.info(
                    f"Админ {admin_id} добавил оборудование '{equipment_name}' в категорию '{category_name}' (ID категории: {category_id}).")
            else:
                # Если используется MSG_ADMIN_EQUIP_ADD_FAIL_GENERAL, и в ней есть плейсхолдеры,
                # также используйте .format() и parse_mode
                # MSG_ADMIN_EQUIP_ADD_FAIL_GENERAL = "❌ Не удалось добавить оборудование '{name_equip}'."
                msg_text_fail = const.MSG_ADMIN_EQUIP_ADD_FAIL_GENERAL.format(name_equip=equipment_name)
                bot_i.reply_to(message, msg_text_fail + " Проверьте логи сервера.", reply_markup=admin_reply_markup,
                            parse_mode="HTML")
        except Exception as e:
            logger.error(f"Исключение при вызове add_equipment админом {admin_id}: {e}", exc_info=True)
            bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при сохранении в базу данных.", reply_markup=admin_reply_markup)

    # --- Управление Бронированиями (Админ) ---
    @bot.message_handler(commands=[const.CMD_ADMIN_CANCEL_BOOKING])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_ADMIN_CANCEL_KB)
    def admin_cancel_start(message: Message):  # <--- Убрали bot_instance и db_conn
        user_id = message.from_user.id

        if not _is_admin_user(user_id):
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)  # <--- Используем глобальный bot
            return

        logger.info(f"Админ {user_id} инициировал команду отмены брони (текст: '{message.text}')")

        try:
            # Используем глобальный db
            bookings_for_display = booking_service.get_all_active_bookings_for_admin_display(db)

            if not bookings_for_display:
                bot.reply_to(message, "Нет активных бронирований для отмены.")  # <--- Глобальный bot
                return

            response_text_parts = ["Выберите бронь для принудительной отмены:\n"]

            for booking in bookings_for_display:
                user_name = booking.get('user_name', 'N/A')
                equip_name = booking.get('equipment_name', 'N/A')
                booking_date_obj = booking.get('date')
                time_start_obj = booking.get('time_start')
                time_end_obj = booking.get('time_end')
                booking_id = booking.get('id')

                formatted_date = booking_date_obj.strftime('%d-%m-%Y') if booking_date_obj else 'N/A'
                formatted_time_start = time_start_obj.strftime('%H:%M') if time_start_obj else 'N/A'
                formatted_time_end = time_end_obj.strftime('%H:%M') if time_end_obj else 'N/A'

                response_text_parts.append(
                    f"\n👤 *Пользователь:* {user_name}\n"
                    f"💻 *Оборудование:* {equip_name}\n"
                    f"📅 *Дата:* {formatted_date}\n"
                    f"⏰ *Время:* {formatted_time_start} - {formatted_time_end}\n"
                    f"(ID: `{booking_id}`)"
                )

            full_response_text = "\n------------------------------------\n".join(response_text_parts)

            markup = keyboards.generate_admin_cancel_inline_keyboard(bookings_for_display)

            if not markup.keyboard:
                bot.reply_to(message, "Не удалось сформировать кнопки для отмены. Попробуйте позже.")
                logger.warning("generate_admin_cancel_inline_keyboard вернула пустую клавиатуру.")
                return

            bot.send_message(message.chat.id, full_response_text, reply_markup=markup,
                             parse_mode="HTML")  # <--- Глобальный bot

        except Exception as e:
            logger.error(f"Ошибка в admin_cancel_start (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)  # <--- Глобальный bot

    # --- Просмотр и Отчеты ---
    @bot.message_handler(commands=[const.CMD_ALL_BOOKINGS])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_ALL_KB)
    def all_bookings_filter_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.info(f"Админ {user_id} запросил /all для генерации отчета")
        try:
            markup = keyboards.generate_filter_options_keyboard()
            bot.send_message(message.chat.id, "Выберите критерий для фильтрации бронирований в отчете:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /all (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Рассылка ---
    @bot.message_handler(commands=[const.CMD_BROADCAST])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_BROADCAST_KB)
    def broadcast_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.info(f"Админ {user_id} инициировал /broadcast")
        sent_msg = bot.reply_to(message, "Введите текст сообщения для рассылки всем активным пользователям (или /cancel для отмены):", reply_markup=ReplyKeyboardRemove())
        # Передаем bot и db
        bot.register_next_step_handler(sent_msg, process_broadcast_text, bot, db)

    def process_broadcast_text(message: Message, bot_i: telebot.TeleBot, db_i: Database):
        admin_id = message.from_user.id
        admin_reply_markup = keyboards.create_admin_reply_keyboard()
        text = message.text

        if text and text.startswith('/'):
            if text.lower() == '/cancel':
                bot_i.reply_to(message, "Рассылка отменена.", reply_markup=admin_reply_markup)
                logger.info(f"Админ {admin_id} отменил broadcast.")
            else:
                bot_i.reply_to(message, "Пожалуйста, завершите рассылку или используйте /cancel.", reply_markup=ReplyKeyboardRemove())
                bot_i.register_next_step_handler(message, process_broadcast_text, bot_i, db_i)
            return

        if not text or len(text.strip()) < 5:
            msg = bot_i.reply_to(message, "Сообщение слишком короткое (требуется минимум 5 символов). Повторите ввод или /cancel:")
            bot_i.register_next_step_handler(msg, process_broadcast_text, bot_i, db_i)
            return

        logger.info(f"Админ {admin_id} подтвердил broadcast: '{text[:50]}...'")
        try:
            # bot_instance импортирован из bot_app
            sent_count = admin_service.broadcast_message_to_users(db_i, bot_instance, text, admin_id)
            bot_i.reply_to(message, f"✅ Рассылка запущена. Сообщение будет отправлено {sent_count} пользователям.", reply_markup=admin_reply_markup)
            logger.info(f"Broadcast админа {admin_id} отправлен {sent_count} пользователям.")
        except Exception as e:
            logger.error(f"Ошибка при выполнении broadcast админом {admin_id}: {e}", exc_info=True)
            bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при рассылке.", reply_markup=admin_reply_markup)

    # --- Управление Пользователями ---
    @bot.message_handler(commands=[const.CMD_USERS_LIST])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_USERS_KB)
    def view_users_handler(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.debug(f"Админ {user_id} запросил /users")
        try:
            # Сервис должен возвращать список словарей List[Dict[str, Any]]
            users = user_service.get_all_users(db, include_inactive=True)
            if not users:
                bot.reply_to(message, "В базе нет зарегистрированных пользователей.")
                return

            resp = "👥 *Зарегистрированные пользователи:*\n\n"
            for user_data in users: # Итерация по словарям
                u_id = user_data.get('users_id')
                # Используем 'fi' из таблицы users, если есть, иначе пробуем собрать
                u_name = user_data.get('fi')
                if not u_name:
                    first = user_data.get('first_name', '')
                    last = user_data.get('last_name', '')
                    u_name = f"{first} {last}".strip() or f"ID {u_id}" # Собираем или используем ID

                if u_id is None: continue

                # Получаем детали для статуса (ожидаем кортеж от сервиса)
                details = user_service.get_user_details_for_management(db, u_id)
                status = "🔴 Заблок." if details and details[1] else "🟢 Активен"
                resp += f"{status} ID: `{u_id}` | ФИ: {u_name}\n" # Используем u_name

            # Отправка сообщения (логика разбиения остается)
            if len(resp) <= const.MAX_MESSAGE_LENGTH:
                bot.send_message(message.chat.id, resp, parse_mode="Markdown")
            else:
                # ... (код для разбиения сообщения) ...
                logger.warning(f"Список пользователей /users слишком длинный ({len(resp)}), отправляем частями.")
                parts = []
                # Начинаем со второй строки, т.к. заголовок уже есть
                header = resp.splitlines()[0] + "\n" + resp.splitlines()[1] + "\n\n"
                lines = resp.splitlines()[2:]
                current_part = ""
                part_num = 1

                for line in lines:
                    if len(header) + len(current_part) + len(line) + 1 > const.MAX_MESSAGE_LENGTH:
                        # Завершаем предыдущую часть
                        parts.append(header.replace("(часть X)", f"(часть {part_num})") + current_part)
                        current_part = "" # Начинаем новую часть
                        part_num += 1
                    current_part += line + "\n"
                # Добавляем последнюю часть
                parts.append(header.replace("(часть X)", f"(часть {part_num})") + current_part)

                # Обновляем заголовок во всех частях (кроме первой, если она одна)
                final_header = header.replace("Пользователи:", f"Пользователи (часть {part_num}/{len(parts)}):") if len(parts) > 1 else header

                for i, part in enumerate(parts, 1):
                    part_header = header.replace("Пользователи:", f"Пользователи (часть {i}/{len(parts)}):") if len(parts) > 1 else header
                    # Убираем старый заголовок из части и добавляем новый
                    content = part[len(header):]
                    bot.send_message(message.chat.id, part_header + content, parse_mode="Markdown")


        except Exception as e:
            logger.error(f"Ошибка /users (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=[const.CMD_MANAGE_USER])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_MANAGE_USER_KB)
    def manage_user_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.info(f"Админ {user_id} инициировал /manage_user")
        try:
            # Сервис должен возвращать список словарей List[Dict[str, Any]]
            users = user_service.get_all_users(db, include_inactive=True)
            if not users:
                bot.reply_to(message, "Нет зарегистрированных пользователей для управления.")
                return
            # Клавиатура ожидает список словарей
            markup = keyboards.generate_user_management_keyboard(users)
            bot.send_message(message.chat.id, "Выберите пользователя для блокировки/разблокировки:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /manage_user (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Обновление планировщика ---
    @bot.message_handler(commands=[const.CMD_SCHEDULE_UPDATE])
    @bot.message_handler(func=lambda msg: msg.text == const.BTN_TEXT_SCHEDULE_KB)
    def force_schedule_update(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id): bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION); return
        logger.info(f"Админ {user_id} инициировал /schedule (принудительное обновление графика)")
        try:
            processing_msg = bot.send_message(message.chat.id, "⏳ Обновляю график уведомлений...")

            # Вызываем функцию сервиса уведомлений с компонентами из bot_app
            notification_service.schedule_all_notifications(
                db, bot_instance, scheduler, active_timers, scheduled_jobs_registry
            )

            bot.edit_message_text("✅ График уведомлений успешно обновлен.",
                                chat_id=processing_msg.chat.id,
                                message_id=processing_msg.message_id)
            logger.info("График уведомлений обновлен по команде /schedule от админа.")

        except Exception as e:
            logger.error(f"Ошибка при выполнении /schedule (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, f"❌ Произошла ошибка при обновлении графика: {e}")

    logger.info("Обработчики админ-команд успешно зарегистрированы.")