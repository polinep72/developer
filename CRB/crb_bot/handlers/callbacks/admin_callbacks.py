# --- START OF FILE handlers/callbacks/admin_callbacks.py ---
"""
Обработчики callback-запросов, предназначенные для администраторов (CRB v.1 Version).

Отвечает за:
- Подтверждение/отклонение регистрации пользователей.
- Блокировку/разблокировку пользователей.
- Принудительную отмену бронирований.
- Выбор фильтров для отчета /allbookings и его генерацию.
- Удаление переговорных комнат (выбор, подтверждение).
- Отмену процесса добавления комнаты.
- Обработку кнопок "Отмена" в админских диалогах.
"""
import os
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery, Message
from typing import Dict, Any, Optional, Set, Tuple, List
from datetime import datetime

from database import Database, QueryResult
from logger import logger
import constants as const # Используем обновленные константы
import services.user_service as userService
import services.booking_service as bookingService
# --- ИЗМЕНЕНИЕ: Используем conference_room_service ---
import services.conference_room_service as room_service
# --- КОНЕЦ ИЗМЕНЕНИЯ ---
import services.admin_service as adminService # Потребует адаптации позже
import services.notification_service as notificationService
import services.registration_notification_service as registration_notification_service
from utils import keyboards # Используем обновленные клавиатуры
from apscheduler.schedulers.background import BackgroundScheduler

from utils.message_utils import edit_or_send_message
# Функции из admin_commands больше не вызываются напрямую из колбэков добавления
# from handlers import admin_commands

# --- Обработчики добавления комнаты (УДАЛЕНЫ обработчики категорий) ---

# Обработчик для кнопки отмены в процессе добавления (если он был начат через callback, а не команду)
def handle_admin_add_cr_cancel(
    bot: telebot.TeleBot,
    db: Database, # db не используется, но оставляем для консистентности сигнатур
    call: CallbackQuery,
):
    admin_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    logger.info(f"Admin {admin_id} отменил добавление комнаты через кнопку 'Отмена'.")
    try: bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
    except apihelper.ApiTelegramException as e_ans: logger.warning(f"Не удалось ответить на callback отмены добавления комнаты: {e_ans}")
    try: bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="Добавление переговорной комнаты отменено.", reply_markup=None)
    except apihelper.ApiTelegramException as e_edit: logger.error(f"Не удалось отредактировать сообщение при отмене добавления комнаты админом {admin_id}: {e_edit}")
    except Exception as e: logger.error(f"Общая ошибка при редактировании сообщения об отмене (admin {admin_id}): {e}", exc_info=True)

