# handlers/callbacks/booking_callbacks.py
import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple, List
from datetime import datetime, date, time, timedelta

from database import Database  # Прямой импорт Database, а не db_connection
from logger import logger
import constants as const
import services.booking_service as booking_service
import services.equipment_service as equipment_service  # Нужен для получения инфо о категориях/оборудовании
#import services.notification_service as notification_service
from utils import keyboards
from apscheduler.schedulers.background import BackgroundScheduler  # Для тайпинга

# Импортируем user_booking_states и clear_user_state из states.py
from states import user_booking_states, clear_user_state


# Вспомогательная функция (можно вынести в utils.message_utils)
def _edit_or_send_message(bot_instance: telebot.TeleBot, chat_id: int, message_id: Optional[int], text: str,
                          reply_markup=None, parse_mode=None):
    try:
        if message_id:
            bot_instance.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup,
                                           parse_mode=parse_mode)
        else:
            bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except telebot.apihelper.ApiTelegramException as e:
        if "message to edit not found" in str(e).lower() or \
                "message is not modified" in str(e).lower() or \
                "message can't be edited" in str(e).lower():
            logger.warning(
                f"Сообщение {message_id} не найдено/не изменено/не может быть отредактировано, отправка нового. Ошибка: {e}")
            try:  # Попытка отправить новое, если редактирование не удалось
                bot_instance.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception as e_send_new:
                logger.error(
                    f"Не удалось отправить новое сообщение после ошибки редактирования (chat_id: {chat_id}): {e_send_new}")
        else:
            logger.error(
                f"Ошибка API при редактировании/отправке сообщения (chat_id: {chat_id}, msg_id: {message_id}): {e}")
    except Exception as e_gen:
        logger.error(
            f"Общая ошибка при редактировании/отправке сообщения (chat_id: {chat_id}, msg_id: {message_id}): {e_gen}",
            exc_info=True)


