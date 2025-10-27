# --- START OF FILE callback_handlers.py ---

# handlers/callback_handlers.py
import telebot
from telebot import types
from telebot.types import CallbackQuery
from database import Database, QueryResult
from logger import logger
# Используем псевдонимы для импортированных сервисов для ясности
import services.user_service as userService
import services.booking_service as bookingService
import services.equipment_service as equipmentService
import services.admin_service as adminService
import services.notification_service as notificationService

from utils import keyboards
import constants as const
from datetime import datetime, date, time, timedelta
import os
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict, Any, Set, Tuple, Optional, List
import logging
from telebot import apihelper # Добавим импорт

# <<< ИЗМЕНЕНИЕ: Импортируем состояния и функции очистки из нового модуля states.py >>>
from states import (
    user_booking_states,
    admin_process_states,
    clear_user_state,
    clear_admin_state
)

# <<< ИЗМЕНЕНИЕ: Старые импорты/определения состояний удалены >>>
# try:
#     from handlers.admin_commands import admin_process_states, clear_admin_state
# except ImportError:
#     logger.error("Не удалось импортировать admin_process_states, clear_admin_state из admin_commands. Возможен циклический импорт!")
#     # Создаем заглушки, чтобы код не падал, но функционал админки будет сломан
#     admin_process_states: Dict[int, Dict[str, Any]] = {}
#     def clear_admin_state(admin_id: int):
#         logger.error(f"Вызвана заглушка clear_admin_state для {admin_id}. Состояния не работают!")
#         if admin_id in admin_process_states:
#              try:
#                  del admin_process_states[admin_id]
#              except KeyError:
#                   pass # Уже удалено
#
# # Глобальный словарь состояний пользователя
# user_booking_states: Dict[int, Dict[str, Any]] = {}
#
# def clear_user_state(user_id: int):
#     """Безопасно удаляет состояние пользователя."""
#     if user_id in user_booking_states:
#         try:
#             del user_booking_states[user_id]
#             logger.debug(f"Состояние user {user_id} очищено.")
#         except KeyError:
#              logger.warning(f"Попытка удалить уже отсутствующее состояние для user {user_id}")


def _edit_or_send_message(bot: telebot.TeleBot, chat_id: int, message_id: Optional[int], text: str, **kwargs):
    """Пытается отредактировать сообщение, если message_id есть, иначе отправляет новое."""
    user_id_for_state_update = kwargs.pop('user_id_for_state_update', None)
    admin_id_for_state_update = kwargs.pop('admin_id_for_state_update', None) # Добавлено для админских состояний
    new_message_id = None # ID сообщения, которое в итоге будет актуальным

    try:
        if message_id:
            # Пытаемся отредактировать существующее сообщение
            bot.edit_message_text(text, chat_id, message_id, **kwargs)
            logger.debug(f"Сообщение {message_id} отредактировано в чате {chat_id}")
            new_message_id = message_id
        else:
            # Если message_id нет, отправляем новое сообщение
            logger.warning(f"Нет message_id для редактирования в чате {chat_id}, отправка нового сообщения.")
            sent_message = None
            try:
                sent_message = bot.send_message(chat_id, text, **kwargs)
            except Exception as e_send_inner:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (внутренняя ошибка): {e_send_inner}")
                 raise e_send_inner # Пробрасываем ошибку выше

            if sent_message: # Проверяем, что сообщение было успешно отправлено
                new_message_id = sent_message.message_id
            else:
                 logger.error(f"Отправка нового сообщения в {chat_id} не вернула объект сообщения.")

    except apihelper.ApiTelegramException as e_api:
        error_text = str(e_api).lower()
        if "message is not modified" in error_text:
            # Сообщение не изменилось, ID остается прежним
            logger.debug(f"Сообщение {message_id} не изменено (API: not modified).")
            new_message_id = message_id
        elif "message to edit not found" in error_text or "message can't be edited" in error_text:
            # Сообщение не найдено или не может быть отредактировано, отправляем новое
            logger.warning(f"Не удалось отредактировать {message_id} в {chat_id} (API: {error_text}). Отправка нового.")
            sent_message_fallback = None
            try:
                sent_message_fallback = bot.send_message(chat_id, text, **kwargs)
            except Exception as e_send_fallback:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (fallback): {e_send_fallback}")

            if sent_message_fallback:
                new_message_id = sent_message_fallback.message_id
        else:
            # Другая ошибка API при редактировании/отправке
            logger.error(f"Ошибка API при редактировании/отправке {message_id} в {chat_id}: {e_api}")
            # Попытка отправить новое сообщение как последняя мера
            sent_message_final = None
            try:
                 sent_message_final = bot.send_message(chat_id, text, **kwargs)
            except Exception as e_send_final:
                 logger.error(f"Не удалось отправить новое сообщение в {chat_id} (final fallback): {e_send_final}")

            if sent_message_final:
                 new_message_id = sent_message_final.message_id
    except Exception as e:
        # Любая другая ошибка при редактировании/отправке
        logger.error(f"Общая ошибка в _edit_or_send_message (chat={chat_id}, msg_id={message_id}): {e}", exc_info=True)
        # Попытка отправить новое сообщение
        sent_message_generic_fallback = None
        try:
             sent_message_generic_fallback = bot.send_message(chat_id, text, **kwargs)
        except Exception as e_send_generic_fallback:
             logger.error(f"Не удалось отправить новое сообщение в {chat_id} (generic fallback): {e_send_generic_fallback}")

        if sent_message_generic_fallback:
             new_message_id = sent_message_generic_fallback.message_id

    # Обновляем message_id в состоянии пользователя, если необходимо
    if user_id_for_state_update:
         if new_message_id:
             # Используем импортированный словарь user_booking_states
             if user_id_for_state_update in user_booking_states:
                 current_state = user_booking_states[user_id_for_state_update]
                 current_msg_id = current_state.get('message_id')
                 if current_msg_id != new_message_id:
                      current_state['message_id'] = new_message_id
                      logger.debug(f"Обновлен message_id на {new_message_id} для user {user_id_for_state_update}")
             else:
                  logger.debug(f"Состояние для user {user_id_for_state_update} не найдено, message_id не обновлен.")

    # Обновляем message_id в состоянии админа, если необходимо
    if admin_id_for_state_update:
         if new_message_id:
             # Используем импортированный словарь admin_process_states
             if admin_id_for_state_update in admin_process_states:
                 current_admin_state = admin_process_states[admin_id_for_state_update]
                 current_admin_msg_id = current_admin_state.get('message_id')
                 if current_admin_msg_id != new_message_id:
                      current_admin_state['message_id'] = new_message_id
                      logger.debug(f"Обновлен message_id на {new_message_id} для admin {admin_id_for_state_update}")
             else:
                  logger.debug(f"Состояние для admin {admin_id_for_state_update} не найдено, message_id не обновлен.")


