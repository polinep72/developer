# --- START OF FILE admin_commands.py (Исправленная версия) ---

# handlers/admin_commands.py
import telebot
from telebot.types import Message, ReplyKeyboardRemove
from database import Database
from logger import logger
from services import (
    user_service, booking_service, conference_room_service as room_service,
    admin_service, notification_service
)
from utils import keyboards
import constants as const # Импортируем константы для текстов кнопок
from typing import Dict, Any

from bot_app import bot as bot_instance, scheduler, active_timers, scheduled_jobs_registry

def register_admin_command_handlers(bot: telebot.TeleBot, db: Database):
    """Регистрирует обработчики команд только для администраторов."""

    def _is_admin_user(user_id: int) -> bool:
        is_admin = False
        try:
            is_admin = user_service.is_admin(db, user_id)
            # logger.debug(f"Проверка _is_admin_user для {user_id}: результат={is_admin}") # Можно убрать для продакшена
        except Exception as e:
            logger.error(f"Ошибка при проверке прав админа для user_id {user_id}: {e}", exc_info=True)
            is_admin = False
        return is_admin

    @bot.message_handler(commands=['adminhelp'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_ADMIN_HELP)
    def admin_help_handler(message: Message):
        user_id = message.from_user.id
        # Повторная проверка прав не нужна, если она есть в func, но оставим для явности или если func уберут
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.debug(f"Admin {user_id} запросил /adminhelp или нажал кнопку '{const.BTN_TEXT_ADMIN_HELP}'")
        help_text = const.MSG_ADMIN_HELP
        reply_markup = keyboards.create_admin_reply_keyboard()
        try:
            bot.reply_to(message, help_text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e_reply:
             logger.error(f"Ошибка отправки /adminhelp админу {user_id}: {e_reply}")

    @bot.message_handler(commands=['view_rooms'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_VIEW_ROOMS)
    def view_rooms_handler(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.debug(f"Админ {user_id} запросил /view_rooms или нажал кнопку '{const.BTN_TEXT_VIEW_ROOMS}'")
        try:
            all_rooms = room_service.get_all_conference_rooms(db)
            if not all_rooms:
                bot.reply_to(message, "В базе данных нет ни одной переговорной комнаты.")
                return
            markup = keyboards.generate_conference_room_list_with_delete_keyboard(all_rooms)
            bot.send_message(message.chat.id, "Текущие переговорные комнаты (нажмите 🗑️ для удаления):", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /view_rooms (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['add_room'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_ADD_ROOM)
    def add_room_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал добавление комнаты (/add_room или кнопка '{const.BTN_TEXT_ADD_ROOM}')")
        try:
            msg_text = const.MSG_ADMIN_PROMPT_CR_NAME + " (или введите `отмена`)"
            sent_msg = bot.send_message(message.chat.id, msg_text, reply_markup=ReplyKeyboardRemove())
            bot.register_next_step_handler(sent_msg, process_conference_room_name_input, bot_instance, db) # Передаем bot_instance
        except Exception as e:
            logger.error(f"Ошибка начала /add_room (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Не удалось начать процесс добавления.")

    @bot.message_handler(commands=['admin_cancel'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_ADMIN_CANCEL)
    def admin_cancel_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /admin_cancel или нажал кнопку '{const.BTN_TEXT_ADMIN_CANCEL}'")
        try:
            bookings_data = booking_service.get_all_active_bookings_for_admin_keyboard(db)
            if not bookings_data:
                bot.reply_to(message, "Нет активных или будущих бронирований для отмены.")
                return
            markup = keyboards.generate_admin_cancel_keyboard(bookings_data)
            bot.send_message(message.chat.id, "Выберите бронирование для принудительной отмены:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /admin_cancel (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['all'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_ALL)
    def all_bookings_filter_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} запросил /all или нажал кнопку '{const.BTN_TEXT_ALL}' для генерации отчета")
        try:
            markup = keyboards.generate_filter_options_keyboard()
            bot.send_message(message.chat.id, "Выберите критерий для фильтрации бронирований в отчете:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка /all (админ {user_id}): {e}", exc_info=True)
            bot.reply_to(message, const.MSG_ERROR_GENERAL)

    @bot.message_handler(commands=['broadcast'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_BROADCAST)
    def broadcast_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /broadcast или нажал кнопку '{const.BTN_TEXT_BROADCAST}'")
        sent_msg = None
        try:
            sent_msg = bot.reply_to(message, "Введите текст сообщения для рассылки всем активным пользователям (или введите `отмена` для отмены):", reply_markup=ReplyKeyboardRemove())
            bot.register_next_step_handler(sent_msg, process_broadcast_text, bot_instance, db) # Передаем bot_instance
        except Exception as e_reply:
            logger.error(f"Ошибка отправки запроса на ввод broadcast админу {user_id}: {e_reply}")
            bot.reply_to(message, f"{const.MSG_ERROR_GENERAL} Не удалось начать рассылку.")

    # process_broadcast_text - это next_step_handler, он не вызывается напрямую текстом кнопки
    def process_broadcast_text(message: Message, bot_i: telebot.TeleBot, db_i: Database):
        admin_id = message.from_user.id
        admin_reply_markup = keyboards.create_admin_reply_keyboard()
        text = message.text
        if text and text.lower() == 'отмена':
            bot_i.reply_to(message, "Рассылка отменена.", reply_markup=admin_reply_markup)
            logger.info(f"Админ {admin_id} отменил broadcast.")
            return
        if text and text.startswith('/'):
            bot_i.reply_to(message, "Пожалуйста, завершите рассылку или используйте слово `отмена`.", reply_markup=ReplyKeyboardRemove())
            bot_i.register_next_step_handler(message, process_broadcast_text, bot_i, db_i)
            return
        if not text or len(text.strip()) < 5:
            msg = bot_i.reply_to(message, "Сообщение слишком короткое (требуется минимум 5 символов). Повторите ввод или введите `отмена`:")
            bot_i.register_next_step_handler(msg, process_broadcast_text, bot_i, db_i)
            return
        logger.info(f"Админ {admin_id} подтвердил broadcast: '{text[:50]}...'")
        sent_count = 0
        failed_count = 0 # Добавим счетчик ошибок
        try:
            sent_count, failed_count = admin_service.broadcast_message_to_users(db_i, bot_instance, text, admin_id)
            reply_msg = f"✅ Рассылка запущена. Сообщение будет отправлено {sent_count} пользователям."
            if failed_count > 0:
                reply_msg += f"\n⚠️ Не удалось отправить {failed_count} пользователям (см. логи)."
            bot_i.reply_to(message, reply_msg, reply_markup=admin_reply_markup)
            logger.info(f"Broadcast админа {admin_id} отправлен {sent_count} пользователям, ошибок: {failed_count}.")
        except Exception as e:
            logger.error(f"Ошибка при выполнении broadcast админом {admin_id}: {e}", exc_info=True)
            bot_i.reply_to(message, f"{const.MSG_ERROR_GENERAL} Ошибка при рассылке.", reply_markup=admin_reply_markup)

    @bot.message_handler(commands=['users'])
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_USERS)
    def view_users_handler(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.debug(f"Админ {user_id} запросил /users или нажал кнопку '{const.BTN_TEXT_USERS}'")
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
                is_blocked = user_data.get('is_blocked', False)
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
                total_parts = 1 # Инициализируем
                # Сначала считаем общее количество частей
                temp_current_part_calc = ""
                for line_calc in lines:
                    if len(header) + len(temp_current_part_calc) + len(line_calc) + 1 > const.MAX_MESSAGE_LENGTH:
                        total_parts += 1
                        temp_current_part_calc = line_calc + "\n"
                    else:
                        temp_current_part_calc += line_calc + "\n"

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
    @bot.message_handler(func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_MANAGE_USER)
    def manage_user_start(message: Message):
        user_id = message.from_user.id
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить админское действие без прав (текст: {message.text}).")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /manage_user или нажал кнопку '{const.BTN_TEXT_MANAGE_USER}'")
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
    @bot.message_handler(
        func=lambda message: _is_admin_user(message.from_user.id) and message.text == const.BTN_TEXT_SCHEDULE)
    def force_schedule_update(message: Message):
        user_id = message.from_user.id  # Получаем user_id для логгирования
        if not _is_admin_user(user_id):
            logger.warning(f"Пользователь {user_id} попытался выполнить команду /schedule без прав.")
            bot.reply_to(message, const.MSG_ERROR_NO_PERMISSION)
            return
        logger.info(f"Админ {user_id} инициировал /schedule (принудительное обновление графика)")
        processing_msg = None
        try:
            processing_msg = bot.send_message(message.chat.id, "⏳ Обновляю график уведомлений...")
            # --- ИЗМЕНЕННЫЙ ВЫЗОВ ---
            notification_service.schedule_all_notifications()
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---
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
                    bot.send_message(message.chat.id, fail_msg)  # Отправляем новое, если редактирование не удалось
            else:
                bot.reply_to(message, fail_msg)  # Если даже начальное сообщение не отправилось

logger.info("Обработчики админ-команд успешно зарегистрированы.")

# Функции process_conference_room_name_input и process_conference_room_note_input
# не требуют декораторов для текста кнопок, так как вызываются через register_next_step_handler.
def process_conference_room_name_input(message: Message, bot_instance: telebot.TeleBot, db_instance: Database):
    admin_id = message.from_user.id
    chat_id = message.chat.id
    room_name = message.text.strip() if message.text else ""
    admin_reply_markup = keyboards.create_admin_reply_keyboard()
    logger.debug(f"Admin {admin_id} ввел название комнаты: '{room_name}'")

    if room_name.lower() == 'отмена':
        bot_instance.send_message(chat_id, "Добавление комнаты отменено.", reply_markup=admin_reply_markup)
        logger.info(f"Admin {admin_id} отменил ввод имени комнаты.")
        return
    if not room_name:
        msg = bot_instance.reply_to(message, "Название комнаты не может быть пустым. Попробуйте еще раз или введите `отмена`.")
        bot_instance.register_next_step_handler(msg, process_conference_room_name_input, bot_instance, db_instance)
        return
    if len(room_name) > 150:
        msg = bot_instance.reply_to(message, "Название комнаты слишком длинное (макс. 150 символов). Попробуйте еще раз или введите `отмена`.")
        bot_instance.register_next_step_handler(msg, process_conference_room_name_input, bot_instance, db_instance)
        return
    try:
        exists = room_service.check_conference_room_exists(db_instance, room_name)
        if exists:
            msg_text = const.MSG_CR_ADD_FAIL_EXISTS.format(cr_name=f"'{room_name}'")
            msg_retry = bot_instance.reply_to(message, msg_text + " Введите другое название или введите `отмена`:")
            bot_instance.register_next_step_handler(msg_retry, process_conference_room_name_input, bot_instance, db_instance)
            return
        prompt_text = const.MSG_ADMIN_PROMPT_CR_NOTE.format(cr_name=f"'{room_name}'") + " (можно пропустить введя `-`, или `отмена`)"
        msg_note = bot_instance.send_message(chat_id, prompt_text, parse_mode="Markdown")
        bot_instance.register_next_step_handler(msg_note, process_conference_room_note_input, room_name, bot_instance, db_instance)
    except Exception as e:
        logger.error(f"Ошибка при проверке/обработке имени комнаты '{room_name}' (админ {admin_id}): {e}", exc_info=True)
        bot_instance.send_message(chat_id, f"{const.MSG_ERROR_GENERAL} Ошибка при проверке имени.", reply_markup=admin_reply_markup)

def process_conference_room_note_input(message: Message, room_name: str, bot_instance: telebot.TeleBot, db_instance: Database):
    admin_id = message.from_user.id
    chat_id = message.chat.id
    note_text = message.text.strip() if message.text else ""
    admin_reply_markup = keyboards.create_admin_reply_keyboard()
    logger.debug(f"Admin {admin_id} ввел примечание: '{note_text}' для комнаты '{room_name}'")

    if note_text.lower() == 'отмена':
        bot_instance.send_message(chat_id, "Добавление комнаты отменено.", reply_markup=admin_reply_markup)
        logger.info(f"Admin {admin_id} отменил ввод примечания.")
        return
    final_note = None
    if note_text and note_text != '-':
        final_note = note_text
        if len(final_note) > 500:
            msg = bot_instance.reply_to(message, "Примечание слишком длинное (макс. 500 символов). Попробуйте еще раз, пропустите (`-`) или введите `отмена`.")
            bot_instance.register_next_step_handler(msg, process_conference_room_note_input, room_name, bot_instance, db_instance)
            return
    try:
        success, result_message = room_service.add_conference_room(db_instance, name=room_name, note=final_note)
        if success:
            logger.info(f"Комната '{room_name}' успешно добавлена админом {admin_id}.")
            bot_instance.send_message(chat_id, f"{result_message}", reply_markup=admin_reply_markup)
        else:
            logger.error(f"Ошибка добавления комнаты '{room_name}' админом {admin_id}: {result_message}")
            bot_instance.send_message(chat_id, f"{result_message}", reply_markup=admin_reply_markup)
    except Exception as e:
        logger.critical(f"Критическая ошибка при вызове add_conference_room админом {admin_id} для '{room_name}': {e}", exc_info=True)
        bot_instance.send_message(chat_id, const.MSG_ERROR_GENERAL, reply_markup=admin_reply_markup)

# --- END OF FILE admin_commands.py ---