# --- START OF FILE admin_commands.py ---

# handlers/admin_commands.py
import telebot
from telebot.types import Message, ReplyKeyboardRemove, InlineKeyboardMarkup
from database import Database
from logger import logger
from services import (
    user_service, booking_service, equipment_service,
    admin_service, notification_service
)
from utils import keyboards
import constants as const
from typing import Dict, Any

# Импортируем компоненты из bot_app
from bot_app import bot as bot_instance, scheduler, active_timers, scheduled_jobs_registry

# Импортируем состояния и функцию очистки из нового модуля states.py
from states import admin_process_states, clear_admin_state

def register_admin_command_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики команд только для администраторов."""

    # Внутренняя функция для проверки прав админа
    def _is_admin_user(user_id: int) -> bool:
        is_admin = False # Значение по умолчанию
        try:
            is_admin = user_service.is_admin(db, user_id)
            # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
            logger.debug(f"Проверка _is_admin_user для {user_id}: результат={is_admin}")
            # -----------------------------
            if not is_admin:
                logger.warning(f"Пользователь {user_id} попытался выполнить админ-команду без прав.")
        except Exception as e:
            logger.error(f"Ошибка при проверке прав админа для user_id {user_id}: {e}", exc_info=True)
            is_admin = False # В случае ошибки считаем, что прав нет
        finally:
            return is_admin # Возвращаем результат проверки

    # --- Обработчики команд ---

    @bot.message_handler(commands=['adminhelp'])
    def admin_help_handler(message: Message):
        """Обработчик команды /adminhelp для администраторов."""
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return

        logger.debug(f"Admin {user_id} запросил /adminhelp")

        # Используем текст помощи из констант
        help_text = const.MSG_ADMIN_HELP

        # Показываем админскую Reply клавиатуру для удобства
        reply_markup = keyboards.create_admin_reply_keyboard()
        try:
            bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e_reply:
             logger.error(f"Ошибка отправки /adminhelp админу {user_id}: {e_reply}")


    # --- Управление Оборудованием ---
    @bot.message_handler(commands=['view_equipment'])
    def view_equipment_handler(message: Message):
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return

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

    @bot.message_handler(commands=['add_equipment'])
    def add_equipment_start(message: Message):
        """Начинает процесс добавления нового оборудования."""
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return

        # Очищаем предыдущее состояние админа на всякий случай
        # Используем импортированную функцию
        clear_admin_state(user_id)
        logger.info(f"Админ {user_id} инициировал добавление оборудования (/add_equipment)")

        try:
            # Получаем список существующих категорий
            categories = equipment_service.get_all_categories(db)

            # Генерируем inline клавиатуру с категориями и опциями
            markup = keyboards.generate_add_equipment_category_keyboard(categories)

            msg_text = "Выберите существующую категорию для нового оборудования или добавьте новую:"
            # Отправляем сообщение с inline клавиатурой
            bot.send_message(message.chat.id, msg_text, reply_markup=markup)

        except Exception as e:
            logger.error(f"Ошибка начала /add_equipment (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Не удалось начать процесс добавления.")
            # Используем импортированную функцию
            clear_admin_state(user_id) # Очищаем состояние при ошибке старта

    # --- Обработчик текстовых сообщений для шагов добавления оборудования ---
    @bot.message_handler(
        # Используем импортированный словарь состояний
        func=lambda message: _is_admin_user(message.from_user.id) and admin_process_states.get(message.from_user.id) is not None,
        content_types=['text']
    )
    def handle_admin_add_equipment_steps(message: Message):
        """Обрабатывает текстовый ввод админа на разных шагах добавления оборудования."""
        admin_id = message.from_user.id
        # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
        logger.debug(f"Вошли в handle_admin_add_equipment_steps для admin {admin_id}. Текст: '{message.text}'")
        # -----------------------------
        # Используем импортированный словарь состояний
        state = admin_process_states.get(admin_id)
        admin_reply_markup = keyboards.create_admin_reply_keyboard() # Клавиатура для завершения/отмены

        # Проверка состояния (на всякий случай)
        if not state:
             logger.warning(f"Получено сообщение от админа {admin_id}, но состояние процесса не найдено в handle_admin_add_equipment_steps.")
             # Не отвечаем, чтобы не мешать другим хендлерам
             return

        # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
        logger.debug(f"Проверка состояния перед обработкой шага для admin {admin_id}. Состояние: {state}")
        current_step = state.get('step')
        logger.debug(f"Извлеченный шаг: {current_step}")
        # -----------------------------

        # Обработка команды /cancel внутри процесса
        if message.text:
            if message.text.lower() == '/cancel':
                # Используем импортированную функцию
                clear_admin_state(admin_id)
                bot.reply_to(message, "Добавление оборудования отменено.", reply_markup=admin_reply_markup)
                logger.info(f"Админ {admin_id} отменил добавление оборудования на шаге '{current_step}'.")
                return

        # --- Шаг: Ожидание имени НОВОЙ категории ---
        if current_step == const.ADMIN_STATE_ADD_EQUIP_NEW_CAT_NAME:
            # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
            logger.debug(f"Обработка шага ADMIN_STATE_ADD_EQUIP_NEW_CAT_NAME для admin {admin_id}")
            # -----------------------------
            category_name = message.text.strip()
            if not category_name:
                 bot.reply_to(message, "Название новой категории не может быть пустым. Повторите ввод или /cancel:")
                 # Состояние не меняем, ждем повторного ввода
                 return

            logger.debug(f"Admin {admin_id} ввел имя новой категории: '{category_name}'")
            category_id = None
            try:
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Вызов equipment_service.find_or_create_category для '{category_name}' (admin {admin_id})...")
                # -----------------------------
                category_id = equipment_service.find_or_create_category(db, category_name)
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Результат find_or_create_category: category_id={category_id}")
                # -----------------------------

                if category_id is None:
                    # Используем константу
                    fail_msg = const.MSG_CAT_CREATE_FAIL.format(category_name=category_name)
                    bot.reply_to(message, fail_msg, reply_markup=admin_reply_markup)
                    logger.warning(f"Не удалось найти/создать категорию '{category_name}' для админа {admin_id}.")
                    # Используем импортированную функцию
                    clear_admin_state(admin_id) # Прерываем процесс
                    return

                # Успешно создали/нашли категорию, переходим к вводу имени оборудования
                state['step'] = const.ADMIN_STATE_ADD_EQUIP_NAME
                state['category_id'] = category_id
                state['category_name'] = category_name # Сохраняем имя для сообщений
                msg_text = f"Категория: '{category_name}' (ID: {category_id}).\nТеперь введите **название** нового оборудования (или /cancel):"
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Отправка запроса имени оборудования admin {admin_id}")
                # -----------------------------
                bot.reply_to(message, msg_text, parse_mode="Markdown")
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Обновленное состояние для admin {admin_id}: {state}")
                # -----------------------------
                # Состояние обновлено, ждем следующего сообщения

            except Exception as e:
                 logger.error(f"Ошибка обработки новой категории '{category_name}' (admin {admin_id}): {e}", exc_info=True)
                 bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при работе с категорией.", reply_markup=admin_reply_markup)
                 # Используем импортированную функцию
                 clear_admin_state(admin_id)

        # --- Шаг: Ожидание имени ОБОРУДОВАНИЯ ---
        elif current_step == const.ADMIN_STATE_ADD_EQUIP_NAME:
            # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
            logger.debug(f"Обработка шага ADMIN_STATE_ADD_EQUIP_NAME для admin {admin_id}")
            # -----------------------------
            equipment_name = message.text.strip()
            category_id = state.get('category_id')
            category_name = state.get('category_name', '???') # Получаем имя категории из состояния

            if not equipment_name:
                bot.reply_to(message, "Название оборудования не может быть пустым. Повторите ввод или /cancel:")
                # Состояние не меняем
                return
            if category_id is None:
                 logger.error(f"Отсутствует category_id в состоянии админа {admin_id} на шаге ввода имени оборудования.")
                 bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка состояния (нет ID категории).", reply_markup=admin_reply_markup)
                 # Используем импортированную функцию
                 clear_admin_state(admin_id)
                 return

            logger.debug(f"Admin {admin_id} ввел имя оборудования: '{equipment_name}' для категории '{category_name}' ({category_id})")

            try:
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Вызов equipment_service.check_equipment_exists для '{equipment_name}', cat_id={category_id}...")
                # -----------------------------
                exists = equipment_service.check_equipment_exists(db, category_id, equipment_name)
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Результат check_equipment_exists: {exists}")
                # -----------------------------
                if exists:
                    # Используем константу
                    msg_text = const.MSG_EQUIP_ADD_FAIL_EXISTS.format(
                        equipment_name=f"'{equipment_name}'",
                        category_name=f"'{category_name}'"
                    )
                    bot.reply_to(message, msg_text + " Введите другое название или /cancel:")
                    # Состояние не меняем, ждем другого имени
                    return

                # Имя уникально, переходим к вводу описания
                state['step'] = const.ADMIN_STATE_ADD_EQUIP_NOTE
                state['equipment_name'] = equipment_name # Сохраняем имя
                msg_text = f"Название: '{equipment_name}'.\nВведите **описание** оборудования (можно оставить пустым, нажав Enter, или /cancel):"
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Отправка запроса описания оборудования admin {admin_id}")
                # -----------------------------
                bot.reply_to(message, msg_text, parse_mode="Markdown")
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Обновленное состояние для admin {admin_id}: {state}")
                # -----------------------------
                # Состояние обновлено

            except Exception as e:
                 logger.error(f"Ошибка при проверке/обработке имени оборудования '{equipment_name}' (админ {admin_id}): {e}", exc_info=True)
                 bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при проверке имени.", reply_markup=admin_reply_markup)
                 # Используем импортированную функцию
                 clear_admin_state(admin_id)

        # --- Шаг: Ожидание ОПИСАНИЯ оборудования ---
        elif current_step == const.ADMIN_STATE_ADD_EQUIP_NOTE:
            # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
            logger.debug(f"Обработка шага ADMIN_STATE_ADD_EQUIP_NOTE для admin {admin_id}")
            # -----------------------------
            note = message.text.strip() if message.text else "" # Пустое описание допустимо
            category_id = state.get('category_id')
            equipment_name = state.get('equipment_name')
            category_name = state.get('category_name', '???')

            # Проверяем наличие данных из предыдущих шагов
            if category_id is None or equipment_name is None:
                 logger.error(f"Отсутствует category_id или equipment_name в состоянии админа {admin_id} на шаге ввода описания.")
                 bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка состояния.", reply_markup=admin_reply_markup)
                 # Используем импортированную функцию
                 clear_admin_state(admin_id)
                 return

            logger.debug(f"Admin {admin_id} ввел описание: '{note}' для оборудования '{equipment_name}' в категории '{category_name}'")

            try:
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Вызов equipment_service.add_equipment...")
                # -----------------------------
                success = equipment_service.add_equipment(db, category_id, equipment_name, note)
                # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ ---
                logger.debug(f"Результат add_equipment: {success}")
                # -----------------------------
                if success:
                    # Используем константу
                    msg_text = const.MSG_EQUIP_ADD_SUCCESS.format(
                        equipment_name=f"'{equipment_name}'",
                        category_name=f"'{category_name}'"
                    )
                    bot.reply_to(message, msg_text, reply_markup=admin_reply_markup)
                    logger.info(f"Админ {admin_id} успешно добавил оборудование '{equipment_name}' (категория ID {category_id}).")
                else:
                    # Используем константу
                    msg_text = const.MSG_EQUIP_ADD_FAIL.format(equipment_name=f"'{equipment_name}'")
                    bot.reply_to(message, msg_text + " Проверьте логи сервера.", reply_markup=admin_reply_markup)
                    # Лог ошибки должен быть в сервисе

            except Exception as e:
                logger.error(f"Исключение при вызове add_equipment админом {admin_id} для '{equipment_name}': {e}", exc_info=True)
                bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при сохранении в базу данных.", reply_markup=admin_reply_markup)
            finally:
                 # Завершаем процесс в любом случае (успех или неудача)
                 # Используем импортированную функцию
                 clear_admin_state(admin_id)

        # --- Неизвестный шаг ---
        else:
             logger.error(f"Неизвестный шаг '{current_step}' в состоянии админа {admin_id}.")
             bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Неизвестное состояние процесса.", reply_markup=admin_reply_markup)
             # Используем импортированную функцию
             clear_admin_state(admin_id)


    # --- Управление Бронированиями (Админ) ---
    @bot.message_handler(commands=['admin_cancel'])
    def admin_cancel_start(message: Message):
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return

        logger.info(f"Админ {user_id} инициировал /admin_cancel")
        try:
            # Сервис должен возвращать список словарей List[Dict[str, Any]]
            bookings_data = booking_service.get_all_active_bookings_for_admin_keyboard(db)
            if not bookings_data:
                bot.reply_to(message, "Нет активных бронирований для отмены.")
                return

            # Клавиатура ожидает список словарей
            markup = keyboards.generate_admin_cancel_keyboard(bookings_data)
            bot.send_message(message.chat.id, "Выберите бронирование для принудительной отмены:", reply_markup=markup)

        except Exception as e:
            logger.error(f"Ошибка /admin_cancel (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Просмотр и Отчеты ---
    @bot.message_handler(commands=['all'])
    def all_bookings_filter_start(message: Message):
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return

        logger.info(f"Админ {user_id} запросил /all для генерации отчета")
        try:
            markup = keyboards.generate_filter_options_keyboard()
            bot.send_message(message.chat.id, "Выберите критерий для фильтрации бронирований в отчете:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /all (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    # --- Рассылка ---
    @bot.message_handler(commands=['broadcast'])
    def broadcast_start(message: Message):
         user_id = message.from_user.id
         # Проверяем права
         if not _is_admin_user(user_id):
              bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
              return

         logger.info(f"Админ {user_id} инициировал /broadcast")
         sent_msg = None
         try:
             sent_msg = bot.reply_to(message, "Введите текст сообщения для рассылки всем активным пользователям (или /cancel для отмены):", reply_markup=ReplyKeyboardRemove())
             # Передаем bot и db в следующий шаг
             bot.register_next_step_handler(sent_msg, process_broadcast_text, bot, db) # Оставляем RNSH для простого ввода текста
         except Exception as e_reply:
              logger.error(f"Ошибка отправки запроса на ввод broadcast админу {user_id}: {e_reply}")
              bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Не удалось начать рассылку.")


    def process_broadcast_text(message: Message, bot_i: telebot.TeleBot, db_i: Database):
         """Обрабатывает текст для рассылки."""
         admin_id = message.from_user.id
         admin_reply_markup = keyboards.create_admin_reply_keyboard()
         text = message.text

         # Обработка /cancel
         if text:
             if text.lower() == '/cancel':
                 bot_i.reply_to(message, "Рассылка отменена.", reply_markup=admin_reply_markup)
                 logger.info(f"Админ {admin_id} отменил broadcast.")
                 return
             # Игнорируем другие команды
             elif text.startswith('/'):
                  bot_i.reply_to(message, "Пожалуйста, завершите рассылку или используйте /cancel.", reply_markup=ReplyKeyboardRemove())
                  # Повторно регистрируем этот же шаг
                  bot_i.register_next_step_handler(message, process_broadcast_text, bot_i, db_i)
                  return

         # Проверка длины текста
         if not text or len(text.strip()) < 5:
             msg = bot_i.reply_to(message, "Сообщение слишком короткое (требуется минимум 5 символов). Повторите ввод или /cancel:")
             bot_i.register_next_step_handler(msg, process_broadcast_text, bot_i, db_i)
             return

         logger.info(f"Админ {admin_id} подтвердил broadcast: '{text[:50]}...'")
         sent_count = 0
         try:
            # bot_instance импортирован из bot_app
            sent_count = admin_service.broadcast_message_to_users(db_i, bot_instance, text, admin_id)
            bot_i.reply_to(message, f"✅ Рассылка запущена. Сообщение будет отправлено {sent_count} пользователям.", reply_markup=admin_reply_markup)
            logger.info(f"Broadcast админа {admin_id} отправлен {sent_count} пользователям.")
         except Exception as e:
             logger.error(f"Ошибка при выполнении broadcast админом {admin_id}: {e}", exc_info=True)
             bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при рассылке.", reply_markup=admin_reply_markup)

    # --- Управление Пользователями ---
    @bot.message_handler(commands=['users'])
    def view_users_handler(message: Message):
         user_id = message.from_user.id
         # Проверяем права
         if not _is_admin_user(user_id):
              bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
              return

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
                 if u_id is None: continue # Пропускаем, если нет ID

                 # Используем 'fi' из таблицы users, если есть, иначе пробуем собрать
                 u_name = user_data.get('fi')
                 if not u_name:
                     first = user_data.get('first_name', '')
                     last = user_data.get('last_name', '')
                     u_name = f"{first} {last}".strip() or f"ID {u_id}" # Собираем или используем ID

                 # Получаем детали для статуса (ожидаем кортеж от сервиса)
                 details = None
                 is_blocked = False # Статус по умолчанию
                 try:
                     details = user_service.get_user_details_for_management(db, u_id)
                     if details:
                         is_blocked = details[1] # Второй элемент кортежа - статус блокировки
                 except Exception as e_details:
                      logger.error(f"Ошибка получения деталей для user {u_id} в /users: {e_details}")
                      # Продолжаем без статуса или со статусом по умолчанию

                 status = "🔴 Заблок." if is_blocked else "🟢 Активен"
                 resp += f"{status} ID: `{u_id}` | ФИ: {u_name}\n" # Используем u_name

             # Отправка сообщения (логика разбиения остается)
             if len(resp) <= const.MAX_MESSAGE_LENGTH:
                 bot.send_message(message.chat.id, resp, parse_mode="Markdown")
             else:
                  logger.warning(f"Список пользователей /users слишком длинный ({len(resp)}), отправляем частями.")
                  parts = []
                  # Определяем заголовок
                  header_lines = resp.splitlines()[:2] # Первые две строки - заголовок
                  header = "\n".join(header_lines) + "\n\n"
                  lines = resp.splitlines()[2:] # Остальные строки - данные
                  current_part = ""
                  part_num = 1
                  total_parts = 1 # Посчитаем общее количество частей

                  # Сначала посчитаем количество частей
                  temp_current_part = ""
                  for line in lines:
                      if len(header) + len(temp_current_part) + len(line) + 1 > const.MAX_MESSAGE_LENGTH:
                          total_parts += 1
                          temp_current_part = line + "\n"
                      else:
                          temp_current_part += line + "\n"

                  # Теперь формируем части
                  for line in lines:
                      # Проверяем, поместится ли следующая строка
                      if len(header) + len(current_part) + len(line) + 1 > const.MAX_MESSAGE_LENGTH:
                          # Завершаем текущую часть
                          part_header = header.replace("*:", f" (часть {part_num}/{total_parts}):*")
                          parts.append(part_header + current_part)
                          current_part = "" # Начинаем новую часть
                          part_num += 1
                      current_part += line + "\n"

                  # Добавляем последнюю часть
                  part_header = header.replace("*:", f" (часть {part_num}/{total_parts}):*")
                  parts.append(part_header + current_part)

                  # Отправляем все части
                  for part_msg in parts:
                      try:
                          bot.send_message(message.chat.id, part_msg, parse_mode="Markdown")
                      except Exception as e_send_part:
                           logger.error(f"Ошибка отправки части списка /users: {e_send_part}")
                           # Можно прервать отправку или продолжить со следующей частью

         except Exception as e:
             logger.error(f"Ошибка /users (админ {user_id}): {e}", exc_info=True)
             bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['manage_user'])
    def manage_user_start(message: Message):
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return

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
    @bot.message_handler(commands=['schedule'])
    def force_schedule_update(message: Message):
        user_id = message.from_user.id
        # Проверяем права
        if not _is_admin_user(user_id):
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return

        logger.info(f"Админ {user_id} инициировал /schedule (принудительное обновление графика)")
        processing_msg = None
        try:
            processing_msg = bot.send_message(message.chat.id, "⏳ Обновляю график уведомлений...")

            # Вызываем функцию сервиса уведомлений с компонентами из bot_app
            notification_service.schedule_all_notifications(
                db, bot_instance, scheduler, active_timers, scheduled_jobs_registry
                # <-- Убедиться, что используется импортированный
            )

            # Редактируем сообщение об успехе
            if processing_msg:
                 bot.edit_message_text("✅ График уведомлений успешно обновлен.",
                                       chat_id=processing_msg.chat.id,
                                       message_id=processing_msg.message_id)
            else:
                 # Если исходное сообщение не отправилось, отправляем новое
                 bot.send_message(message.chat.id, "✅ График уведомлений успешно обновлен.")

            logger.info("График уведомлений обновлен по команде /schedule от админа.")

        except Exception as e:
            logger.error(f"Ошибка при выполнении /schedule (админ {user_id}): {e}", exc_info=True)
            fail_msg = f"❌ Произошла ошибка при обновлении графика: {e}"
            if processing_msg:
                 try:
                      bot.edit_message_text(fail_msg,
                                            chat_id=processing_msg.chat.id,
                                            message_id=processing_msg.message_id)
                 except Exception as e_edit_fail:
                      logger.error(f"Не удалось отредактировать сообщение об ошибке /schedule: {e_edit_fail}")
                      bot.send_message(message.chat.id, fail_msg) # Отправляем новым сообщением
            else:
                 bot.reply_to(message, fail_msg)


    logger.info("Обработчики админ-команд успешно зарегистрированы.")

# --- END OF FILE admin_commands.py ---