def handle_booking_steps(
    bot: telebot.TeleBot, db: Database, call: CallbackQuery, state: Dict[str, Any],
    scheduler: Optional[BackgroundScheduler], active_timers: Dict[int, Any], scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """Обрабатывает колбэки в процессе бронирования на основе состояния."""
    user_id = call.from_user.id
    chat_id = state.get('chat_id', call.message.chat.id)
    message_id = state.get('message_id')
    current_step = state.get('step', const.STATE_BOOKING_IDLE)
    cb_data = call.data
    user_state_data = state.get('data', {})
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
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_PROCESS_CANCELLED, reply_markup=None, **kwargs_edit_send)
        except Exception as e_edit_cancel:
             logger.error(f"Не удалось отредактировать сообщение при отмене бронирования user {user_id}: {e_edit_cancel}")
        finally:
            # Используем импортированную функцию
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
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный ID категории.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['category_id'] = category_id
                logger.debug(f"User {user_id} выбрал категорию {category_id}")
                equipment = None
                try:
                    equipment = equipmentService.get_equipment_by_category(db, category_id)
                except Exception as e_get_eq:
                    logger.error(f"Ошибка получения оборудования для категории {category_id} (user {user_id}): {e_get_eq}", exc_info=True)
                    _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                if not equipment:
                    logger.warning(f"В категории {category_id} нет оборудования (user {user_id}).")
                    _edit_or_send_message(bot, chat_id, message_id, "В этой категории нет доступного оборудования.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                markup = keyboards.generate_equipment_keyboard(equipment, const.CB_BOOK_SELECT_EQUIPMENT)
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_2_EQUIPMENT, reply_markup=markup, **kwargs_edit_send)
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
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный ID оборудования.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                equipment_name = None
                try:
                    equipment_name = equipmentService.get_equipment_name_by_id(db, equipment_id)
                except Exception as e_get_name:
                    logger.error(f"Ошибка получения имени для оборудования {equipment_id} (user {user_id}): {e_get_name}", exc_info=True)
                    # Имя не критично для процесса, продолжаем с ID

                user_state_data['equipment_id'] = equipment_id
                user_state_data['equipment_name'] = equipment_name or f"ID {equipment_id}" # Используем ID если имя не найдено
                logger.debug(f"User {user_id} выбрал оборудование {equipment_id} ('{user_state_data['equipment_name']}')")

                markup = keyboards.generate_date_keyboard(const.CB_BOOK_SELECT_DATE)
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_3_DATE, reply_markup=markup, **kwargs_edit_send)
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
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка: Неверный формат даты.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                equipment_id = user_state_data.get('equipment_id')
                if not equipment_id:
                    logger.error(f"Отсутствует equipment_id в состоянии user {user_id} на шаге 3.")
                    _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None, **kwargs_edit_send)
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
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка получения свободных слотов.", reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                user_state_data['available_slots'] = available_slots # Сохраняем слоты в состоянии
                if not available_slots:
                    logger.warning(f"Нет свободных слотов для {equipment_id} на {selected_date_str} (user {user_id}).")
                    _edit_or_send_message(bot, chat_id, message_id, const.MSG_NO_SLOTS_AVAILABLE, reply_markup=None, **kwargs_edit_send)
                    clear_user_state(user_id)
                    return

                # Проверяем, свободен ли весь день
                is_full_day_free = False
                if len(available_slots) == 1:
                    slot_start = available_slots[0][0]
                    slot_end = available_slots[0][1]
                    if slot_start == const.WORKING_HOURS_START and slot_end == const.WORKING_HOURS_END:
                        is_full_day_free = True

                if is_full_day_free:
                    # Весь день свободен, переходим сразу к выбору времени начала
                    logger.debug(f"Дата {selected_date_str} полностью свободна для {equipment_id} (user {user_id}).")
                    full_day_slot = (const.WORKING_HOURS_START, const.WORKING_HOURS_END)
                    user_state_data['selected_slot'] = full_day_slot # Сохраняем полный слот
                    markup = keyboards.generate_time_keyboard_in_slot(full_day_slot, selected_date_obj, const.CB_BOOK_SELECT_TIME)
                    _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_5_START_TIME, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_START_TIME
                else:
                    # День частично занят, показываем доступные слоты
                    logger.debug(f"Дата {selected_date_str} частично занята для {equipment_id} (user {user_id}): {available_slots}")
                    markup = keyboards.generate_available_slots_keyboard(available_slots, const.CB_BOOK_SELECT_SLOT)
                    _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_4_SLOT, reply_markup=markup, **kwargs_edit_send)
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
                    user_state_data['selected_slot'] = selected_slot # Сохраняем выбранный слот

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
                    _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_START_TIME

                except (ValueError, IndexError, TypeError) as e:
                    logger.error(f"Ошибка выбора слота user {user_id}: {e}", exc_info=True)
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор слота.", reply_markup=None, **kwargs_edit_send)
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

                    # Определяем конец интервала для выбора длительности
                    effective_end_time = None
                    if selected_slot:
                         if isinstance(selected_slot, tuple) and len(selected_slot) == 2 and isinstance(selected_slot[1], time):
                             effective_end_time = selected_slot[1] # Конец выбранного слота
                         else:
                             logger.warning(f"Некорректный selected_slot {selected_slot} у user {user_id}, используем конец рабочего дня.")
                             effective_end_time = const.WORKING_HOURS_END
                    else:
                        # Если слот не был выбран (например, при свободном дне)
                        effective_end_time = const.WORKING_HOURS_END

                    if not isinstance(effective_end_time, time):
                        logger.error(f"Не удалось определить effective_end_time (тип: {type(effective_end_time)}) для user {user_id}")
                        raise TypeError("effective_end_time должен быть объектом time")

                    markup = keyboards.generate_duration_keyboard_in_slot(
                        start_time_obj, selected_date_obj, effective_end_time, const.CB_BOOK_SELECT_DURATION
                    )
                    # Формируем текст-подсказку
                    prompt_text = const.MSG_BOOKING_STEP_6_DURATION
                    if selected_slot: # Если был выбран конкретный слот, уточняем его конец
                        prompt_text = const.MSG_BOOKING_PROMPT_DURATION_IN_SLOT.format(
                            end_slot=bookingService._format_time(effective_end_time)
                        )
                    _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_DURATION

                except (ValueError, TypeError, KeyError) as e:
                    logger.error(f"Ошибка выбора времени начала user {user_id}: {e}", exc_info=True)
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор времени.", reply_markup=None, **kwargs_edit_send)
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

                    # Проверяем наличие всех необходимых данных из предыдущих шагов
                    selected_date_obj = user_state_data.get('selected_date_obj')
                    start_time_obj = user_state_data.get('start_time_obj')
                    if not selected_date_obj or not start_time_obj:
                        missing_keys = [k for k in ['selected_date_obj', 'start_time_obj'] if not user_state_data.get(k)]
                        logger.error(f"Отсутствуют ключи {missing_keys} в состоянии user {user_id} на шаге 6")
                        raise KeyError(f"Отсутствуют необходимые данные: {missing_keys}")

                    start_dt = datetime.combine(selected_date_obj, start_time_obj)
                    # Парсим длительность HH:MM
                    hours_str, minutes_str = duration_str.split(':')
                    hours = int(hours_str)
                    minutes = int(minutes_str)
                    duration_delta = timedelta(hours=hours, minutes=minutes)
                    end_dt = start_dt + duration_delta

                    user_state_data['end_time_obj'] = end_dt.time()
                    user_state_data['end_time_str'] = end_dt.strftime('%H:%M')
                    logger.debug(f"User {user_id} выбрал длительность {duration_str}, время окончания: {user_state_data['end_time_str']}")

                    # Получаем данные для текста подтверждения
                    equip_name = user_state_data.get('equipment_name')
                    sel_date_str = user_state_data.get('selected_date_str')
                    s_time_str = user_state_data.get('start_time_str')
                    e_time_str = user_state_data.get('end_time_str')

                    # Проверяем наличие всех данных для подтверждения
                    if not all ([equip_name, sel_date_str, s_time_str, e_time_str]):
                        missing = [k for k in ['equipment_name', 'selected_date_str', 'start_time_str', 'end_time_str'] if not user_state_data.get(k)]
                        logger.error(f"Отсутствуют данные для формирования подтверждения user {user_id}: {missing}")
                        raise KeyError(f"Недостаточно данных для формирования подтверждения: {missing}")

                    # Формируем текст подтверждения
                    confirm_text = const.MSG_BOOKING_CONFIRM_DETAILS.format(
                        equip_name=equip_name,
                        date=sel_date_str,
                        start_time=s_time_str,
                        end_time=e_time_str,
                        duration=duration_str
                    )
                    markup = keyboards.generate_booking_confirmation_keyboard()
                    _edit_or_send_message(bot, chat_id, message_id, f"{const.MSG_BOOKING_STEP_7_CONFIRM}\n{confirm_text}", reply_markup=markup, parse_mode="Markdown", **kwargs_edit_send)
                    state['step'] = const.STATE_BOOKING_CONFIRM

                except (ValueError, KeyError, AttributeError) as e: # AttributeError если combine не сработает
                    logger.error(f"Ошибка выбора длительности user {user_id}: {e}", exc_info=True)
                    _edit_or_send_message(bot, chat_id, message_id, "Ошибка: Не удалось обработать выбор длительности.", reply_markup=None, **kwargs_edit_send)
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
                     # Извлекаем все необходимые данные из состояния
                     equip_id = user_state_data.get('equipment_id')
                     sel_date_str = user_state_data.get('selected_date_str')
                     s_time_str = user_state_data.get('start_time_str')
                     dur_str = user_state_data.get('duration_str')

                     # Проверяем наличие данных
                     if not all([equip_id, sel_date_str, s_time_str, dur_str]):
                         missing = [k for k in ['equipment_id', 'selected_date_str', 'start_time_str', 'duration_str'] if not user_state_data.get(k)]
                         logger.error(f"Отсутствуют критические данные для создания бронирования user {user_id}: {missing}")
                         raise ValueError(f"Недостаточно данных для создания бронирования: {missing}")

                     success = False
                     msg = const.MSG_BOOKING_FAIL_GENERAL # Сообщение по умолчанию
                     new_booking_id = None
                     # Вызов сервиса создания бронирования
                     success, msg, new_booking_id = bookingService.create_booking(
                         db, user_id, equip_id, sel_date_str, s_time_str, dur_str
                     )

                     # Редактируем сообщение с результатом
                     _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown", **kwargs_edit_send)

                     # Если бронь успешно создана, планируем уведомления
                     if success:
                         if new_booking_id:
                             if scheduler:
                                 logger.debug(f"Бронь {new_booking_id} успешно создана, планируем уведомления...")
                                 try:
                                     # Перепланируем все уведомления (проще и надежнее)
                                     notificationService.schedule_all_notifications(
                                         db, bot, scheduler, active_timers, scheduled_jobs_registry
                                     )
                                     logger.info(f"Уведомления перепланированы после создания брони {new_booking_id}.")
                                 except Exception as e_schedule:
                                     logger.error(f"Ошибка планирования уведомлений после создания брони {new_booking_id}: {e_schedule}", exc_info=True)
                                     # Не сообщаем пользователю, но логируем
                             else:
                                 logger.warning("Планировщик (scheduler) не передан в handle_booking_steps, уведомления не запланированы.")
                         else:
                             # Странная ситуация: успех есть, а ID нет
                             logger.error(f"create_booking вернул success=True, но new_booking_id=None для user {user_id}. Данные: {user_state_data}")
                     # else: Сообщение об ошибке уже отправлено через _edit_or_send_message

                except ValueError as e:
                     logger.error(f"Ошибка данных при финальном подтверждении бронирования user {user_id}: {e}", exc_info=True)
                     _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
                except Exception as e:
                     logger.error(f"Непредвиденная ошибка при вызове create_booking user {user_id}: {e}", exc_info=True)
                     _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_FAIL_GENERAL, reply_markup=None, **kwargs_edit_send)
                finally:
                     # Очищаем состояние пользователя в любом случае после попытки подтверждения
                     clear_user_state(user_id)

        # --- Неверный шаг или callback внутри процесса бронирования ---
        else:
             # Проверяем, является ли колбэк частью процесса бронирования (на случай нажатия старой кнопки)
             if cb_data.startswith(const.CB_BOOK_ACTION):
                 logger.warning(f"User {user_id} нажал кнопку бронирования '{cb_data}' на неверном шаге {current_step}. Возможно, старое сообщение.")
                 try:
                     bot.answer_callback_query(call.id, "Это действие сейчас неактуально. Пожалуйста, используйте последнее сообщение.", show_alert=True)
                 except Exception as e_ans_wrong_step:
                      logger.warning(f"Не удалось ответить на callback неверного шага: {e_ans_wrong_step}")
                 # Не сбрасываем состояние, даем шанс нажать на правильном сообщении
             else:
                 # Если колбэк вообще не из процесса бронирования, но состояние активно - это ошибка
                 logger.error(f"Неожиданный callback '{cb_data}' от user {user_id} во время активного шага бронирования {current_step}. Сброс состояния.")
                 try:
                     bot.answer_callback_query(call.id, "Произошла ошибка в процессе бронирования. Попробуйте начать заново.", show_alert=True)
                 except Exception as e_ans_unexpected:
                      logger.warning(f"Не удалось ответить на callback при неожиданном действии: {e_ans_unexpected}")
                 try: # Попытка отредактировать сообщение, чтобы убрать кнопки
                     _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None, **kwargs_edit_send)
                 except Exception as e_edit_unexpected:
                     logger.error(f"Не удалось отредактировать сообщение при неожиданном колбэке user {user_id}: {e_edit_unexpected}")
                 finally:
                     clear_user_state(user_id) # Сбрасываем состояние

    # --- Обработка любых исключений внутри блока try шагов ---
    except Exception as e:
        logger.critical(f"Критическая ошибка в handle_booking_steps (user={user_id}, step={current_step}, cb='{cb_data}'): {e}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception as e_ans_crit:
             logger.error(f"Не удалось ответить на callback после критической ошибки в handle_booking_steps: {e_ans_crit}")

        try: # Попытка безопасно отредактировать сообщение
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit_send)
        except Exception as e_edit_crit:
            logger.error(f"Не удалось отредактировать сообщение после критической ошибки в handle_booking_steps: {e_edit_crit}")
        finally:
             # Очищаем состояние при любой критической ошибке в обработке шага
             clear_user_state(user_id)


# <<< Главная функция обработки callback >>>
# Примерные строки: 415 - 712

