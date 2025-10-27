# handlers/callbacks/notification_callbacks.py
"""
Обработчики callback-запросов, связанных с уведомлениями бота для WSB.
"""
import telebot
from telebot import apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional

try:
    from bot_app import bot as global_bot_instance
    from bot_app import active_timers as global_active_timers
except ImportError:
    critical_error_msg_ncb = "КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать компоненты из bot_app.py (WSB NotificationCallbacks)."
    try:
        from logger import logger; logger.critical(critical_error_msg_ncb)
    except ImportError:
        import sys; sys.stderr.write(f"CRITICAL: {critical_error_msg_ncb}\n")
    global_bot_instance, global_active_timers = None, {}

from logger import logger
import constants as const
import services.notification_service as notification_service
from utils.message_utils import edit_or_send_message
#from .booking_callbacks import handle_user_extend_select_booking


def register_notification_callback_handlers(bot_param: telebot.TeleBot):
    """Регистрирует обработчики колбэков для уведомлений."""

    # Используем global_bot_instance, bot_param здесь для консистентности сигнатуры, если понадобится

    @global_bot_instance.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_CONFIRM_START))
    def handle_confirm_start_callback(call: CallbackQuery):
        if not global_bot_instance:
            logger.error("global_bot_instance не инициализирован в handle_confirm_start_callback.")
            return

        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        booking_id_str = call.data[len(const.CB_BOOK_CONFIRM_START):]
        booking_id: Optional[int] = None
        try:
            booking_id = int(booking_id_str)
        except ValueError:
            logger.error(f"Неверный booking_id '{booking_id_str}' в CB_BOOK_CONFIRM_START от user {user_id}")
            try:
                global_bot_instance.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            except apihelper.ApiTelegramException:
                pass
            return

        logger.info(f"User {user_id} подтверждает бронь {booking_id} из уведомления.")
        success = False
        try:
            success = notification_service.confirm_booking_callback_logic(booking_id, user_id)
        except Exception as e_confirm_logic:
            logger.error(
                f"Ошибка в notification_service.confirm_booking_callback_logic для {booking_id}, user {user_id}: {e_confirm_logic}",
                exc_info=True)
            success = False

        if success:
            try:
                global_bot_instance.answer_callback_query(call.id, const.MSG_BOOKING_CONFIRMED)
            except apihelper.ApiTelegramException:
                pass

            confirmed_booking_info = notification_service.booking_service.find_booking_by_id(
                notification_service.global_db_instance, booking_id)
            if confirmed_booking_info:
                equip_name = confirmed_booking_info.get('name_equip', 'Ваше')
                cat_name = confirmed_booking_info.get('name_cat', '')
                time_interval = confirmed_booking_info.get('time_interval', 'N/A')
                msg_text = (f"✅ Вы подтвердили начало использования оборудования '{equip_name}' "
                            f"{'(категория: ' + cat_name + ')' if cat_name else ''} "
                            f"на время {time_interval}.")
            else:
                msg_text = f"✅ {const.MSG_BOOKING_CONFIRMED}"

            edit_or_send_message(
                global_bot_instance, chat_id, message_id,
                text=msg_text,
                reply_markup=None, parse_mode="Markdown"
            )
        else:
            alert_msg_fail = "Не удалось подтвердить. Возможно, время вышло или бронь уже обработана/отменена."
            try:
                global_bot_instance.answer_callback_query(call.id, alert_msg_fail, show_alert=True)
            except apihelper.ApiTelegramException:
                pass
            edit_or_send_message(global_bot_instance, chat_id, message_id, text=alert_msg_fail, reply_markup=None)

    @global_bot_instance.callback_query_handler(func=lambda call: call.data.startswith(const.CB_NOTIFY_EXTEND_PROMPT))
    def handle_notify_extend_prompt_callback(call: CallbackQuery):
        if not global_bot_instance:
            logger.error("global_bot_instance не инициализирован в handle_notify_extend_prompt_callback.")
            return

        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        booking_id_str = call.data[len(const.CB_NOTIFY_EXTEND_PROMPT):]
        booking_id: Optional[int] = None
        try:
            booking_id = int(booking_id_str)
        except ValueError:
            logger.error(f"Неверный booking_id '{booking_id_str}' в CB_NOTIFY_EXTEND_PROMPT от user {user_id}")
            try:
                global_bot_instance.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            except apihelper.ApiTelegramException:
                pass
            return

        logger.info(f"User {user_id} выбрал бронь {booking_id} для продления (из уведомления)")

        ui_timer = global_active_timers.pop(booking_id, None)
        if ui_timer:
            try:
                ui_timer.cancel()
                logger.info(f"UI-таймер отмены продления для {booking_id} отменен (нажал 'Продлить').")
            except Exception as e_cancel_ui_timer:
                logger.error(f"Ошибка отмены UI-таймера продления {booking_id}: {e_cancel_ui_timer}")
        else:
            logger.warning(f"UI-таймер отмены продления для {booking_id} не найден при нажатии 'Продлить'.")

        try:
            handle_user_extend_select_booking(call)  # <--- ИСПРАВЛЕНО: Вызов корректной функции
        except Exception as e_call_extend_helper:
            logger.error(
                f"Ошибка вызова handle_user_extend_select_booking из handle_notify_extend_prompt_callback для {booking_id}: {e_call_extend_helper}",
                exc_info=True)
            try:
                global_bot_instance.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
            except apihelper.ApiTelegramException:
                pass
            edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)

    @global_bot_instance.callback_query_handler(func=lambda call: call.data.startswith(const.CB_NOTIFY_DECLINE_EXT))
    def handle_notify_decline_extend_callback(call: CallbackQuery):
        if not global_bot_instance:
            logger.error("global_bot_instance не инициализирован в handle_notify_decline_extend_callback.")
            return

        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        booking_id_str = call.data[len(const.CB_NOTIFY_DECLINE_EXT):]
        booking_id: Optional[int] = None
        try:
            booking_id = int(booking_id_str)
        except ValueError:
            logger.error(f"Неверный booking_id '{booking_id_str}' в CB_NOTIFY_DECLINE_EXT от user {user_id}")
            try:
                global_bot_instance.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            except apihelper.ApiTelegramException:
                pass
            return

        logger.info(f"User {user_id} отказался продлевать бронь {booking_id} из уведомления.")

        ui_timer_decline = global_active_timers.pop(booking_id, None)
        if ui_timer_decline:
            try:
                ui_timer_decline.cancel()
                logger.info(f"UI-таймер отмены продления для {booking_id} отменен (нажал 'Отмена').")
            except Exception as e_cancel_ui_timer_dec:
                logger.error(f"Ошибка отмены UI-таймера продления {booking_id} (отказ): {e_cancel_ui_timer_dec}")
        else:
            logger.warning(f"UI-таймер отмены продления для {booking_id} не найден при нажатии 'Отмена'.")

        try:
            global_bot_instance.answer_callback_query(call.id, "Хорошо, бронирование завершится по расписанию.")
        except apihelper.ApiTelegramException:
            pass

        try:
            edit_or_send_message(
                global_bot_instance, chat_id, message_id,
                text=const.MSG_EXTEND_ACTION_DECLINED_BY_USER,
                reply_markup=None,
                parse_mode="Markdown"
            )
        except Exception as e_edit_decline_msg:
            logger.warning(
                f"Не удалось отредактировать сообщение {message_id} после отказа от продления {booking_id}: {e_edit_decline_msg}")

    logger.info("Обработчики колбэков уведомлений WSB зарегистрированы.")