def register_booking_callback_handlers(
        bot: telebot.TeleBot,
        db: Database,  # Принимаем экземпляр Database
        scheduler: BackgroundScheduler,  # Используем BackgroundScheduler для тайпинга
        active_timers: Dict[int, Any],  # Эти зависимости нужны для notification_service
        scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """Регистрирует обработчики колбэков, связанные с процессом бронирования пользователя."""

    # === Обработчики для процесса бронирования пользователя (WSB) ===

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_SELECT_CATEGORY))
    def handle_booking_select_category(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or \
                user_booking_states[user_id].get('step') != const.STATE_BOOKING_SELECT_CATEGORY:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг. Начните заново.",
                                      show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        try:
            category_id = int(call.data[len(const.CB_BOOK_SELECT_CATEGORY):])
        except ValueError:
            logger.error(f"Ошибка парсинга category_id из callback: {call.data} для user {user_id}")
            bot.answer_callback_query(call.id, "Ошибка данных категории.", show_alert=True)
            return

        category_info = equipment_service.get_category_by_id(db, category_id)
        if not category_info:
            bot.answer_callback_query(call.id, "Выбранная категория не найдена.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, "Ошибка: категория не найдена.", reply_markup=None)
            return

        bot.answer_callback_query(call.id, f"Категория '{category_info['name_cat']}' выбрана.")
        user_booking_states[user_id]['data']['category_id'] = category_id
        user_booking_states[user_id]['data']['category_name'] = category_info['name_cat']
        user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_EQUIPMENT

        equipments = equipment_service.get_equipment_by_category(db, category_id)
        markup = keyboards.generate_equipment_keyboard_for_booking(equipments, category_info['name_cat'])
        prompt_text = const.MSG_BOOKING_STEP_2_SELECT_EQUIPMENT.format(category_name=category_info['name_cat'])
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_SELECT_EQUIPMENT))
    def handle_booking_select_equipment(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or \
                user_booking_states[user_id].get('step') != const.STATE_BOOKING_SELECT_EQUIPMENT:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг. Начните заново.",
                                      show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        try:
            equipment_id = int(call.data[len(const.CB_BOOK_SELECT_EQUIPMENT):])
        except ValueError:
            logger.error(f"Ошибка парсинга equipment_id из callback: {call.data} для user {user_id}")
            bot.answer_callback_query(call.id, "Ошибка данных оборудования.", show_alert=True)
            return

        equipment_info = equipment_service.get_equipment_details_by_id(db, equipment_id)
        if not equipment_info:
            bot.answer_callback_query(call.id, "Выбранное оборудование не найдено.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, "Ошибка: оборудование не найдено.", reply_markup=None)
            return

        bot.answer_callback_query(call.id, f"Оборудование '{equipment_info['name_equip']}' выбрано.")
        user_booking_states[user_id]['data']['equip_id'] = equipment_id
        user_booking_states[user_id]['data']['equip_name'] = equipment_info['name_equip']
        user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_DATE

        markup = keyboards.generate_date_keyboard_for_booking()
        prompt_text = const.MSG_BOOKING_STEP_3_SELECT_DATE
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_SELECT_DATE))
    def handle_booking_select_date(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or user_booking_states[user_id].get(
                'step') != const.STATE_BOOKING_SELECT_DATE:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        selected_date_str_cb = call.data[len(const.CB_BOOK_SELECT_DATE):]  # YYYY-MM-DD
        try:
            selected_date_obj = datetime.strptime(selected_date_str_cb, '%Y-%m-%d').date()
        except ValueError:
            logger.error(f"Неверный формат даты '{selected_date_str_cb}' от user {user_id}")
            bot.answer_callback_query(call.id, "Ошибка формата даты.", show_alert=True)
            return

        bot.answer_callback_query(call.id, f"Дата {selected_date_obj.strftime('%d.%m.%Y')} выбрана.")
        user_booking_states[user_id]['data']['selected_date'] = selected_date_obj
        user_booking_states[user_id]['data']['selected_date_str_for_service'] = selected_date_obj.strftime(
            '%d-%m-%Y')  # Для create_booking
        user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_SLOT

        equip_id = user_booking_states[user_id]['data'].get('equip_id')
        if not equip_id:
            logger.error(f"Отсутствует equip_id в состоянии user {user_id} на шаге выбора даты.")
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)
            clear_user_state(user_id)
            return

        available_slots = booking_service.calculate_available_slots(db, equip_id, selected_date_obj)
        markup = keyboards.generate_available_slots_keyboard_for_booking(available_slots)
        prompt_text = const.MSG_BOOKING_STEP_4_SELECT_SLOT
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_SELECT_SLOT))
    def handle_booking_select_slot(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or user_booking_states[user_id].get(
                'step') != const.STATE_BOOKING_SELECT_SLOT:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        try:
            selected_slot_index = int(call.data[len(const.CB_BOOK_SELECT_SLOT):])
        except ValueError:
            logger.error(f"Неверный индекс слота из callback: {call.data} для user {user_id}")
            bot.answer_callback_query(call.id, "Ошибка выбора слота.", show_alert=True)
            return

        equip_id = user_booking_states[user_id]['data'].get('equip_id')
        selected_date_obj = user_booking_states[user_id]['data'].get('selected_date')
        if not equip_id or not selected_date_obj:
            logger.error(f"Отсутствуют equip_id или selected_date в состоянии user {user_id} на шаге выбора слота.")
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)
            clear_user_state(user_id)
            return

        all_available_slots = booking_service.calculate_available_slots(db, equip_id, selected_date_obj)
        if not (0 <= selected_slot_index < len(all_available_slots)):
            logger.error(
                f"Индекс слота {selected_slot_index} вне диапазона для user {user_id}. Всего слотов: {len(all_available_slots)}")
            bot.answer_callback_query(call.id, "Выбранный слот недействителен.", show_alert=True)
            # Показываем снова клавиатуру слотов
            markup_slots_again = keyboards.generate_available_slots_keyboard_for_booking(all_available_slots)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_NO_SLOTS_AVAILABLE_FOR_EQUIPMENT,
                                  reply_markup=markup_slots_again)
            return

        selected_slot_times_tuple = all_available_slots[selected_slot_index]  # (start_time_obj, end_time_obj)

        bot.answer_callback_query(call.id,
                                  f"Слот {booking_service._format_time(selected_slot_times_tuple[0])}-{booking_service._format_time(selected_slot_times_tuple[1])} выбран.")
        user_booking_states[user_id]['data']['selected_slot_index'] = selected_slot_index
        user_booking_states[user_id]['data']['selected_slot_times'] = selected_slot_times_tuple
        user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_START_TIME

        available_start_times_in_slot = booking_service.get_start_times_in_slot(selected_slot_times_tuple,
                                                                                selected_date_obj)
        markup = keyboards.generate_start_time_keyboard_for_booking(selected_slot_index, available_start_times_in_slot)
        prompt_text = const.MSG_BOOKING_STEP_5_SELECT_START_TIME.format(
            start_slot=booking_service._format_time(selected_slot_times_tuple[0]),
            end_slot=booking_service._format_time(selected_slot_times_tuple[1])
        )
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_SELECT_TIME))
    def handle_booking_select_start_time(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or user_booking_states[user_id].get(
                'step') != const.STATE_BOOKING_SELECT_START_TIME:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        callback_data_payload = call.data[len(const.CB_BOOK_SELECT_TIME):]
        try:
            parts = callback_data_payload.split('_')
            if len(parts) != 2: raise ValueError("Incorrect payload format for start time")
            selected_slot_idx_from_cb = int(parts[0])
            selected_start_time_str = parts[1]  # HH:MM
            selected_start_time_obj = datetime.strptime(selected_start_time_str, '%H:%M').time()
        except ValueError as e:
            logger.error(
                f"Неверный формат времени начала из callback: {callback_data_payload} для user {user_id}. Ошибка: {e}")
            bot.answer_callback_query(call.id, "Ошибка формата времени.", show_alert=True)
            return

        saved_slot_idx = user_booking_states[user_id]['data'].get('selected_slot_index')
        if saved_slot_idx != selected_slot_idx_from_cb:  # Важная проверка
            logger.warning(
                f"Несовпадение индекса слота при выборе времени начала: CB={selected_slot_idx_from_cb}, State={saved_slot_idx} для user {user_id}")
            bot.answer_callback_query(call.id, "Ошибка данных сессии. Попробуйте выбрать слот заново.", show_alert=True)
            # Можно вернуть на шаг выбора слота
            return

        selected_slot_times = user_booking_states[user_id]['data'].get('selected_slot_times')
        selected_date_obj = user_booking_states[user_id]['data'].get('selected_date')

        if not selected_slot_times or not selected_date_obj:
            logger.error(
                f"Отсутствуют selected_slot_times или selected_date в состоянии user {user_id} на шаге выбора времени начала.")
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)
            clear_user_state(user_id)
            return

        bot.answer_callback_query(call.id, f"Время начала {selected_start_time_str} выбрано.")
        user_booking_states[user_id]['data']['selected_start_time_str'] = selected_start_time_str
        user_booking_states[user_id]['data']['selected_start_time_obj'] = selected_start_time_obj
        user_booking_states[user_id]['step'] = const.STATE_BOOKING_SELECT_DURATION

        available_durations = booking_service.get_available_durations_for_start_time(
            selected_start_time_obj,
            selected_date_obj,
            selected_slot_times[1]  # Время окончания слота (time_obj)
        )
        markup = keyboards.generate_duration_keyboard_for_booking(
            available_durations,
            saved_slot_idx,
            selected_start_time_str
        )
        prompt_text = const.MSG_BOOKING_STEP_6_SELECT_DURATION.format(
            end_slot=booking_service._format_time(selected_slot_times[1]))
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_SELECT_DURATION))
    def handle_booking_select_duration(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or user_booking_states[user_id].get(
                'step') != const.STATE_BOOKING_SELECT_DURATION:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        callback_data_payload = call.data[len(const.CB_BOOK_SELECT_DURATION):]
        try:
            parts = callback_data_payload.split('_')
            if len(parts) != 3: raise ValueError("Incorrect payload format for duration")
            # slot_idx_from_cb = int(parts[0]) # Можно проверить
            # start_time_str_from_cb = parts[1] # Можно проверить
            selected_duration_str_for_service = parts[2]  # HH:MM
            datetime.strptime(selected_duration_str_for_service, '%H:%M')
        except ValueError as e:
            logger.error(
                f"Неверный формат длительности из callback: {callback_data_payload} для user {user_id}. Ошибка: {e}")
            bot.answer_callback_query(call.id, "Ошибка формата длительности.", show_alert=True)
            return

        bot.answer_callback_query(call.id, f"Длительность {selected_duration_str_for_service} выбрана.")
        user_booking_states[user_id]['data']['selected_duration_str_for_service'] = selected_duration_str_for_service
        user_booking_states[user_id]['step'] = const.STATE_BOOKING_CONFIRM_BOOKING

        data = user_booking_states[user_id]['data']
        category_name = data.get('category_name', '??')
        equip_name = data.get('equip_name', '??')
        s_date_str_display = data['selected_date'].strftime('%d.%m.%Y')  # Формат для отображения
        s_start_time_str_display = data.get('selected_start_time_str', '??:??')

        try:
            start_dt = datetime.combine(data['selected_date'], data['selected_start_time_obj'])
            h_dur, m_dur = map(int, selected_duration_str_for_service.split(':'))
            duration_td = timedelta(hours=h_dur, minutes=m_dur)
            end_dt = start_dt + duration_td
            s_end_time_str_display = end_dt.strftime('%H:%M')
            duration_display_text = f"{h_dur}ч {m_dur:02d}м"
        except Exception as e_calc_end:
            logger.error(f"Ошибка расчета времени окончания для подтверждения (user {user_id}): {e_calc_end}")
            s_end_time_str_display = '??:??'
            duration_display_text = selected_duration_str_for_service  # Показываем как есть, если ошибка

        confirm_text = const.MSG_BOOKING_CONFIRM_DETAILS_TEXT.format(
            category_name=category_name,
            equip_name=equip_name,
            date=s_date_str_display,
            start_time=s_start_time_str_display,
            end_time=s_end_time_str_display,
            duration=duration_display_text
        )
        markup = keyboards.generate_final_booking_confirmation_keyboard()
        _edit_or_send_message(bot, chat_id, message_id, confirm_text, reply_markup=markup, parse_mode='Markdown')

    @bot.callback_query_handler(func=lambda call: call.data == const.CB_BOOK_CONFIRM_FINAL)
    def handle_booking_final_confirm(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        if user_id not in user_booking_states or user_booking_states[user_id].get(
                'step') != const.STATE_BOOKING_CONFIRM_BOOKING:
            bot.answer_callback_query(call.id, "Сессия бронирования истекла или неверный шаг.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_INVALID_STATE, reply_markup=None)
            return

        bot.answer_callback_query(call.id, "Создаю бронирование...")

        data = user_booking_states[user_id]['data']
        equip_id = data.get('equip_id')
        # Используем selected_date_str_for_service, т.к. create_booking ожидает ДД-ММ-ГГГГ
        date_str_for_service = data.get('selected_date_str_for_service')
        start_time_str_for_service = data.get('selected_start_time_str')  # HH:MM
        duration_str_for_service = data.get('selected_duration_str_for_service')  # HH:MM

        if not all([equip_id, date_str_for_service, start_time_str_for_service, duration_str_for_service]):
            logger.error(f"Неполные данные для создания брони в состоянии user {user_id}: {data}")
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None)
            clear_user_state(user_id)
            return

        success, msg_from_service, new_booking_id = booking_service.create_booking(
            db, user_id, equip_id, date_str_for_service, start_time_str_for_service, duration_str_for_service
        )

        final_user_message = msg_from_service
        if success and new_booking_id:
            # Если бронь создана со статусом pending_confirmation (как указано в create_booking)
            timeout_minutes = const.BOOKING_CONFIRMATION_TIMEOUT_SECONDS // 60
            final_user_message = const.MSG_BOOKING_NEEDS_CONFIRMATION_TEXT.format(timeout_min=timeout_minutes)
            # Планируем задачи: автоотмена и уведомление о необходимости подтвердить
            notification_service.schedule_booking_confirmation_flow(
                db, bot, scheduler, scheduled_jobs_registry, new_booking_id, user_id
            )
        elif not success and msg_from_service == const.MSG_BOOKING_FAIL_TIME_OVERLAP:
            # Если ошибка из-за пересечения, можно вернуть на шаг выбора слота/времени
            # Для этого нужно сохранить message_id предыдущего шага и передать его
            # Пока просто выводим сообщение об ошибке
            pass  # final_user_message уже содержит сообщение об ошибке

        _edit_or_send_message(bot, chat_id, message_id, final_user_message, reply_markup=None, parse_mode='Markdown')
        clear_user_state(user_id)

    @bot.callback_query_handler(func=lambda call: call.data == const.CB_BOOK_CANCEL_PROCESS)
    def handle_booking_cancel_process(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_PROCESS_CANCELLED_BY_USER, reply_markup=None,
                              parse_mode='Markdown')
        clear_user_state(user_id)

    # === Обработчики отмены, завершения, продления существующей брони ===

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_CANCEL_SELECT_BOOKING))
    def handle_user_cancel_select_booking(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        try:
            booking_id = int(call.data[len(const.CB_CANCEL_SELECT_BOOKING):])
        except ValueError:
            logger.error(f"Invalid booking_id in CB_CANCEL_SELECT_BOOKING: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            return

        logger.info(f"User {user_id} selected booking {booking_id} for cancellation.")
        bot.answer_callback_query(call.id, "Отменяю бронирование...")

        success, msg, _ = booking_service.cancel_booking(db, booking_id,
                                                         user_id=user_id)  # is_admin_cancel=False по умолчанию
        _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown")

        if success:
            try:
                notification_service.cleanup_booking_notifications(scheduler, scheduled_jobs_registry, booking_id)
            except Exception as e_clean:
                logger.error(f"Error cleaning up notifications for cancelled booking {booking_id}: {e_clean}",
                             exc_info=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_FINISH_SELECT_BOOKING))
    def handle_user_finish_select_booking(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        try:
            booking_id = int(call.data[len(const.CB_FINISH_SELECT_BOOKING):])
        except ValueError:
            logger.error(f"Invalid booking_id in CB_FINISH_SELECT_BOOKING: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            return

        logger.info(f"User {user_id} selected booking {booking_id} to finish.")
        bot.answer_callback_query(call.id, "Завершаю бронирование...")

        success, msg = booking_service.finish_booking(db, booking_id, user_id)
        _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown")

        if success:
            try:
                notification_service.cleanup_booking_notifications(scheduler, scheduled_jobs_registry, booking_id)
            except Exception as e_clean:
                logger.error(f"Error cleaning up notifications for finished booking {booking_id}: {e_clean}",
                             exc_info=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_EXTEND_SELECT_BOOKING) or \
                                                  call.data.startswith(const.CB_NOTIFY_EXTEND_PROMPT))
    def handle_user_extend_select_booking(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        booking_id_str = ""
        if call.data.startswith(const.CB_EXTEND_SELECT_BOOKING):
            booking_id_str = call.data[len(const.CB_EXTEND_SELECT_BOOKING):]
        elif call.data.startswith(const.CB_NOTIFY_EXTEND_PROMPT):
            booking_id_str = call.data[len(const.CB_NOTIFY_EXTEND_PROMPT):]

        try:
            booking_id = int(booking_id_str)
        except ValueError:
            logger.error(f"Invalid booking_id for extend: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "Проверяю возможность продления...")
        booking_info = booking_service.find_booking_by_id(db, booking_id)

        error_msg = None
        if not booking_info:
            error_msg = const.MSG_EXTEND_FAIL_BOOKING_NOT_FOUND
        elif booking_info.get('user_id') != user_id:
            error_msg = const.MSG_EXTEND_FAIL_NOT_YOUR_BOOKING
        elif booking_info.get('status') != 'active':
            error_msg = const.MSG_EXTEND_FAIL_BOOKING_NOT_ACTIVE
        elif not isinstance(booking_info.get('time_end'), datetime) or \
                booking_info.get('time_end') <= datetime.now(
            booking_info.get('time_end').tzinfo):  # Сравнение с учетом таймзоны
            error_msg = const.MSG_EXTEND_FAIL_BOOKING_ALREADY_ENDED

        if error_msg:
            _edit_or_send_message(bot, chat_id, message_id, error_msg, reply_markup=None)
            return

        current_end_dt = booking_info['time_end']
        equip_id = booking_info['equip_id']

        available_extend_durations = booking_service.get_available_extend_durations(db, equip_id, current_end_dt)

        if not available_extend_durations:
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_EXTEND_FAIL_NO_AVAILABLE_TIME, reply_markup=None)
            return

        markup = keyboards.generate_extend_time_options_keyboard(booking_id, available_extend_durations)
        prompt_text = f"Текущее окончание: {current_end_dt.strftime('%H:%M')}. Выберите на сколько продлить:"
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_EXTEND_SELECT_TIME))
    def handle_user_extend_select_time(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id

        data_part = call.data[len(const.CB_EXTEND_SELECT_TIME):]
        parts = data_part.split('_')
        if len(parts) != 2:
            logger.error(f"Invalid format for CB_EXTEND_SELECT_TIME: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка формата данных.", show_alert=True)
            return

        try:
            booking_id = int(parts[0])
            extension_str = parts[1]  # HH:MM
            datetime.strptime(extension_str, "%H:%M")
        except ValueError:
            logger.error(f"Invalid booking_id or extension_str in CB_EXTEND_SELECT_TIME: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка данных продления.", show_alert=True)
            return

        bot.answer_callback_query(call.id, f"Продлеваю на {extension_str}...")

        booking_info_recheck = booking_service.find_booking_by_id(db, booking_id)
        error_msg_recheck = None
        # ... (повторная проверка как в предыдущей версии) ...
        if not booking_info_recheck:
            error_msg_recheck = const.MSG_EXTEND_FAIL_BOOKING_NOT_FOUND
        elif booking_info_recheck.get('user_id') != user_id:
            error_msg_recheck = const.MSG_EXTEND_FAIL_NOT_YOUR_BOOKING
        # ... и т.д.

        if error_msg_recheck:
            _edit_or_send_message(bot, chat_id, message_id, error_msg_recheck, reply_markup=None)
            return

        success, msg = booking_service.extend_booking(db, booking_id, user_id, extension_str)
        _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown")

        if success:
            try:
                notification_service.schedule_all_notifications()  # Передаем глобальные экземпляры (если они так доступны)
                # или notification_service.schedule_all_notifications(db, bot, scheduler, active_timers, scheduled_jobs_registry)
            except Exception as e_reschedule:
                logger.error(f"Ошибка перепланировки уведомлений после продления брони {booking_id}: {e_reschedule}",
                             exc_info=True)

    # === Обработчики уведомлений (CB_NOTIFY_...) ===

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_NOTIFY_DECLINE_EXT))
    def handle_notify_decline_extend(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        bot.answer_callback_query(call.id, "Хорошо.")
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_EXTEND_ACTION_DECLINED_BY_USER, reply_markup=None)

    @bot.callback_query_handler(func=lambda call: call.data.startswith(const.CB_BOOK_CONFIRM_START))
    def handle_booking_confirm_start_from_notification(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        try:
            booking_id = int(call.data[len(const.CB_BOOK_CONFIRM_START):])
        except ValueError:
            logger.error(f"Invalid booking_id in CB_BOOK_CONFIRM_START: {call.data}")
            bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "Подтверждаю начало...")
        success = booking_service.confirm_start_booking(db, booking_id, user_id)

        if success:
            booking_info = booking_service.find_booking_by_id(db, booking_id)
            if booking_info:
                equip_name = booking_info.get('name_equip', 'Ваше')
                cat_name = booking_info.get('name_cat', '')
                time_interval = booking_info.get('time_interval', 'N/A')
                msg_text = (f"✅ Вы подтвердили начало использования оборудования '{equip_name}' "
                            f"{'(категория: ' + cat_name + ')' if cat_name else ''} "
                            f"на время {time_interval}.")
            else:
                msg_text = const.MSG_BOOKING_SUCCESSFULLY_CONFIRMED_ACTIVE

            _edit_or_send_message(bot, chat_id, message_id, msg_text, reply_markup=None, parse_mode='Markdown')
            notification_service.schedule_single_booking_notifications(db, bot, scheduler, active_timers,
                                                                       scheduled_jobs_registry, booking_id)
        else:
            booking_info = booking_service.find_booking_by_id(db, booking_id)
            current_status = booking_info.get('status', "неизвестен") if booking_info else "неизвестен"
            error_msg = f"Не удалось подтвердить бронь. Текущий статус: {current_status}."
            if booking_info and booking_info.get('user_id') != user_id:
                error_msg = "Это не ваше бронирование."
            elif current_status == 'active':
                error_msg = "Бронь уже была подтверждена и активна."
            _edit_or_send_message(bot, chat_id, message_id, error_msg, reply_markup=None)

    logger.info("Обработчики колбэков для бронирований WSB (пользовательских) зарегистрированы.")