# <<< Главная функция обработки callback >>>
# <<< Главная функция обработки callback >>>
# <<< Главная функция обработки callback >>>
# <<< Главная функция обработки callback >>>
def handle_callback_query(
    bot: telebot.TeleBot, db: Database, scheduler: Optional[BackgroundScheduler],
    active_timers: Dict[int, Any], scheduled_jobs_registry: Set[Tuple[str, int]], call: CallbackQuery
):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    cb_data = call.data
    logger.debug(f"Callback: user={user_id}, chat={chat_id}, msg={message_id}, data='{cb_data}'")

    # --- Обработка подтверждения брони (из уведомления) ---
    if cb_data.startswith(const.CB_BOOK_CONFIRM_START):
        booking_id_str = cb_data[len(const.CB_BOOK_CONFIRM_START):]
        booking_id = None
        try:
            booking_id = int(booking_id_str)
        except ValueError:
            logger.error(f"Неверный booking_id '{booking_id_str}' в CB_BOOK_CONFIRM_START от user {user_id}")
            try:
                bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
            except Exception:
                pass
            return # Выход

        logger.info(f"User {user_id} подтверждает бронь {booking_id} из уведомления.")
        success = False
        try:
            success = notificationService.confirm_booking_callback_logic(db, active_timers, booking_id, user_id)
        except Exception as e_confirm_logic:
            logger.error(f"Ошибка в confirm_booking_callback_logic для booking {booking_id}, user {user_id}: {e_confirm_logic}", exc_info=True)
            success = False

        if success:
            try:
                bot.answer_callback_query(call.id, const.MSG_BOOKING_CONFIRMED)
            except Exception as e_ans_confirm_ok:
                 logger.warning(f"Не удалось ответить на callback после успешного подтверждения {booking_id}: {e_ans_confirm_ok}")
            try:
                bot.edit_message_text(f"✅ {const.MSG_BOOKING_CONFIRMED}", chat_id, message_id, reply_markup=None)
            except Exception as e_edit_confirm:
                logger.warning(f"Не удалось отредактировать сообщение {message_id} после подтверждения брони {booking_id}: {e_edit_confirm}")
        else:
            alert_msg = "Не удалось подтвердить. Возможно, время вышло или бронь отменена."
            try:
                bot.answer_callback_query(call.id, alert_msg, show_alert=True)
            except Exception as e_ans_confirm_fail:
                 logger.warning(f"Не удалось ответить на callback после неудачного подтверждения {booking_id}: {e_ans_confirm_fail}")
        return

    # --- 1. Проверка состояния бронирования пользователя ---
    user_state = user_booking_states.get(user_id)
    if user_state:
        current_state_step = user_state.get('step', const.STATE_BOOKING_IDLE)
        if current_state_step != const.STATE_BOOKING_IDLE:
            current_message_id = user_state.get('message_id')
            if current_message_id:
                 if message_id != current_message_id:
                     logger.warning(f"User {user_id} нажал кнопку '{cb_data}' на старом сообщении {message_id} процесса бронирования. Активное сообщение: {current_message_id}. Игнорируем.")
                     try:
                         bot.answer_callback_query(call.id, "Пожалуйста, используйте кнопки на последнем сообщении процесса бронирования.", show_alert=True)
                     except apihelper.ApiTelegramException as e_ans_old:
                          logger.warning(f"Не удалось ответить на callback старого сообщения {message_id} процесса бронирования: {e_ans_old}")
                     return
            handle_booking_steps(bot, db, call, user_state, scheduler, active_timers, scheduled_jobs_registry)
            return

    # --- 2. Обработка колбэков вне процесса бронирования пользователя ---
    logger.debug(f"User {user_id} не в процессе бронирования, обработка callback '{cb_data}'...")

    # --- 2.1 Проверка прав доступа (Админ/Активный пользователь) ---
    is_admin_user = False
    is_active_user = False
    try:
        is_admin_user = userService.is_admin(db, user_id)
        if not is_admin_user:
            is_active_user = userService.is_user_registered_and_active(db, user_id)
    except Exception as e_perm_check:
        logger.error(f"Ошибка проверки прав доступа для user {user_id} при обработке callback '{cb_data}': {e_perm_check}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception as e_ans_perm:
            logger.error(f"Не удалось ответить на callback после ошибки проверки прав: {e_ans_perm}")
        return

    is_admin_action = (
        cb_data.startswith(const.CB_REG_CONFIRM_USER) or
        cb_data.startswith(const.CB_REG_DECLINE_USER) or
        cb_data.startswith(const.CB_MANAGE_SELECT_USER) or
        cb_data.startswith(const.CB_MANAGE_BLOCK_USER) or
        cb_data.startswith(const.CB_MANAGE_UNBLOCK_USER) or
        cb_data.startswith(const.CB_ADMIN_CANCEL_SELECT) or
        cb_data.startswith(const.CB_ADMIN_CANCEL_CONFIRM) or
        cb_data.startswith(const.CB_FILTER_BY_TYPE) or
        cb_data.startswith(const.CB_FILTER_SELECT_USER) or
        cb_data.startswith(const.CB_FILTER_SELECT_EQUIPMENT) or
        cb_data.startswith(const.CB_FILTER_SELECT_DATE) or
        cb_data.startswith(const.CB_EQUIP_DELETE_SELECT) or
        cb_data.startswith(const.CB_EQUIP_DELETE_CONFIRM) or
        cb_data.startswith(const.CB_ADMIN_ADD_EQUIP_SELECT_CAT_) or
        cb_data == const.CB_ADMIN_ADD_EQUIP_NEW_CAT or
        cb_data == const.CB_ADMIN_ADD_EQUIP_CANCEL
    )

    needs_active_user_check = not (
        is_admin_action or
        cb_data == const.CB_IGNORE or
        cb_data.startswith(const.CB_ACTION_CANCEL) or
        cb_data.startswith(const.CB_BOOK_CANCEL_PROCESS)
    )

    if is_admin_action:
        if not is_admin_user:
             logger.warning(f"Пользователь {user_id} (не админ) попытался выполнить админское действие '{cb_data}'.")
             try:
                 bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)
             except Exception as e_ans_no_perm:
                 logger.error(f"Не удалось ответить на callback при отказе в админском доступе: {e_ans_no_perm}")
             return

    if needs_active_user_check:
        if not is_admin_user:
            if not is_active_user:
                logger.warning(f"Неактивный или незарегистрированный пользователь {user_id} попытался выполнить действие '{cb_data}'.")
                try:
                    bot.answer_callback_query(call.id, const.MSG_ERROR_NOT_REGISTERED, show_alert=True)
                except Exception as e_ans_not_reg:
                    logger.error(f"Не удалось ответить на callback неактивному пользователю: {e_ans_not_reg}")
                try:
                    bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
                except Exception as e_edit_not_reg:
                    logger.debug(f"Не удалось убрать клавиатуру у неактивного пользователя {user_id}: {e_edit_not_reg}")
                return

    # --- 2.2 Маршрутизация колбэков ---
    admin_id_param = user_id if is_admin_user else None
    kwargs_edit_send_other = {'user_id_for_state_update': user_id, 'admin_id_for_state_update': admin_id_param}

    try:
        # --- Обработка добавления оборудования админом ---
        if cb_data.startswith(const.CB_ADMIN_ADD_EQUIP_SELECT_CAT_):
             if is_admin_user:
                 handle_admin_add_equip_select_cat(bot, db, call, user_id, chat_id, message_id)
             else:
                 logger.error(f"Не-админ {user_id} достиг обработчика CB_ADMIN_ADD_EQUIP_SELECT_CAT_")
                 bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)
        elif cb_data == const.CB_ADMIN_ADD_EQUIP_NEW_CAT:
             if is_admin_user:
                 handle_admin_add_equip_new_cat(bot, db, call, user_id, chat_id, message_id)
             else:
                 logger.error(f"Не-админ {user_id} достиг обработчика CB_ADMIN_ADD_EQUIP_NEW_CAT")
                 bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)
        elif cb_data == const.CB_ADMIN_ADD_EQUIP_CANCEL:
             if is_admin_user:
                 handle_admin_add_equip_cancel(bot, db, call, user_id, chat_id, message_id)
             else:
                 logger.error(f"Не-админ {user_id} достиг обработчика CB_ADMIN_ADD_EQUIP_CANCEL")
                 bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)

        # --- Отмена бронирования пользователем (из списка /mybookings) ---
        # --- START OF MODIFIED BLOCK ---
        elif cb_data.startswith(const.CB_CANCEL_SELECT_BOOKING):
            booking_id_str = cb_data[len(const.CB_CANCEL_SELECT_BOOKING):]
            booking_id = None
            try:
                booking_id = int(booking_id_str)
            except ValueError:
                logger.error(f"Неверный booking_id '{booking_id_str}' в CB_CANCEL_SELECT_BOOKING от user {user_id}")
                bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
                return
            logger.info(f"User {user_id} инициировал отмену брони {booking_id}")
            try:
                bot.answer_callback_query(call.id, "Отменяем бронирование...")
            except Exception as e_ans_cancel:
                logger.warning(f"Не удалось ответить на callback отмены {booking_id}: {e_ans_cancel}")
            success = False
            # --- ИЗМЕНЕНИЕ: Используем общую ошибку как fallback ---
            msg = const.MSG_ERROR_GENERAL # Сообщение по умолчанию при непредвиденной ошибке
            owner_user_id_unused = None
            try:
                # Сервис должен вернуть (True, MSG_BOOKING_CANCELLED) или (False, "Причина неудачи")
                success, msg, owner_user_id_unused = bookingService.cancel_booking(db, booking_id, user_id=user_id, is_admin_cancel=False)
            except Exception as e_cancel_logic:
                logger.error(f"Ошибка в cancel_booking для booking {booking_id}, user {user_id}: {e_cancel_logic}", exc_info=True)
                success = False
                msg = const.MSG_ERROR_GENERAL # Перезаписываем на общую ошибку при исключении
            # Проверяем, что msg не None перед отправкой
            if msg is None:
                logger.error(f"cancel_booking не вернул сообщение для брони {booking_id}")
                msg = const.MSG_ERROR_GENERAL # Запасной вариант
            _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown", **kwargs_edit_send_other)
            if success:
                 if scheduler:
                     logger.debug(f"Бронь {booking_id} отменена пользователем, очищаем связанные задачи...")
                     try:
                         notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
                     except Exception as e_cleanup:
                         logger.error(f"Ошибка очистки задач после отмены брони {booking_id}: {e_cleanup}", exc_info=True)
                 else:
                     logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")
        # --- END OF MODIFIED BLOCK ---

        # --- Выбор брони для отмены админом (шаг 1) ---
        elif cb_data.startswith(const.CB_ADMIN_CANCEL_SELECT):
             booking_id_str = cb_data[len(const.CB_ADMIN_CANCEL_SELECT):]
             booking_id = None
             try:
                 booking_id = int(booking_id_str)
             except ValueError:
                 logger.error(f"Неверный booking_id '{booking_id_str}' в CB_ADMIN_CANCEL_SELECT от admin {user_id}")
                 bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
                 return
             handle_admin_cancel_select(bot, db, call, user_id, chat_id, message_id, booking_id)

        # --- Подтверждение отмены админом (шаг 2) ---
        elif cb_data.startswith(const.CB_ADMIN_CANCEL_CONFIRM):
             booking_id_str = cb_data[len(const.CB_ADMIN_CANCEL_CONFIRM):]
             booking_id = None
             try:
                 booking_id = int(booking_id_str)
             except ValueError:
                 logger.error(f"Неверный booking_id '{booking_id_str}' в CB_ADMIN_CANCEL_CONFIRM от admin {user_id}")
                 bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
                 return
             handle_admin_cancel_confirm(bot, db, call, user_id, chat_id, message_id, booking_id, scheduler, scheduled_jobs_registry)

        # --- Завершение бронирования пользователем (из списка /mybookings) ---
        elif cb_data.startswith(const.CB_FINISH_SELECT_BOOKING):
             booking_id_str = cb_data[len(const.CB_FINISH_SELECT_BOOKING):]
             booking_id = None
             try:
                 booking_id = int(booking_id_str)
             except ValueError:
                 logger.error(f"Неверный booking_id '{booking_id_str}' в CB_FINISH_SELECT_BOOKING от user {user_id}")
                 bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
                 return
             logger.info(f"User {user_id} инициировал завершение брони {booking_id}")
             try:
                 bot.answer_callback_query(call.id, "Завершаю бронирование...")
             except Exception as e_ans_finish:
                 logger.warning(f"Не удалось ответить на callback завершения {booking_id}: {e_ans_finish}")
             success = False
             msg = None
             try:
                 success, msg = bookingService.finish_booking(db, booking_id, user_id)
             except Exception as e_finish_logic:
                 logger.error(f"Ошибка в finish_booking для booking {booking_id}, user {user_id}: {e_finish_logic}", exc_info=True)
                 success = False
                 msg = const.MSG_ERROR_GENERAL
             if msg is None:
                 logger.error(f"finish_booking не вернул сообщение для брони {booking_id}")
                 msg = const.MSG_ERROR_GENERAL
             _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, parse_mode="Markdown", **kwargs_edit_send_other)
             if success:
                  if scheduler:
                      logger.debug(f"Бронь {booking_id} завершена пользователем, очищаем связанные задачи...")
                      try:
                          notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
                      except Exception as e_cleanup_finish:
                          logger.error(f"Ошибка очистки задач после завершения брони {booking_id}: {e_cleanup_finish}", exc_info=True)
                  else:
                      logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")

        # --- Выбор брони для продления (из /extend или из уведомления) ---
        elif cb_data.startswith(const.CB_EXTEND_SELECT_BOOKING) or cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT):
             is_from_notify = cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT)
             prefix_len = len(const.CB_NOTIFY_EXTEND_PROMPT) if is_from_notify else len(const.CB_EXTEND_SELECT_BOOKING)
             booking_id_str = cb_data[prefix_len:]
             booking_id = None
             try:
                 booking_id = int(booking_id_str)
             except ValueError:
                 logger.error(f"Неверный booking_id '{booking_id_str}' в колбэке продления от user {user_id}")
                 bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
                 return
             source = "из уведомления" if is_from_notify else "из команды /extend"
             logger.info(f"User {user_id} выбрал бронь {booking_id} для продления ({source})")
             if is_from_notify:
                 timer = active_timers.pop(booking_id, None)
                 if timer:
                     try:
                         timer.cancel()
                         logger.info(f"Таймер изменения сообщения продления для брони {booking_id} отменен пользователем (нажал 'Продлить').")
                     except Exception as e_cancel_timer:
                         logger.error(f"Ошибка при отмене таймера продления {booking_id} (нажал 'Продлить'): {e_cancel_timer}")
                 else:
                     logger.warning(f"Таймер изменения сообщения продления для брони {booking_id} не найден при нажатии 'Продлить'.")
             handle_extend_select_booking(bot, db, call, user_id, chat_id, message_id, booking_id, source)

        # --- Выбор времени продления ---
        elif cb_data.startswith(const.CB_EXTEND_SELECT_TIME):
             data_part = cb_data[len(const.CB_EXTEND_SELECT_TIME):]
             parts = data_part.split('_')
             booking_id = None
             extension_str = None
             if len(parts) == 2:
                 try:
                     booking_id = int(parts[0])
                     extension_str = parts[1]
                     if len(extension_str.split(':')) != 2:
                          raise ValueError("Неверный формат времени продления")
                 except (ValueError, IndexError) as e_parse_ext:
                     logger.error(f"Неверный формат данных '{data_part}' в CB_EXTEND_SELECT_TIME от user {user_id}: {e_parse_ext}")
                     bot.answer_callback_query(call.id, "Ошибка данных для продления.", show_alert=True)
                     return
             else:
                 logger.error(f"Неверное количество частей '{len(parts)}' в CB_EXTEND_SELECT_TIME от user {user_id}")
                 bot.answer_callback_query(call.id, "Ошибка формата колбэка.", show_alert=True)
                 return
             logger.info(f"User {user_id} выбрал продление на {extension_str} для брони {booking_id}")
             handle_extend_select_time(bot, db, call, user_id, chat_id, message_id, booking_id, extension_str, scheduler, active_timers, scheduled_jobs_registry)

        # --- Отказ от продления (из уведомления) ---
        elif cb_data.startswith(const.CB_NOTIFY_DECLINE_EXT):
             booking_id_str = cb_data[len(const.CB_NOTIFY_DECLINE_EXT):]
             booking_id = None
             try:
                 booking_id = int(booking_id_str)
             except ValueError:
                 logger.error(f"Неверный booking_id '{booking_id_str}' в CB_NOTIFY_DECLINE_EXT от user {user_id}")
                 bot.answer_callback_query(call.id, "Ошибка ID брони.", show_alert=True)
                 return
             logger.info(f"User {user_id} отказался продлевать бронь {booking_id} из уведомления.")
             timer = active_timers.pop(booking_id, None)
             if timer:
                 try:
                     timer.cancel()
                     logger.info(f"Таймер изменения сообщения продления для брони {booking_id} отменен пользователем (нажал 'Отмена').")
                 except Exception as e_cancel_timer_decline:
                     logger.error(f"Ошибка при отмене таймера продления {booking_id} (нажал 'Отмена'): {e_cancel_timer_decline}")
             else:
                 logger.warning(f"Таймер изменения сообщения продления для брони {booking_id} не найден при нажатии 'Отмена'.")
             try:
                 bot.answer_callback_query(call.id, "Хорошо, бронирование завершится по расписанию.")
             except Exception as e_ans_decline:
                 logger.warning(f"Не удалось ответить на callback отказа от продления {booking_id}: {e_ans_decline}")
             try:
                 original_text = call.message.text or f"Бронирование {booking_id}"
                 bot.edit_message_text(f"{original_text}\n\n{const.MSG_EXTEND_DECLINED}", chat_id, message_id, reply_markup=None)
             except Exception as e_edit_decline:
                 logger.warning(f"Не удалось отредактировать сообщение {message_id} после отказа от продления {booking_id}: {e_edit_decline}")

        # --- Обработка регистрации ---
        elif cb_data.startswith(const.CB_REG_CONFIRM_USER):
             handle_registration_confirm(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_REG_DECLINE_USER):
             handle_registration_decline(bot, db, call, user_id, chat_id, message_id)

        # --- Просмотр броней по дате (/datebookings) ---
        elif cb_data.startswith(const.CB_DATEB_SELECT_DATE):
             handle_datebookings_select(bot, db, call, user_id, chat_id, message_id)

        # --- Просмотр броней по месту (/workspacebookings) ---
        elif cb_data.startswith(const.CB_WSB_SELECT_CATEGORY):
             handle_wsb_category_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_WSB_SELECT_EQUIPMENT):
             handle_wsb_equipment_select(bot, db, call, user_id, chat_id, message_id)

        # --- Фильтрация для отчета (/allbookings) ---
        elif cb_data.startswith(const.CB_FILTER_BY_TYPE):
             handle_filter_type_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith((const.CB_FILTER_SELECT_USER, const.CB_FILTER_SELECT_EQUIPMENT, const.CB_FILTER_SELECT_DATE)):
             handle_filter_value_select(bot, db, call, user_id, chat_id, message_id)

        # --- Удаление оборудования ---
        elif cb_data.startswith(const.CB_EQUIP_DELETE_SELECT):
             handle_equip_delete_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_EQUIP_DELETE_CONFIRM):
             handle_equip_delete_confirm(bot, db, call, user_id, chat_id, message_id)

        # --- Управление пользователями ---
        elif cb_data.startswith(const.CB_MANAGE_SELECT_USER):
             handle_manage_user_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_MANAGE_BLOCK_USER) or cb_data.startswith(const.CB_MANAGE_UNBLOCK_USER):
             handle_manage_user_action(bot, db, call, user_id, chat_id, message_id)

        # --- Обработка кнопок отмены ---
        elif cb_data.startswith(const.CB_ACTION_CANCEL):
             context = cb_data[len(const.CB_ACTION_CANCEL):]
             logger.debug(f"User {user_id} нажал кнопку отмены для контекста '{context}'. Сообщение: {message_id}")
             try:
                 bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
             except Exception as e_ans_cancel:
                 logger.warning(f"Не удалось ответить на callback отмены '{context}': {e_ans_cancel}")
             try:
                 if context == "delete_equip":
                     handle_cancel_delete_equip(bot, db, chat_id, message_id, **kwargs_edit_send_other)
                 elif context == "admin_cancel_confirm":
                     handle_cancel_admin_cancel(bot, db, chat_id, message_id, **kwargs_edit_send_other)
                 elif context == "manage_user_list":
                     handle_cancel_manage_user(bot, db, chat_id, message_id, **kwargs_edit_send_other)
                 elif context == const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1).rstrip('_'):
                     logger.debug(f"Отмена выбора времени продления (контекст '{context}'), удаляем сообщение {message_id}")
                     try:
                         bot.delete_message(chat_id, message_id)
                     except Exception as e_del_cancel_ext:
                         logger.warning(f"Не удалось удалить сообщение {message_id} при отмене продления: {e_del_cancel_ext}")
                 else:
                     logger.debug(f"Общая отмена для контекста '{context}', редактируем сообщение {message_id}")
                     _edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None, **kwargs_edit_send_other)
             except Exception as e_cancel_action:
                 logger.error(f"Ошибка при обработке отмены для контекста '{context}', сообщение {message_id}: {e_cancel_action}", exc_info=True)
                 try:
                     _edit_or_send_message(bot, chat_id, message_id, const.MSG_ACTION_CANCELLED, reply_markup=None, **kwargs_edit_send_other)
                 except Exception as e_edit_fallback_cancel:
                     logger.error(f"Не удалось даже отредактировать сообщение {message_id} после ошибки отмены '{context}': {e_edit_fallback_cancel}")

        # --- Игнорирование колбэка ---
        elif cb_data == const.CB_IGNORE:
            try:
                bot.answer_callback_query(call.id)
            except Exception as e_ans_ignore:
                logger.warning(f"Не удалось ответить на callback CB_IGNORE: {e_ans_ignore}")

        # --- Неизвестный колбэк ---
        else:
            logger.warning(f"Получен неизвестный callback от user {user_id}: '{cb_data}'")
            try:
                bot.answer_callback_query(call.id, "Неизвестное действие.")
            except Exception as e_ans_unknown:
                logger.warning(f"Не удалось ответить на неизвестный callback '{cb_data}': {e_ans_unknown}")

    # --- Обработка ожидаемых ошибок парсинга/API ---
    except (ValueError, TypeError) as e_parse:
        logger.error(f"Ошибка парсинга данных callback '{cb_data}' от user {user_id}: {e_parse}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "Ошибка в данных запроса.", show_alert=True)
        except Exception as e_ans_parse:
            logger.error(f"Не удалось ответить на callback после ошибки парсинга: {e_ans_parse}")
    except IndexError as e_index:
        logger.error(f"Ошибка индекса при обработке callback '{cb_data}' от user {user_id}: {e_index}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, "Ошибка обработки данных.", show_alert=True)
        except Exception as e_ans_index:
            logger.error(f"Не удалось ответить на callback после ошибки индекса: {e_ans_index}")
    except apihelper.ApiTelegramException as e_api:
        error_text = str(e_api).lower()
        if "message is not modified" in error_text:
            logger.debug(f"Сообщение {message_id} не было изменено (API).")
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
        elif "message to edit not found" in error_text or "message can't be edited" in error_text:
            logger.warning(f"Сообщение {message_id} не найдено или не может быть отредактировано (API).")
            try:
                bot.answer_callback_query(call.id, "Сообщение устарело или недоступно.", show_alert=True)
            except Exception:
                pass
        elif "message to delete not found" in error_text:
            logger.warning(f"Сообщение {message_id} не найдено для удаления (API).")
            try:
                bot.answer_callback_query(call.id)
            except Exception:
                pass
        elif "bot was blocked by the user" in error_text or "user is deactivated" in error_text:
             logger.warning(f"Бот заблокирован пользователем {user_id} или пользователь деактивирован.")
             try:
                 bot.answer_callback_query(call.id)
             except Exception:
                 pass
             temp_db = None
             try:
                 temp_db = Database()
                 userService.handle_user_blocked_bot(temp_db, user_id)
             except Exception as e_block_handle:
                 logger.error(f"Ошибка обработки блокировки бота пользователем {user_id}: {e_block_handle}")
             finally:
                  if temp_db:
                      pass
        else:
            logger.error(f"Необработанная ошибка Telegram API при обработке callback '{cb_data}' user {user_id}: {e_api}", exc_info=True)
            try:
                bot.answer_callback_query(call.id, "Произошла ошибка при взаимодействии с Telegram.", show_alert=True)
            except Exception as e_ans_api_other:
                 logger.error(f"Не удалось ответить на callback после необработанной ошибки API: {e_ans_api_other}")

    # --- Обработка любых других непредвиденных исключений ---
    except Exception as e_global:
        logger.critical(f"Критическая непредвиденная ошибка при обработке callback '{cb_data}' от user {user_id}: {e_global}", exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except Exception as e_ans_crit:
            logger.error(f"Не удалось ответить на callback после критической ошибки: {e_ans_crit}")

# --- Регистрация обработчиков ---
# (Функция register_callback_handlers остается без изменений)
# --- Регистрация обработчиков ---
# (Функция register_callback_handlers остается без изменений)

# --- Регистрация обработчиков ---
def register_callback_handlers(
    bot: telebot.TeleBot, db: Database, scheduler: Optional[BackgroundScheduler],
    active_timers: Dict[int, Any], scheduled_jobs_registry: Set[Tuple[str, int]]
):
    """Регистрирует основной обработчик для всех inline callback-запросов."""

    @bot.callback_query_handler(func=lambda call: True)
    def main_callback_dispatcher(call: CallbackQuery):
        # Передаем все необходимые зависимости в главную функцию обработки
        handle_callback_query(bot, db, scheduler, active_timers, scheduled_jobs_registry, call)

    logger.info("Основной обработчик callback-запросов успешно зарегистрирован.")


# <<< Функции-обработчики для конкретных колбэков (вынесены для чистоты) >>>
# Эти функции вызываются из handle_callback_query

# --- НОВЫЕ ОБРАБОТЧИКИ для добавления оборудования ---

def handle_admin_add_equip_select_cat(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_id: int, chat_id: int, message_id: int):
    """Обрабатывает выбор СУЩЕСТВУЮЩЕЙ категории при добавлении оборудования."""
    category_id_str = call.data[len(const.CB_ADMIN_ADD_EQUIP_SELECT_CAT_):]
    category_id = None
    try:
        category_id = int(category_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID категории из callback '{call.data}' (admin {admin_id})")
        bot.answer_callback_query(call.id, "Ошибка ID категории.", show_alert=True)
        return

    logger.debug(f"Admin {admin_id} выбрал существующую категорию {category_id} для добавления оборудования.")
    try:
        bot.answer_callback_query(call.id)
    except Exception as e_ans:
         logger.warning(f"Не удалось ответить на callback выбора категории {category_id}: {e_ans}")

    category_name = None
    try:
        # Получаем имя категории для отображения и сохранения в состоянии
        category_name = equipmentService.get_category_name_by_id(db, category_id)
        if not category_name:
             logger.error(f"Не найдено имя для категории {category_id} (admin {admin_id})")
             category_name = f"ID {category_id}" # Используем ID как запасной вариант

        # Устанавливаем состояние админа: ожидаем имя оборудования
        # Используем импортированный словарь admin_process_states
        admin_process_states[admin_id] = {
            'step': const.ADMIN_STATE_ADD_EQUIP_NAME,
            'category_id': category_id,
            'category_name': category_name,
            'message_id': message_id # Сохраняем ID сообщения для возможного обновления
        }
        logger.debug(f"Установлено состояние для admin {admin_id}: {admin_process_states[admin_id]}")

        # Редактируем сообщение, запрашивая имя оборудования
        prompt_text = f"Категория: '{category_name}'.\nТеперь введите **название** нового оборудования (или /cancel):"
        # Передаем admin_id для обновления message_id в его состоянии
        kwargs_edit = {'admin_id_for_state_update': admin_id, 'parse_mode': "Markdown", 'reply_markup': None}
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, **kwargs_edit)

    except Exception as e:
        logger.error(f"Ошибка при обработке выбора категории {category_id} админом {admin_id}: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Ошибка обработки выбора.", show_alert=True)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, admin_id_for_state_update=admin_id)
        # Используем импортированную функцию
        clear_admin_state(admin_id) # Очищаем состояние при ошибке


def handle_admin_add_equip_new_cat(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_id: int, chat_id: int, message_id: int):
    """Обрабатывает нажатие кнопки 'Добавить новую категорию'."""
    logger.debug(f"Admin {admin_id} выбрал добавление новой категории.")
    try:
        bot.answer_callback_query(call.id)
    except Exception as e_ans:
         logger.warning(f"Не удалось ответить на callback добавления новой категории: {e_ans}")

    try:
        # Устанавливаем состояние админа: ожидаем имя НОВОЙ категории
        # Используем импортированный словарь admin_process_states
        admin_process_states[admin_id] = {
            'step': const.ADMIN_STATE_ADD_EQUIP_NEW_CAT_NAME,
            'message_id': message_id # Сохраняем ID сообщения
        }
        logger.debug(f"Установлено состояние для admin {admin_id}: {admin_process_states[admin_id]}")

        # Редактируем сообщение, запрашивая имя новой категории
        prompt_text = "Введите **название** новой категории (или /cancel):"
        kwargs_edit = {'admin_id_for_state_update': admin_id, 'parse_mode': "Markdown", 'reply_markup': None}
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, **kwargs_edit)

    except Exception as e:
        logger.error(f"Ошибка при обработке нажатия 'Добавить новую категорию' админом {admin_id}: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Ошибка обработки действия.", show_alert=True)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, admin_id_for_state_update=admin_id)
        # Используем импортированную функцию
        clear_admin_state(admin_id) # Очищаем состояние при ошибке


