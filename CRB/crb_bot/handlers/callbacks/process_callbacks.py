# --- START OF FILE handlers/callbacks/process_callbacks.py ---
"""
Обработчик callback-запросов для пошагового процесса бронирования пользователя.

Отвечает за:
- Обработку выбора комнаты, даты, слота, времени, длительности.
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
# --- ИЗМЕНЕНО: Импорт сервиса комнат ---
import services.conference_room_service as room_service
# --- КОНЕЦ ИЗМЕНЕНИЯ ---
import services.notification_service as notificationService
from utils import keyboards # Используем обновленные клавиатуры
from states import user_booking_states, clear_user_state # Импорт состояний пользователя
from apscheduler.schedulers.background import BackgroundScheduler

# Импортируем хелпер для редактирования/отправки сообщений
try:
    from utils.message_utils import edit_or_send_message
except ImportError:
    from ..utils.message_utils import edit_or_send_message # Попробуем относительный импорт, если структура изменилась
except ImportError:
    logger.error("Не удалось импортировать edit_or_send_message.")
    # Определяем заглушку здесь же, если импорт не удался
    def edit_or_send_message(bot, chat_id, message_id, text, **kwargs):
        logger.warning(f"Вызвана заглушка edit_or_send_message для chat_id {chat_id}")
        reply_markup = kwargs.get('reply_markup')
        parse_mode = kwargs.get('parse_mode')
        try:
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                # Если message_id не предоставлен (например, после ошибки), просто отправляем новое сообщение
                logger.warning("message_id не предоставлен в edit_or_send_message, отправляем новое сообщение.")
                bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        except apihelper.ApiTelegramException as e_api:
            if "message is not modified" in str(e_api).lower():
                logger.debug(f"Сообщение {message_id} не было изменено (заглушка).")
            elif "message to edit not found" in str(e_api).lower():
                logger.warning(f"Сообщение {message_id} не найдено для редактирования (заглушка), отправляем новое.")
                try:
                    bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
                except Exception as e_send:
                    logger.error(f"Ошибка отправки нового сообщения в заглушке edit_or_send_message: {e_send}")
            else:
                logger.error(f"Ошибка API в заглушке edit_or_send_message: {e_api}")
        except Exception as e:
            logger.error(f"Общая ошибка в заглушке edit_or_send_message: {e}")


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
    chat_id = state.get('chat_id')
    message_id = state.get('message_id')
    current_step = state.get('step') # Шаг теперь устанавливается при первом нажатии кнопки
    cb_data = call.data
    user_state_data = state.get('data', {})

    if not chat_id or not message_id:
        logger.error(f"Отсутствует chat_id ({chat_id}) или message_id ({message_id}) в состоянии user {user_id}. Callback: {cb_data}")
        try: bot.answer_callback_query(call.id, "Ошибка состояния. Начните заново /booking.", show_alert=True)
        except Exception: pass
        clear_user_state(user_id)
        return

    # Аргументы для edit_or_send_message, передаем user_id для обновления состояния
    kwargs_edit_send = {'user_id_for_state_update': user_id}
    logger.debug(f"handle_booking_steps: user={user_id}, step={current_step}, data='{cb_data}', state_data={user_state_data}")

    # --- Отмена процесса бронирования ---
    if cb_data == const.CB_BOOK_CANCEL_PROCESS:
        logger.info(f"User {user_id} отменил процесс бронирования на шаге {current_step}.")
        try: bot.answer_callback_query(call.id, const.MSG_BOOKING_PROCESS_CANCELLED)
        except Exception: pass # Игнорируем ошибку ответа на коллбэк
        try:
            edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_PROCESS_CANCELLED, reply_markup=None, **kwargs_edit_send)
        except Exception as e_edit_cancel:
            logger.error(f"Не удалось отредактировать сообщение при отмене бронирования user {user_id}: {e_edit_cancel}")
        finally:
            clear_user_state(user_id)
        return

    # --- Обработка шагов ---
    try:
        # --- Шаг 1 (Новый): Выбор комнаты ---
        # Этот шаг инициируется нажатием кнопки с префиксом CB_BOOK_SELECT_CR
        if current_step == const.STATE_BOOKING_CONFERENCE_ROOM and cb_data.startswith(const.CB_BOOK_SELECT_CR):
            # Логика обработки выбора комнаты...
            state['step'] = const.STATE_BOOKING_DATE  # Переход на следующий шаг
            # Устанавливаем шаг только сейчас, когда пользователь нажал кнопку выбора комнаты
            # state['step'] = const.STATE_BOOKING_CONFERENCE_ROOM
            # current_step = const.STATE_BOOKING_CONFERENCE_ROOM
            # logger.debug(f"User {user_id} перешел на шаг {current_step}")
            try: bot.answer_callback_query(call.id)
            except Exception: pass

            cr_id_str = cb_data[len(const.CB_BOOK_SELECT_CR):]
            cr_id = None
            try:
                cr_id = int(cr_id_str)
            except ValueError:
                logger.error(f"Неверный cr_id '{cr_id_str}' в callback от user {user_id}")
                edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный ID комнаты.", reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return

            cr_name = None
            try:
                # Используем room_service
                cr_name = room_service.get_conference_room_name_by_id(db, cr_id)
            except Exception as e_get_name:
                logger.error(f"Ошибка получения имени для комнаты {cr_id} (user {user_id}): {e_get_name}", exc_info=True)
                # Продолжаем без имени, но логируем ошибку

            user_state_data['cr_id'] = cr_id # Сохраняем ID комнаты
            user_state_data['cr_name'] = cr_name or f"ID {cr_id}" # Сохраняем имя
            logger.debug(f"User {user_id} выбрал комнату {cr_id} ('{user_state_data['cr_name']}')")

            markup = keyboards.generate_date_keyboard(const.CB_BOOK_SELECT_DATE)
            # Используем константу для шага выбора даты
            edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_2_DATE, reply_markup=markup, **kwargs_edit_send)
            state['step'] = const.STATE_BOOKING_DATE # Переходим на следующий шаг

        # --- Шаг 2 (Старый Шаг 3): Выбор даты ---
        elif current_step == const.STATE_BOOKING_DATE:
            if cb_data.startswith(const.CB_BOOK_SELECT_DATE):
                try: bot.answer_callback_query(call.id)
                except Exception: pass

                selected_date_str = cb_data[len(const.CB_BOOK_SELECT_DATE):]
                selected_date_obj = None
                try:
                    selected_date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
                except ValueError:
                    logger.error(f"Неверный формат даты '{selected_date_str}' в callback от user {user_id}")
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный формат даты.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                cr_id = user_state_data.get('cr_id') # Получаем ID комнаты из состояния
                if not cr_id:
                    logger.error(f"Отсутствует cr_id в состоянии user {user_id} на шаге {current_step}.")
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['selected_date_str'] = selected_date_str
                user_state_data['selected_date_obj'] = selected_date_obj
                logger.debug(f"User {user_id} выбрал дату {selected_date_str} для комнаты {cr_id}")

                available_slots = None
                try:
                    # Передаем ID комнаты в сервис расчета слотов
                    available_slots = bookingService.calculate_available_slots(db, cr_id, selected_date_obj)
                except Exception as e_calc_slots:
                    logger.error(f"Ошибка расчета слотов для комнаты {cr_id} на {selected_date_str} (user {user_id}): {e_calc_slots}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка получения свободных слотов.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['available_slots'] = available_slots
                if not available_slots:
                    logger.warning(f"Нет свободных слотов для комнаты {cr_id} на {selected_date_str} (user {user_id}).")
                    # Используем константу
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_NO_SLOTS_AVAILABLE, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                # Проверка, свободен ли весь день (логика та же)
                is_full_day_free = False
                if len(available_slots) == 1:
                    slot_start, slot_end = available_slots[0]
                    if slot_start == const.WORKING_HOURS_START and slot_end == const.WORKING_HOURS_END:
                        is_full_day_free = True

                if is_full_day_free:
                    logger.debug(f"Дата {selected_date_str} полностью свободна для комнаты {cr_id} (user {user_id}). Пропускаем выбор слота.")
                    full_day_slot = (const.WORKING_HOURS_START, const.WORKING_HOURS_END)
                    user_state_data['selected_slot'] = full_day_slot
                    markup = keyboards.generate_time_keyboard_in_slot(full_day_slot, selected_date_obj, const.CB_BOOK_SELECT_TIME)
                    # Используем константу для шага выбора времени
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_4_START_TIME, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_START_TIME # Переход на шаг выбора времени
                else:
                    logger.debug(f"Дата {selected_date_str} частично занята для комнаты {cr_id} (user {user_id}): {available_slots}")
                    markup = keyboards.generate_available_slots_keyboard(available_slots, const.CB_BOOK_SELECT_SLOT)
                    # Используем константу для шага выбора слота
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_3_SLOT, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_SLOT # Переход на шаг выбора слота

        # --- Шаг 3 (Старый Шаг 4): Выбор слота ---
        elif current_step == const.STATE_BOOKING_SLOT:
            if cb_data.startswith(const.CB_BOOK_SELECT_SLOT):
                try: bot.answer_callback_query(call.id)
                except Exception: pass

                selected_slot = None
                try:
                    slot_index_str = cb_data[len(const.CB_BOOK_SELECT_SLOT):]
                    slot_index = int(slot_index_str)

                    available_slots = user_state_data.get('available_slots')
                    if not isinstance(available_slots, list) or not (0 <= slot_index < len(available_slots)):
                        logger.error(f"Неверные available_slots или индекс {slot_index} в состоянии user {user_id}")
                        raise ValueError("Неверные данные слотов или индекс.")

                    selected_slot = available_slots[slot_index]
                    user_state_data['selected_slot'] = selected_slot

                    selected_date_obj = user_state_data.get('selected_date_obj')
                    if not isinstance(selected_date_obj, date):
                        logger.error(f"selected_date_obj не является датой в состоянии user {user_id}")
                        raise TypeError("selected_date_obj не является датой.")

                    logger.debug(f"User {user_id} выбрал слот {selected_slot}")
                    markup = keyboards.generate_time_keyboard_in_slot(selected_slot, selected_date_obj, const.CB_BOOK_SELECT_TIME)
                    # Используем константу для запроса времени в слоте
                    prompt_text = const.MSG_BOOKING_PROMPT_START_TIME_IN_SLOT.format(
                        start_slot=bookingService._format_time(selected_slot[0]),
                        end_slot=bookingService._format_time(selected_slot[1])
                    )
                    edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_START_TIME # Переход на шаг выбора времени

                except (ValueError, IndexError, TypeError) as e:
                    logger.error(f"Ошибка выбора слота user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор слота.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)

        # --- Шаг 4 (Старый Шаг 5): Выбор времени начала ---
        elif current_step == const.STATE_BOOKING_START_TIME:
            if cb_data.startswith(const.CB_BOOK_SELECT_TIME):
                try: bot.answer_callback_query(call.id)
                except Exception: pass

                start_time_obj = None
                try:
                    start_time_str = cb_data[len(const.CB_BOOK_SELECT_TIME):]
                    start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()

                    user_state_data['start_time_str'] = start_time_str
                    user_state_data['start_time_obj'] = start_time_obj

                    selected_date_obj = user_state_data.get('selected_date_obj')
                    if not isinstance(selected_date_obj, date):
                        raise TypeError("selected_date_obj не дата")

                    selected_slot = user_state_data.get('selected_slot')
                    logger.debug(f"User {user_id} выбрал время начала {start_time_str}")

                    # Определяем конец интервала для выбора длительности
                    effective_end_time = const.WORKING_HOURS_END # По умолчанию конец рабочего дня
                    if selected_slot and isinstance(selected_slot, tuple) and len(selected_slot) == 2 and isinstance(selected_slot[1], time):
                        effective_end_time = selected_slot[1]
                    else:
                        logger.warning(f"Не удалось определить конец слота для user {user_id}, используем конец рабочего дня {effective_end_time}.")

                    markup = keyboards.generate_duration_keyboard_in_slot(
                        start_time_obj, selected_date_obj, effective_end_time, const.CB_BOOK_SELECT_DURATION
                    )
                    # Используем константу для запроса длительности
                    prompt_text = const.MSG_BOOKING_STEP_5_DURATION # Новый номер шага
                    if selected_slot:
                        # Используем константу для запроса длительности в слоте
                        prompt_text = const.MSG_BOOKING_PROMPT_DURATION_IN_SLOT.format(
                            end_slot=bookingService._format_time(effective_end_time)
                        )
                    edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_DURATION # Переход на шаг выбора длительности

                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"Ошибка выбора времени начала user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор времени.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)

        # --- Шаг 5 (Старый Шаг 6): Выбор длительности ---
        elif current_step == const.STATE_BOOKING_DURATION:
            if cb_data.startswith(const.CB_BOOK_SELECT_DURATION):
                try: bot.answer_callback_query(call.id)
                except Exception: pass

                try:
                    duration_str = cb_data[len(const.CB_BOOK_SELECT_DURATION):]
                    user_state_data['duration_str'] = duration_str

                    # Проверяем наличие всех нужных данных
                    selected_date_obj = user_state_data.get('selected_date_obj')
                    start_time_obj = user_state_data.get('start_time_obj')
                    cr_name = user_state_data.get('cr_name') # Имя комнаты
                    sel_date_str = user_state_data.get('selected_date_str')
                    s_time_str = user_state_data.get('start_time_str')

                    if not all([selected_date_obj, start_time_obj, cr_name, sel_date_str, s_time_str]):
                        missing = [k for k,v in user_state_data.items() if not v]
                        logger.error(f"Отсутствуют данные {missing} в состоянии user {user_id} на шаге {current_step}")
                        raise KeyError(f"Недостаточно данных в состоянии: {missing}")

                    # Рассчитываем время окончания
                    start_dt = datetime.combine(selected_date_obj, start_time_obj)
                    hours_str, minutes_str = duration_str.split(':')
                    duration_delta = timedelta(hours=int(hours_str), minutes=int(minutes_str))
                    end_dt = start_dt + duration_delta
                    e_time_str = end_dt.strftime('%H:%M')
                    user_state_data['end_time_obj'] = end_dt.time()
                    user_state_data['end_time_str'] = e_time_str
                    logger.debug(f"User {user_id} выбрал длительность {duration_str}, время окончания: {e_time_str}")

                    # Формируем текст подтверждения, используя обновленную константу
                    confirm_text = const.MSG_BOOKING_CONFIRM_DETAILS.format(
                        cr_name=cr_name, # Используем имя комнаты
                        date=sel_date_str,
                        start_time=s_time_str,
                        end_time=e_time_str,
                        duration=duration_str
                    )
                    markup = keyboards.generate_booking_confirmation_keyboard()
                    # Используем константу для шага подтверждения
                    edit_or_send_message(bot, chat_id, message_id, f"{const.MSG_BOOKING_STEP_6_CONFIRM}\n{confirm_text}", reply_markup=markup, parse_mode="Markdown", **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_CONFIRM # Переход на шаг подтверждения

                except (ValueError, KeyError, AttributeError) as e:
                    logger.error(f"Ошибка выбора длительности user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор длительности.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)

        # --- Шаг 6 (Старый Шаг 7): Финальное подтверждение ---
        elif current_step == const.STATE_BOOKING_CONFIRM:
            if cb_data == const.CB_BOOK_CONFIRM_FINAL:
                try: bot.answer_callback_query(call.id, "Сохраняем бронирование...")
                except Exception: pass

                logger.info(f"User {user_id} подтвердил создание бронирования: {user_state_data}")
                try:
                    # Извлекаем нужные данные для создания бронирования
                    cr_id = user_state_data.get('cr_id') # ID комнаты
                    sel_date_str = user_state_data.get('selected_date_str')
                    s_time_str = user_state_data.get('start_time_str')
                    dur_str = user_state_data.get('duration_str')

                    if not all([cr_id, sel_date_str, s_time_str, dur_str]):
                        missing = [k for k in ['cr_id', 'selected_date_str', 'start_time_str', 'duration_str'] if not user_state_data.get(k)]
                        logger.error(f"Отсутствуют критические данные для создания бронирования user {user_id}: {missing}")
                        raise ValueError(f"Недостаточно данных для создания бронирования: {missing}")

                    success = False
                    msg = const.MSG_BOOKING_FAIL_GENERAL
                    new_booking_id = None
                    # Вызываем сервис создания бронирования, передавая cr_id
                    success, msg, new_booking_id = bookingService.create_booking(
                        db, user_id, cr_id, sel_date_str, s_time_str, dur_str
                    )

                    if msg is None:
                        logger.error(f"create_booking не вернул сообщение для user {user_id}, success={success}")
                        msg = const.MSG_BOOKING_SUCCESS if success else const.MSG_BOOKING_FAIL_GENERAL

                    edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown", **kwargs_edit_send)

                    # Перепланируем уведомления в случае успеха
                    if success and new_booking_id:
                        if scheduler:
                            logger.debug(f"Бронь {new_booking_id} успешно создана, перепланируем уведомления...")
                            try:
                                # Вызываем перепланировку
                                notificationService.schedule_all_notifications()
                                logger.info(f"Уведомления перепланированы после создания брони {new_booking_id}.")
                            except Exception as e_schedule:
                                logger.error(f"Ошибка планирования уведомлений после создания брони {new_booking_id}: {e_schedule}", exc_info=True)
                        else:
                            logger.warning("Планировщик (scheduler) не доступен, уведомления не запланированы.")
                    elif success and not new_booking_id:
                        logger.error(f"create_booking вернул success=True, но new_booking_id=None для user {user_id}. Данные: {user_state_data}")

                except ValueError as e:
                    logger.error(f"Ошибка данных при финальном подтверждении бронирования user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_FAIL_GENERAL, reply_markup=None, **kwargs_edit_send) # Используем общую ошибку
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при вызове create_booking user {user_id}: {e}", exc_info=True)
                    edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_FAIL_GENERAL, reply_markup=None, **kwargs_edit_send)
                finally:
                    clear_user_state(user_id) # Очищаем состояние в любом случае после попытки создания

        # --- Неверный шаг или callback ---
        else:
            # Логика обработки неверного шага или колбэка остается прежней
            if cb_data.startswith(const.CB_BOOK_ACTION):
                logger.warning(f"User {user_id} нажал кнопку бронирования '{cb_data}' на неверном шаге {current_step}. Возможно, старое сообщение.")
                try: bot.answer_callback_query(call.id, "Это действие сейчас неактуально. Пожалуйста, используйте последнее сообщение.", show_alert=True)
                except Exception: pass
            else:
                # Если callback не относится к процессу бронирования, но состояние активно - это ошибка
                logger.error(f"Неожиданный callback '{cb_data}' от user {user_id} во время активного шага бронирования {current_step}. Сброс состояния.")
                try: bot.answer_callback_query(call.id, "Произошла ошибка в процессе бронирования. Попробуйте начать заново.", show_alert=True)
                except Exception: pass
                try: edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None, **kwargs_edit_send)
                except Exception as e_edit_unexpected: logger.error(f"Не удалось отредактировать сообщение при неожиданном колбэке user {user_id}: {e_edit_unexpected}")
                finally: clear_user_state(user_id)

    # --- Обработка любых исключений внутри блока try шагов ---
    except Exception as e:
        logger.critical(f"Критическая ошибка в handle_booking_steps (user={user_id}, step={current_step}, cb='{cb_data}'): {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception: pass
        try: edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
        except Exception as e_edit_crit: logger.error(f"Не удалось отредактировать сообщение после критической ошибки в handle_booking_steps: {e_edit_crit}")
        finally: clear_user_state(user_id)

# --- END OF FILE handlers/callbacks/process_callbacks.py ---