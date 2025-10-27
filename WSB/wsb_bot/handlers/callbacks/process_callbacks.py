# handlers/callbacks/process_callbacks.py (WSB)
"""
Обработчик callback-запросов для пошагового процесса бронирования пользователя в WSB.
"""
import telebot  # Для аннотации типов
from telebot.types import CallbackQuery
from telebot import apihelper
from typing import Dict, Any, Optional, List  # Убрал Set, Tuple, если не используются здесь
from datetime import datetime, date, time, timedelta
import html  # Для экранирования

# --- Импортируем глобальные объекты из bot_app ---
try:
    from bot_app import bot as global_bot_instance
    from bot_app import db_connection as global_db_connection
    # scheduler, active_timers, scheduled_jobs_registry нужны, если create_booking
    # или другие функции здесь напрямую вызывают schedule_all_notifications с этими аргументами.
    # Но мы перешли на то, что schedule_all_notifications использует глобальные.
    # from bot_app import scheduler as global_scheduler
    # from bot_app import active_timers as global_active_timers
    # from bot_app import scheduled_jobs_registry as global_scheduled_jobs_registry
except ImportError:
    critical_error_msg_pcb = "КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать компоненты из bot_app.py (WSB ProcessCallbacks)."
    try:
        from logger import logger; logger.critical(critical_error_msg_pcb)
    except ImportError:
        import sys; sys.stderr.write(f"CRITICAL: {critical_error_msg_pcb}\n")
    global_bot_instance, global_db_connection = None, None

from logger import logger
import constants as const
# Сервисы будут использовать свои глобальные экземпляры или получать их
import services.booking_service as bookingService
import services.equipment_service as equipmentService
import services.notification_service as notificationService  # Для schedule_all_notifications
from utils import keyboards as keyboards_wsb  # Используем ваш keyboards.py (возможно, переименовать для ясности)
from states import user_booking_states, clear_user_state
from utils.message_utils import edit_or_send_message


# utils.time_utils, если bookingService._format_time не используется повсеместно
# from utils.time_utils import format_time, format_date


# --- Основная функция обработки шагов ---