def handle_admin_add_equip_cancel(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_id: int, chat_id: int, message_id: int):
    """Обрабатывает нажатие кнопки 'Отмена' в процессе добавления оборудования."""
    logger.info(f"Admin {admin_id} отменил добавление оборудования через кнопку 'Отмена'.")
    try:
        bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
    except Exception as e_ans:
         logger.warning(f"Не удалось ответить на callback отмены добавления оборудования: {e_ans}")

    try:
        # Редактируем сообщение на "Отменено" и убираем клавиатуру
        kwargs_edit = {'admin_id_for_state_update': admin_id, 'reply_markup': None}
        _edit_or_send_message(bot, chat_id, message_id, "Добавление оборудования отменено.", **kwargs_edit)
    except Exception as e_edit:
         logger.error(f"Не удалось отредактировать сообщение при отмене добавления оборудования админом {admin_id}: {e_edit}")
    finally:
        # Очищаем состояние админа в любом случае
        # Используем импортированную функцию
        clear_admin_state(admin_id)

# --- КОНЕЦ НОВЫХ ОБРАБОТЧИКОВ ---


def handle_registration_confirm(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_user_id: int, chat_id: int, message_id: int):
    """Обрабатывает подтверждение регистрации админом."""
    temp_user_id_str = call.data[len(const.CB_REG_CONFIRM_USER):]
    temp_user_id = None
    try:
        temp_user_id = int(temp_user_id_str)
    except ValueError:
        logger.error(f"Неверный user_id '{temp_user_id_str}' в CB_REG_CONFIRM_USER от admin {admin_user_id}")
        bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
        return # Выход

    logger.info(f"Admin {admin_user_id} подтверждает регистрацию пользователя {temp_user_id}")
    try:
        bot.answer_callback_query(call.id, "Регистрирую пользователя...")
    except Exception as e_ans_reg_conf:
         logger.warning(f"Не удалось ответить на callback подтверждения регистрации {temp_user_id}: {e_ans_reg_conf}")

    success = False
    user_info = None
    try:
        success, user_info = userService.confirm_registration(db, temp_user_id)
    except Exception as e_confirm:
        logger.error(f"Ошибка при подтверждении регистрации {temp_user_id} админом {admin_user_id}: {e_confirm}", exc_info=True)
        success = False

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'admin_id_for_state_update': admin_user_id}
    text = ""
    if success:
        first_name = user_info.get('first_name', '') if user_info else ''
        user_display = first_name or f"ID {temp_user_id}"
        if user_info:
            text = f"✅ Пользователь {user_display} успешно зарегистрирован."
            # Попытка уведомить пользователя
            try:
                bot.send_message(temp_user_id, const.MSG_REGISTRATION_APPROVED)
            except apihelper.ApiTelegramException as e_notify:
                logger.error(f"Не удалось уведомить пользователя {temp_user_id} о регистрации: {e_notify}")
            except Exception as e_notify_other:
                logger.error(f"Другая ошибка при уведомлении пользователя {temp_user_id}: {e_notify_other}")
        else:
            # Случай, когда сервис вернул success=True, но без user_info
            logger.warning(f"confirm_registration для {temp_user_id} вернул success=True, но user_info=None.")
            text = f"✅ Пользователь с ID `{temp_user_id}` зарегистрирован (доп. информация не найдена)."
    else:
        text = f"❌ Не удалось зарегистрировать пользователя с ID `{temp_user_id}`. Проверьте логи."

    _edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)


