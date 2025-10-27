# --- START OF FILE admin_commands.py ---

# handlers/admin_commands.py
import telebot
from telebot.types import Message, ReplyKeyboardRemove
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

# --- УДАЛЕНЫ ИМПОРТЫ СОСТОЯНИЙ ---

# --- Регистрация обработчиков команд ---
def register_admin_command_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики команд только для администраторов."""

    # Внутренняя функция для проверки прав админа
    def _is_admin_user(user_id: int) -> bool:
        is_admin = False
        try:
            is_admin = user_service.is_admin(db, user_id)
            logger.debug(f"Проверка _is_admin_user для {user_id}: результат={is_admin}")
        except Exception as e:
            logger.error(f"Ошибка при проверке прав админа для user_id {user_id}: {e}", exc_info=True)
            is_admin = False
        finally:
            return is_admin

    # --- Обработчики команд ---
    @bot.message_handler(commands=['adminhelp'])
    def admin_help_handler(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /adminhelp без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.debug(f"Admin {user_id} запросил /adminhelp")
        help_text = const.MSG_ADMIN_HELP
        reply_markup = keyboards.create_admin_reply_keyboard()
        try:
            bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e_reply:
             logger.error(f"Ошибка отправки /adminhelp админу {user_id}: {e_reply}")

    @bot.message_handler(commands=['view_equipment'])
    def view_equipment_handler(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /view_equipment без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.debug(f"Админ {user_id} запросил /view_equipment")
        try:
            all_equipment = equipment_service.get_all_equipment(db)
            if not all_equipment:
                bot.reply_to(message, "В базе данных нет ни одного оборудования.")
                return
            markup = keyboards.generate_equipment_list_with_delete_keyboard(all_equipment)
            bot.send_message(message.chat.id, "Текущее оборудование (нажмите 🗑️ для удаления):", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /view_equipment (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['add_equipment'])
    def add_equipment_start(message: Message):
        """
        Начинает процесс добавления нового оборудования.
        Запрашивает у администратора выбор существующей категории или добавление новой.
        """
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /add_equipment без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал добавление оборудования (/add_equipment)")
        markup = None
        try:
            categories = equipment_service.get_all_categories(db)
            markup = keyboards.generate_add_equipment_category_keyboard(categories)
            msg_text = "Выберите существующую категорию для нового оборудования или добавьте новую:"
            bot.send_message(message.chat.id, msg_text, reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка начала /add_equipment (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Не удалось начать процесс добавления.")

    @bot.message_handler(commands=['admin_cancel'])
    def admin_cancel_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /admin_cancel без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /admin_cancel")
        try:
            bookings_data = booking_service.get_all_active_bookings_for_admin_keyboard(db)
            if not bookings_data:
                bot.reply_to(message, "Нет активных бронирований для отмены.")
                return
            markup = keyboards.generate_admin_cancel_keyboard(bookings_data)
            bot.send_message(message.chat.id, "Выберите бронирование для принудительной отмены:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /admin_cancel (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['all'])
    def all_bookings_filter_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /all без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} запросил /all для генерации отчета")
        try:
            markup = keyboards.generate_filter_options_keyboard()
            bot.send_message(message.chat.id, "Выберите критерий для фильтрации бронирований в отчете:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /all (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['broadcast'])
    def broadcast_start(message: Message):
         user_id = message.from_user.id
         if not _is_admin_user(user_id):
             logger.warning(f"Пользователь {user_id} попытался выполнить команду /broadcast без прав.")
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return
         logger.info(f"Админ {user_id} инициировал /broadcast")
         sent_msg = None
         try:
             # --- ИЗМЕНЕНИЕ: Подсказка для broadcast ---
             sent_msg = bot.reply_to(message, "Введите текст сообщения для рассылки всем активным пользователям (или введите `отмена` для отмены):", reply_markup=ReplyKeyboardRemove())
             bot.register_next_step_handler(sent_msg, process_broadcast_text, bot, db)
         except Exception as e_reply:
              logger.error(f"Ошибка отправки запроса на ввод broadcast админу {user_id}: {e_reply}")
              bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Не удалось начать рассылку.")

    def process_broadcast_text(message: Message, bot_i: telebot.TeleBot, db_i: Database):
         """Обрабатывает текст для рассылки."""
         admin_id = message.from_user.id
         admin_reply_markup = keyboards.create_admin_reply_keyboard()
         text = message.text

         if text:
             # --- ИЗМЕНЕНИЕ: Проверка отмены для broadcast ---
             if text.lower() == 'отмена':
                 bot_i.reply_to(message, "Рассылка отменена.", reply_markup=admin_reply_markup)
                 logger.info(f"Админ {admin_id} отменил broadcast.")
                 return
             elif text.startswith('/'):
                  # --- ИЗМЕНЕНИЕ: Подсказка при вводе команды ---
                  bot_i.reply_to(message, "Пожалуйста, завершите рассылку или используйте слово `отмена`.", reply_markup=ReplyKeyboardRemove())
                  bot_i.register_next_step_handler(message, process_broadcast_text, bot_i, db_i)
                  return

         if not text or len(text.strip()) < 5:
             # --- ИЗМЕНЕНИЕ: Подсказка при коротком сообщении ---
             msg = bot_i.reply_to(message, "Сообщение слишком короткое (требуется минимум 5 символов). Повторите ввод или введите `отмена`:")
             bot_i.register_next_step_handler(msg, process_broadcast_text, bot_i, db_i)
             return

         logger.info(f"Админ {admin_id} подтвердил broadcast: '{text[:50]}...'")
         sent_count = 0
         try:
            sent_count = admin_service.broadcast_message_to_users(db_i, bot_instance, text, admin_id)
            bot_i.reply_to(message, f"✅ Рассылка запущена. Сообщение будет отправлено {sent_count} пользователям.", reply_markup=admin_reply_markup)
            logger.info(f"Broadcast админа {admin_id} отправлен {sent_count} пользователям.")
         except Exception as e:
             logger.error(f"Ошибка при выполнении broadcast админом {admin_id}: {e}", exc_info=True)
             bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при рассылке.", reply_markup=admin_reply_markup)

    @bot.message_handler(commands=['users'])
    def view_users_handler(message: Message):
         user_id = message.from_user.id
         if not _is_admin_user(user_id):
             logger.warning(f"Пользователь {user_id} попытался выполнить команду /users без прав.")
             bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
             return
         logger.debug(f"Админ {user_id} запросил /users")
         try:
             users = user_service.get_all_users(db, include_inactive=True)
             if not users:
                 bot.reply_to(message, "В базе нет зарегистрированных пользователей.")
                 return
             resp = "👥 *Зарегистрированные пользователи:*\n\n"
             for user_data in users:
                 u_id = user_data.get('users_id')
                 if u_id is None: continue
                 u_name = user_data.get('fi')
                 if not u_name:
                     first = user_data.get('first_name', '')
                     last = user_data.get('last_name', '')
                     u_name = f"{first} {last}".strip() or f"ID {u_id}"
                 details = None
                 is_blocked = False
                 try:
                     details = user_service.get_user_details_for_management(db, u_id)
                     if details:
                         is_blocked = details[1]
                 except Exception as e_details:
                      logger.error(f"Ошибка получения деталей для user {u_id} в /users: {e_details}")
                 status = "🔴 Заблок." if is_blocked else "🟢 Активен"
                 resp += f"{status} ID: `{u_id}` | ФИ: {u_name}\n"
             if len(resp) <= const.MAX_MESSAGE_LENGTH:
                 bot.send_message(message.chat.id, resp, parse_mode="Markdown")
             else:
                  logger.warning(f"Список пользователей /users слишком длинный ({len(resp)}), отправляем частями.")
                  parts = []
                  header_lines = resp.splitlines()[:2]
                  header = "\n".join(header_lines) + "\n\n"
                  lines = resp.splitlines()[2:]
                  current_part = ""
                  part_num = 1
                  total_parts = 1
                  temp_current_part = ""
                  for line in lines:
                      if len(header) + len(temp_current_part) + len(line) + 1 > const.MAX_MESSAGE_LENGTH:
                          total_parts += 1
                          temp_current_part = line + "\n"
                      else:
                          temp_current_part += line + "\n"
                  for line in lines:
                      if len(header) + len(current_part) + len(line) + 1 > const.MAX_MESSAGE_LENGTH:
                          part_header = header.replace("*:", f" (часть {part_num}/{total_parts}):*")
                          parts.append(part_header + current_part)
                          current_part = ""
                          part_num += 1
                      current_part += line + "\n"
                  part_header = header.replace("*:", f" (часть {part_num}/{total_parts}):*")
                  parts.append(part_header + current_part)
                  for part_msg in parts:
                      try:
                          bot.send_message(message.chat.id, part_msg, parse_mode="Markdown")
                      except Exception as e_send_part:
                           logger.error(f"Ошибка отправки части списка /users: {e_send_part}")
         except Exception as e:
             logger.error(f"Ошибка /users (админ {user_id}): {e}", exc_info=True)
             bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['manage_user'])
    def manage_user_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /manage_user без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /manage_user")
        try:
            users = user_service.get_all_users(db, include_inactive=True)
            if not users:
                bot.reply_to(message, "Нет зарегистрированных пользователей для управления.")
                return
            markup = keyboards.generate_user_management_keyboard(users)
            bot.send_message(message.chat.id, "Выберите пользователя для блокировки/разблокировки:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /manage_user (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['schedule'])
    def force_schedule_update(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /schedule без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /schedule (принудительное обновление графика)")
        processing_msg = None
        try:
            processing_msg = bot.send_message(message.chat.id, "⏳ Обновляю график уведомлений...")
            notification_service.schedule_all_notifications(
                db, bot_instance, scheduler, active_timers, scheduled_jobs_registry
            )
            if processing_msg:
                 bot.edit_message_text("✅ График уведомлений успешно обновлен.",
                                       chat_id=processing_msg.chat.id,
                                       message_id=processing_msg.message_id)
            else:
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
                      bot.send_message(message.chat.id, fail_msg)
            else:
                 bot.reply_to(message, fail_msg)

    logger.info("Обработчики админ-команд успешно зарегистрированы.")


# --- НОВЫЕ ФУНКЦИИ ДЛЯ register_next_step_handler (ВЫЗЫВАЮТСЯ ИЗ CALLBACK HANDLERS) ---

def process_new_category_name_input(message: Message, bot_instance: telebot.TeleBot, db_instance: Database):
    """
    Обрабатывает ввод названия новой категории оборудования.
    Вызывается через register_next_step_handler после нажатия кнопки "Добавить категорию".
    """
    admin_id = message.from_user.id
    chat_id = message.chat.id
    new_cat_name = ""
    if message.text:
        new_cat_name = message.text.strip()

    admin_reply_markup = keyboards.create_admin_reply_keyboard()

    logger.debug(f"Admin {admin_id} ввел название новой категории: '{new_cat_name}'")

    # --- ИЗМЕНЕНИЕ: Проверка на слово "отмена" ---
    if new_cat_name.lower() == 'отмена':
        bot_instance.send_message(chat_id, "Добавление новой категории отменено.", reply_markup=admin_reply_markup)
        logger.info(f"Admin {admin_id} отменил ввод имени новой категории.")
        return

    # Валидация имени
    if not new_cat_name:
        msg = None
        try:
            # --- ИЗМЕНЕНИЕ: Подсказка при пустом вводе ---
            msg = bot_instance.reply_to(message, "Название категории не может быть пустым. Попробуйте еще раз или введите `отмена` для отмены.")
            bot_instance.register_next_step_handler(msg, process_new_category_name_input, bot_instance, db_instance)
        except Exception as e_reg:
             logger.error(f"Ошибка повторной регистрации шага для пустой категории (админ {admin_id}): {e_reg}")
             bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
        return

    if len(new_cat_name) > 100:
        msg = None
        try:
            # --- ИЗМЕНЕНИЕ: Подсказка при длинном вводе ---
            msg = bot_instance.reply_to(message, "Название категории слишком длинное (макс. 100 символов). Попробуйте еще раз или введите `отмена`.")
            bot_instance.register_next_step_handler(msg, process_new_category_name_input, bot_instance, db_instance)
        except Exception as e_reg:
             logger.error(f"Ошибка повторной регистрации шага для длинной категории (админ {admin_id}): {e_reg}")
             bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
        return

    # Добавляем категорию в БД
    category_id = None
    try:
        category_id = equipment_service.add_category(db_instance, new_cat_name)
        if category_id:
            logger.info(f"Админ {admin_id} добавил новую категорию '{new_cat_name}' (ID: {category_id}).")
            bot_instance.send_message(chat_id, f"✅ Добавлена новая категория: '{new_cat_name}'.")
            msg_equip = None
            try:
                # --- ИЗМЕНЕНИЕ: Подсказка для следующего шага ---
                msg_equip = bot_instance.send_message(chat_id, "Теперь введите **название** нового оборудования (или введите `отмена`):", parse_mode="Markdown")
                bot_instance.register_next_step_handler(msg_equip, process_equipment_name_input, category_id, bot_instance, db_instance)
            except Exception as e_next:
                logger.error(f"Ошибка регистрации шага для ввода имени оборудования (админ {admin_id}, категория {category_id}): {e_next}")
                bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка перехода к следующему шагу.", reply_markup=admin_reply_markup)
        else:
            logger.warning(f"Не удалось добавить категорию '{new_cat_name}' админом {admin_id}. Возможно, она уже существует.")
            msg_retry = None
            try:
                # --- ИЗМЕНЕНИЕ: Подсказка при дубликате категории ---
                msg_retry = bot_instance.reply_to(message, f"⚠️ Не удалось добавить категорию '{new_cat_name}'. Возможно, она уже существует. Попробуйте другое имя или введите `отмена`.")
                bot_instance.register_next_step_handler(msg_retry, process_new_category_name_input, bot_instance, db_instance)
            except Exception as e_reg_retry:
                 logger.error(f"Ошибка повторной регистрации шага для существующей категории (админ {admin_id}): {e_reg_retry}")
                 bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при добавлении новой категории '{new_cat_name}' админом {admin_id}: {e}", exc_info=True)
        bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка при добавлении категории.", reply_markup=admin_reply_markup)


def process_equipment_name_input(message: Message, category_id: int, bot_instance: telebot.TeleBot, db_instance: Database):
    """
    Обрабатывает ввод названия нового оборудования.
    Вызывается через register_next_step_handler после выбора категории или добавления новой.
    """
    admin_id = message.from_user.id
    chat_id = message.chat.id
    equipment_name = ""
    if message.text:
        equipment_name = message.text.strip()

    admin_reply_markup = keyboards.create_admin_reply_keyboard()

    logger.debug(f"Admin {admin_id} ввел название оборудования: '{equipment_name}' для категории ID: {category_id}")

    # --- ИЗМЕНЕНИЕ: Проверка на слово "отмена" ---
    if equipment_name.lower() == 'отмена':
        bot_instance.send_message(chat_id, "Добавление оборудования отменено.", reply_markup=admin_reply_markup)
        logger.info(f"Admin {admin_id} отменил ввод имени оборудования.")
        return

    # Валидация имени
    if not equipment_name:
        msg = None
        try:
            # --- ИЗМЕНЕНИЕ: Подсказка при пустом вводе ---
            msg = bot_instance.reply_to(message, "Название оборудования не может быть пустым. Попробуйте еще раз или введите `отмена`.")
            bot_instance.register_next_step_handler(msg, process_equipment_name_input, category_id, bot_instance, db_instance)
        except Exception as e_reg:
             logger.error(f"Ошибка повторной регистрации шага для пустого имени оборудования (админ {admin_id}): {e_reg}")
             bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
        return

    if len(equipment_name) > 150:
        msg = None
        try:
            # --- ИЗМЕНЕНИЕ: Подсказка при длинном вводе ---
            msg = bot_instance.reply_to(message, "Название оборудования слишком длинное (макс. 150 символов). Попробуйте еще раз или введите `отмена`.")
            bot_instance.register_next_step_handler(msg, process_equipment_name_input, category_id, bot_instance, db_instance)
        except Exception as e_reg:
             logger.error(f"Ошибка повторной регистрации шага для длинного имени оборудования (админ {admin_id}): {e_reg}")
             bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
        return

    # Проверка на дубликат
    try:
        exists = equipment_service.check_equipment_exists(db_instance, category_id, equipment_name)
        if exists:
            category_name = "???"
            try:
                category_name_result = equipment_service.get_category_name_by_id(db_instance, category_id)
                if category_name_result:
                    category_name = category_name_result
                else:
                    category_name = f"ID {category_id}"
            except Exception as e_cat_name:
                logger.error(f"Не удалось получить имя категории {category_id} для сообщения об ошибке дубликата: {e_cat_name}")
                category_name = f"ID {category_id}"

            msg_text = const.MSG_EQUIP_ADD_FAIL_EXISTS.format(
                equipment_name=f"'{equipment_name}'",
                category_name=f"'{category_name}'"
            )
            msg_retry = None
            try:
                # --- ИЗМЕНЕНИЕ: Подсказка при дубликате оборудования ---
                msg_retry = bot_instance.reply_to(message, msg_text + " Введите другое название или введите `отмена`:")
                bot_instance.register_next_step_handler(msg_retry, process_equipment_name_input, category_id, bot_instance, db_instance)
            except Exception as e_reg_retry:
                 logger.error(f"Ошибка повторной регистрации шага для дубликата оборудования (админ {admin_id}): {e_reg_retry}")
                 bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
            return

        # Имя уникально, переходим к вводу описания
        msg_note = None
        try:
            # --- ИЗМЕНЕНИЕ: Подсказка для следующего шага ---
            msg_note = bot_instance.send_message(
                chat_id,
                f"Оборудование: '{equipment_name}'.\nТеперь введите **примечание** (опционально, можно пропустить введя `-` и нажав Enter, или введите `отмена` для отмены всего процесса):",
                parse_mode="Markdown"
            )
            bot_instance.register_next_step_handler(
                msg_note, process_equipment_note_input, category_id, equipment_name, bot_instance, db_instance
            )
        except Exception as e_next:
            logger.error(f"Ошибка регистрации шага для ввода примечания (админ {admin_id}, оборудование {equipment_name}): {e_next}")
            bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка перехода к следующему шагу.", reply_markup=admin_reply_markup)
    except Exception as e:
         logger.error(f"Ошибка при проверке/обработке имени оборудования '{equipment_name}' (админ {admin_id}): {e}", exc_info=True)
         bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка при проверке имени.", reply_markup=admin_reply_markup)


def process_equipment_note_input(message: Message, category_id: int, equipment_name: str, bot_instance: telebot.TeleBot, db_instance: Database):
    """
    Обрабатывает ввод примечания для нового оборудования и добавляет его в БД.
    Вызывается через register_next_step_handler после ввода имени оборудования.
    """
    admin_id = message.from_user.id
    chat_id = message.chat.id
    note_text = ""
    if message.text:
        note_text = message.text.strip()

    admin_reply_markup = keyboards.create_admin_reply_keyboard()

    logger.debug(f"Admin {admin_id} ввел примечание: '{note_text}' для оборудования '{equipment_name}' (категория ID: {category_id})")

    # --- ИЗМЕНЕНИЕ: Проверка на слово "отмена" ---
    if note_text.lower() == 'отмена':
        bot_instance.send_message(chat_id, "Добавление оборудования отменено.", reply_markup=admin_reply_markup)
        logger.info(f"Admin {admin_id} отменил ввод примечания.")
        return

    # Обработка пропуска примечания
    final_note = None
    if note_text and note_text != '-':
        final_note = note_text
        if len(final_note) > 500:
             msg = None
             try:
                 # --- ИЗМЕНЕНИЕ: Подсказка при длинном примечании ---
                 msg = bot_instance.reply_to(message, "Примечание слишком длинное (макс. 500 символов). Попробуйте еще раз, пропустите (`-` или пустое сообщение) или введите `отмена`.")
                 bot_instance.register_next_step_handler(
                     msg, process_equipment_note_input, category_id, equipment_name, bot_instance, db_instance
                 )
             except Exception as e_reg:
                 logger.error(f"Ошибка повторной регистрации шага для длинного примечания (админ {admin_id}): {e_reg}")
                 bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка. Попробуйте снова.", reply_markup=admin_reply_markup)
             return

    # Добавляем оборудование в БД
    try:
        # Используем правильное имя аргумента 'name' согласно определению функции
        success, result_message = equipment_service.add_equipment(
            db_instance,
            category_id=category_id,
            name=equipment_name,  # ПРАВИЛЬНО
            note=final_note
        )
        if success:
             logger.info(f"Оборудование '{equipment_name}' успешно добавлено админом {admin_id} в категорию ID:{category_id}.")
             bot_instance.send_message(chat_id, f"✅ {result_message}", reply_markup=admin_reply_markup)
        else:
             logger.error(f"Ошибка добавления оборудования '{equipment_name}' админом {admin_id}: {result_message}")
             bot_instance.send_message(chat_id, f"❌ {result_message}", reply_markup=admin_reply_markup)
    except Exception as e:
        logger.error(f"Критическая ошибка при вызове add_equipment админом {admin_id} для '{equipment_name}': {e}", exc_info=True)
        bot_instance.send_message(chat_id, const.MSG_ERROR_GENERAL, reply_markup=admin_reply_markup)

# --- END OF FILE admin_commands.py ---