# --- Обработчики регистрации (без изменений в логике) ---
def handle_registration_confirm(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_user_id: int = call.from_user.id
    cb_data: str = call.data
    temp_user_id_str: str = cb_data[len(const.CB_REG_CONFIRM_USER):]
    temp_user_id: Optional[int] = None
    try: temp_user_id = int(temp_user_id_str)
    except ValueError:
        logger.error(f"Неверный user_id '{temp_user_id_str}' в CB_REG_CONFIRM_USER от admin {admin_user_id}")
        try: bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
        except Exception: pass
        return
    logger.info(f"Admin {admin_user_id} подтверждает регистрацию пользователя {temp_user_id}")
    try: bot.answer_callback_query(call.id, "Регистрирую пользователя...")
    except Exception as e_ans_reg_conf: logger.warning(f"Не удалось ответить на callback подтверждения регистрации {temp_user_id}: {e_ans_reg_conf}")
    success: bool = False
    user_info: Optional[Dict] = None
    admin_info: Optional[Dict] = None
    try:
        admin_info = userService.get_user_info(db, admin_user_id)
        success, user_info = userService.confirm_registration(db, temp_user_id)
    except Exception as e_confirm:
        logger.error(f"Ошибка при подтверждении регистрации {temp_user_id} админом {admin_user_id}: {e_confirm}", exc_info=True)
        success = False
        try: edit_or_send_message(bot, call.message.chat.id, call.message.message_id, f"❌ Ошибка при регистрации пользователя ID `{temp_user_id}`.", reply_markup=None, parse_mode="Markdown")
        except Exception as e_edit_err: logger.error(f"Не удалось отредактировать сообщение об ошибке подтверждения {temp_user_id}: {e_edit_err}")
        return
    if success:
        user_display: str = f"ID {temp_user_id}"
        if user_info:
            user_fi = user_info.get('fi')
            first_name = user_info.get('first_name', '')
            user_display = user_fi or first_name or f"ID {temp_user_id}"
            try: bot.send_message(temp_user_id, const.MSG_REGISTRATION_APPROVED)
            except Exception as e_notify: logger.error(f"Не удалось уведомить пользователя {temp_user_id} о регистрации: {e_notify}")
        else: logger.warning(f"confirm_registration для {temp_user_id} вернул success=True, но user_info=None.")
        admin_name: str = admin_info.get('fi') if admin_info else f"ID {admin_user_id}"
        final_text: str = f"✅ Заявка пользователя {user_display} (ID: `{temp_user_id}`) была **подтверждена** администратором {admin_name}."
        notifications_to_edit: List[Dict] = registration_notification_service.get_admin_reg_notifications(db, temp_user_id)
        edited_count = 0
        for notif_data in notifications_to_edit:
            notif_admin_id = notif_data.get('admin_user_id')
            notif_chat_id = notif_data.get('chat_id')
            notif_message_id = notif_data.get('message_id')
            if notif_chat_id and notif_message_id:
                try:
                    bot.edit_message_text(chat_id=notif_chat_id, message_id=notif_message_id, text=final_text, reply_markup=None, parse_mode="Markdown")
                    edited_count += 1
                except apihelper.ApiTelegramException as e_edit_api:
                    if "message to edit not found" in str(e_edit_api).lower() or "message can't be edited" in str(e_edit_api).lower() or "message is not modified" in str(e_edit_api).lower(): logger.warning(f"Не удалось/не требуется редактировать сообщение {notif_message_id} для админа {notif_admin_id} (заявка {temp_user_id}): {e_edit_api}")
                    else: logger.error(f"Ошибка API при редактировании сообщения {notif_message_id} для админа {notif_admin_id}: {e_edit_api}")
                except Exception as e_edit_other: logger.error(f"Ошибка при редактировании сообщения {notif_message_id} для админа {notif_admin_id}: {e_edit_other}", exc_info=True)
        logger.info(f"Отредактировано {edited_count} из {len(notifications_to_edit)} сообщений админов о подтверждении заявки {temp_user_id}.")
        registration_notification_service.delete_admin_reg_notifications(db, temp_user_id)
    else:
        error_text = f"ℹ️ Заявка пользователя ID `{temp_user_id}` уже была обработана ранее другим администратором."
        try: edit_or_send_message(bot, call.message.chat.id, call.message.message_id, error_text, reply_markup=None, parse_mode="Markdown")
        except Exception as e_edit_fail: logger.error(f"Не удалось отредактировать сообщение о неудачном подтверждении {temp_user_id}: {e_edit_fail}")

def handle_registration_decline(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_user_id: int = call.from_user.id
    cb_data: str = call.data
    temp_user_id_str: str = cb_data[len(const.CB_REG_DECLINE_USER):]
    temp_user_id: Optional[int] = None
    try: temp_user_id = int(temp_user_id_str)
    except ValueError:
        logger.error(f"Неверный user_id '{temp_user_id_str}' в CB_REG_DECLINE_USER от admin {admin_user_id}")
        try: bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
        except Exception: pass
        return
    logger.info(f"Admin {admin_user_id} отклоняет регистрацию пользователя {temp_user_id}")
    try: bot.answer_callback_query(call.id, "Отклоняю регистрацию...")
    except Exception as e_ans_reg_dec: logger.warning(f"Не удалось ответить на callback отклонения регистрации {temp_user_id}: {e_ans_reg_dec}")
    success: bool = False
    admin_info: Optional[Dict] = None
    temp_user_info: Optional[Dict] = None
    try:
        admin_info = userService.get_user_info(db, admin_user_id)
        temp_user_info = userService.find_temp_user(db, temp_user_id)
        success = userService.decline_registration(db, temp_user_id)
    except Exception as e_decline:
        logger.error(f"Ошибка при отклонении регистрации {temp_user_id} админом {admin_user_id}: {e_decline}", exc_info=True)
        success = False
        try: edit_or_send_message(bot, call.message.chat.id, call.message.message_id, f"❌ Ошибка при отклонении заявки ID `{temp_user_id}`.", reply_markup=None, parse_mode="Markdown")
        except Exception as e_edit_err: logger.error(f"Не удалось отредактировать сообщение об ошибке отклонения {temp_user_id}: {e_edit_err}")
        return
    if success:
        user_display: str = temp_user_info.get('fi') if temp_user_info else f"ID {temp_user_id}"
        try: bot.send_message(temp_user_id, const.MSG_REGISTRATION_DECLINED)
        except Exception as e_notify: logger.warning(f"Не удалось уведомить пользователя {temp_user_id} об отклонении регистрации: {e_notify}")
        admin_name: str = admin_info.get('fi') if admin_info else f"ID {admin_user_id}"
        final_text: str = f"🚫 Заявка пользователя {user_display} (ID: `{temp_user_id}`) была **отклонена** администратором {admin_name}."
        notifications_to_edit: List[Dict] = registration_notification_service.get_admin_reg_notifications(db, temp_user_id)
        edited_count = 0
        for notif_data in notifications_to_edit:
            notif_admin_id = notif_data.get('admin_user_id')
            notif_chat_id = notif_data.get('chat_id')
            notif_message_id = notif_data.get('message_id')
            if notif_chat_id and notif_message_id:
                try:
                    bot.edit_message_text(chat_id=notif_chat_id, message_id=notif_message_id, text=final_text, reply_markup=None, parse_mode="Markdown")
                    edited_count += 1
                except apihelper.ApiTelegramException as e_edit_api:
                    if "message to edit not found" in str(e_edit_api).lower() or "message can't be edited" in str(e_edit_api).lower() or "message is not modified" in str(e_edit_api).lower(): logger.warning(f"Не удалось/не требуется редактировать сообщение {notif_message_id} для админа {notif_admin_id} (заявка {temp_user_id}): {e_edit_api}")
                    else: logger.error(f"Ошибка API при редактировании сообщения {notif_message_id} для админа {notif_admin_id}: {e_edit_api}")
                except Exception as e_edit_other: logger.error(f"Ошибка при редактировании сообщения {notif_message_id} для админа {notif_admin_id}: {e_edit_other}", exc_info=True)
        logger.info(f"Отредактировано {edited_count} из {len(notifications_to_edit)} сообщений админов об отклонении заявки {temp_user_id}.")
        registration_notification_service.delete_admin_reg_notifications(db, temp_user_id)
    else:
        error_text = f"ℹ️ Заявка пользователя ID `{temp_user_id}` уже была обработана ранее другим администратором или произошла ошибка."
        try: edit_or_send_message(bot, call.message.chat.id, call.message.message_id, error_text, reply_markup=None, parse_mode="Markdown")
        except Exception as e_edit_fail: logger.error(f"Не удалось отредактировать сообщение о неудачном отклонении {temp_user_id}: {e_edit_fail}")

# --- Обработчики управления пользователями (без изменений) ---
def handle_manage_user_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    target_user_id_str: str = cb_data[len(const.CB_MANAGE_SELECT_USER):]
    target_user_id: Optional[int] = None
    try: target_user_id = int(target_user_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID пользователя из callback '{cb_data}' (admin {admin_user_id})")
        try: bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
        except Exception as e_ans: logger.warning(f"Не удалось ответить на callback с ошибкой ID: {e_ans}")
        return
    logger.debug(f"Admin {admin_user_id} выбрал пользователя {target_user_id} для управления.")
    try: bot.answer_callback_query(call.id)
    except Exception as e_ans_manage_sel: logger.warning(f"Не удалось ответить на callback выбора пользователя {target_user_id}: {e_ans_manage_sel}")
    kwargs_edit: Dict[str, Any] = {} # Не передаем admin_id_for_state_update, т.к. нет состояния FSM
    details: Optional[Tuple[str, bool]] = None
    try: details = userService.get_user_details_for_management(db, target_user_id)
    except Exception as e_get_details:
        logger.error(f"Ошибка при получении деталей пользователя {target_user_id} для управления (admin {admin_user_id}): {e_get_details}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Ошибка получения данных.", show_alert=True)
        except Exception as e_ans: logger.warning(f"Не удалось ответить на callback после ошибки получения деталей: {e_ans}")
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return
    if not details:
        logger.warning(f"Пользователь {target_user_id} не найден при выборе для управления (admin {admin_user_id}).")
        try: bot.answer_callback_query(call.id, "Пользователь не найден.", show_alert=True)
        except Exception as e_ans: logger.warning(f"Не удалось ответить на callback 'не найден': {e_ans}")
        edit_or_send_message(bot, chat_id, message_id, "Выбранный пользователь не найден в базе данных.", reply_markup=None, **kwargs_edit)
        return
    name, is_blocked = details
    user_display_name: str = name if name else f"ID {target_user_id}"
    status_text: str = "🔴 Заблокирован" if is_blocked else "🟢 Активен"
    markup: types.InlineKeyboardMarkup = keyboards.generate_user_status_keyboard(target_user_id, is_blocked)
    message_text: str = (f"Управление пользователем:\n👤 Имя: {user_display_name}\n🆔 ID: `{target_user_id}`\n🚦 Статус: {status_text}\n\nВыберите действие:")
    edit_or_send_message(bot, chat_id, message_id, message_text, reply_markup=markup, parse_mode="Markdown", **kwargs_edit)

def handle_manage_user_action(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    block_action: bool = cb_data.startswith(const.CB_MANAGE_BLOCK_USER)
    target_user_id: Optional[int] = None
    try:
        target_user_id_str: str = cb_data.split('_')[-1]
        target_user_id = int(target_user_id_str)
    except (ValueError, TypeError, IndexError) as e:
        logger.error(f"Ошибка парсинга ID пользователя из callback '{cb_data}' при блокировке/разблокировке (admin {admin_user_id}): {e}")
        try: bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
        except Exception as e_ans: logger.warning(f"Не удалось ответить на callback с ошибкой ID: {e_ans}")
        return
    action_verb: str = "блокирует" if block_action else "разблокирует"
    action_gerund: str = "Блокировка" if block_action else "Разблокировка"
    action_past: str = "заблокирован" if block_action else "разблокирован"
    action_infinitive: str = "заблокировать" if block_action else "разблокировать"
    logger.info(f"Admin {admin_user_id} {action_verb} пользователя {target_user_id}.")
    try: bot.answer_callback_query(call.id, f"{action_gerund} пользователя...")
    except Exception as e_ans_manage_act: logger.warning(f"Не удалось ответить на callback {action_gerund} пользователя {target_user_id}: {e_ans_manage_act}")
    kwargs_edit: Dict[str, Any] = {'reply_markup': None, 'parse_mode': "Markdown"}
    success: bool = False
    try: success = userService.update_user_block_status(db, target_user_id, block=block_action)
    except Exception as e_update_status:
        logger.error(f"Ошибка при попытке {action_infinitive} пользователя {target_user_id} (admin {admin_user_id}): {e_update_status}", exc_info=True)
        success = False
    details_after: Optional[Tuple[str, bool]] = None
    try: details_after = userService.get_user_details_for_management(db, target_user_id)
    except Exception as e_get_details_after:
        logger.error(f"Ошибка получения деталей пользователя {target_user_id} ПОСЛЕ {action_gerund} (admin {admin_user_id}): {e_get_details_after}", exc_info=True)
        error_text: str = f"❌ Произошла ошибка при попытке {action_infinitive} пользователя ID `{target_user_id}`."
        edit_or_send_message(bot, chat_id, message_id, error_text, **kwargs_edit)
        return
    if details_after:
        name_after, blocked_after = details_after
        user_display_name_after: str = name_after if name_after else f"ID {target_user_id}"
        status_text_after: str = "🔴 Заблокирован" if blocked_after else "🟢 Активен"
        result_message: str = const.MSG_USER_BLOCKED if block_action else const.MSG_USER_UNBLOCKED
        status_icon: str = "✅" if success else "❌"
        result_line: str = f"{status_icon} {result_message}" if success else f"{status_icon} Не удалось {action_infinitive} пользователя."
        markup_after: types.InlineKeyboardMarkup = keyboards.generate_user_status_keyboard(target_user_id, blocked_after)
        text_after: str = (f"Управление пользователем:\n👤 Имя: {user_display_name_after}\n🆔 ID: `{target_user_id}`\n🚦 Статус: {status_text_after}\n\n{result_line}\n\nВыберите следующее действие:")
        kwargs_edit['reply_markup'] = markup_after
        edit_or_send_message(bot, chat_id, message_id, text_after, **kwargs_edit)
    else:
        logger.error(f"Пользователь {target_user_id} не найден ПОСЛЕ попытки {action_infinitive} (admin {admin_user_id}).")
        error_text = f"❌ Ошибка: Пользователь ID `{target_user_id}` не найден после выполнения действия."
        edit_or_send_message(bot, chat_id, message_id, error_text, **kwargs_edit)

# --- Обработчики админской отмены брони (Адаптировано) ---
def handle_admin_cancel_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    booking_id_str: str = cb_data[len(const.CB_ADMIN_CANCEL_SELECT):]
    booking_id: Optional[int] = None
    try: booking_id = int(booking_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID брони из callback '{cb_data}' при админской отмене (admin {admin_user_id})")
        try: bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return
    logger.info(f"Admin {admin_user_id} выбрал бронь {booking_id} для возможной отмены.")
    try: bot.answer_callback_query(call.id)
    except Exception: pass # Игнорируем ошибку ответа
    kwargs_edit: Dict[str, Any] = {}
    booking_info: Optional[Dict[str, Any]] = None
    try:
        booking_info = bookingService.find_booking_by_id(db, booking_id)
    except Exception as e_find:
        logger.error(f"Ошибка поиска брони {booking_id} для админской отмены (admin {admin_user_id}): {e_find}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Ошибка поиска брони.", show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return

    if booking_info:
        b_status = booking_info.get('status')
        cr_name: str = booking_info.get('cr_name', '???') # <-- Имя комнаты
        user_fi: str = booking_info.get('user_fi', '???')
        user_id_owner: Any = booking_info.get('user_id', '???')
        date_val = booking_info.get('date')
        start_time = booking_info.get('time_start')
        end_time = booking_info.get('time_end')

        if b_status == 'cancelled':
            msg_edit: str = f"Бронь ID `{booking_id}` уже была отменена ранее."
            alert_msg: str = "Бронь уже отменена."
            logger.warning(f"Admin {admin_user_id} попытался отменить уже отмененную бронь {booking_id}.")
            try: bot.answer_callback_query(call.id, alert_msg)
            except Exception: pass
            edit_or_send_message(bot, chat_id, message_id, msg_edit, reply_markup=None, parse_mode="Markdown", **kwargs_edit)
            return
        elif b_status == 'finished':
            msg_edit = f"Бронь ID `{booking_id}` уже завершена и не может быть отменена."
            alert_msg = "Бронь уже завершена."
            logger.warning(f"Admin {admin_user_id} попытался отменить уже завершенную бронь {booking_id}.")
            try: bot.answer_callback_query(call.id, alert_msg)
            except Exception: pass
            edit_or_send_message(bot, chat_id, message_id, msg_edit, reply_markup=None, parse_mode="Markdown", **kwargs_edit)
            return
        else: # Бронь активна, подтверждена или ожидает подтверждения
            date_str: str = bookingService._format_date(date_val)
            start_str: str = bookingService._format_time(start_time)
            end_str: str = bookingService._format_time(end_time)
            confirm_text: str = (f"❓ Вы уверены, что хотите принудительно отменить бронирование ID `{booking_id}`?\n\n"
                            f"👤 Пользователь: {user_fi} (ID: `{user_id_owner}`)\n"
                            f"🚪 Переговорная: {cr_name}\n" # <-- Используем cr_name
                            f"🗓️ Дата и время: {date_str} с {start_str} по {end_str}\n\n"
                            f"❗ Пользователь будет уведомлен об отмене.")
            confirm_callback: str = f"{const.CB_ADMIN_CANCEL_CONFIRM}{booking_id}"
            cancel_callback: str = const.CB_ACTION_CANCEL + "admin_cancel_confirm"
            markup: types.InlineKeyboardMarkup = keyboards.generate_confirmation_keyboard(confirm_callback, cancel_callback)
            edit_or_send_message(bot, chat_id, message_id, confirm_text, reply_markup=markup, parse_mode="Markdown", **kwargs_edit)
    else:
        logger.warning(f"Бронь {booking_id} не найдена при попытке админской отмены (admin {admin_user_id}).")
        try: bot.answer_callback_query(call.id, "Бронь не найдена.", show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, "Выбранное бронирование не найдено.", reply_markup=None, **kwargs_edit)

def handle_admin_cancel_confirm(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    scheduler: Optional[BackgroundScheduler],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    admin_user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    booking_id_str: str = cb_data[len(const.CB_ADMIN_CANCEL_CONFIRM):]
    booking_id: Optional[int] = None
    try: booking_id = int(booking_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID брони из callback '{cb_data}' при подтверждении админской отмены (admin {admin_user_id})")
        try: bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
        except Exception: pass
        return
    logger.info(f"Admin {admin_user_id} подтвердил принудительную отмену брони {booking_id}.")
    try: bot.answer_callback_query(call.id, "Отменяю бронирование...")
    except Exception: pass
    kwargs_edit: Dict[str, Any] = {'reply_markup': None, 'parse_mode': "Markdown"}
    success: bool = False
    msg: str = const.MSG_ERROR_GENERAL
    owner_user_id: Optional[int] = None
    booking_info_before: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id) # Получаем инфо до отмены

    try:
        # Вызываем отмену
        success, msg, owner_user_id = bookingService.cancel_booking(db, booking_id, user_id=admin_user_id, is_admin_cancel=True)
    except Exception as e_cancel_admin:
        logger.error(f"Ошибка при выполнении админской отмены брони {booking_id} (admin {admin_user_id}): {e_cancel_admin}", exc_info=True)
        success = False; msg = const.MSG_ERROR_GENERAL

    if msg is None: logger.error(f"cancel_booking (admin) не вернул сообщение для брони {booking_id}"); msg = const.MSG_BOOKING_CANCELLED if success else const.MSG_ERROR_GENERAL

    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

    if success:
        # Очистка задач планировщика
        if scheduler:
            logger.debug(f"Бронь {booking_id} отменена админом, очищаем связанные задачи...")
            try:
                notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry) # Используем общую очистку
            except Exception as e_cleanup_admin_cancel: logger.error(f"Ошибка очистки задач после админской отмены брони {booking_id}: {e_cleanup_admin_cancel}", exc_info=True)
        else: logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")

        # Уведомление пользователя
        if owner_user_id:
            try:
                # Получаем детали из информации ДО отмены
                if booking_info_before:
                    cr_name_n: str = booking_info_before.get('cr_name', 'Ваше') # <-- Используем cr_name
                    date_val_n = booking_info_before.get('date')
                    start_time_n = booking_info_before.get('time_start')
                    date_str_n: str = bookingService._format_date(date_val_n)
                    start_str_n: str = bookingService._format_time(start_time_n)
                    # Обновляем текст уведомления
                    notify_text: str = (f"❗️ Ваше бронирование переговорной '{cr_name_n}' на {date_str_n} в {start_str_n} "
                                    f"было отменено администратором.")
                    bot.send_message(owner_user_id, notify_text)
                    logger.info(f"Уведомление об админской отмене брони {booking_id} отправлено пользователю {owner_user_id}")
                else:
                    logger.warning(f"Не удалось получить детали брони {booking_id} для уведомления пользователя {owner_user_id} об отмене.")
                    notify_text = f"❗️ Ваше бронирование (ID: {booking_id}) было отменено администратором."
                    bot.send_message(owner_user_id, notify_text)
            except apihelper.ApiTelegramException as e_notify_api:
                if "bot was blocked by the user" in str(e_notify_api).lower(): logger.warning(f"Не удалось уведомить пользователя {owner_user_id} об адм.отмене {booking_id}: бот заблокирован.")
                else: logger.error(f"Ошибка API при уведомлении пользователя {owner_user_id} об адм.отмене {booking_id}: {e_notify_api}")
            except Exception as e_notify_other: logger.error(f"Другая ошибка при уведомлении пользователя {owner_user_id} об адм.отмене {booking_id}: {e_notify_other}", exc_info=True)
        else: logger.warning(f"Не удалось получить ID владельца ({owner_user_id}) для брони {booking_id} после админской отмены. Уведомление не отправлено.")

# --- Обработчики фильтров отчета (Адаптировано) ---
def handle_filter_type_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    f_type: str = cb_data[len(const.CB_FILTER_BY_TYPE):]
    logger.debug(f"Admin {user_id} выбрал тип фильтра '{f_type}' для отчета /all")
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    opts: List[Tuple[str, Any]] = []
    cb_pfx: str = ""
    prompt: str = ""
    kwargs_edit: Dict[str, Any] = {}
    try:
        if f_type == "users":
            users_data: List[Dict] = userService.get_all_users(db, include_inactive=True)
            opts = []
            if users_data:
                for user in users_data:
                    user_id_val: Optional[int] = user.get('users_id')
                    if user_id_val:
                        # --- ИСПРАВЛЕНО ---
                        user_fi_val: str = user.get('fi', '').strip()
                        # Сначала формируем display_name_val
                        display_name_val: str = user_fi_val or f"ID {user_id_val}"
                        # Затем используем его в f-строке для кортежа
                        opts.append((f"{display_name_val} ({user_id_val})", user_id_val))
                        # -----------------
                opts.sort(key=lambda x: x[0])  # Сортируем по отображаемому имени
            cb_pfx = const.CB_FILTER_SELECT_USER
            prompt = "Выберите пользователя для фильтрации отчета:"
        # --- ИЗМЕНЕНО: Обработка фильтра по комнатам ---
        elif f_type == "cr":  # <-- Тип фильтра для комнат
            room_data: List[Dict] = room_service.get_all_conference_rooms(db)  # <-- Получаем комнаты
            if room_data:
                opts = []  # Инициализируем здесь
                for room in room_data:
                    room_id_val: Optional[int] = room.get('id')
                    if room_id_val:
                        # --- ИСПРАВЛЕНО (аналогично) ---
                        cr_name_val: str = room.get('cr_name', '').strip()
                        display_name_val: str = cr_name_val or f"ID {room_id_val}"
                        opts.append((f"{display_name_val} ({room_id_val})", room_id_val))
                        # -----------------
                opts.sort(key=lambda x: x[0])
            cb_pfx = const.CB_FILTER_SELECT_CR  # <-- Префикс для комнат
            prompt = "Выберите переговорную комнату для фильтрации отчета:"  # <-- Текст для комнат
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        elif f_type == "dates":
            query_months: str = "SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month_year FROM bookings WHERE date IS NOT NULL ORDER BY month_year DESC;"
            months_result: Optional[QueryResult] = db.execute_query(query_months, fetch_results=True)
            if months_result:
                opts = [(m.get('month_year'), m.get('month_year')) for m in months_result if m.get('month_year')]
            cb_pfx = const.CB_FILTER_SELECT_DATE
            prompt = "Выберите месяц (YYYY-MM) для фильтрации отчета:"
        else:
            logger.warning(f"Неизвестный тип фильтра '{f_type}' выбран админом {user_id}")
            try: bot.answer_callback_query(call.id, "Неизвестный тип фильтра.")
            except Exception: pass
            return

        if not opts:
            logger.warning(f"Нет данных для фильтра типа '{f_type}' (admin {user_id})")
            try: bot.answer_callback_query(call.id, "Нет данных для этого типа фильтра.")
            except Exception: pass
            edit_or_send_message(bot, chat_id, message_id, f"Не найдено данных для фильтрации по типу '{f_type}'.", reply_markup=None, **kwargs_edit)
        else:
            markup: types.InlineKeyboardMarkup = keyboards.generate_filter_selection_keyboard(opts, cb_pfx)
            edit_or_send_message(bot, chat_id, message_id, prompt, reply_markup=markup, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при подготовке опций для фильтра '{f_type}' (admin {user_id}): {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Ошибка при загрузке опций.", show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)

def handle_filter_value_select(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
     user_id: int = call.from_user.id
     chat_id: int = call.message.chat.id
     message_id: int = call.message.message_id
     cb_data: str = call.data
     f_type: str = ""
     f_val_str: str = ""
     f_val_int: Optional[int] = None
     f_details: str = "неизвестный фильтр"
     path: Optional[str] = None
     kwargs_edit: Dict[str, Any] = {'reply_markup': None}
     filter_value: Any = None

     try:
          if cb_data.startswith(const.CB_FILTER_SELECT_USER):
              f_type = "users"
              f_val_str = cb_data[len(const.CB_FILTER_SELECT_USER):]
              f_val_int = int(f_val_str); filter_value = f_val_int
              user_info: Optional[Dict] = userService.get_user_info(db, f_val_int)
              user_display: str = f"ID {f_val_int}"
              if user_info: user_display = f"{user_info.get('fi', '').strip() or user_display} ({f_val_int})"
              f_details = f"Пользователь: {user_display}"
          # --- ИЗМЕНЕНО: Обработка фильтра по комнатам ---
          elif cb_data.startswith(const.CB_FILTER_SELECT_CR):
              f_type = "cr" # <-- Тип фильтра
              f_val_str = cb_data[len(const.CB_FILTER_SELECT_CR):]
              f_val_int = int(f_val_str); filter_value = f_val_int
              name: Optional[str] = room_service.get_conference_room_name_by_id(db, f_val_int) # <-- Сервис комнат
              cr_display: str = f"ID {f_val_int}"
              if name: cr_display = f"{name} ({f_val_int})"
              f_details = f"Переговорная: {cr_display}" # <-- Текст для комнат
          # --- КОНЕЦ ИЗМЕНЕНИЯ ---
          elif cb_data.startswith(const.CB_FILTER_SELECT_DATE):
              f_type = "dates"
              f_val_str = cb_data[len(const.CB_FILTER_SELECT_DATE):]
              datetime.strptime(f_val_str, '%Y-%m') # Проверка формата
              filter_value = f_val_str
              f_details = f"Месяц: {f_val_str}"
          else:
              logger.error(f"Неизвестный префикс в handle_filter_value_select: '{cb_data}'")
              try: bot.answer_callback_query(call.id, "Ошибка типа фильтра.", show_alert=True)
              except Exception: pass
              return
     except (ValueError, TypeError, IndexError) as e:
         logger.error(f"Ошибка парсинга значения фильтра из callback '{cb_data}' (admin {user_id}): {e}")
         try: bot.answer_callback_query(call.id, "Ошибка в данных фильтра.", show_alert=True)
         except Exception: pass
         return
     except Exception as e_parse_val:
         logger.error(f"Ошибка при подготовке данных для фильтра '{cb_data}' (admin {user_id}): {e_parse_val}", exc_info=True)
         try: bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
         except Exception: pass
         return

     logger.info(f"Admin {user_id} запросил отчет /all с фильтром: {f_details}")
     try: bot.answer_callback_query(call.id, "Формирую отчет...")
     except Exception: pass
     edit_or_send_message(bot, chat_id, message_id, f"⏳ Пожалуйста, подождите, идет формирование отчета ({f_details})...", **kwargs_edit)

     try:
         # * ПРЕДПОЛАГАЕМ, что adminService адаптирован для f_type='cr' *
         bookings_data: List[Dict[str, Any]] = adminService.get_filtered_bookings(db, f_type, filter_value)
         if not bookings_data:
             logger.info(f"Нет бронирований, соответствующих фильтру '{f_details}' (admin {user_id}).")
             edit_or_send_message(bot, chat_id, message_id, f"По выбранному фильтру '{f_details}' не найдено ни одного бронирования.", **kwargs_edit)
             return

         # * ПРЕДПОЛАГАЕМ, что adminService адаптирован для генерации отчета с комнатами *
         path = adminService.create_bookings_report_file(bookings_data, filter_details=f_details)
         if path and os.path.exists(path):
             logger.info(f"Отправка отчета {os.path.basename(path)} админу {user_id} ({f_details})")
             report_file = None
             try:
                 report_file = open(path, 'rb')
                 bot.send_document(chat_id, report_file, caption=f"Отчет по бронированиям ({f_details})")
                 try: bot.delete_message(chat_id, message_id) # Удаляем сообщение "Подождите"
                 except Exception as e_del_orig: logger.warning(f"Не удалось удалить исходное сообщение {message_id} после отправки отчета: {e_del_orig}")
             except FileNotFoundError:
                 logger.error(f"Сгенерированный файл отчета не найден: {path}")
                 edit_or_send_message(bot, chat_id, message_id, f"❌ Ошибка: Не найден файл отчета.", **kwargs_edit)
             except Exception as e_send:
                 logger.error(f"Ошибка при отправке файла отчета {path} админу {user_id}: {e_send}", exc_info=True)
                 edit_or_send_message(bot, chat_id, message_id, f"❌ Произошла ошибка при отправке файла отчета.", **kwargs_edit)
             finally:
                  if report_file:
                      try: report_file.close()
                      except Exception: pass # Ошибки закрытия игнорируем
         elif path and not os.path.exists(path):
             logger.error(f"Функция create_bookings_report_file вернула путь {path}, но файл не существует.")
             edit_or_send_message(bot, chat_id, message_id, f"❌ Ошибка: Не удалось создать файл отчета.", **kwargs_edit)
         else: # path is None
             logger.error(f"Не удалось создать файл отчета для фильтра '{f_details}' (admin {user_id}).")
             edit_or_send_message(bot, chat_id, message_id, f"❌ Не удалось создать файл отчета.", **kwargs_edit)
     except Exception as e_report:
         logger.error(f"Критическая ошибка при генерации или отправке отчета /all ({f_details}, admin {user_id}): {e_report}", exc_info=True)
         edit_or_send_message(bot, chat_id, message_id, f"❌ Произошла критическая ошибка при формировании отчета.", **kwargs_edit)
     finally:
         # Удаление временного файла отчета (если он был создан)
         if path and os.path.exists(path):
             try: os.remove(path); logger.debug(f"Временный файл отчета {path} удален.")
             except OSError as e_remove: logger.error(f"Ошибка при удалении временного файла отчета {path}: {e_remove}")

# --- Обработчики удаления комнаты (Адаптировано) ---
def handle_cr_delete_select( # <-- Переименовано
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    cr_id_str: str = cb_data[len(const.CB_CR_DELETE_SELECT):] # <-- Используем префикс CR
    cr_id: Optional[int] = None
    try: cr_id = int(cr_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID комнаты из callback '{cb_data}' (admin {user_id})")
        try: bot.answer_callback_query(call.id, "Ошибка ID комнаты.", show_alert=True)
        except Exception: pass
        return
    logger.info(f"Admin {user_id} выбрал комнату {cr_id} для возможного удаления.")
    try: bot.answer_callback_query(call.id)
    except Exception: pass
    kwargs_edit: Dict[str, Any] = {}
    cr_info: Optional[Dict] = None
    cr_name: str = f'ID {cr_id}'
    has_bookings: bool = True # Считаем, что используется, пока не доказано обратное
    try:
        cr_info = room_service.get_conference_room_info_by_id(db, cr_id) # <-- Сервис комнат
        if not cr_info:
            logger.warning(f"Комната {cr_id} не найдена при попытке удаления (admin {user_id}).")
            try: bot.answer_callback_query(call.id, "Комната не найдена.", show_alert=True)
            except Exception: pass
            edit_or_send_message(bot, chat_id, message_id, const.MSG_CR_DELETE_FAIL_NOT_FOUND, reply_markup=None, **kwargs_edit) # <-- Константа CR
            return
        cr_name = cr_info.get('cr_name', f'ID {cr_id}') # <-- Поле cr_name
        has_bookings = room_service.check_conference_room_usage(db, cr_id) # <-- Сервис комнат
    except Exception as e_check:
        logger.error(f"Ошибка при проверке комнаты {cr_id} перед удалением (admin {user_id}): {e_check}", exc_info=True)
        try: bot.answer_callback_query(call.id, "Ошибка проверки комнаты.", show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return

    if has_bookings:
        error_msg: str = const.MSG_CR_DELETE_FAIL_USED.format(cr_name=f"'{cr_name}'") # <-- Константа и имя CR
        logger.info(f"Попытка удаления используемой комнаты {cr_id} ('{cr_name}') админом {user_id}.")
        try: bot.answer_callback_query(call.id, "Комната используется!", show_alert=True)
        except Exception: pass
        edit_or_send_message(bot, chat_id, message_id, error_msg, reply_markup=None, **kwargs_edit)
        return

    # Предлагаем подтвердить удаление
    confirm_text: str = (f"❓ Вы уверены, что хотите удалить переговорную '{cr_name}' (ID: {cr_id})?\n\n" # <-- Текст CR
                    f"❗ **Это действие необратимо!**")
    confirm_callback: str = f"{const.CB_CR_DELETE_CONFIRM}{cr_id}" # <-- Константа CR
    cancel_callback: str = const.CB_ACTION_CANCEL + "delete_cr" # Контекст для отмены
    markup: types.InlineKeyboardMarkup = keyboards.generate_confirmation_keyboard(confirm_callback, cancel_callback, confirm_text="✅ Да, удалить", cancel_text="❌ Нет, отмена")
    edit_or_send_message(bot, chat_id, message_id, confirm_text, reply_markup=markup, parse_mode="Markdown", **kwargs_edit)

def handle_cr_delete_confirm( # <-- Переименовано
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    user_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    cb_data: str = call.data
    cr_id_str: str = cb_data[len(const.CB_CR_DELETE_CONFIRM):] # <-- Префикс CR
    cr_id: Optional[int] = None
    try: cr_id = int(cr_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID комнаты из callback '{cb_data}' при подтверждении удаления (admin {user_id})")
        try: bot.answer_callback_query(call.id, "Ошибка ID комнаты.", show_alert=True)
        except Exception: pass
        return
    logger.info(f"Admin {user_id} подтвердил удаление комнаты {cr_id}.")
    try: bot.answer_callback_query(call.id, "Удаляю комнату...")
    except Exception: pass
    success: bool = False
    msg: str = f"Не удалось удалить комнату ID {cr_id}."
    try:
        success, msg = room_service.delete_conference_room_if_unused(db, cr_id) # <-- Сервис комнат
    except Exception as e_delete:
        logger.error(f"Ошибка при выполнении удаления комнаты {cr_id} (admin {user_id}): {e_delete}", exc_info=True)
        success = False
        msg = const.MSG_ERROR_GENERAL

    if msg is None: logger.error(f"delete_conference_room_if_unused не вернул сообщение для ID {cr_id}"); msg = const.MSG_CR_DELETE_FAIL_DB # <-- Константа CR

    kwargs_edit: Dict[str, Any] = {'reply_markup': None}
    edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)
    # Здесь можно добавить обновление списка комнат, если нужно, но обычно сообщение об успехе/ошибке достаточно

# --- Обработчики кнопок "Отмена" для админских диалогов (Адаптировано) ---
def handle_cancel_delete_cr( # <-- Переименовано
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    kwargs_edit: Dict[str, Any] = {}
    logger.debug(f"Отмена подтверждения удаления комнаты (admin {admin_id}), возврат к списку. Msg: {message_id}")
    all_rooms: Optional[List[Dict]] = None
    markup: Optional[types.InlineKeyboardMarkup] = None
    try:
        all_rooms = room_service.get_all_conference_rooms(db) # <-- Сервис и данные комнат
        if all_rooms:
            markup = keyboards.generate_conference_room_list_with_delete_keyboard(all_rooms) # <-- Клавиатура комнат
            edit_or_send_message(bot, chat_id, message_id, "Удаление отменено. Выберите комнату для удаления:", reply_markup=markup, **kwargs_edit) # <-- Текст для комнат
        else:
            edit_or_send_message(bot, chat_id, message_id, "Удаление отменено. Нет доступных комнат для удаления.", reply_markup=None, **kwargs_edit) # <-- Текст для комнат
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку комнат после отмены удаления (admin {admin_id}): {e}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, "Удаление отменено. Ошибка загрузки списка.", reply_markup=None, **kwargs_edit)

def handle_cancel_admin_cancel(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    kwargs_edit: Dict[str, Any] = {}
    logger.debug(f"Отмена подтверждения админской отмены брони (admin {admin_id}), возврат к списку. Msg: {message_id}")
    active_bookings: Optional[List[Dict]] = None
    markup: Optional[types.InlineKeyboardMarkup] = None
    try:
        active_bookings = bookingService.get_all_active_bookings_for_admin_keyboard(db) # Уже адаптирован
        if active_bookings:
            markup = keyboards.generate_admin_cancel_keyboard(active_bookings) # Уже адаптирован
            edit_or_send_message(bot, chat_id, message_id, "Отмена действия отменена. Выберите бронирование для принудительной отмены:", reply_markup=markup, **kwargs_edit)
        else:
            edit_or_send_message(bot, chat_id, message_id, "Отмена действия отменена. Нет активных бронирований для отмены.", reply_markup=None, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку броней после отмены админской отмены (admin {admin_id}): {e}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, "Отмена действия отменена. Ошибка загрузки списка броней.", reply_markup=None, **kwargs_edit)

def handle_cancel_manage_user(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
):
    admin_id: int = call.from_user.id
    chat_id: int = call.message.chat.id
    message_id: int = call.message.message_id
    kwargs_edit: Dict[str, Any] = {}
    logger.debug(f"Отмена выбора действия для пользователя (admin {admin_id}), возврат к списку. Msg: {message_id}")
    users_list: Optional[List[Dict]] = None
    markup: Optional[types.InlineKeyboardMarkup] = None
    try:
        users_list = userService.get_all_users(db, include_inactive=True)
        if users_list:
            markup = keyboards.generate_user_management_keyboard(users_list) # Не зависит от комнат
            edit_or_send_message(bot, chat_id, message_id, "Действие отменено. Выберите пользователя для управления:", reply_markup=markup, **kwargs_edit)
        else:
            edit_or_send_message(bot, chat_id, message_id, "Действие отменено. Нет пользователей для управления.", reply_markup=None, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку пользователей после отмены управления (admin {admin_id}): {e}", exc_info=True)
        edit_or_send_message(bot, chat_id, message_id, "Действие отменено. Ошибка загрузки списка пользователей.", reply_markup=None, **kwargs_edit)

# --- END OF FILE handlers/callbacks/admin_callbacks.py ---