def handle_registration_decline(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_user_id: int, chat_id: int, message_id: int):
    """Обрабатывает отклонение регистрации админом."""
    temp_user_id_str = call.data[len(const.CB_REG_DECLINE_USER):]
    temp_user_id = None
    try:
        temp_user_id = int(temp_user_id_str)
    except ValueError:
        logger.error(f"Неверный user_id '{temp_user_id_str}' в CB_REG_DECLINE_USER от admin {admin_user_id}")
        bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
        return # Выход

    logger.info(f"Admin {admin_user_id} отклоняет регистрацию пользователя {temp_user_id}")
    try:
        bot.answer_callback_query(call.id, "Отклоняю регистрацию...")
    except Exception as e_ans_reg_dec:
         logger.warning(f"Не удалось ответить на callback отклонения регистрации {temp_user_id}: {e_ans_reg_dec}")

    success = False
    try:
        success = userService.decline_registration(db, temp_user_id)
    except Exception as e_decline:
        logger.error(f"Ошибка при отклонении регистрации {temp_user_id} админом {admin_user_id}: {e_decline}", exc_info=True)
        success = False

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'admin_id_for_state_update': admin_user_id}
    text = ""
    if success:
        text = f"🚫 Регистрация для пользователя с ID `{temp_user_id}` отклонена."
        # Попытка уведомить пользователя
        try:
            bot.send_message(temp_user_id, const.MSG_REGISTRATION_DECLINED)
        except apihelper.ApiTelegramException as e_notify:
            # Пользователь мог заблокировать бота после запроса, это нормально
            logger.warning(f"Не удалось уведомить пользователя {temp_user_id} об отклонении регистрации: {e_notify}")
        except Exception as e_notify_other:
            logger.warning(f"Другая ошибка при уведомлении пользователя {temp_user_id} об отклонении: {e_notify_other}")
    else:
        text = f"❌ Не удалось отклонить регистрацию для ID `{temp_user_id}`. Проверьте логи."

    _edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)


def handle_datebookings_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
    """Обрабатывает выбор даты в /datebookings."""
    data_part = call.data[len(const.CB_DATEB_SELECT_DATE):]
    # Ожидаемый формат: DD-MM-YYYY
    selected_date_str = data_part
    # page_num = 1 # Пагинация пока не реализована

    logger.debug(f"User {user_id} запросил бронирования на дату {selected_date_str} (callback)")
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}
    date_obj = None
    try:
        date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        try:
            bot.answer_callback_query(call.id, f"Загружаю бронирования на {selected_date_str}...")
        except Exception as e_ans_dateb:
             logger.warning(f"Не удалось ответить на callback /datebookings {selected_date_str}: {e_ans_dateb}")

        text = bookingService.get_bookings_by_date_text(db, date_obj)
        _edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)
    except ValueError:
        logger.warning(f"Неверный формат даты '{selected_date_str}' в callback /datebookings от user {user_id}")
        bot.answer_callback_query(call.id, "Ошибка формата даты.", show_alert=True)
        # Не редактируем сообщение об ошибке, чтобы пользователь видел исходные кнопки
    except Exception as e:
        logger.error(f"Ошибка при получении бронирований на дату {selected_date_str} для user {user_id}: {e}", exc_info=True)
        bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)


def handle_wsb_category_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
    """Обрабатывает выбор категории в /workspacebookings."""
    cat_id_str = call.data[len(const.CB_WSB_SELECT_CATEGORY):]
    cat_id = None
    try:
        cat_id = int(cat_id_str)
    except ValueError:
        logger.error(f"Неверный category_id '{cat_id_str}' в CB_WSB_SELECT_CATEGORY от user {user_id}")
        bot.answer_callback_query(call.id, "Ошибка ID категории.", show_alert=True)
        return # Выход

    logger.debug(f"User {user_id} выбрал категорию {cat_id} для /workspacebookings")
    try:
        bot.answer_callback_query(call.id) # Отвечаем сразу
    except Exception as e_ans_wsb_cat:
         logger.warning(f"Не удалось ответить на callback /workspacebookings category {cat_id}: {e_ans_wsb_cat}")

    kwargs_edit = {'user_id_for_state_update': user_id}
    equipment = None
    try:
        equipment = equipmentService.get_equipment_by_category(db, cat_id)
    except Exception as e_get_eq:
        logger.error(f"Ошибка получения оборудования для кат. {cat_id} (wsb): {e_get_eq}", exc_info=True)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return # Выход

    if not equipment:
        logger.warning(f"В категории {cat_id} нет оборудования (wsb, user {user_id}).")
        _edit_or_send_message(bot, chat_id, message_id, "В этой категории нет доступного оборудования.", reply_markup=None, **kwargs_edit)
        return # Выход

    markup = keyboards.generate_equipment_keyboard(equipment, const.CB_WSB_SELECT_EQUIPMENT)
    _edit_or_send_message(bot, chat_id, message_id, "Выберите конкретное оборудование:", reply_markup=markup, **kwargs_edit)


def handle_wsb_equipment_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
     """Обрабатывает выбор оборудования в /workspacebookings."""
     equip_id_str = call.data[len(const.CB_WSB_SELECT_EQUIPMENT):]
     equip_id = None
     try:
         equip_id = int(equip_id_str)
     except ValueError:
         logger.error(f"Неверный equipment_id '{equip_id_str}' в CB_WSB_SELECT_EQUIPMENT от user {user_id}")
         bot.answer_callback_query(call.id, "Ошибка ID оборудования.", show_alert=True)
         return # Выход

     logger.debug(f"User {user_id} выбрал оборудование {equip_id} для просмотра бронирований (/workspacebookings)")
     try:
         bot.answer_callback_query(call.id, "Загружаю информацию о бронированиях...")
     except Exception as e_ans_wsb_eq:
          logger.warning(f"Не удалось ответить на callback /workspacebookings equipment {equip_id}: {e_ans_wsb_eq}")

     kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}
     name = None
     text = ""
     try:
         name = equipmentService.get_equipment_name_by_id(db, equip_id)
         if not name:
             logger.warning(f"Не найдено имя для оборудования {equip_id} (wsb, user {user_id})")
             _edit_or_send_message(bot, chat_id, message_id, "Не удалось найти информацию о выбранном оборудовании.", **kwargs_edit)
             return # Выход
         # Получаем текст с бронированиями
         text = bookingService.get_bookings_by_workspace_text(db, equip_id, name)
         _edit_or_send_message(bot, chat_id, message_id, text, **kwargs_edit)
     except Exception as e:
         logger.error(f"Ошибка при получении бронирований для оборудования {equip_id} (wsb, user {user_id}): {e}", exc_info=True)
         _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)


def handle_filter_type_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
     """Обрабатывает выбор типа фильтра для отчета /allbookings."""
     f_type = call.data[len(const.CB_FILTER_BY_TYPE):]
     logger.debug(f"Admin {user_id} выбрал тип фильтра '{f_type}' для отчета /allbookings")
     try:
         bot.answer_callback_query(call.id) # Отвечаем сразу
     except Exception as e_ans_filter_type:
          logger.warning(f"Не удалось ответить на callback выбора типа фильтра '{f_type}': {e_ans_filter_type}")

     opts: List[Tuple[str, Any]] = [] # Список кортежей (Текст кнопки, callback_data_value)
     cb_pfx = ""
     prompt = ""
     kwargs_edit = {'admin_id_for_state_update': user_id} # Используем admin_id для состояния
     try:
          if f_type == "users":
              users_data = userService.get_all_users(db, include_inactive=True)
              # Формируем список (Имя Фамилия (ID), user_id)
              opts = []
              if users_data:
                  for user in users_data:
                      user_id_val = user.get('users_id')
                      if user_id_val:
                          user_fi = user.get('fi', '').strip()
                          display_name = f"{user_fi} ({user_id_val})" if user_fi else f"ID {user_id_val}"
                          opts.append((display_name, user_id_val))
                  opts.sort(key=lambda x: x[0]) # Сортируем по отображаемому имени
              cb_pfx = const.CB_FILTER_SELECT_USER
              prompt = "Выберите пользователя для фильтрации отчета:"
          elif f_type == "equipment":
              equip_data = equipmentService.get_all_equipment(db)
              # Формируем список (Имя оборудования (ID), equipment_id)
              opts = []
              if equip_data:
                  for eq in equip_data:
                       eq_id_val = eq.get('id')
                       if eq_id_val:
                           eq_name = eq.get('name_equip', '').strip()
                           display_name = f"{eq_name} ({eq_id_val})" if eq_name else f"ID {eq_id_val}"
                           opts.append((display_name, eq_id_val))
                  opts.sort(key=lambda x: x[0])
              cb_pfx = const.CB_FILTER_SELECT_EQUIPMENT
              prompt = "Выберите оборудование для фильтрации отчета:"
          elif f_type == "dates":
              # Получаем уникальные месяцы в формате YYYY-MM
              query = """
                  SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month_year
                  FROM bookings
                  WHERE date IS NOT NULL
                  ORDER BY month_year DESC;
              """
              months_result: Optional[QueryResult] = db.execute_query(query, fetch_results=True)
              opts = []
              if months_result:
                   for m in months_result:
                       # Проверяем тип элемента (может быть dict или tuple/list)
                       month_str = None
                       if isinstance(m, dict):
                            month_str = m.get('month_year')
                       elif isinstance(m, (list, tuple)) and len(m) > 0:
                            month_str = m[0]

                       if month_str:
                           opts.append((month_str, month_str)) # Текст и значение одинаковы
              cb_pfx = const.CB_FILTER_SELECT_DATE
              prompt = "Выберите месяц (YYYY-MM) для фильтрации отчета:"
          else:
              logger.warning(f"Неизвестный тип фильтра '{f_type}' выбран админом {user_id}")
              bot.answer_callback_query(call.id, "Неизвестный тип фильтра.")
              return # Выходим, не меняя сообщение

          # Проверяем, есть ли опции для выбора
          if not opts:
              logger.warning(f"Нет данных для фильтра типа '{f_type}' (admin {user_id})")
              bot.answer_callback_query(call.id, "Нет данных для этого типа фильтра.")
              _edit_or_send_message(bot, chat_id, message_id, f"Не найдено данных для фильтрации по типу '{f_type}'.", reply_markup=None, **kwargs_edit)
          else:
              # Генерируем клавиатуру с опциями
              markup = keyboards.generate_filter_selection_keyboard(opts, cb_pfx)
              _edit_or_send_message(bot, chat_id, message_id, prompt, reply_markup=markup, **kwargs_edit)

     except Exception as e:
         logger.error(f"Ошибка при подготовке опций для фильтра '{f_type}' (admin {user_id}): {e}", exc_info=True)
         bot.answer_callback_query(call.id, "Ошибка при загрузке опций.", show_alert=True)
         _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)


