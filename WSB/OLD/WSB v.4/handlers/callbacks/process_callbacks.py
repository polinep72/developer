# --- START OF FILE handlers/callbacks/process_callbacks.py ---
"""
Обработчик callback-запросов для пошагового процесса бронирования пользователя.

Отвечает за:
- Обработку выбора категории, оборудования, даты, слота, времени, длительности.
- Финальное подтверждение и создание бронирования.
- Отмену процесса бронирования на любом шаге.
- Управление состоянием пользователя (`user_booking_states`).
"""

import telebot
from telebot import types, apihelper
from telebot.types import CallbackQuery
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime, date, time, timedelta

from database import Database
from logger import logger
import constants as const
import services.booking_service as bookingService
import services.equipment_service as equipmentService
import services.notification_service as notificationService
from utils import keyboards
from states import user_booking_states, clear_user_state # Импорт состояний пользователя
from apscheduler.schedulers.background import BackgroundScheduler

# Импортируем хелпер для редактирования/отправки сообщений
# Предполагаем, что он останется в основном callback_handlers или будет вынесен в utils
try:
    from utils.message_utils import edit_or_send_message
except ImportError:
    # Заглушка на случай, если основной файл еще не обновлен
    logger.error("Не удалось импортировать edit_or_send_message из callback_handlers")
    def edit_or_send_message(bot, chat_id, message_id, text, **kwargs):
        logger.warning(f"Вызвана заглушка edit_or_send_message для chat_id {chat_id}")
        try:
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, **kwargs)
            else:
                bot.send_message(chat_id, text, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в заглушке edit_or_send_message: {e}")

# --- Основная функция обработки шагов ---

def handle_booking_steps(
    bot: telebot.TeleBot,
    db: Database,
    call: CallbackQuery,
    state: Dict[str, Any], # Текущее состояние пользователя из user_booking_states
    scheduler: Optional[BackgroundScheduler],
    active_timers: Dict[int, Any],
    scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """Обрабатывает колбэки в процессе бронирования на основе состояния."""
    user_id = call.from_user.id
    # Извлекаем chat_id и message_id из состояния, а не из call.message,
    # так как call мог прийти от другого сообщения (например, старого)
    chat_id = state.get('chat_id')
    message_id = state.get('message_id')
    current_step = state.get('step', const.STATE_BOOKING_IDLE)
    cb_data = call.data
    user_state_data = state.get('data', {})

    # Проверяем наличие chat_id и message_id в состоянии
    if not chat_id or not message_id:
        logger.error(f"Отсутствует chat_id ({chat_id}) или message_id ({message_id}) в состоянии user {user_id}. Шаг: {current_step}. Callback: {cb_data}")
        try:
            # Пытаемся ответить на коллбэк, даже если не можем отредактировать сообщение
            bot.answer_callback_query(call.id, "Ошибка состояния. Начните заново.", show_alert=True)
        except Exception: pass
        clear_user_state(user_id)
        return

    # Передаем user_id для обновления message_id в состоянии
    kwargs_edit_send = {'user_id_for_state_update': user_id}
    logger.debug(f"handle_booking_steps: user={user_id}, step={current_step}, data='{cb_data}', state_data={user_state_data}")

    # --- Отмена процесса бронирования ---
    if cb_data == const.CB_BOOK_CANCEL_PROCESS:
        logger.info(f"User {user_id} отменил процесс бронирования на шаге {current_step}.")
        try:
            bot.answer_callback_query(call.id, const.MSG_BOOKING_PROCESS_CANCELLED)
        except Exception as e_ans_cancel:
            logger.warning(f"Не удалось ответить на callback отмены бронирования: {e_ans_cancel}")
        try:
            edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_PROCESS_CANCELLED, reply_markup=None, **kwargs_edit_send)
        except Exception as e_edit_cancel:
            logger.error(f"Не удалось отредактировать сообщение при отмене бронирования user {user_id}: {e_edit_cancel}")
        finally:
            clear_user_state(user_id)
        return # Завершаем обработку

    # --- Обработка шагов ---
    try:
        # --- Шаг 1: Выбор категории ---
        if current_step == const.STATE_BOOKING_CATEGORY:
            if cb_data.startswith(const.CB_BOOK_SELECT_CATEGORY):
                try:
                    bot.answer_callback_query(call.id)
                except Exception as e_ans_step1:
                    logger.warning(f"Не удалось ответить на callback шага 1: {e_ans_step1}")

                category_id_str = cb_data[len(const.CB_BOOK_SELECT_CATEGORY):]
                category_id = None
                try:
                    category_id = int(category_id_str)
                except ValueError:
                    logger.error(f"Неверный category_id '{category_id_str}' в callback от user {user_id}")
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный ID категории.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['category_id'] = category_id
                logger.debug(f"User {user_id} выбрал категорию {category_id}")
                equipment = None
                try:
                    equipment = equipmentService.get_equipment_by_category(db, category_id)
                except Exception as e_get_eq:
                    logger.error(f"Ошибка получения оборудования для категории {category_id} (user {user_id}): {e_get_eq}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                if not equipment:
                    logger.warning(f"В категории {category_id} нет оборудования (user {user_id}).")
                    edit_or_send_message(bot, chat_id, message_id, "В этой категории нет доступного оборудования.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                markup = keyboards.generate_equipment_keyboard(equipment, const.CB_BOOK_SELECT_EQUIPMENT)
                edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_2_EQUIPMENT, reply_markup=markup, **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_EQUIPMENT

        # --- Шаг 2: Выбор оборудования ---
        elif current_step == const.STATE_BOOKING_EQUIPMENT:
            if cb_data.startswith(const.CB_BOOK_SELECT_EQUIPMENT):
                try:
                    bot.answer_callback_query(call.id)
                except Exception as e_ans_step2:
                    logger.warning(f"Не удалось ответить на callback шага 2: {e_ans_step2}")

                equipment_id_str = cb_data[len(const.CB_BOOK_SELECT_EQUIPMENT):]
                equipment_id = None
                try:
                    equipment_id = int(equipment_id_str)
                except ValueError:
                    logger.error(f"Неверный equipment_id '{equipment_id_str}' в callback от user {user_id}")
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный ID оборудования.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                equipment_name = None
                try:
                    equipment_name = equipmentService.get_equipment_name_by_id(db, equipment_id)
                except Exception as e_get_name:
                    logger.error(f"Ошибка получения имени для оборудования {equipment_id} (user {user_id}): {e_get_name}", exc_info=True)

                user_state_data['equipment_id'] = equipment_id
                user_state_data['equipment_name'] = equipment_name or f"ID {equipment_id}"
                logger.debug(f"User {user_id} выбрал оборудование {equipment_id} ('{user_state_data['equipment_name']}')")

                markup = keyboards.generate_date_keyboard(const.CB_BOOK_SELECT_DATE)
                edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_3_DATE, reply_markup=markup, **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_DATE

        # --- Шаг 3: Выбор даты ---
        elif current_step == const.STATE_BOOKING_DATE:
            if cb_data.startswith(const.CB_BOOK_SELECT_DATE):
                try:
                    bot.answer_callback_query(call.id)
                except Exception as e_ans_step3:
                    logger.warning(f"Не удалось ответить на callback шага 3: {e_ans_step3}")

                selected_date_str = cb_data[len(const.CB_BOOK_SELECT_DATE):]
                selected_date_obj = None
                try:
                    selected_date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
                except ValueError:
                    logger.error(f"Неверный формат даты '{selected_date_str}' в callback от user {user_id}")
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный формат даты.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                equipment_id = user_state_data.get('equipment_id')
                if not equipment_id:
                    logger.error(f"Отсутствует equipment_id в состоянии user {user_id} на шаге 3.")
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['selected_date_str'] = selected_date_str
                user_state_data['selected_date_obj'] = selected_date_obj
                logger.debug(f"User {user_id} выбрал дату {selected_date_str} для оборудования {equipment_id}")

                available_slots = None
                try:
                    available_slots = bookingService.calculate_available_slots(db, equipment_id, selected_date_obj)
                except Exception as e_calc_slots:
                    logger.error(f"Ошибка расчета слотов для {equipment_id} на {selected_date_str} (user {user_id}): {e_calc_slots}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка получения свободных слотов.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['available_slots'] = available_slots
                if not available_slots:
                    logger.warning(f"Нет свободных слотов для {equipment_id} на {selected_date_str} (user {user_id}).")
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_NO_SLOTS_AVAILABLE, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                is_full_day_free = False
                if len(available_slots) == 1:
                    slot_start, slot_end = available_slots[0]
                    if slot_start == const.WORKING_HOURS_START and slot_end == const.WORKING_HOURS_END:
                        is_full_day_free = True

                if is_full_day_free:
                    logger.debug(f"Дата {selected_date_str} полностью свободна для {equipment_id} (user {user_id}).")
                    full_day_slot = (const.WORKING_HOURS_START, const.WORKING_HOURS_END)
                    user_state_data['selected_slot'] = full_day_slot
                    markup = keyboards.generate_time_keyboard_in_slot(full_day_slot, selected_date_obj, const.CB_BOOK_SELECT_TIME)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_5_START_TIME, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_START_TIME
                else:
                    logger.debug(f"Дата {selected_date_str} частично занята для {equipment_id} (user {user_id}): {available_slots}")
                    markup = keyboards.generate_available_slots_keyboard(available_slots, const.CB_BOOK_SELECT_SLOT)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_4_SLOT, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_SLOT

        # --- Шаг 4: Выбор слота ---
        elif current_step == const.STATE_BOOKING_SLOT:
            if cb_data.startswith(const.CB_BOOK_SELECT_SLOT):
                try:
                    bot.answer_callback_query(call.id)
                except Exception as e_ans_step4:
                    logger.warning(f"Не удалось ответить на callback шага 4: {e_ans_step4}")

                selected_slot = None
                try:
                    slot_index_str = cb_data[len(const.CB_BOOK_SELECT_SLOT):]
                    slot_index = int(slot_index_str)

                    available_slots = user_state_data.get('available_slots')
                    if not isinstance(available_slots, list):
                        logger.error(f"available_slots не найден или не является списком в состоянии user {user_id}")
                        raise TypeError("available_slots не найден или не является списком.")
                    if slot_index < 0 or slot_index >= len(available_slots):
                        logger.error(f"Неверный индекс слота {slot_index} (из {len(available_slots)}) в callback от user {user_id}")
                        raise IndexError("Неверный индекс слота.")

                    selected_slot = available_slots[slot_index]
                    user_state_data['selected_slot'] = selected_slot

                    selected_date_obj = user_state_data.get('selected_date_obj')
                    if not isinstance(selected_date_obj, date):
                        logger.error(f"selected_date_obj не найден или не является датой в состоянии user {user_id}")
                        raise TypeError("selected_date_obj не найден или не является датой.")

                    logger.debug(f"User {user_id} выбрал слот {selected_slot}")
                    markup = keyboards.generate_time_keyboard_in_slot(selected_slot, selected_date_obj, const.CB_BOOK_SELECT_TIME)
                    prompt_text = const.MSG_BOOKING_PROMPT_START_TIME_IN_SLOT.format(
                        start_slot=bookingService._format_time(selected_slot[0]),
                        end_slot=bookingService._format_time(selected_slot[1])
                    )
                    edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_START_TIME

                except (ValueError, IndexError, TypeError) as e:
                    logger.error(f"Ошибка выбора слота user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор слота.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)

        # --- Шаг 5: Выбор времени начала ---
        elif current_step == const.STATE_BOOKING_START_TIME:
            if cb_data.startswith(const.CB_BOOK_SELECT_TIME):
                try:
                    bot.answer_callback_query(call.id)
                except Exception as e_ans_step5:
                    logger.warning(f"Не удалось ответить на callback шага 5: {e_ans_step5}")

                start_time_obj = None
                try:
                    start_time_str = cb_data[len(const.CB_BOOK_SELECT_TIME):]
                    start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()

                    user_state_data['start_time_str'] = start_time_str
                    user_state_data['start_time_obj'] = start_time_obj

                    selected_date_obj = user_state_data.get('selected_date_obj')
                    if not isinstance(selected_date_obj, date):
                        logger.error(f"selected_date_obj не найден или не является датой в состоянии user {user_id} на шаге 5")
                        raise TypeError("selected_date_obj не найден или не является датой.")

                    selected_slot = user_state_data.get('selected_slot')
                    logger.debug(f"User {user_id} выбрал время начала {start_time_str}")

                    effective_end_time = None
                    if selected_slot:
                        if isinstance(selected_slot, tuple) and len(selected_slot) == 2 and isinstance(selected_slot[1], time):
                            effective_end_time = selected_slot[1]
                        else:
                            logger.warning(f"Некорректный selected_slot {selected_slot} у user {user_id}, используем конец рабочего дня.")
                            effective_end_time = const.WORKING_HOURS_END
                    else:
                        effective_end_time = const.WORKING_HOURS_END

                    if not isinstance(effective_end_time, time):
                        logger.error(f"Не удалось определить effective_end_time (тип: {type(effective_end_time)}) для user {user_id}")
                        raise TypeError("effective_end_time должен быть объектом time")

                    markup = keyboards.generate_duration_keyboard_in_slot(
                        start_time_obj, selected_date_obj, effective_end_time, const.CB_BOOK_SELECT_DURATION
                    )
                    prompt_text = const.MSG_BOOKING_STEP_6_DURATION
                    if selected_slot:
                        prompt_text = const.MSG_BOOKING_PROMPT_DURATION_IN_SLOT.format(
                            end_slot=bookingService._format_time(effective_end_time)
                        )
                    edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_DURATION

                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"Ошибка выбора времени начала user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор времени.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)

        # --- Шаг 6: Выбор длительности ---
        elif current_step == const.STATE_BOOKING_DURATION:
            if cb_data.startswith(const.CB_BOOK_SELECT_DURATION):
                try:
                    bot.answer_callback_query(call.id)
                except Exception as e_ans_step6:
                    logger.warning(f"Не удалось ответить на callback шага 6: {e_ans_step6}")

                try:
                    duration_str = cb_data[len(const.CB_BOOK_SELECT_DURATION):]
                    user_state_data['duration_str'] = duration_str

                    selected_date_obj = user_state_data.get('selected_date_obj')
                    start_time_obj = user_state_data.get('start_time_obj')
                    if not selected_date_obj or not start_time_obj:
                        missing_keys = [k for k in ['selected_date_obj', 'start_time_obj'] if not user_state_data.get(k)]
                        logger.error(f"Отсутствуют ключи {missing_keys} в состоянии user {user_id} на шаге 6")
                        raise KeyError(f"Отсутствуют необходимые данные: {missing_keys}")

                    start_dt = datetime.combine(selected_date_obj, start_time_obj)
                    hours_str, minutes_str = duration_str.split(':')
                    hours = int(hours_str)
                    minutes = int(minutes_str)
                    duration_delta = timedelta(hours=hours, minutes=minutes)
                    end_dt = start_dt + duration_delta

                    user_state_data['end_time_obj'] = end_dt.time()
                    user_state_data['end_time_str'] = end_dt.strftime('%H:%M')
                    logger.debug(f"User {user_id} выбрал длительность {duration_str}, время окончания: {user_state_data['end_time_str']}")

                    equip_name = user_state_data.get('equipment_name')
                    sel_date_str = user_state_data.get('selected_date_str')
                    s_time_str = user_state_data.get('start_time_str')
                    e_time_str = user_state_data.get('end_time_str')

                    if not all ([equip_name, sel_date_str, s_time_str, e_time_str]):
                        missing = [k for k in ['equipment_name', 'selected_date_str', 'start_time_str', 'end_time_str'] if not user_state_data.get(k)]
                        logger.error(f"Отсутствуют данные для формирования подтверждения user {user_id}: {missing}")
                        raise KeyError(f"Недостаточно данных для формирования подтверждения: {missing}")

                    confirm_text = const.MSG_BOOKING_CONFIRM_DETAILS.format(
                        equip_name=equip_name,
                        date=sel_date_str,
                        start_time=s_time_str,
                        end_time=e_time_str,
                        duration=duration_str
                    )
                    markup = keyboards.generate_booking_confirmation_keyboard()
                    edit_or_send_message(bot, chat_id, message_id, f"{const.MSG_BOOKING_STEP_7_CONFIRM}\n{confirm_text}", reply_markup=markup, parse_mode="Markdown", **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_CONFIRM

                except (ValueError, KeyError, AttributeError) as e:
                    logger.error(f"Ошибка выбора длительности user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор длительности.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)

        # --- Шаг 7: Финальное подтверждение ---
        elif current_step == const.STATE_BOOKING_CONFIRM:
            if cb_data == const.CB_BOOK_CONFIRM_FINAL:
                try:
                    bot.answer_callback_query(call.id, "Сохраняем бронирование...")
                except Exception as e_ans_step7:
                    logger.warning(f"Не удалось ответить на callback шага 7: {e_ans_step7}")

                logger.info(f"User {user_id} подтвердил создание бронирования: {user_state_data}")
                try:
                    equip_id = user_state_data.get('equipment_id')
                    sel_date_str = user_state_data.get('selected_date_str')
                    s_time_str = user_state_data.get('start_time_str')
                    dur_str = user_state_data.get('duration_str')

                    if not all([equip_id, sel_date_str, s_time_str, dur_str]):
                        missing = [k for k in ['equipment_id', 'selected_date_str', 'start_time_str', 'duration_str'] if not user_state_data.get(k)]
                        logger.error(f"Отсутствуют критические данные для создания бронирования user {user_id}: {missing}")
                        raise ValueError(f"Недостаточно данных для создания бронирования: {missing}")

                    success = False
                    msg = const.MSG_BOOKING_FAIL_GENERAL
                    new_booking_id = None
                    success, msg, new_booking_id = bookingService.create_booking(
                        db, user_id, equip_id, sel_date_str, s_time_str, dur_str
                    )

                    if msg is None: # Доп. проверка, если сервис вернул None
                        logger.error(f"create_booking не вернул сообщение для user {user_id}, success={success}")
                        msg = const.MSG_BOOKING_SUCCESS if success else const.MSG_BOOKING_FAIL_GENERAL

                    edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown", **kwargs_edit_send)

                    if success:
                        if new_booking_id:
                            if scheduler:
                                logger.debug(f"Бронь {new_booking_id} успешно создана, планируем уведомления...")
                                try:
                                    notificationService.schedule_all_notifications(
                                        db, bot, scheduler, active_timers, scheduled_jobs_registry
                                    )
                                    logger.info(f"Уведомления перепланированы после создания брони {new_booking_id}.")
                                except Exception as e_schedule:
                                    logger.error(f"Ошибка планирования уведомлений после создания брони {new_booking_id}: {e_schedule}", exc_info=True)
                            else:
                                logger.warning("Планировщик (scheduler) не передан в handle_booking_steps, уведомления не запланированы.")
                        else:
                            logger.error(f"create_booking вернул success=True, но new_booking_id=None для user {user_id}. Данные: {user_state_data}")

                except ValueError as e:
                    logger.error(f"Ошибка данных при финальном подтверждении бронирования user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при вызове create_booking user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_FAIL_GENERAL, reply_markup=None, **kwargs_edit_send)
                finally:
                    clear_user_state(user_id)

        # --- Неверный шаг или callback внутри процесса бронирования ---
        else:
            # Эта проверка должна срабатывать только если колбэк относится к процессу бронирования
            if cb_data.startswith(const.CB_BOOK_ACTION):
                logger.warning(f"User {user_id} нажал кнопку бронирования '{cb_data}' на неверном шаге {current_step}. Возможно, старое сообщение.")
                try:
                    bot.answer_callback_query(call.id, "Это действие сейчас неактуально. Пожалуйста, используйте последнее сообщение.", show_alert=True)
                except Exception as e_ans_wrong_step:
                    logger.warning(f"Не удалось ответить на callback неверного шага: {e_ans_wrong_step}")
            else:
                # Если колбэк вообще не из процесса бронирования, но состояние активно - это ошибка
                logger.error(f"Неожиданный callback '{cb_data}' от user {user_id} во время активного шага бронирования {current_step}. Сброс состояния.")
                try:
                    bot.answer_callback_query(call.id, "Произошла ошибка в процессе бронирования. Попробуйте начать заново.", show_alert=True)
                except Exception as e_ans_unexpected:
                    logger.warning(f"Не удалось ответить на callback при неожиданном действии: {e_ans_unexpected}")
                try:
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None, **kwargs_edit_send)
                except Exception as e_edit_unexpected:
                    logger.error(f"Не удалось отредактировать сообщение при неожиданном колбэке user {user_id}: {e_edit_unexpected}")
                finally:
                    clear_user_state(user_id)

    # --- Обработка любых исключений внутри блока try шагов ---
    except Exception as e:
        logger.critical(f"Критическая ошибка в handle_booking_steps (user={user_id}, step={current_step}, cb='{cb_data}'): {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception as e_ans_crit:
            logger.error(f"Не удалось ответить на callback после критической ошибки в handle_booking_steps: {e_ans_crit}")

        try:
            edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
        except Exception as e_edit_crit:
            logger.error(f"Не удалось отредактировать сообщение после критической ошибки в handle_booking_steps: {e_edit_crit}")
        finally:
            clear_user_state(user_id)

# --- END OF FILE handlers/callbacks/process_callbacks.py ---