def handle_booking_steps_wsb(
        call: CallbackQuery,
        state: Dict[str, Any]  # Текущее состояние пользователя из user_booking_states
):
    """Обрабатывает колбэки в процессе бронирования WSB на основе состояния."""
    if not global_bot_instance or not global_db_connection:
        logger.error("Глобальные компоненты (bot/db) не инициализированы в handle_booking_steps_wsb.")
        # Пытаемся ответить на коллбэк, если call.message.bot доступен
        try:
            call.message.bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        clear_user_state(call.from_user.id)
        return

    user_id = call.from_user.id
    chat_id = state.get('chat_id')
    message_id = state.get('message_id')  # ID сообщения, которое мы редактируем
    current_step = state.get('step', const.STATE_BOOKING_IDLE)
    cb_data = call.data
    user_state_data = state.get('data', {})  # Данные, собранные на предыдущих шагах

    # kwargs для edit_or_send_message
    kwargs_edit: Dict[str, Any] = {'user_id_for_state_update': user_id, 'parse_mode': "HTML"}

    logger.debug(
        f"handle_booking_steps_wsb: user={user_id}, step={current_step}, data='{cb_data}', state_data={user_state_data}")

    if not chat_id or not message_id:
        logger.error(
            f"Отсутствует chat_id ({chat_id}) или message_id ({message_id}) в состоянии user {user_id} (WSB). Callback: {cb_data}")
        try:
            global_bot_instance.answer_callback_query(call.id, "Ошибка состояния. Начните заново /booking.",
                                                    show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        clear_user_state(user_id)
        return

    # --- Отмена процесса бронирования ---
    if cb_data == const.CB_BOOK_CANCEL_PROCESS:
        logger.info(f"User {user_id} отменил процесс бронирования WSB на шаге {current_step}.")
        try:
            global_bot_instance.answer_callback_query(call.id, const.MSG_BOOKING_PROCESS_CANCELLED)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        try:
            edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_BOOKING_PROCESS_CANCELLED,
                                reply_markup=None, **kwargs_edit)
        except Exception as e_edit_cancel_proc:
            logger.error(
                f"Не удалось отредактировать сообщение при отмене бронирования user {user_id} (WSB): {e_edit_cancel_proc}")
        finally:
            clear_user_state(user_id)
        return

    # --- Обработка шагов ---
    try:
        # --- Шаг 1 WSB: Выбор категории ---
        # current_step устанавливается в user_commands.booking_start_handler
        if current_step == const.STATE_BOOKING_CATEGORY and cb_data.startswith(const.CB_BOOK_SELECT_CATEGORY):
            try:
                global_bot_instance.answer_callback_query(call.id)
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")

            category_id_str = cb_data[len(const.CB_BOOK_SELECT_CATEGORY):]
            category_id: Optional[int] = None
            try:
                category_id = int(category_id_str)
            except ValueError:
                logger.error(f"Неверный category_id '{category_id_str}' в callback от user {user_id} (WSB)")
                edit_or_send_message(global_bot_instance, chat_id, message_id, "Ошибка: Неверный ID категории.",
                                    reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)
                return

            user_state_data['category_id'] = category_id
            # equipmentService использует global_db_connection
            category_name = equipmentService.get_category_by_id(category_id) or f"Категория ID {category_id}"
            user_state_data['category_name'] = category_name
            logger.debug(f"User {user_id} выбрал категорию {category_id} ('{html.escape(category_name)}') (WSB)")

            equipment_list = equipmentService.get_equipment_by_category(category_id)
            if not equipment_list:
                logger.warning(
                    f"В категории {category_id} ('{html.escape(category_name)}') нет оборудования (user {user_id}, WSB).")
                msg_no_equip = const.MSG_NO_EQUIPMENT_IN_CATEGORY.format(category_name=html.escape(category_name))
                edit_or_send_message(global_bot_instance, chat_id, message_id, msg_no_equip, reply_markup=None,
                                     **kwargs_edit)
                clear_user_state(user_id)
                return

            markup_equip = keyboards_wsb.generate_equipment_keyboard(equipment_list, const.CB_BOOK_SELECT_EQUIPMENT,
                                                                    category_name)
            # Сообщение для следующего шага (MSG_BOOKING_STEP_2_SELECT_EQUIPMENT из constants.py WSB)
            # Оно должно быть в HTML, если category_name вставляется в <b>
            msg_text_step2 = const.MSG_BOOKING_STEP_2_EQUIPMENT  # Уже должно быть HTML с плейсхолдером
            # Если плейсхолдера нет, формируем здесь:
            # msg_text_step2 = f"<b>Шаг 2:</b> Оборудование в категории '<i>{html.escape(category_name)}</i>':"
            edit_or_send_message(global_bot_instance, chat_id, message_id, msg_text_step2, reply_markup=markup_equip,
                                 **kwargs_edit)
            state['step'] = const.STATE_BOOKING_EQUIPMENT

        # --- Шаг 2 WSB: Выбор оборудования ---
        elif current_step == const.STATE_BOOKING_EQUIPMENT and cb_data.startswith(
                const.CB_BOOK_SELECT_EQUIPMENT):
            try:
                global_bot_instance.answer_callback_query(call.id)
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")

            equipment_id_str = cb_data[len(const.CB_BOOK_SELECT_EQUIPMENT):]
            equipment_id: Optional[int] = None
            try:
                equipment_id = int(equipment_id_str)
            except ValueError:  # Обработка ошибки
                logger.error(f"Неверный equipment_id '{equipment_id_str}' в callback от user {user_id} (WSB)")
                edit_or_send_message(global_bot_instance, chat_id, message_id, "Ошибка: Неверный ID оборудования.",
                                    reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)
                return

            equipment_name = equipmentService.get_equipment_name_by_id(
                equipment_id) or f"Оборудование ID {equipment_id}"
            user_state_data['equipment_id'] = equipment_id
            user_state_data['equipment_name'] = equipment_name
            logger.debug(f"User {user_id} выбрал оборудование {equipment_id} ('{html.escape(equipment_name)}') (WSB)")

            markup_date = keyboards_wsb.generate_date_keyboard(const.CB_BOOK_SELECT_DATE)
            edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_BOOKING_STEP_3_DATE,
                                reply_markup=markup_date, **kwargs_edit)
            state['step'] = const.STATE_BOOKING_DATE

        # --- Шаг 3 WSB: Выбор даты ---
        elif current_step == const.STATE_BOOKING_DATE and cb_data.startswith(const.CB_BOOK_SELECT_DATE):
            try:
                global_bot_instance.answer_callback_query(call.id)
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")

            selected_date_str_from_cb = cb_data[len(const.CB_BOOK_SELECT_DATE):]  # Формат YYYY-MM-DD из клавиатуры
            selected_date_object: Optional[date] = None
            try:
                selected_date_object = datetime.strptime(selected_date_str_from_cb, '%Y-%m-%d').date()
            except ValueError:
                logger.error(f"Неверный формат даты '{selected_date_str_from_cb}' от user {user_id} (WSB)")
                edit_or_send_message(global_bot_instance, chat_id, message_id, "Ошибка: Неверный формат даты.",
                                    reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)
                return

            equipment_id_val = user_state_data.get('equipment_id')
            if not equipment_id_val:  # Проверка
                logger.error(f"Отсутствует equipment_id в состоянии user {user_id} на шаге даты (WSB).")
                edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE,
                                    reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)
                return

            user_state_data['selected_date_str'] = selected_date_object.strftime(
                '%d-%m-%Y')  # Сохраняем в DD-MM-YYYY для отображения
            user_state_data['selected_date_obj'] = selected_date_object
            logger.debug(
                f"User {user_id} выбрал дату {user_state_data['selected_date_str']} для оборудования {equipment_id_val} (WSB)")

            # bookingService.calculate_available_slots использует global_db
            available_slots_list = bookingService.calculate_available_slots(equipment_id_val, selected_date_object)
            user_state_data['available_slots'] = available_slots_list

            if not available_slots_list:
                edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_NO_SLOTS_AVAILABLE,
                                    reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)
                return

            # Проверка, свободен ли весь день
            is_full_day_available = False
            if len(available_slots_list) == 1:
                slot_s, slot_e = available_slots_list[0]
                # Приводим const к time, если они datetime
                ws_start = const.WORKING_HOURS_START.time() if isinstance(const.WORKING_HOURS_START,
                                                                        datetime) else const.WORKING_HOURS_START
                ws_end = const.WORKING_HOURS_END.time() if isinstance(const.WORKING_HOURS_END,
                                                                    datetime) else const.WORKING_HOURS_END
                if slot_s == ws_start and slot_e == ws_end:
                    is_full_day_available = True

            if is_full_day_available:
                full_day_slot_tuple = (const.WORKING_HOURS_START, const.WORKING_HOURS_END)
                if isinstance(full_day_slot_tuple[0], datetime):  # Убедимся, что это time объекты
                    full_day_slot_tuple = (full_day_slot_tuple[0].time(), full_day_slot_tuple[1].time())
                user_state_data['selected_slot'] = full_day_slot_tuple
                markup_time = keyboards_wsb.generate_time_keyboard_in_slot(full_day_slot_tuple, selected_date_object,
                                                                        const.CB_BOOK_SELECT_TIME)
                edit_or_send_message(global_bot_instance, chat_id, message_id,
                                    const.MSG_BOOKING_STEP_5_START_TIME, reply_markup=markup_time,
                                     **kwargs_edit)
                state['step'] = const.STATE_BOOKING_START_TIME
            else:
                markup_slots = keyboards_wsb.generate_available_slots_keyboard(available_slots_list,
                                                                            const.CB_BOOK_SELECT_SLOT)
                edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_BOOKING_STEP_4_SLOT,
                                    reply_markup=markup_slots, **kwargs_edit)
                state['step'] = const.STATE_BOOKING_SLOT

        # --- Шаг 4 WSB: Выбор слота ---
        elif current_step == const.STATE_BOOKING_SLOT and cb_data.startswith(const.CB_BOOK_SELECT_SLOT):
            try:
                global_bot_instance.answer_callback_query(call.id)
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")
            # ... (логика как в CRB, но с MSG_BOOKING_PROMPT_START_TIME_IN_SLOT (Шаг 5 WSB) и STATE_BOOKING_SELECT_START_TIME) ...
            try:
                slot_idx_str = cb_data[len(const.CB_BOOK_SELECT_SLOT):]
                slot_idx = int(slot_idx_str)
                available_slots = user_state_data.get('available_slots')
                if not isinstance(available_slots, list) or not (0 <= slot_idx < len(available_slots)):
                    raise ValueError("Неверные данные слотов или индекс.")

                selected_slot_val = available_slots[slot_idx]  # (time, time)
                user_state_data['selected_slot'] = selected_slot_val
                selected_date_obj_val = user_state_data.get('selected_date_obj')
                if not isinstance(selected_date_obj_val, date): raise TypeError("selected_date_obj не дата")

                markup_time_in_slot = keyboards_wsb.generate_time_keyboard_in_slot(selected_slot_val,
                                                                                selected_date_obj_val,
                                                                                const.CB_BOOK_SELECT_TIME)
                prompt_text_time = const.MSG_BOOKING_PROMPT_START_TIME_IN_SLOT.format(
                    start_slot=bookingService._format_time(selected_slot_val[0]),
                    # bookingService должен быть импортирован
                    end_slot=bookingService._format_time(selected_slot_val[1])
                )
                edit_or_send_message(global_bot_instance, chat_id, message_id, prompt_text_time,
                                    reply_markup=markup_time_in_slot, **kwargs_edit)
                state['step'] = const.STATE_BOOKING_START_TIME
            except (ValueError, IndexError, TypeError) as e_slot_select:
                logger.error(f"Ошибка выбора слота user {user_id} (WSB): {e_slot_select}", exc_info=True)
                edit_or_send_message(global_bot_instance, chat_id, message_id,
                                    "Ошибка: Не удалось обработать выбор слота.", reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)


        # --- Шаг 5 WSB: Выбор времени начала ---
        elif current_step == const.STATE_BOOKING_START_TIME and cb_data.startswith(const.CB_BOOK_SELECT_TIME):
            try:
                global_bot_instance.answer_callback_query(call.id)
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")
            # ... (логика как в CRB, но с MSG_BOOKING_STEP_6_SELECT_DURATION, MSG_BOOKING_PROMPT_DURATION_IN_SLOT и STATE_BOOKING_SELECT_DURATION) ...
            try:
                start_time_str_val = cb_data[len(const.CB_BOOK_SELECT_TIME):]
                start_time_obj_val = datetime.strptime(start_time_str_val, '%H:%M').time()
                user_state_data['start_time_str'] = start_time_str_val
                user_state_data['start_time_obj'] = start_time_obj_val
                selected_date_obj_val_st = user_state_data.get('selected_date_obj')
                if not isinstance(selected_date_obj_val_st, date): raise TypeError("selected_date_obj не дата")

                selected_slot_val_st = user_state_data.get(
                    'selected_slot')  # Может быть None, если был is_full_day_available
                effective_slot_end_time = const.WORKING_HOURS_END.time() if isinstance(const.WORKING_HOURS_END,
                                                                                    datetime) else const.WORKING_HOURS_END
                if selected_slot_val_st and isinstance(selected_slot_val_st[1], time):
                    effective_slot_end_time = selected_slot_val_st[1]

                markup_duration = keyboards_wsb.generate_duration_keyboard_in_slot(
                    start_time_obj_val, selected_date_obj_val_st, effective_slot_end_time, const.CB_BOOK_SELECT_DURATION
                )
                prompt_text_duration = const.MSG_BOOKING_STEP_6_DURATION
                if selected_slot_val_st:  # Если был выбран конкретный слот
                    prompt_text_duration = const.MSG_BOOKING_PROMPT_DURATION_IN_SLOT.format(
                        end_slot=bookingService._format_time(effective_slot_end_time)
                    )
                edit_or_send_message(global_bot_instance, chat_id, message_id, prompt_text_duration,
                                    reply_markup=markup_duration, **kwargs_edit)
                state['step'] = const.STATE_BOOKING_DURATION
            except (ValueError, TypeError, KeyError) as e_start_time_select:
                logger.error(f"Ошибка выбора времени начала user {user_id} (WSB): {e_start_time_select}", exc_info=True)
                edit_or_send_message(global_bot_instance, chat_id, message_id,
                                    "Ошибка: Не удалось обработать выбор времени.", reply_markup=None, **kwargs_edit)
                clear_user_state(user_id)

        # --- Шаг 6 WSB: Выбор длительности ---
        elif current_step == const.STATE_BOOKING_DURATION  and cb_data.startswith(const.CB_BOOK_SELECT_DURATION):
            try:
                global_bot_instance.answer_callback_query(call.id)
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")
            # ... (логика как в CRB, но с MSG_BOOKING_CONFIRM_DETAILS (включая category_name), MSG_BOOKING_STEP_7_CONFIRM и STATE_BOOKING_CONFIRM_DETAILS)
            try:
                duration_str_val = cb_data[len(const.CB_BOOK_SELECT_DURATION):]
                user_state_data['duration_str'] = duration_str_val
                # Проверка наличия всех данных
                selected_date_obj_dur = user_state_data.get('selected_date_obj')
                start_time_obj_dur = user_state_data.get('start_time_obj')
                category_name_dur = user_state_data.get('category_name')
                equipment_name_dur = user_state_data.get('equipment_name')
                sel_date_str_dur = user_state_data.get('selected_date_str')
                s_time_str_dur = user_state_data.get('start_time_str')

                if not all([selected_date_obj_dur, start_time_obj_dur, category_name_dur, equipment_name_dur,
                            sel_date_str_dur, s_time_str_dur]):
                    missing_data = [k for k, v in user_state_data.items() if
                                    not v and k in ['selected_date_obj', 'start_time_obj', 'category_name',
                                                    'equipment_name', 'selected_date_str', 'start_time_str']]
                    raise KeyError(f"Отсутствуют данные: {missing_data}")

                start_dt_val = datetime.combine(selected_date_obj_dur, start_time_obj_dur)
                hours_val, minutes_val = map(int, duration_str_val.split(':'))
                duration_delta_val = timedelta(hours=hours_val, minutes=minutes_val)
                end_dt_val = start_dt_val + duration_delta_val
                user_state_data['end_time_obj'] = end_dt_val.time()
                user_state_data['end_time_str'] = end_dt_val.strftime('%H:%M')

                confirm_text_details = const.MSG_BOOKING_CONFIRM_DETAILS.format(
                    category_name=html.escape(category_name_dur),
                    equip_name=html.escape(equipment_name_dur),
                    date=sel_date_str_dur,
                    start_time=s_time_str_dur,
                    end_time=user_state_data.get('end_time_str'),
                    duration=duration_str_val
                )
                markup_confirm = keyboards_wsb.generate_booking_confirmation_keyboard()
                edit_or_send_message(global_bot_instance, chat_id, message_id,
                                    f"{const.MSG_BOOKING_STEP_7_CONFIRM}\n{confirm_text_details}",
                                    reply_markup=markup_confirm, **kwargs_edit)
                state['step'] = const.STATE_BOOKING_CONFIRM
            except (ValueError, KeyError, AttributeError) as e_duration_select:
                logger.error(f"Ошибка выбора длительности user {user_id} (WSB): {e_duration_select}", exc_info=True)
                edit_or_send_message(global_bot_instance, chat_id, message_id,
                                    "Ошибка: Не удалось обработать выбор длительности.", reply_markup=None,
                                     **kwargs_edit)
                clear_user_state(user_id)

        # --- Шаг 7 WSB: Финальное подтверждение ---
        elif current_step == const.STATE_BOOKING_CONFIRM and cb_data == const.CB_BOOK_CONFIRM_FINAL:
            try:
                global_bot_instance.answer_callback_query(call.id, "Сохраняем бронирование...")
            except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                logger.debug(f"Не удалось ответить на callback query: {e}")
            logger.info(f"User {user_id} подтвердил создание бронирования WSB: {user_state_data}")
            try:
                equipment_id_final = user_state_data.get('equipment_id')
                # Дата из календаря была YYYY-MM-DD, мы ее сохранили как selected_date_obj
                # и в selected_date_str в формате DD-MM-YYYY.
                # bookingService.create_booking ожидает DD-MM-YYYY или YYYY-MM-DD - нужно проверить его реализацию.
                # Если create_booking ожидает YYYY-MM-DD, то передаем:
                # selected_date_obj_final = user_state_data.get('selected_date_obj')
                # sel_date_str_final = selected_date_obj_final.strftime('%Y-%m-%d') if selected_date_obj_final else None
                # Если DD-MM-YYYY, то:
                sel_date_str_final = user_state_data.get('selected_date_str')  # Уже в DD-MM-YYYY

                s_time_str_final = user_state_data.get('start_time_str')
                dur_str_final = user_state_data.get('duration_str')

                if not all([equipment_id_final, sel_date_str_final, s_time_str_final, dur_str_final]):
                    raise ValueError("Недостаточно данных для создания бронирования WSB (финал).")

                # bookingService.create_booking использует global_db
                success_create, msg_create, new_booking_id_created = bookingService.create_booking(
                    user_id, equipment_id_final, sel_date_str_final, s_time_str_final, dur_str_final
                )
                if msg_create is None: msg_create = const.MSG_BOOKING_SUCCESS if success_create else const.MSG_BOOKING_FAIL_GENERAL
                edit_or_send_message(global_bot_instance, chat_id, message_id, msg_create, reply_markup=None,
                                     **kwargs_edit)

                if success_create and new_booking_id_created:
                    logger.debug(f"Бронь WSB {new_booking_id_created} создана, перепланируем уведомления...")
                    try:
                        # notificationService.schedule_all_notifications использует глобальные компоненты
                        notificationService.schedule_all_notifications()
                    except Exception as e_schedule_final:
                        logger.error(
                            f"Ошибка планирования уведомлений после брони WSB {new_booking_id_created}: {e_schedule_final}",
                            exc_info=True)
                # ... (доп. логирование, если new_booking_id не вернулся) ...
            except Exception as e_create_final:
                logger.error(f"Ошибка создания брони WSB user {user_id} (финал): {e_create_final}", exc_info=True)
                edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_BOOKING_FAIL_GENERAL,
                                    reply_markup=None, **kwargs_edit)
            finally:
                clear_user_state(user_id)

        # --- Неверный шаг или callback ---
        else:
            if cb_data.startswith(const.CB_BOOK_ACTION):  # Если колбэк от кнопок бронирования
                logger.warning(
                    f"User {user_id} нажал кнопку бронирования '{cb_data}' на неверном шаге {current_step} (WSB). Возможно, старое сообщение.")
                try:
                    global_bot_instance.answer_callback_query(call.id,
                                                            "Это действие сейчас неактуально. Пожалуйста, используйте последнее сообщение.",
                                                            show_alert=True)
                except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                    logger.debug(f"Не удалось ответить на callback query: {e}")
            else:  # Если это какой-то другой колбэк, но пользователь в состоянии бронирования
                logger.error(
                    f"Неожиданный callback '{cb_data}' от user {user_id} во время активного шага бронирования {current_step} (WSB). Сброс состояния.")
                try:
                    global_bot_instance.answer_callback_query(call.id,
                                                            "Произошла ошибка в процессе бронирования. Попробуйте начать заново.",
                                                            show_alert=True)
                except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                    logger.debug(f"Не удалось ответить на callback query: {e}")
                try:
                    edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE,
                                        reply_markup=None, **kwargs_edit)
                except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
                    logger.debug(f"Не удалось ответить на callback query: {e}")
                finally:
                    clear_user_state(user_id)

    except Exception as e_steps_main_wsb:  # Общий обработчик ошибок для всего блока try
        logger.critical(
            f"Критическая ошибка в handle_booking_steps_wsb (user={user_id}, step={current_step}, cb='{cb_data}'): {e_steps_main_wsb}",
            exc_info=True)
        try:
            global_bot_instance.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось ответить на callback query: {e}")
        try:
            edit_or_send_message(global_bot_instance, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None,
                                 **kwargs_edit)
        except (apihelper.ApiTelegramException, ConnectionError, TimeoutError, AttributeError) as e:
            logger.debug(f"Не удалось отредактировать сообщение: {e}")
        finally:
            clear_user_state(user_id)

# --- END OF FILE handlers/callbacks/process_callbacks.py (WSB - исправленный проект) ---