def handle_filter_value_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
     """Обрабатывает выбор конкретного значения для фильтра /allbookings и генерирует отчет."""
     f_type = ""         # Тип фильтра ('users', 'equipment', 'dates')
     f_val_str = ""      # Выбранное значение как строка
     f_val_int: Optional[int] = None # Выбранное значение как int (для ID)
     f_details = "неизвестный фильтр" # Описание фильтра для отчета
     path = None         # Путь к сгенерированному файлу отчета

     kwargs_edit = {'reply_markup': None, 'admin_id_for_state_update': user_id} # Используем admin_id

     try:
          # Определяем тип фильтра и извлекаем значение из callback_data
          if call.data.startswith(const.CB_FILTER_SELECT_USER):
              f_type = "users"
              f_val_str = call.data[len(const.CB_FILTER_SELECT_USER):]
              f_val_int = int(f_val_str) # ID пользователя
              user_info = userService.get_user_info(db, f_val_int)
              user_display = f"ID {f_val_int}"
              if user_info:
                  user_fi = user_info.get('fi', '').strip()
                  user_display = f"{user_fi} ({f_val_int})" if user_fi else f"ID {f_val_int}"
              f_details = f"Пользователь: {user_display}"

          elif call.data.startswith(const.CB_FILTER_SELECT_EQUIPMENT):
              f_type = "equipment"
              f_val_str = call.data[len(const.CB_FILTER_SELECT_EQUIPMENT):]
              f_val_int = int(f_val_str) # ID оборудования
              name = equipmentService.get_equipment_name_by_id(db, f_val_int)
              eq_display = f"ID {f_val_int}"
              if name:
                  eq_display = f"{name} ({f_val_int})"
              f_details = f"Оборудование: {eq_display}"

          elif call.data.startswith(const.CB_FILTER_SELECT_DATE):
              f_type = "dates"
              f_val_str = call.data[len(const.CB_FILTER_SELECT_DATE):] # Значение YYYY-MM
              # Проверяем формат
              datetime.strptime(f_val_str, '%Y-%m')
              f_details = f"Месяц: {f_val_str}"
          else:
              # Этого не должно произойти, если маршрутизация верна
              logger.error(f"Неизвестный префикс в handle_filter_value_select: '{call.data}'")
              bot.answer_callback_query(call.id, "Ошибка типа фильтра.", show_alert=True)
              return # Выход

     except (ValueError, TypeError, IndexError) as e:
         logger.error(f"Ошибка парсинга значения фильтра из callback '{call.data}' (admin {user_id}): {e}")
         bot.answer_callback_query(call.id, "Ошибка в данных фильтра.", show_alert=True)
         return # Выход
     except Exception as e_parse_val: # Ловим другие возможные ошибки (например, DB при получении имени)
         logger.error(f"Ошибка при подготовке данных для фильтра '{call.data}' (admin {user_id}): {e_parse_val}", exc_info=True)
         bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
         return # Выход

     logger.info(f"Admin {user_id} запросил отчет /allbookings с фильтром: {f_details}")
     try:
         bot.answer_callback_query(call.id, "Формирую отчет...")
     except Exception as e_ans_filter_val:
          logger.warning(f"Не удалось ответить на callback выбора значения фильтра '{f_details}': {e_ans_filter_val}")

     # Редактируем исходное сообщение, показывая статус
     _edit_or_send_message(bot, chat_id, message_id, f"⏳ Пожалуйста, подождите, идет формирование отчета ({f_details})...", **kwargs_edit)

     try:
         # Определяем значение для передачи в сервис (int для ID, str для даты)
         filter_value: Any = f_val_int if f_val_int is not None else f_val_str

         # 1. Получаем отфильтрованные данные
         bookings_data: List[Dict[str, Any]] = adminService.get_filtered_bookings(db, f_type, filter_value)

         # 2. Проверяем, есть ли данные
         if not bookings_data:
             logger.info(f"Нет бронирований, соответствующих фильтру '{f_details}' (admin {user_id}).")
             _edit_or_send_message(bot, chat_id, message_id, f"По выбранному фильтру '{f_details}' не найдено ни одного бронирования.", **kwargs_edit)
             return # Завершаем, т.к. отчета не будет

         # 3. Создаем файл отчета
         path = adminService.create_bookings_report_file(bookings_data, filter_details=f_details)

         # 4. Проверяем, что файл создан
         if path:
             if os.path.exists(path):
                 # 5. Отправляем файл
                 logger.info(f"Отправка отчета {os.path.basename(path)} админу {user_id} ({f_details})")
                 report_file = None
                 try:
                     report_file = open(path, 'rb')
                     bot.send_document(chat_id, report_file, caption=f"Отчет по бронированиям ({f_details})")
                     # После успешной отправки можно удалить исходное сообщение "Формирую отчет..."
                     try:
                         bot.delete_message(chat_id, message_id)
                     except Exception as e_del_orig:
                         logger.warning(f"Не удалось удалить исходное сообщение {message_id} после отправки отчета: {e_del_orig}")
                 except FileNotFoundError:
                      logger.error(f"Сгенерированный файл отчета не найден: {path}")
                      _edit_or_send_message(bot, chat_id, message_id, f"❌ Ошибка: Не найден файл отчета.", **kwargs_edit)
                 except Exception as e_send:
                      logger.error(f"Ошибка при отправке файла отчета {path} админу {user_id}: {e_send}", exc_info=True)
                      _edit_or_send_message(bot, chat_id, message_id, f"❌ Произошла ошибка при отправке файла отчета.", **kwargs_edit)
                 finally:
                      if report_file:
                          try:
                              report_file.close()
                          except Exception as e_close:
                               logger.error(f"Ошибка закрытия файла отчета {path}: {e_close}")
             else:
                  logger.error(f"Функция create_bookings_report_file вернула путь {path}, но файл не существует.")
                  _edit_or_send_message(bot, chat_id, message_id, f"❌ Ошибка: Не удалось создать файл отчета.", **kwargs_edit)
         else:
             # Если create_bookings_report_file вернула None
             logger.error(f"Не удалось создать файл отчета для фильтра '{f_details}' (admin {user_id}).")
             _edit_or_send_message(bot, chat_id, message_id, f"❌ Не удалось создать файл отчета.", **kwargs_edit)

     except Exception as e_report:
         logger.error(f"Критическая ошибка при генерации или отправке отчета /allbookings ({f_details}, admin {user_id}): {e_report}", exc_info=True)
         _edit_or_send_message(bot, chat_id, message_id, f"❌ Произошла критическая ошибка при формировании отчета.", **kwargs_edit)
     finally:
         # Удаляем временный файл отчета, если он был создан
         if path:
             if os.path.exists(path):
                 try:
                     os.remove(path)
                     logger.debug(f"Временный файл отчета {path} удален.")
                 except OSError as e_remove:
                     logger.error(f"Ошибка при удалении временного файла отчета {path}: {e_remove}")


def handle_equip_delete_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
    """Обрабатывает выбор оборудования для удаления (шаг 1)."""
    equipment_id_str = call.data[len(const.CB_EQUIP_DELETE_SELECT):]
    equipment_id = None
    try:
        equipment_id = int(equipment_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID оборудования из callback '{call.data}' (admin {user_id})")
        bot.answer_callback_query(call.id, "Ошибка ID оборудования.", show_alert=True)
        return # Выход

    logger.info(f"Admin {user_id} выбрал оборудование {equipment_id} для возможного удаления.")
    try:
        bot.answer_callback_query(call.id) # Отвечаем сразу
    except Exception as e_ans_del_sel:
         logger.warning(f"Не удалось ответить на callback выбора удаления {equipment_id}: {e_ans_del_sel}")

    kwargs_edit = {'admin_id_for_state_update': user_id} # Используем admin_id
    equip_info = None
    equip_name = f'ID {equipment_id}' # Имя по умолчанию
    has_bookings = True # По умолчанию считаем, что есть брони (безопаснее)

    try:
        # Получаем информацию об оборудовании
        equip_info = equipmentService.get_equipment_info_by_id(db, equipment_id)
        if not equip_info:
            logger.warning(f"Оборудование {equipment_id} не найдено при попытке удаления (admin {user_id}).")
            bot.answer_callback_query(call.id, "Оборудование не найдено.", show_alert=True)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_EQUIP_DELETE_FAIL_NOT_FOUND, reply_markup=None, **kwargs_edit)
            return # Выход

        equip_name = equip_info.get('name_equip', f'ID {equipment_id}')

        # Проверяем наличие активных или будущих бронирований
        has_bookings = equipmentService.check_equipment_usage(db, equipment_id)

    except Exception as e_check:
        logger.error(f"Ошибка при проверке оборудования {equipment_id} перед удалением (admin {user_id}): {e_check}", exc_info=True)
        bot.answer_callback_query(call.id, "Ошибка проверки оборудования.", show_alert=True)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return # Выход

    # Если есть бронирования, сообщаем об этом и не показываем кнопку подтверждения
    if has_bookings:
        error_msg = const.MSG_EQUIP_DELETE_FAIL_USED.format(equipment_name=f"'{equip_name}'")
        logger.info(f"Попытка удаления используемого оборудования {equipment_id} ('{equip_name}') админом {user_id}.")
        bot.answer_callback_query(call.id, "Оборудование используется!", show_alert=True)
        _edit_or_send_message(bot, chat_id, message_id, error_msg, reply_markup=None, **kwargs_edit)
        return # Выход

    # Если бронирований нет, показываем подтверждение
    confirm_text = (f"❓ Вы уверены, что хотите удалить оборудование '{equip_name}' (ID: {equipment_id})?\n\n"
                    f"❗ **Это действие необратимо!** Все данные об этом оборудовании будут удалены.")
    # Генерируем клавиатуру подтверждения
    confirm_callback = f"{const.CB_EQUIP_DELETE_CONFIRM}{equipment_id}"
    cancel_callback = const.CB_ACTION_CANCEL + "delete_equip" # Контекст для кнопки отмены
    markup = keyboards.generate_confirmation_keyboard(
        confirm_callback, cancel_callback, confirm_text="✅ Да, удалить", cancel_text="❌ Нет, отмена"
    )
    _edit_or_send_message(bot, chat_id, message_id, confirm_text, reply_markup=markup, parse_mode="Markdown", **kwargs_edit)


def handle_equip_delete_confirm(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int):
    """Обрабатывает подтверждение удаления оборудования (шаг 2)."""
    equipment_id_str = call.data[len(const.CB_EQUIP_DELETE_CONFIRM):]
    equipment_id = None
    try:
        equipment_id = int(equipment_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка парсинга ID оборудования из callback '{call.data}' при подтверждении удаления (admin {user_id})")
        bot.answer_callback_query(call.id, "Ошибка ID оборудования.", show_alert=True)
        return # Выход

    logger.info(f"Admin {user_id} подтвердил удаление оборудования {equipment_id}.")
    try:
        bot.answer_callback_query(call.id, "Удаляю оборудование...")
    except Exception as e_ans_del_conf:
         logger.warning(f"Не удалось ответить на callback подтверждения удаления {equipment_id}: {e_ans_del_conf}")

    success = False
    msg = f"Не удалось удалить оборудование ID {equipment_id}." # Сообщение по умолчанию
    try:
        # Вызываем сервис для удаления (он должен еще раз проверить использование на всякий случай)
        success, msg = equipmentService.delete_equipment_if_unused(db, equipment_id)
    except Exception as e_delete:
         logger.error(f"Ошибка при выполнении удаления оборудования {equipment_id} (admin {user_id}): {e_delete}", exc_info=True)
         success = False
         msg = const.MSG_ERROR_GENERAL

    # Редактируем сообщение с результатом
    kwargs_edit = {'admin_id_for_state_update': user_id} # Используем admin_id
    _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, **kwargs_edit)


def handle_manage_user_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_user_id: int, chat_id: int, message_id: int):
     """Обрабатывает выбор пользователя в /manageusers (шаг 1)."""
     target_user_id_str = call.data[len(const.CB_MANAGE_SELECT_USER):]
     target_user_id = None
     try:
         target_user_id = int(target_user_id_str)
     except (ValueError, TypeError):
         logger.error(f"Ошибка парсинга ID пользователя из callback '{call.data}' (admin {admin_user_id})")
         bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
         return # Выход

     logger.debug(f"Admin {admin_user_id} выбрал пользователя {target_user_id} для управления.")
     try:
         bot.answer_callback_query(call.id) # Отвечаем сразу
     except Exception as e_ans_manage_sel:
          logger.warning(f"Не удалось ответить на callback выбора пользователя {target_user_id}: {e_ans_manage_sel}")

     kwargs_edit = {'admin_id_for_state_update': admin_user_id} # Используем admin_id
     details = None
     try:
         # Получаем детали пользователя (имя, статус блокировки)
         details = userService.get_user_details_for_management(db, target_user_id)
     except Exception as e_get_details:
          logger.error(f"Ошибка при получении деталей пользователя {target_user_id} для управления (admin {admin_user_id}): {e_get_details}", exc_info=True)
          bot.answer_callback_query(call.id, "Ошибка получения данных.", show_alert=True)
          _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
          return # Выход

     if not details:
         logger.warning(f"Пользователь {target_user_id} не найден при выборе для управления (admin {admin_user_id}).")
         bot.answer_callback_query(call.id, "Пользователь не найден.", show_alert=True)
         _edit_or_send_message(bot, chat_id, message_id, "Выбранный пользователь не найден в базе данных.", reply_markup=None, **kwargs_edit)
         return # Выход

     # Распаковываем детали
     name, is_blocked = details
     user_display_name = name if name else f"ID {target_user_id}"
     status_text = "🔴 Заблокирован" if is_blocked else "🟢 Активен"

     # Генерируем клавиатуру с кнопками "Заблокировать"/"Разблокировать" и "Отмена"
     markup = keyboards.generate_user_status_keyboard(target_user_id, is_blocked)

     # Формируем текст сообщения
     message_text = (
         f"Управление пользователем:\n"
         f"👤 Имя: {user_display_name}\n"
         f"🆔 ID: `{target_user_id}`\n"
         f"🚦 Статус: {status_text}\n\n"
         f"Выберите действие:"
     )
     _edit_or_send_message(bot, chat_id, message_id, message_text, reply_markup=markup, parse_mode="Markdown", **kwargs_edit)


def handle_manage_user_action(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_user_id: int, chat_id: int, message_id: int):
     """Обрабатывает нажатие кнопки 'Заблокировать' или 'Разблокировать' (шаг 2)."""
     block_action = call.data.startswith(const.CB_MANAGE_BLOCK_USER)
     target_user_id = None
     try:
         # Извлекаем ID пользователя из callback_data (он должен быть последней частью после '_')
         target_user_id_str = call.data.split('_')[-1]
         target_user_id = int(target_user_id_str)
     except (ValueError, TypeError, IndexError) as e:
         logger.error(f"Ошибка парсинга ID пользователя из callback '{call.data}' при блокировке/разблокировке (admin {admin_user_id}): {e}")
         bot.answer_callback_query(call.id, "Ошибка ID пользователя.", show_alert=True)
         return # Выход

     action_verb = "блокирует" if block_action else "разблокирует"
     action_gerund = "Блокировка" if block_action else "Разблокировка"
     action_past = "заблокирован" if block_action else "разблокирован"
     action_infinitive = "заблокировать" if block_action else "разблокировать"

     logger.info(f"Admin {admin_user_id} {action_verb} пользователя {target_user_id}.")
     try:
         bot.answer_callback_query(call.id, f"{action_gerund} пользователя...")
     except Exception as e_ans_manage_act:
          logger.warning(f"Не удалось ответить на callback {action_gerund} пользователя {target_user_id}: {e_ans_manage_act}")

     kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'admin_id_for_state_update': admin_user_id} # Используем admin_id
     success = False
     try:
         # Выполняем действие через сервис
         success = userService.update_user_block_status(db, target_user_id, block=block_action)
     except Exception as e_update_status:
          logger.error(f"Ошибка при попытке {action_infinitive} пользователя {target_user_id} (admin {admin_user_id}): {e_update_status}", exc_info=True)
          success = False

     # Получаем обновленные детали пользователя для отображения актуального статуса
     details_after = None
     try:
         details_after = userService.get_user_details_for_management(db, target_user_id)
     except Exception as e_get_details_after:
         logger.error(f"Ошибка получения деталей пользователя {target_user_id} ПОСЛЕ {action_gerund} (admin {admin_user_id}): {e_get_details_after}", exc_info=True)
         # Не можем показать актуальный статус, сообщаем об ошибке
         error_text = f"❌ Произошла ошибка при попытке {action_infinitive} пользователя ID `{target_user_id}`."
         _edit_or_send_message(bot, chat_id, message_id, error_text, **kwargs_edit)
         return # Выход

     if details_after:
          name_after, blocked_after = details_after
          user_display_name_after = name_after if name_after else f"ID {target_user_id}"
          status_text_after = "🔴 Заблокирован" if blocked_after else "🟢 Активен"
          result_message = const.MSG_USER_BLOCKED if block_action else const.MSG_USER_UNBLOCKED
          status_icon = "✅" if success else "❌"
          result_line = f"{status_icon} {result_message}" if success else f"{status_icon} Не удалось {action_infinitive} пользователя."

          # Обновляем клавиатуру с новым статусом
          markup_after = keyboards.generate_user_status_keyboard(target_user_id, blocked_after)

          # Формируем текст с результатом
          text_after = (
              f"Управление пользователем:\n"
              f"👤 Имя: {user_display_name_after}\n"
              f"🆔 ID: `{target_user_id}`\n"
              f"🚦 Статус: {status_text_after}\n\n"
              f"{result_line}\n\n"
              f"Выберите следующее действие:"
          )
          kwargs_edit['reply_markup'] = markup_after # Добавляем обновленную клавиатуру
          _edit_or_send_message(bot, chat_id, message_id, text_after, **kwargs_edit)
     else:
         # Если пользователь вдруг не найден после действия
         logger.error(f"Пользователь {target_user_id} не найден ПОСЛЕ попытки {action_infinitive} (admin {admin_user_id}).")
         error_text = f"❌ Ошибка: Пользователь ID `{target_user_id}` не найден после выполнения действия."
         _edit_or_send_message(bot, chat_id, message_id, error_text, **kwargs_edit)


def handle_admin_cancel_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_user_id: int, chat_id: int, message_id: int, booking_id: int):
     """Показывает подтверждение админу перед отменой брони (шаг 1)."""
     logger.info(f"Admin {admin_user_id} выбрал бронь {booking_id} для возможной отмены.")
     try:
         bot.answer_callback_query(call.id) # Отвечаем сразу
     except Exception as e_ans_admin_cancel_sel:
          logger.warning(f"Не удалось ответить на callback выбора админской отмены {booking_id}: {e_ans_admin_cancel_sel}")

     kwargs_edit = {'admin_id_for_state_update': admin_user_id} # Используем admin_id
     booking_info: Optional[Dict[str, Any]] = None
     try:
         booking_info = bookingService.find_booking_by_id(db, booking_id)
     except Exception as e_find:
          logger.error(f"Ошибка поиска брони {booking_id} для админской отмены (admin {admin_user_id}): {e_find}", exc_info=True)
          bot.answer_callback_query(call.id, "Ошибка поиска брони.", show_alert=True)
          _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
          return # Выход

     if booking_info:
         is_cancelled = booking_info.get('cancel', False)
         is_finished = booking_info.get('finish') is not None
         equip_name = booking_info.get('equipment_name', '???')
         user_fi = booking_info.get('user_fi', '???')
         user_id_owner = booking_info.get('user_id', '???') # Получаем ID владельца
         date_val = booking_info.get('date')
         start_time = booking_info.get('time_start')
         end_time = booking_info.get('time_end')

         # Проверяем статус брони
         if is_cancelled:
             msg_edit = f"Бронь ID `{booking_id}` уже была отменена ранее."
             alert_msg = "Бронь уже отменена."
             logger.warning(f"Admin {admin_user_id} попытался отменить уже отмененную бронь {booking_id}.")
             bot.answer_callback_query(call.id, alert_msg)
             _edit_or_send_message(bot, chat_id, message_id, msg_edit, reply_markup=None, parse_mode="Markdown", **kwargs_edit)
             return # Выход
         elif is_finished:
             msg_edit = f"Бронь ID `{booking_id}` уже завершена и не может быть отменена."
             alert_msg = "Бронь уже завершена."
             logger.warning(f"Admin {admin_user_id} попытался отменить уже завершенную бронь {booking_id}.")
             bot.answer_callback_query(call.id, alert_msg)
             _edit_or_send_message(bot, chat_id, message_id, msg_edit, reply_markup=None, parse_mode="Markdown", **kwargs_edit)
             return # Выход
         else:
             # Бронь активна, показываем подтверждение
             date_str = bookingService._format_date(date_val)
             start_str = bookingService._format_time(start_time)
             end_str = bookingService._format_time(end_time)
             confirm_text = (
                 f"❓ Вы уверены, что хотите принудительно отменить бронирование ID `{booking_id}`?\n\n"
                 f"👤 Пользователь: {user_fi} (ID: `{user_id_owner}`)\n"
                 f"🔬 Оборудование: {equip_name}\n"
                 f"🗓️ Дата и время: {date_str} с {start_str} по {end_str}\n\n"
                 f"❗ Пользователь будет уведомлен об отмене."
             )
             confirm_callback = f"{const.CB_ADMIN_CANCEL_CONFIRM}{booking_id}"
             cancel_callback = const.CB_ACTION_CANCEL + "admin_cancel_confirm" # Контекст для отмены
             markup = keyboards.generate_confirmation_keyboard(confirm_callback, cancel_callback)
             _edit_or_send_message(bot, chat_id, message_id, confirm_text, reply_markup=markup, parse_mode="Markdown", **kwargs_edit)
     else:
         # Бронь не найдена
         logger.warning(f"Бронь {booking_id} не найдена при попытке админской отмены (admin {admin_user_id}).")
         bot.answer_callback_query(call.id, "Бронь не найдена.", show_alert=True)
         _edit_or_send_message(bot, chat_id, message_id, "Выбранное бронирование не найдено.", reply_markup=None, **kwargs_edit)


def handle_admin_cancel_confirm(bot: telebot.TeleBot, db: Database, call: CallbackQuery, admin_user_id: int, chat_id: int, message_id: int, booking_id: int, scheduler: Optional[BackgroundScheduler], scheduled_jobs_registry: Set[Tuple[str, int]]):
     """Выполняет отмену брони админом и уведомляет пользователя (шаг 2)."""
     logger.info(f"Admin {admin_user_id} подтвердил принудительную отмену брони {booking_id}.")
     try:
         bot.answer_callback_query(call.id, "Отменяю бронирование...")
     except Exception as e_ans_admin_cancel_conf:
          logger.warning(f"Не удалось ответить на callback подтверждения админской отмены {booking_id}: {e_ans_admin_cancel_conf}")

     kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'admin_id_for_state_update': admin_user_id} # Используем admin_id
     success = False
     msg = const.MSG_BOOKING_CANCEL_FAIL # Сообщение по умолчанию
     owner_user_id = None

     try:
         # Вызываем сервис отмены с флагом is_admin_cancel=True
         success, msg, owner_user_id = bookingService.cancel_booking(
             db, booking_id, user_id=admin_user_id, is_admin_cancel=True
         )
     except Exception as e_cancel_admin:
         logger.error(f"Ошибка при выполнении админской отмены брони {booking_id} (admin {admin_user_id}): {e_cancel_admin}", exc_info=True)
         success = False
         msg = const.MSG_BOOKING_CANCEL_FAIL

     # Редактируем сообщение админа с результатом
     _edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

     if success:
         # Очищаем задачи планировщика, связанные с этой бронью
         if scheduler:
             logger.debug(f"Бронь {booking_id} отменена админом, очищаем связанные задачи...")
             try:
                 notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
             except Exception as e_cleanup_admin_cancel:
                 logger.error(f"Ошибка очистки задач после админской отмены брони {booking_id}: {e_cleanup_admin_cancel}", exc_info=True)
         else:
             logger.warning("Планировщик (scheduler) не передан, очистка задач не выполнена.")

         # Уведомляем пользователя, если его ID был получен
         if owner_user_id:
             try:
                 # Получаем детали брони для уведомления
                 booking_info_notify: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)
                 if booking_info_notify:
                      equip_name_n = booking_info_notify.get('equipment_name', 'Ваше')
                      date_val_n = booking_info_notify.get('date')
                      start_time_n = booking_info_notify.get('time_start')
                      date_str_n = bookingService._format_date(date_val_n)
                      start_str_n = bookingService._format_time(start_time_n)
                      notify_text = (f"❗️ Ваше бронирование оборудования '{equip_name_n}' на {date_str_n} в {start_str_n} "
                                     f"было отменено администратором.")
                      bot.send_message(owner_user_id, notify_text)
                      logger.info(f"Уведомление об админской отмене брони {booking_id} отправлено пользователю {owner_user_id}")
                 else:
                      # Если детали не найдены после отмены (маловероятно, но возможно)
                      logger.warning(f"Не удалось получить детали брони {booking_id} для уведомления пользователя {owner_user_id} об отмене.")
                      notify_text = f"❗️ Ваше бронирование (ID: {booking_id}) было отменено администратором."
                      bot.send_message(owner_user_id, notify_text)
             except apihelper.ApiTelegramException as e_notify:
                 logger.error(f"Не удалось уведомить пользователя {owner_user_id} об админской отмене брони {booking_id}: {e_notify}")
             except Exception as e_notify_other:
                 logger.error(f"Другая ошибка при уведомлении пользователя {owner_user_id} об админской отмене {booking_id}: {e_notify_other}", exc_info=True)
         else:
              logger.warning(f"Не удалось получить ID владельца ({owner_user_id}) для брони {booking_id} после админской отмены. Уведомление не отправлено.")


def handle_extend_select_booking(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int, booking_id: int, source: str):
    """Проверяет возможность продления и показывает варианты времени (шаг 1)."""
    try:
        bot.answer_callback_query(call.id, "Проверяю возможность продления...")
    except Exception as e_ans_ext_sel:
        logger.warning(f"Не удалось ответить на callback выбора продления {booking_id} ({source}): {e_ans_ext_sel}")

    kwargs_edit = {'user_id_for_state_update': user_id}
    booking_info: Optional[Dict[str, Any]] = None
    owner_id = None
    is_cancelled = True
    is_finished = True
    equip_id = None
    current_end_dt: Optional[datetime] = None

    try:
        booking_info = bookingService.find_booking_by_id(db, booking_id)
        if booking_info:
            owner_id = booking_info.get('user_id')
            is_cancelled = booking_info.get('cancel', False)
            is_finished = booking_info.get('finish') is not None
            equip_id = booking_info.get('equip_id')
            date_val = booking_info.get('date')
            end_time_val = booking_info.get('time_end')

            # Преобразование типов для date и time_end
            date_obj = None
            time_obj = None
            if isinstance(date_val, str):
                try:
                    date_obj = datetime.strptime(date_val, '%Y-%m-%d').date()
                except ValueError as e:
                    logger.error(f"Некорректный формат date для брони {booking_id}: {date_val}, ошибка: {e}")
            elif isinstance(date_val, date):
                date_obj = date_val
            else:
                logger.error(f"Неподдерживаемый тип date для брони {booking_id}: {type(date_val)}")

            if isinstance(end_time_val, str):
                try:
                    end_time_dt = datetime.strptime(end_time_val, '%Y-%m-%d %H:%M:%S')
                    time_obj = end_time_dt.time()
                except ValueError as e:
                    logger.error(f"Некорректный формат time_end для брони {booking_id}: {end_time_val}, ошибка: {e}")
            elif isinstance(end_time_val, datetime):
                time_obj = end_time_val.time()
            elif isinstance(end_time_val, time):
                time_obj = end_time_val
            else:
                logger.error(f"Неподдерживаемый тип time_end для брони {booking_id}: {type(end_time_val)}")

            if date_obj and time_obj:
                current_end_dt = datetime.combine(date_obj, time_obj)
            else:
                logger.error(f"Не удалось сформировать current_end_dt для брони {booking_id}: date={date_val}, time_end={end_time_val}")

    except Exception as e_find_ext:
        logger.error(f"Ошибка поиска брони {booking_id} для продления (user {user_id}, {source}): {e_find_ext}", exc_info=True)
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None, **kwargs_edit)
        return

    # Проверки возможности продления
    msg_err = None
    alert_msg = None
    now_naive = datetime.now().replace(tzinfo=None)

    if not booking_info:
        msg_err = const.MSG_EXTEND_FAIL_NOT_FOUND
        alert_msg = "Бронь не найдена."
    elif owner_id != user_id:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_NOT_OWNER', "Это не ваша бронь.")
        alert_msg = "Это не ваша бронь."
    elif is_cancelled:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_CANCELLED', "Бронь отменена.")
        alert_msg = "Бронь отменена."
    elif is_finished:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_FINISHED', "Бронь уже завершена.")
        alert_msg = "Бронь уже завершена."
    elif not current_end_dt or equip_id is None:
        msg_err = const.MSG_ERROR_GENERAL
        alert_msg = "Ошибка данных брони."
        logger.error(f"Отсутствуют current_end_dt={current_end_dt} или equip_id={equip_id} для брони {booking_id} при попытке продления.")
    elif current_end_dt <= now_naive:
        msg_err = getattr(const, 'MSG_EXTEND_FAIL_EXPIRED', "Время бронирования истекло.")
        alert_msg = "Время бронирования истекло."
        logger.warning(f"User {user_id} пытается продлить истекшую бронь {booking_id} ({source}). End: {current_end_dt}, Now: {now_naive}")

    if msg_err:
        try:
            bot.answer_callback_query(call.id, alert_msg, show_alert=True)
        except Exception as e_ans_err:
            logger.warning(f"Не удалось ответить на callback с ошибкой продления {booking_id}: {e_ans_err}")
        _edit_or_send_message(bot, chat_id, message_id, msg_err, reply_markup=None, **kwargs_edit)
        return

    # Расчет доступного времени для продления
    next_booking_start_dt: Optional[datetime] = None
    try:
        next_booking = bookingService.find_next_booking(db, equip_id, current_end_dt)
        if next_booking:
            next_start_time = next_booking.get('time_start')
            if isinstance(next_start_time, datetime):
                next_booking_start_dt = next_start_time
            else:
                logger.warning(f"Некорректное time_start следующей брони для equip_id={equip_id}: {next_start_time}")
    except Exception as e_find_next:
        logger.error(f"Ошибка поиска следующей брони для equip {equip_id} после {current_end_dt} (продление {booking_id}): {e_find_next}", exc_info=True)

    available_until_dt = datetime.combine(current_end_dt.date(), const.WORKING_HOURS_END) if not next_booking_start_dt else next_booking_start_dt
    max_duration_available = timedelta(0)
    if available_until_dt > current_end_dt:
        delta = available_until_dt - current_end_dt
        total_minutes = int(delta.total_seconds() // 60)
        allowed_minutes = (total_minutes // const.BOOKING_TIME_STEP_MINUTES) * const.BOOKING_TIME_STEP_MINUTES
        if allowed_minutes > 0:
            max_duration_available = timedelta(minutes=allowed_minutes)

    logger.debug(f"Максимальное доступное время для продления брони {booking_id} ({source}): {max_duration_available}")

    if max_duration_available > timedelta(0):
        markup = keyboards.generate_extend_time_keyboard(booking_id, max_duration=max_duration_available)
        prompt_text = getattr(const, 'MSG_EXTEND_PROMPT_TIME', "Выберите время продления (текущее окончание {end_time}):").format(
            end_time=current_end_dt.strftime('%H:%M')
        )
        _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit)
    else:
        logger.info(f"Нет доступного времени для продления брони {booking_id} ({source}).")
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_EXTEND_FAIL_NO_TIME, reply_markup=None, **kwargs_edit)

# --- START OF MODIFIED FUNCTION handle_extend_select_time ---
# --- START OF MODIFIED FUNCTION handle_extend_select_time ---
def handle_extend_select_time(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: int, message_id: int, booking_id: int, extension_str: str, scheduler: Optional[BackgroundScheduler], active_timers: Dict[int, Any], scheduled_jobs_registry: Set[Tuple[str, int]]):
     """Выполняет продление брони на выбранное время (шаг 2)."""
     kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id} # Используем user_id

     # --- Повторная проверка возможности продления перед выполнением ---
     booking_info_recheck: Optional[Dict[str, Any]] = None
     owner_id_recheck = None
     is_cancelled_recheck = True
     is_finished_recheck = True
     current_end_dt_recheck: Optional[datetime] = None
     try:
         booking_info_recheck = bookingService.find_booking_by_id(db, booking_id)
         if booking_info_recheck:
             owner_id_recheck = booking_info_recheck.get('user_id')
             is_cancelled_recheck = booking_info_recheck.get('cancel', False)
             is_finished_recheck = booking_info_recheck.get('finish') is not None
             date_val_rc = booking_info_recheck.get('date')
             end_time_val_rc = booking_info_recheck.get('time_end')

             # --- Логика извлечения даты и времени (остается исправленной) ---
             date_obj_rc = None
             time_obj_rc = None
             if isinstance(date_val_rc, date): date_obj_rc = date_val_rc
             elif isinstance(date_val_rc, str):
                 try: date_obj_rc = datetime.strptime(date_val_rc, '%Y-%m-%d').date()
                 except ValueError: logger.error(f"Некорректный формат date (строка) для брони {booking_id} при речеке: {date_val_rc}")
             else: logger.error(f"Неподдерживаемый тип date для брони {booking_id} при речеке: {type(date_val_rc)}")

             if isinstance(end_time_val_rc, datetime): time_obj_rc = end_time_val_rc.time()
             elif isinstance(end_time_val_rc, time): time_obj_rc = end_time_val_rc
             elif isinstance(end_time_val_rc, str):
                 try: time_obj_rc = datetime.strptime(end_time_val_rc, '%Y-%m-%d %H:%M:%S').time()
                 except ValueError:
                     try: time_obj_rc = datetime.strptime(end_time_val_rc, '%H:%M:%S').time()
                     except ValueError: logger.error(f"Некорректный формат time_end (строка) для брони {booking_id} при речеке: {end_time_val_rc}")
             else: logger.error(f"Неподдерживаемый тип time_end для брони {booking_id} при речеке: {type(end_time_val_rc)}")

             if date_obj_rc and time_obj_rc: current_end_dt_recheck = datetime.combine(date_obj_rc, time_obj_rc)
             else: logger.error(f"Не удалось сформировать current_end_dt_recheck для брони {booking_id} при речеке: date={date_val_rc}, time_end={end_time_val_rc}")
             # --- Конец логики извлечения ---

     except Exception as e_find_recheck:
          logger.error(f"Ошибка повторной проверки брони {booking_id} перед продлением: {e_find_recheck}", exc_info=True)
          _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, **kwargs_edit)
          return # Выход

     msg_err_recheck = None
     alert_msg_recheck = None
     now_naive_recheck = datetime.now().replace(tzinfo=None)

     if not booking_info_recheck: msg_err_recheck = const.MSG_EXTEND_FAIL_NOT_FOUND; alert_msg_recheck = "Бронь не найдена."
     elif owner_id_recheck != user_id: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_NOT_OWNER', "Это не ваша бронь."); alert_msg_recheck = "Это не ваша бронь."
     elif is_cancelled_recheck: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_CANCELLED', "Бронь отменена."); alert_msg_recheck = "Бронь отменена."
     elif is_finished_recheck: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_FINISHED', "Бронь уже завершена."); alert_msg_recheck = "Бронь уже завершена."
     elif not current_end_dt_recheck: msg_err_recheck = const.MSG_ERROR_GENERAL; alert_msg_recheck = "Ошибка данных брони."
     elif current_end_dt_recheck <= now_naive_recheck: msg_err_recheck = getattr(const, 'MSG_EXTEND_FAIL_EXPIRED', "Время бронирования истекло."); alert_msg_recheck = "Время бронирования истекло."

     if msg_err_recheck:
         logger.warning(f"Повторная проверка перед продлением брони {booking_id} не пройдена: {alert_msg_recheck}")
         try: bot.answer_callback_query(call.id, alert_msg_recheck, show_alert=True)
         except Exception as e_ans_recheck_fail: logger.warning(f"Не удалось ответить на callback после неудачной повторной проверки {booking_id}: {e_ans_recheck_fail}")
         _edit_or_send_message(bot, chat_id, message_id, msg_err_recheck, **kwargs_edit)
         return # Выход
     # --- Конец повторной проверки ---

     try:
         bot.answer_callback_query(call.id, f"Продлеваю бронирование на {extension_str}...")
     except Exception as e_ans_ext_time:
          logger.warning(f"Не удалось ответить на callback выбора времени продления {booking_id} на {extension_str}: {e_ans_ext_time}")

     success = False
     # --- ИЗМЕНЕНИЕ: Используем правильную константу ---
     msg = const.MSG_BOOKING_FAIL_GENERAL # Сообщение по умолчанию
     # --- КОНЕЦ ИЗМЕНЕНИЯ ---
     try:
         # Вызываем сервис для выполнения продления
         success, msg = bookingService.extend_booking(db, booking_id, user_id, extension_str)
     except ValueError as e_val_extend: # Ловим ошибки валидации времени из сервиса
         logger.warning(f"Ошибка валидации при продлении брони {booking_id} на {extension_str}: {e_val_extend}")
         success = False
         msg = str(e_val_extend) # Показываем пользователю причину ошибки валидации
     except Exception as e_extend_logic:
         logger.error(f"Ошибка при выполнении продления брони {booking_id} на {extension_str}: {e_extend_logic}", exc_info=True)
         success = False
         # --- ИЗМЕНЕНИЕ: Используем правильную константу ---
         msg = const.MSG_BOOKING_FAIL_GENERAL
         # --- КОНЕЦ ИЗМЕНЕНИЯ ---

     # Редактируем сообщение с результатом
     _edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit)

     if success:
         # Обновляем уведомления в планировщике
         if scheduler:
             logger.debug(f"Бронь {booking_id} успешно продлена, обновляем уведомления...")
             try:
                 # Перепланируем все (проще, чем искать и обновлять конкретные)
                 notificationService.schedule_all_notifications(db, bot, scheduler, active_timers, scheduled_jobs_registry)
             except Exception as e_reschedule:
                 logger.error(f"Ошибка перепланирования уведомлений после продления брони {booking_id}: {e_reschedule}", exc_info=True)
                 # Не сообщаем пользователю, но логируем
         else:
             logger.warning("Планировщик (scheduler) не передан, уведомления не обновлены после продления.")
# --- END OF MODIFIED FUNCTION handle_extend_select_time ---

# --- Обработчики кнопок "Отмена" для разных контекстов ---

def handle_cancel_delete_equip(bot: telebot.TeleBot, db: Database, chat_id: int, message_id: int, **kwargs_edit):
    """Возвращает пользователя к списку оборудования после отмены подтверждения удаления."""
    logger.debug(f"Отмена подтверждения удаления оборудования (admin), возврат к списку. Msg: {message_id}")
    all_equipment = None
    markup = None
    try:
        all_equipment = equipmentService.get_all_equipment(db)
        if all_equipment:
            markup = keyboards.generate_equipment_list_with_delete_keyboard(all_equipment)
            _edit_or_send_message(bot, chat_id, message_id, "Удаление отменено. Выберите оборудование для удаления:", reply_markup=markup, **kwargs_edit)
        else:
            _edit_or_send_message(bot, chat_id, message_id, "Удаление отменено. Нет доступного оборудования для удаления.", reply_markup=None, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку оборудования после отмены удаления: {e}", exc_info=True)
        _edit_or_send_message(bot, chat_id, message_id, "Удаление отменено. Ошибка загрузки списка.", reply_markup=None, **kwargs_edit)


def handle_cancel_admin_cancel(bot: telebot.TeleBot, db: Database, chat_id: int, message_id: int, **kwargs_edit):
    """Возвращает админа к списку броней для отмены после отмены подтверждения."""
    logger.debug(f"Отмена подтверждения админской отмены брони, возврат к списку. Msg: {message_id}")
    active_bookings = None
    markup = None
    try:
        active_bookings = bookingService.get_all_active_bookings_for_admin_keyboard(db)
        if active_bookings:
            markup = keyboards.generate_admin_cancel_keyboard(active_bookings)
            _edit_or_send_message(bot, chat_id, message_id, "Отмена действия отменена. Выберите бронирование для принудительной отмены:", reply_markup=markup, **kwargs_edit)
        else:
            _edit_or_send_message(bot, chat_id, message_id, "Отмена действия отменена. Нет активных бронирований для отмены.", reply_markup=None, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку броней после отмены админской отмены: {e}", exc_info=True)
        _edit_or_send_message(bot, chat_id, message_id, "Отмена действия отменена. Ошибка загрузки списка броней.", reply_markup=None, **kwargs_edit)


def handle_cancel_manage_user(bot: telebot.TeleBot, db: Database, chat_id: int, message_id: int, **kwargs_edit):
    """Возвращает админа к списку пользователей для управления после отмены выбора действия."""
    logger.debug(f"Отмена выбора действия для пользователя, возврат к списку. Msg: {message_id}")
    users_list = None
    markup = None
    try:
        users_list = userService.get_all_users(db, include_inactive=True)
        if users_list:
            markup = keyboards.generate_user_management_keyboard(users_list)
            _edit_or_send_message(bot, chat_id, message_id, "Действие отменено. Выберите пользователя для управления:", reply_markup=markup, **kwargs_edit)
        else:
            _edit_or_send_message(bot, chat_id, message_id, "Действие отменено. Нет пользователей для управления.", reply_markup=None, **kwargs_edit)
    except Exception as e:
        logger.error(f"Ошибка при возврате к списку пользователей после отмены управления: {e}", exc_info=True)
        _edit_or_send_message(bot, chat_id, message_id, "Действие отменено. Ошибка загрузки списка пользователей.", reply_markup=None, **kwargs_edit)


# --- END OF FILE callback_handlers.py --