# handlers/callback_handlers.py
import telebot
from telebot import types
from telebot.types import CallbackQuery
from database import Database, QueryResult  # QueryResult может не использоваться напрямую здесь, но для консистентности
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
# import logging # logging импортируется через logger.py
from telebot import apihelper

# Глобальный словарь состояний
user_booking_states: Dict[int, Dict[str, Any]] = {}


def clear_user_state(user_id: int):
    """Безопасно удаляет состояние пользователя."""
    if user_id in user_booking_states:
        del user_booking_states[user_id]
        logger.debug(f"Состояние user {user_id} очищено.")


def _edit_or_send_message(bot: telebot.TeleBot, chat_id: int, message_id: Optional[int], text: str, **kwargs):
    """Пытается отредактировать сообщение, если message_id есть, иначе отправляет новое."""
    user_id_for_state_update = kwargs.pop('user_id_for_state_update', None)
    # is_fake_call_flag = kwargs.pop('is_fake', False) # Флаг для отладки, если нужно разное поведение

    new_message_id = None
    try:
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, **kwargs)
            logger.debug(f"Сообщение {message_id} отредактировано в чате {chat_id}")
            new_message_id = message_id
        else:
            logger.warning(f"Нет message_id для редактирования в чате {chat_id}, отправка нового сообщения.")
            sent_message = bot.send_message(chat_id, text, **kwargs)
            new_message_id = sent_message.message_id
            logger.debug(f"Отправлено новое сообщение ID {new_message_id} в чат {chat_id}")
    except apihelper.ApiTelegramException as e_api:
        if "message is not modified" in str(e_api).lower():
            logger.debug(f"Сообщение {message_id} в чате {chat_id} не было изменено (уже содержит этот текст).")
            new_message_id = message_id
        elif "message to edit not found" in str(e_api).lower() or "message can't be edited" in str(e_api).lower():
            logger.warning(f"Не удалось отредактировать сообщение {message_id} в чате {chat_id}. Отправка нового.")
            try:
                sent_message = bot.send_message(chat_id, text, **kwargs)
                new_message_id = sent_message.message_id
                logger.debug(
                    f"Отправлено новое сообщение ID {new_message_id} в чат {chat_id} (после ошибки редактирования).")
            except Exception as e_send:
                logger.error(
                    f"Не удалось отправить новое сообщение в чат {chat_id} (после ошибки редактирования): {e_send}",
                    exc_info=True)
        else:  # Другие ошибки API при редактировании
            logger.error(f"Ошибка API при редактировании сообщения {message_id} в чате {chat_id}: {e_api}",
                         exc_info=True)
            # Попытка отправить новое сообщение в любом случае при ошибке редактирования
            try:
                logger.info(f"Попытка отправить новое сообщение в чат {chat_id} из-за ошибки API при редактировании.")
                sent_message = bot.send_message(chat_id, text, **kwargs)
                new_message_id = sent_message.message_id
                logger.debug(
                    f"Отправлено новое сообщение ID {new_message_id} в чат {chat_id} (после общей ошибки API при редактировании).")
            except Exception as e_send_final:
                logger.error(
                    f"Не удалось отправить новое сообщение в чат {chat_id} (после общей ошибки API при редактировании): {e_send_final}",
                    exc_info=True)
    except Exception as e:  # Непредвиденные ошибки не связанные с API
        logger.error(f"Общая ошибка в _edit_or_send_message (чат={chat_id}, msg_id={message_id}): {e}", exc_info=True)
        # Попытка отправить новое сообщение, если редактирование или предыдущая отправка не удались
        if not new_message_id and chat_id:  # Если new_message_id все еще None
            try:
                logger.info(
                    f"Попытка отправить новое сообщение в чат {chat_id} из-за общей ошибки в _edit_or_send_message.")
                sent_message = bot.send_message(chat_id, text, **kwargs)
                new_message_id = sent_message.message_id
                logger.debug(f"Отправлено новое сообщение ID {new_message_id} в чат {chat_id} (после общей ошибки).")
            except Exception as e_send_critical:
                logger.critical(
                    f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось отправить сообщение в чат {chat_id} даже после всех попыток: {e_send_critical}",
                    exc_info=True)

    if user_id_for_state_update and new_message_id and user_id_for_state_update in user_booking_states:
        if user_booking_states[user_id_for_state_update].get('message_id') != new_message_id:
            user_booking_states[user_id_for_state_update]['message_id'] = new_message_id
            logger.debug(f"Message_id в состоянии пользователя {user_id_for_state_update} обновлен на {new_message_id}")


def handle_booking_steps(
        bot: telebot.TeleBot, db: Database, call: CallbackQuery, state: Dict[str, Any],
        scheduler: Optional[BackgroundScheduler], active_timers: Optional[Dict[int, Any]],
        scheduled_jobs_registry: Optional[Set[Tuple[str, int]]]
):
    user_id = call.from_user.id
    chat_id = state.get('chat_id', call.message.chat.id if call.message else None)
    message_id = state.get('message_id', call.message.message_id if call.message else None)

    if not chat_id:
        logger.error(
            f"Не удалось определить chat_id для user {user_id} в handle_booking_steps. Callback data: {call.data}")
        try:
            bot.answer_callback_query(call.id, "Ошибка: не удалось определить чат.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        clear_user_state(user_id)
        return

    current_step = state.get('step', const.STATE_BOOKING_IDLE)
    cb_data = call.data
    user_state_data = state.get('data', {})
    kwargs_edit_send = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    logger.debug(
        f"handle_booking_steps: user={user_id}, step={current_step}, data='{cb_data}', state_data={user_state_data}, message_id_from_state={state.get('message_id')}, message_id_from_call={call.message.message_id if call.message else 'N/A'}")

    if cb_data == const.CB_BOOK_CANCEL_PROCESS:
        logger.info(f"User {user_id} отменил процесс бронирования на шаге {current_step}.")
        try:
            bot.answer_callback_query(call.id, const.MSG_BOOKING_PROCESS_CANCELLED)
        except apihelper.ApiTelegramException:
            pass
        _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_PROCESS_CANCELLED, reply_markup=None,
                              **kwargs_edit_send)
        clear_user_state(user_id)
        return

    try:
        if current_step == const.STATE_BOOKING_CATEGORY and cb_data.startswith(const.CB_BOOK_SELECT_CATEGORY):
            try:
                bot.answer_callback_query(call.id)
            except apihelper.ApiTelegramException:
                pass
            category_id = int(cb_data[len(const.CB_BOOK_SELECT_CATEGORY):])
            category_info = equipmentService.get_category_by_id(db, category_id)
            if not category_info:
                logger.error(f"Категория с ID {category_id} не найдена для user {user_id}.")
                _edit_or_send_message(bot, chat_id, message_id, "Ошибка: выбранная категория не найдена.",
                                      reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return
            category_name = category_info.get('name_cat')
            if not category_name:
                logger.error(f"Имя категории не найдено для ID {category_id} (user {user_id}).")
                _edit_or_send_message(bot, chat_id, message_id, "Ошибка: не удалось получить имя выбранной категории.",
                                      reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return

            user_state_data['category_id'] = category_id
            user_state_data['category_name'] = category_name
            logger.debug(f"User {user_id} выбрал категорию ID {category_id} ('{category_name}')")

            equipment = equipmentService.get_equipment_by_category(db, category_id)
            if not equipment:
                _edit_or_send_message(bot, chat_id, message_id,
                                      const.MSG_NO_EQUIPMENT_IN_CATEGORY.format(category_name=category_name),
                                      reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return
            markup = keyboards.generate_equipment_keyboard(equipment, const.CB_BOOK_SELECT_EQUIPMENT)
            _edit_or_send_message(bot, chat_id, message_id,
                                  const.MSG_BOOKING_STEP_2_EQUIPMENT.format(category_name=category_name),
                                  reply_markup=markup, **kwargs_edit_send)
            state['step'] = const.STATE_BOOKING_EQUIPMENT

        elif current_step == const.STATE_BOOKING_EQUIPMENT and cb_data.startswith(const.CB_BOOK_SELECT_EQUIPMENT):
            try:
                bot.answer_callback_query(call.id)
            except apihelper.ApiTelegramException:
                pass
            equipment_id = int(cb_data[len(const.CB_BOOK_SELECT_EQUIPMENT):])
            equipment_name = equipmentService.get_equipment_name_by_id(db, equipment_id)
            if not equipment_name:
                logger.error(f"Оборудование с ID {equipment_id} не найдено для user {user_id}.")
                _edit_or_send_message(bot, chat_id, message_id, "Ошибка: выбранное оборудование не найдено.",
                                      reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return

            user_state_data['equipment_id'] = equipment_id
            user_state_data['equipment_name'] = equipment_name
            logger.debug(f"User {user_id} выбрал оборудование ID {equipment_id} ('{equipment_name}')")
            markup = keyboards.generate_date_keyboard(const.CB_BOOK_SELECT_DATE)
            _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_3_DATE, reply_markup=markup,
                                  **kwargs_edit_send)
            state['step'] = const.STATE_BOOKING_DATE

        elif current_step == const.STATE_BOOKING_DATE and cb_data.startswith(const.CB_BOOK_SELECT_DATE):
            try:
                bot.answer_callback_query(call.id)
            except apihelper.ApiTelegramException:
                pass
            selected_date_str = cb_data[len(const.CB_BOOK_SELECT_DATE):]
            try:
                selected_date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
            except ValueError:
                logger.error(f"Неверный формат даты '{selected_date_str}' от user {user_id}")
                _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный формат выбранной даты.",
                                      reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return

            equipment_id = user_state_data.get('equipment_id')
            if not equipment_id:
                logger.error(f"equipment_id не найден в состоянии на шаге выбора даты для user {user_id}")
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None,
                                      **kwargs_edit_send)
                clear_user_state(user_id)
                return

            user_state_data['selected_date_str'] = selected_date_str
            user_state_data['selected_date_obj'] = selected_date_obj
            logger.debug(f"User {user_id} выбрал дату {selected_date_str} для оборудования ID {equipment_id}")

            available_slots = bookingService.calculate_available_slots(db, equipment_id, selected_date_obj)
            user_state_data['available_slots'] = available_slots

            if not available_slots:
                logger.warning(f"Нет доступных слотов для оборудования ID {equipment_id} на дату {selected_date_str}")
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_NO_SLOTS_AVAILABLE, reply_markup=None,
                                      **kwargs_edit_send)
                clear_user_state(user_id)
                return

            is_full_day_free = (len(available_slots) == 1 and
                                available_slots[0][0] == const.WORKING_HOURS_START and
                                available_slots[0][1] == const.WORKING_HOURS_END)

            if is_full_day_free:
                logger.debug(f"Дата {selected_date_str} полностью свободна для оборудования ID {equipment_id}.")
                full_day_slot = (const.WORKING_HOURS_START, const.WORKING_HOURS_END)
                user_state_data['selected_slot'] = full_day_slot
                markup = keyboards.generate_time_keyboard_in_slot(full_day_slot, selected_date_obj,
                                                                  const.CB_BOOK_SELECT_TIME)
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_5_START_TIME,
                                      reply_markup=markup, **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_START_TIME
            else:
                logger.debug(
                    f"Дата {selected_date_str} для оборудования ID {equipment_id} имеет следующие доступные слоты: {available_slots}")
                markup = keyboards.generate_available_slots_keyboard(available_slots, const.CB_BOOK_SELECT_SLOT)
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_STEP_4_SLOT, reply_markup=markup,
                                      **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_SLOT

        elif current_step == const.STATE_BOOKING_SLOT and cb_data.startswith(const.CB_BOOK_SELECT_SLOT):
            try:
                bot.answer_callback_query(call.id)
            except apihelper.ApiTelegramException:
                pass
            try:
                slot_index = int(cb_data[len(const.CB_BOOK_SELECT_SLOT):])
                available_slots = user_state_data.get('available_slots')

                if not isinstance(available_slots, list) or not (0 <= slot_index < len(available_slots)):
                    logger.error(
                        f"Неверный индекс слота {slot_index} или available_slots не список/пуст ({available_slots}) для user {user_id}")
                    raise IndexError("Неверный индекс слота или слоты не найдены.")

                selected_slot = available_slots[slot_index]
                user_state_data['selected_slot'] = selected_slot
                selected_date_obj = user_state_data.get('selected_date_obj')

                if not isinstance(selected_date_obj, date):
                    logger.error(f"selected_date_obj не найден или неверного типа в состоянии user {user_id}")
                    raise ValueError("Дата для выбора времени не найдена в состоянии.")

                logger.debug(f"User {user_id} выбрал слот: {selected_slot}")
                markup = keyboards.generate_time_keyboard_in_slot(selected_slot, selected_date_obj,
                                                                  const.CB_BOOK_SELECT_TIME)
                prompt_text = const.MSG_BOOKING_PROMPT_START_TIME_IN_SLOT.format(
                    start_slot=bookingService._format_time(selected_slot[0]),
                    end_slot=bookingService._format_time(selected_slot[1])
                )
                _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_START_TIME
            except (ValueError, IndexError, TypeError) as e:
                logger.error(f"Ошибка при выборе слота user {user_id}: {e}", exc_info=True)
                _edit_or_send_message(bot, chat_id, message_id,
                                      "Ошибка при обработке выбранного слота. Попробуйте снова.", reply_markup=None,
                                      **kwargs_edit_send)
                clear_user_state(user_id)
                return

        elif current_step == const.STATE_BOOKING_START_TIME and cb_data.startswith(const.CB_BOOK_SELECT_TIME):
            try:
                bot.answer_callback_query(call.id)
            except apihelper.ApiTelegramException:
                pass
            start_time_str = cb_data[len(const.CB_BOOK_SELECT_TIME):]
            try:
                start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
                user_state_data['start_time_str'] = start_time_str
                user_state_data['start_time_obj'] = start_time_obj

                selected_date_obj = user_state_data.get('selected_date_obj')
                selected_slot = user_state_data.get('selected_slot')

                if not isinstance(selected_date_obj, date):
                    logger.error(
                        f"selected_date_obj не найден или неверного типа в состоянии user {user_id} на шаге выбора времени")
                    raise ValueError("Дата для выбора длительности не найдена в состоянии.")

                logger.debug(f"User {user_id} выбрал время начала: {start_time_str}")

                effective_end_time_for_duration_calc = const.WORKING_HOURS_END
                if selected_slot and isinstance(selected_slot, tuple) and len(selected_slot) == 2:
                    effective_end_time_for_duration_calc = selected_slot[1]

                if not isinstance(effective_end_time_for_duration_calc, time):
                    logger.error(
                        f"Некорректный тип effective_end_time_for_duration_calc: {type(effective_end_time_for_duration_calc)} для user {user_id}")
                    raise TypeError("effective_end_time_for_duration_calc должен быть объектом time")

                markup = keyboards.generate_duration_keyboard_in_slot(
                    start_time_obj, selected_date_obj, effective_end_time_for_duration_calc,
                    const.CB_BOOK_SELECT_DURATION
                )
                prompt_text = const.MSG_BOOKING_PROMPT_DURATION_IN_SLOT.format(
                    end_slot=bookingService._format_time(effective_end_time_for_duration_calc)
                ) if selected_slot else const.MSG_BOOKING_STEP_6_DURATION

                _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_DURATION
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Ошибка при выборе времени начала user {user_id}: {e}", exc_info=True)
                _edit_or_send_message(bot, chat_id, message_id,
                                      "Ошибка при обработке выбранного времени. Попробуйте снова.", reply_markup=None,
                                      **kwargs_edit_send)
                clear_user_state(user_id)
                return

        elif current_step == const.STATE_BOOKING_DURATION and cb_data.startswith(const.CB_BOOK_SELECT_DURATION):
            try:
                bot.answer_callback_query(call.id)
            except apihelper.ApiTelegramException:
                pass
            duration_str = cb_data[len(const.CB_BOOK_SELECT_DURATION):]
            try:
                user_state_data['duration_str'] = duration_str

                required_data_keys = ['selected_date_obj', 'start_time_obj', 'category_name', 'equipment_name',
                                      'selected_date_str', 'start_time_str']
                for key_check in required_data_keys:
                    if key_check not in user_state_data or user_state_data[key_check] is None:
                        logger.error(
                            f"Отсутствует ключ '{key_check}' в user_state_data для user {user_id} на шаге выбора длительности. State: {user_state_data}")
                        raise KeyError(f"Отсутствуют необходимые данные в состоянии: {key_check}")

                start_dt = datetime.combine(user_state_data['selected_date_obj'], user_state_data['start_time_obj'])
                hours, minutes = map(int, duration_str.split(':'))
                duration_delta = timedelta(hours=hours, minutes=minutes)
                end_dt = start_dt + duration_delta

                user_state_data['end_time_obj'] = end_dt.time()
                user_state_data['end_time_str'] = end_dt.strftime('%H:%M')

                logger.debug(
                    f"User {user_id} выбрал длительность {duration_str}, время окончания: {user_state_data['end_time_str']}")

                category_name = user_state_data['category_name']
                equip_name = user_state_data['equipment_name']
                sel_date_str = user_state_data['selected_date_str']
                s_time_str = user_state_data['start_time_str']
                e_time_str = user_state_data['end_time_str']

                confirm_text = const.MSG_BOOKING_CONFIRM_DETAILS.format(
                    category_name=category_name,
                    equip_name=equip_name,
                    date=sel_date_str,
                    start_time=s_time_str,
                    end_time=e_time_str,
                    duration=duration_str
                )
                markup = keyboards.generate_booking_confirmation_keyboard()
                _edit_or_send_message(bot, chat_id, message_id, f"{const.MSG_BOOKING_STEP_7_CONFIRM}\n{confirm_text}",
                                      reply_markup=markup, **kwargs_edit_send)
                state['step'] = const.STATE_BOOKING_CONFIRM
            except (ValueError, KeyError) as e:
                logger.error(f"Ошибка при выборе длительности user {user_id}: {e}", exc_info=True)
                _edit_or_send_message(bot, chat_id, message_id, "Ошибка данных для подтверждения. Попробуйте снова.",
                                      reply_markup=None, **kwargs_edit_send)
                clear_user_state(user_id)
                return

        elif current_step == const.STATE_BOOKING_CONFIRM and cb_data == const.CB_BOOK_CONFIRM_FINAL:
            try:
                bot.answer_callback_query(call.id, "Сохраняю бронирование...")
            except apihelper.ApiTelegramException:
                pass
            logger.info(f"User {user_id} подтвердил бронирование. Данные: {user_state_data}")
            try:
                equip_id = user_state_data.get('equipment_id')
                sel_date_str = user_state_data.get('selected_date_str')
                s_time_str = user_state_data.get('start_time_str')
                dur_str = user_state_data.get('duration_str')

                if not all([equip_id, sel_date_str, s_time_str, dur_str]):
                    logger.error(
                        f"Недостаточно данных для создания бронирования user {user_id}. State: {user_state_data}")
                    raise ValueError("Отсутствуют необходимые данные для создания бронирования.")

                success, msg, new_booking_id = bookingService.create_booking(db, user_id, equip_id, sel_date_str,
                                                                             s_time_str, dur_str)
                _edit_or_send_message(bot, chat_id, message_id, msg, reply_markup=None, **kwargs_edit_send)

                if success and new_booking_id:
                    if scheduler and active_timers is not None and scheduled_jobs_registry is not None:
                        logger.debug(f"Бронь ID {new_booking_id} успешно создана, планирую уведомления...")
                        notificationService.schedule_all_notifications(db, bot, scheduler, active_timers,
                                                                       scheduled_jobs_registry)
                    else:
                        logger.warning(
                            "Планировщик или связанные с ним компоненты не переданы, уведомления не будут запланированы.")
            except ValueError as e:
                logger.error(f"Ошибка данных при финальном подтверждении бронирования user {user_id}: {e}",
                             exc_info=True)
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None,
                                      **kwargs_edit_send)
            except Exception as e:
                logger.error(f"Ошибка при создании бронирования user {user_id}: {e}", exc_info=True)
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_FAIL_GENERAL, reply_markup=None,
                                      **kwargs_edit_send)
            finally:
                clear_user_state(user_id)

        else:
            if cb_data.startswith(const.CB_BOOK_ACTION):
                logger.warning(
                    f"User {user_id} нажал кнопку '{cb_data}' на шаге {current_step}. Возможно, это старая кнопка или неверное состояние.")
                try:
                    bot.answer_callback_query(call.id,
                                              "Это действие сейчас неактуально. Пожалуйста, используйте кнопки на последнем сообщении.",
                                              show_alert=True)
                except apihelper.ApiTelegramException:
                    pass
            else:
                logger.warning(
                    f"Неожиданный callback '{cb_data}' от user {user_id} на шаге {current_step} процесса бронирования. Сброс состояния.")
                try:
                    bot.answer_callback_query(call.id, "Произошла ошибка в процессе бронирования, действие прервано.",
                                              show_alert=True)
                except apihelper.ApiTelegramException:
                    pass
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_BOOKING_ERROR_STATE, reply_markup=None,
                                      **kwargs_edit_send)
                clear_user_state(user_id)

    except Exception as e:
        logger.critical(
            f"Критическая ошибка в handle_booking_steps (user={user_id}, step={current_step}, cb_data='{cb_data}'): {e}",
            exc_info=True)
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        try:
            if chat_id:
                _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None,
                                      **kwargs_edit_send)
        except Exception:
            pass
        clear_user_state(user_id)


def handle_callback_query(
        bot: telebot.TeleBot,
        db: Database,
        scheduler_instance: Optional[BackgroundScheduler],
        active_timers_instance: Optional[Dict[int, Any]],
        job_registry_instance: Optional[Set[Tuple[str, int]]],
        call: types.CallbackQuery,
        source_command: str = None
):
    user_id = call.from_user.id
    chat_id = call.message.chat.id if call.message else None
    message_id = call.message.message_id if call.message else None
    cb_data = call.data

    logger.debug(
        f"Callback received: user={user_id}, chat={chat_id}, msg_id={message_id}, data='{cb_data}', source_cmd='{source_command}'")

    is_truly_fake_call = hasattr(call, 'is_fake_call') and call.is_fake_call

    user_state = user_booking_states.get(user_id)
    if user_state and user_state.get('step', const.STATE_BOOKING_IDLE) != const.STATE_BOOKING_IDLE:
        current_fsm_message_id = user_state.get('message_id')
        if message_id and current_fsm_message_id and message_id != current_fsm_message_id:
            logger.warning(f"User {user_id} (callback: '{cb_data}') нажал кнопку на старом сообщении ID {message_id}. "
                           f"Активное сообщение FSM ID: {current_fsm_message_id}. Игнорирую.")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id,
                                              "Пожалуйста, используйте кнопки на последнем сообщении процесса.",
                                              show_alert=True)
                except apihelper.ApiTelegramException:
                    pass
            return
        handle_booking_steps(bot, db, call, user_state, scheduler_instance, active_timers_instance,
                             job_registry_instance)
        return

    logger.debug(f"User {user_id} не в активном процессе бронирования, обработка callback '{cb_data}'...")

    try:
        is_admin_user = userService.is_admin(db, user_id)
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора для user {user_id}: {e}", exc_info=True)
        if not is_truly_fake_call:
            try:
                bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
            except apihelper.ApiTelegramException:
                pass
        return

    is_admin_specific_action = (
            cb_data.startswith(const.CB_REG_CONFIRM_USER) or cb_data.startswith(const.CB_REG_DECLINE_USER) or
            cb_data.startswith(const.CB_MANAGE_USER_SELECT) or cb_data.startswith(const.CB_MANAGE_USER_ACTION_BLOCK) or
            cb_data.startswith(const.CB_MANAGE_USER_ACTION_UNBLOCK) or cb_data.startswith(
        const.CB_ADMIN_CANCEL_SELECT) or
            cb_data.startswith(const.CB_ADMIN_CANCEL_CONFIRM) or cb_data.startswith(const.CB_FILTER_BY_TYPE) or
            cb_data.startswith(const.CB_FILTER_SELECT_USER) or cb_data.startswith(const.CB_FILTER_SELECT_CATEGORY) or
            cb_data.startswith(const.CB_FILTER_SELECT_EQUIPMENT) or cb_data.startswith(const.CB_FILTER_SELECT_DATE) or
            cb_data.startswith(const.CB_ADMIN_MANAGE_EQUIP_SELECT_CAT) or
            cb_data.startswith(const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP) or cb_data.startswith(
        const.CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE) or
            cb_data.startswith(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN) or cb_data.startswith(
        const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN)  # Добавил права админа
    )

    actions_without_active_check = (
            is_admin_specific_action or
            cb_data == const.CB_IGNORE or
            cb_data.startswith(const.CB_ACTION_CANCEL)
    )

    if is_admin_specific_action and not is_admin_user:
        logger.warning(f"Пользователь {user_id} попытался выполнить админское действие '{cb_data}' без прав.")
        if not is_truly_fake_call:
            try:
                bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True)
            except apihelper.ApiTelegramException:
                pass
        return

    if not actions_without_active_check:
        try:
            if not userService.is_user_registered_and_active(db, user_id):
                logger.warning(
                    f"Неактивный/незарегистрированный пользователь {user_id} попытался выполнить действие '{cb_data}'.")
                if not is_truly_fake_call:
                    try:
                        bot.answer_callback_query(call.id, const.MSG_ERROR_NOT_REGISTERED, show_alert=True)
                    except apihelper.ApiTelegramException:
                        pass
                if chat_id and message_id:
                    try:
                        _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_NOT_REGISTERED,
                                              reply_markup=None, user_id_for_state_update=user_id)
                    except Exception:
                        pass
                return
        except Exception as e_check_active:
            logger.error(
                f"Ошибка при проверке статуса пользователя {user_id} для действия '{cb_data}': {e_check_active}",
                exc_info=True)
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                except apihelper.ApiTelegramException:
                    pass
            return

    kwargs_edit_send_other = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    try:
        if cb_data.startswith(const.CB_BOOK_CONFIRM_START):
            booking_id = int(cb_data[len(const.CB_BOOK_CONFIRM_START):])
            logger.info(f"User {user_id} подтверждает бронь ID {booking_id} из уведомления.")
            # --- ИЗМЕНЕННЫЙ ВЫЗОВ ---
            success = notificationService.confirm_booking_callback_logic(
                db,
                bot,  # <--- ПЕРЕДАЕМ ЭКЗЕМПЛЯР БОТА (он доступен как параметр handle_callback_query)
                active_timers_instance if active_timers_instance else {},
                call,  # <--- ПЕРЕДАЕМ ВЕСЬ ОБЪЕКТ CALLBACKQUERY (он доступен как параметр handle_callback_query)
                booking_id,
                user_id
                # user_id можно было бы даже не передавать, если confirm_booking_callback_logic
                # будет брать его из call.from_user.id, но для единообразия оставим
            )
            # --- КОНЕЦ ИЗМЕНЕННОГО ВЫЗОВА ---
            msg_to_user = const.MSG_BOOKING_CONFIRMED if success else "Не удалось подтвердить бронь."
            alert_show = not success
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, msg_to_user, show_alert=alert_show)
                except apihelper.ApiTelegramException:
                    pass
            # if success and chat_id and message_id:
            #     _edit_or_send_message(bot, chat_id, message_id, f"✅ {const.MSG_BOOKING_CONFIRMED}", reply_markup=None,
            #                           **kwargs_edit_send_other)
            # elif not success and chat_id and message_id:
            #     try:
            #         bot.delete_message(chat_id, message_id)
            #     except Exception:
            #         pass

        elif cb_data.startswith(const.CB_CANCEL_SELECT_BOOKING):
            booking_id = int(cb_data[len(const.CB_CANCEL_SELECT_BOOKING):])
            logger.info(f"User {user_id} выбрал для отмены бронь ID {booking_id}")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, "Отменяю бронирование...")
                except apihelper.ApiTelegramException:
                    pass
            success, msg, _ = bookingService.cancel_booking(db, booking_id, user_id=user_id, is_admin_cancel=False)
            if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit_send_other)
            if success and scheduler_instance and job_registry_instance:
                logger.debug(f"Бронь {booking_id} отменена, очищаю связанные задачи планировщика...")
                notificationService.cleanup_completed_jobs(db, scheduler_instance, job_registry_instance)

        elif cb_data.startswith(const.CB_ADMIN_CANCEL_SELECT):
            booking_id = int(cb_data[len(const.CB_ADMIN_CANCEL_SELECT):])
            handle_admin_cancel_select(bot, db, call, user_id, chat_id, message_id, booking_id)

        elif cb_data.startswith(const.CB_ADMIN_CANCEL_CONFIRM):
            booking_id = int(cb_data[len(const.CB_ADMIN_CANCEL_CONFIRM):])
            handle_admin_cancel_confirm(bot, db, call, user_id, chat_id, message_id, booking_id, scheduler_instance,
                                        job_registry_instance)

        elif cb_data.startswith(const.CB_FINISH_SELECT_BOOKING):
            booking_id = int(cb_data[len(const.CB_FINISH_SELECT_BOOKING):])
            logger.info(f"User {user_id} выбрал для завершения бронь ID {booking_id}")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, "Завершаю бронирование...")
                except apihelper.ApiTelegramException:
                    pass
            success, msg = bookingService.finish_booking(db, booking_id, user_id)
            if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg, **kwargs_edit_send_other)
            if success and scheduler_instance and job_registry_instance:
                logger.debug(f"Бронь {booking_id} завершена, очищаю связанные задачи планировщика...")
                notificationService.cleanup_completed_jobs(db, scheduler_instance, job_registry_instance)

        elif cb_data.startswith(const.CB_EXTEND_SELECT_BOOKING) or cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT):
            is_from_notify = cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT)
            prefix_len = len(const.CB_NOTIFY_EXTEND_PROMPT) if is_from_notify else len(const.CB_EXTEND_SELECT_BOOKING)
            booking_id = int(cb_data[prefix_len:])

            effective_source = source_command
            if not effective_source:
                effective_source = "из уведомления" if is_from_notify else "из списка броней"

            logger.info(
                f"User {user_id} инициировал продление для брони ID {booking_id} (source: {effective_source}, is_fake_call_flag: {is_truly_fake_call})")

            handle_extend_select_booking(
                bot, db, call, user_id, chat_id, message_id, booking_id,
                is_truly_fake_call,
                effective_source
            )

        elif cb_data.startswith(const.CB_EXTEND_SELECT_TIME):
            data_part = cb_data[len(const.CB_EXTEND_SELECT_TIME):]
            parts = data_part.split('_')
            if len(parts) != 2:
                logger.error(f"Неверный формат callback-данных для продления времени: {cb_data}")
                raise ValueError("Неверный формат callback-данных для выбора времени продления")
            booking_id = int(parts[0])
            extension_str = parts[1]
            logger.info(f"User {user_id} выбрал длительность продления '{extension_str}' для брони ID {booking_id}")
            handle_extend_select_time(bot, db, call, user_id, chat_id, message_id, booking_id, extension_str,
                                      scheduler_instance, active_timers_instance, job_registry_instance)

        elif cb_data.startswith(const.CB_NOTIFY_DECLINE_EXT):
            booking_id = int(cb_data[len(const.CB_NOTIFY_DECLINE_EXT):])
            logger.info(f"User {user_id} отказался от продления брони {booking_id} через уведомление.")
            try:
                bot.answer_callback_query(call.id, "Ваш выбор учтен.")
            except apihelper.ApiTelegramException:
                pass
            try:
                original_text = call.message.text if call.message and call.message.text else f"Уведомление по брони {booking_id}"
                if chat_id: _edit_or_send_message(bot, chat_id, message_id,
                                                  f"{original_text}\n\n{const.MSG_EXTEND_DECLINED}", reply_markup=None,
                                                  **kwargs_edit_send_other)
            except Exception as e_edit_decline:
                logger.warning(
                    f"Не удалось отредактировать сообщение {message_id} при отказе от продления: {e_edit_decline}")

        elif cb_data.startswith(const.CB_REG_CONFIRM_USER):
            handle_registration_confirm(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_REG_DECLINE_USER):
            handle_registration_decline(bot, db, call, user_id, chat_id, message_id)

        elif cb_data.startswith(const.CB_DATEB_SELECT_DATE):
            handle_datebookings_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_WSPB_SELECT_CATEGORY):
            handle_wsb_category_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_WSPB_SELECT_EQUIPMENT):
            handle_wsb_equipment_select(bot, db, call, user_id, chat_id, message_id)

        elif cb_data.startswith(const.CB_FILTER_BY_TYPE):
            handle_filter_type_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(
                (const.CB_FILTER_SELECT_USER, const.CB_FILTER_SELECT_CATEGORY, const.CB_FILTER_SELECT_EQUIPMENT,
                 const.CB_FILTER_SELECT_DATE)):
            handle_filter_value_select(bot, db, call, user_id, chat_id, message_id)

        elif cb_data.startswith(const.CB_ADMIN_MANAGE_EQUIP_SELECT_CAT):
            handle_admin_manage_cat_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP):
            handle_equip_delete_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE):
            handle_equip_delete_confirm(bot, db, call, user_id, chat_id, message_id)

        elif cb_data.startswith(const.CB_MANAGE_USER_SELECT):
            handle_manage_user_select(bot, db, call, user_id, chat_id, message_id)
        elif cb_data.startswith(const.CB_MANAGE_USER_ACTION_BLOCK) or \
                cb_data.startswith(const.CB_MANAGE_USER_ACTION_UNBLOCK) or \
                cb_data.startswith(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN) or \
                cb_data.startswith(const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN):
            handle_manage_user_action(bot, db, call, user_id, chat_id, message_id)

        elif cb_data.startswith(const.CB_ACTION_CANCEL):
            context_cancel = cb_data[len(const.CB_ACTION_CANCEL):]
            logger.debug(
                f"User {user_id} нажал кнопку отмены действия. Контекст: '{context_cancel}'. Сообщение ID: {message_id}")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
                except apihelper.ApiTelegramException:
                    pass

            default_reply_markup = keyboards.create_user_reply_keyboard()
            if is_admin_user:
                default_reply_markup = keyboards.create_admin_reply_keyboard()

            # Определяем, какой обработчик отмены вызвать или какое действие предпринять
            if context_cancel.startswith("delete_equip_process_"):  # Контекст отмены удаления конкретного оборудования
                handle_cancel_delete_equip(bot, db, chat_id, message_id, user_id_for_state_update=user_id)
            elif context_cancel.startswith("admin_cancel_process_"):  # Контекст отмены админской отмены брони
                handle_cancel_admin_cancel(bot, db, chat_id, message_id, user_id_for_state_update=user_id)
            elif context_cancel == "manage_user_list":  # Контекст "Назад к списку пользователей" из управления конкретным пользователем
                handle_cancel_manage_user(bot, db, chat_id, message_id, user_id_for_state_update=user_id)
            elif context_cancel == const.CB_EXTEND_SELECT_BOOKING.replace('cb_', '', 1).split('_')[
                0]:  # Отмена выбора времени продления
                logger.debug(
                    f"Отмена выбора времени продления (контекст: {context_cancel}), удаляем сообщение с вариантами времени.")
                if chat_id and message_id:
                    try:
                        bot.delete_message(chat_id, message_id)
                    except apihelper.ApiTelegramException:
                        pass
                if chat_id: bot.send_message(chat_id, "Выбор времени продления отменен.",
                                             reply_markup=default_reply_markup)
            else:  # Общая отмена без специфического обработчика
                logger.debug(
                    f"Общая отмена действия (контекст: '{context_cancel}'). Удаляю сообщение {message_id}, если есть.")
                if chat_id and message_id:
                    try:
                        bot.delete_message(chat_id, message_id)
                    except apihelper.ApiTelegramException:
                        pass
                if chat_id: bot.send_message(chat_id, const.MSG_ACTION_CANCELLED, reply_markup=default_reply_markup)

        elif cb_data == const.CB_IGNORE:
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id)
                except apihelper.ApiTelegramException:
                    pass
        else:
            logger.warning(f"Неизвестный callback от user {user_id}: '{cb_data}' (вне FSM бронирования)")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, "Неизвестное действие.")
                except apihelper.ApiTelegramException:
                    pass

    except (ValueError, TypeError) as e_parse_global:
        logger.error(f"Ошибка парсинга данных в callback '{cb_data}' от user {user_id}: {e_parse_global}",
                     exc_info=True)
        if not is_truly_fake_call:
            try:
                bot.answer_callback_query(call.id, "Ошибка в данных запроса.", show_alert=True)
            except apihelper.ApiTelegramException:
                pass
    except IndexError as e_index_global:
        logger.error(f"Ошибка индекса при обработке callback '{cb_data}' от user {user_id}: {e_index_global}",
                     exc_info=True)
        if not is_truly_fake_call:
            try:
                bot.answer_callback_query(call.id, "Ошибка: неверные данные.", show_alert=True)
            except apihelper.ApiTelegramException:
                pass
    except apihelper.ApiTelegramException as e_api_global:
        if "message is not modified" in str(e_api_global).lower():
            logger.debug(f"Сообщение {message_id} (если есть) не было изменено (ошибка API на верхнем уровне).")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id)
                except apihelper.ApiTelegramException:
                    pass
        elif "query is too old" in str(e_api_global).lower() or "query id is invalid" in str(e_api_global).lower():
            logger.warning(f"Callback query {call.id} устарел или невалиден (ошибка API на верхнем уровне).")
        elif "bot was blocked by the user" in str(e_api_global).lower() or "user is deactivated" in str(
                e_api_global).lower():
            logger.warning(f"Бот был заблокирован пользователем {user_id} или пользователь деактивирован.")
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id)
                except apihelper.ApiTelegramException:
                    pass
            try:
                userService.handle_user_blocked_bot(db, user_id)
            except Exception as e_block_handle:
                logger.error(f"Ошибка при обработке блокировки бота пользователем {user_id}: {e_block_handle}")
        else:
            logger.error(
                f"Необработанная ошибка Telegram API при обработке callback '{cb_data}' от user {user_id}: {e_api_global}",
                exc_info=True)
            if not is_truly_fake_call:
                try:
                    bot.answer_callback_query(call.id, "Произошла ошибка при связи с Telegram.", show_alert=True)
                except apihelper.ApiTelegramException:
                    pass
    except Exception as e_global_critical:
        logger.critical(
            f"Критическая необработанная ошибка при обработке callback '{cb_data}' от user {user_id}: {e_global_critical}",
            exc_info=True)
        if not is_truly_fake_call:
            try:
                bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
            except apihelper.ApiTelegramException:
                pass


def register_callback_handlers(
        bot: telebot.TeleBot,
        db: Database,
        scheduler: Optional[BackgroundScheduler],
        active_timers: Optional[Dict[int, Any]],
        scheduled_jobs_registry: Optional[Set[Tuple[str, int]]]
):
    @bot.callback_query_handler(func=lambda call: True)
    def main_callback_dispatcher(call: CallbackQuery):
        handle_callback_query(bot, db, scheduler, active_timers, scheduled_jobs_registry, call, source_command=None)

    logger.info("Обработчики callback-запросов (inline кнопок) успешно зарегистрированы.")


# --- Функции-обработчики для колбэков, вынесенные для чистоты ---
# (Остальные функции как в предыдущем сообщении)

def handle_admin_manage_cat_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                                   chat_id: Optional[int], message_id: Optional[int]):
    try:
        category_id = int(call.data[len(const.CB_ADMIN_MANAGE_EQUIP_SELECT_CAT):])
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID категории из callback: '{call.data}'")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID категории.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} выбрал категорию ID {category_id} для управления оборудованием.")
    try:
        bot.answer_callback_query(call.id)  # Отвечаем на коллбэк без текста
    except apihelper.ApiTelegramException:
        pass

    equipment_in_category = equipmentService.get_equipment_by_category(db, category_id)
    category_info = equipmentService.get_category_by_id(db, category_id)
    category_name = category_info.get('name_cat', f"ID {category_id}") if category_info else f"ID {category_id}"

    if not equipment_in_category:
        msg_text = const.MSG_ADMIN_MANAGE_EQUIP_NO_EQUIP_IN_CAT.format(category_name=category_name)
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg_text, user_id_for_state_update=user_id)
        return

    markup = keyboards.generate_equipment_keyboard(equipment_in_category, const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP)
    prompt_text = const.MSG_ADMIN_MANAGE_EQUIP_CHOOSE_EQUIP.format(category_name=category_name)

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup,
                                      user_id_for_state_update=user_id)


def handle_registration_confirm(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                                chat_id: Optional[int], message_id: Optional[int]):
    temp_user_id_str = call.data[len(const.CB_REG_CONFIRM_USER):]
    try:
        temp_user_id = int(temp_user_id_str)
    except ValueError:
        logger.error(f"Ошибка конвертации temp_user_id '{temp_user_id_str}' в int.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id,
                                          "Ошибка: неверный ID пользователя для подтверждения.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} подтверждает регистрацию для temp_user_id {temp_user_id}")
    try:
        bot.answer_callback_query(call.id, "Подтверждаю регистрацию...")
    except apihelper.ApiTelegramException:
        pass

    success, user_info = userService.confirm_registration(db, temp_user_id)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    if success and user_info:
        first_name = user_info.get('first_name', f'User {temp_user_id}')
        text_for_admin = f"✅ Пользователь {first_name} (ID: `{temp_user_id}`) успешно зарегистрирован."
        try:
            bot.send_message(temp_user_id, const.MSG_REGISTRATION_APPROVED)
            logger.info(f"Уведомление об одобрении отправлено пользователю {temp_user_id}")
        except apihelper.ApiTelegramException as e_notify:
            logger.error(f"Не удалось отправить уведомление об одобрении пользователю {temp_user_id}: {e_notify}")
        except Exception as e_notify_other:
            logger.error(
                f"Другая ошибка при отправке уведомления об одобрении пользователю {temp_user_id}: {e_notify_other}",
                exc_info=True)
    elif success and not user_info:
        logger.warning(
            f"Регистрация temp_user_id {temp_user_id} прошла успешно, но не удалось получить информацию о пользователе.")
        text_for_admin = f"✅ Регистрация для ID `{temp_user_id}` подтверждена (информация о пользователе не получена)."
    else:
        text_for_admin = f"❌ Ошибка при подтверждении регистрации для ID `{temp_user_id}`."

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, text_for_admin, **kwargs_edit)


def handle_registration_decline(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                                chat_id: Optional[int], message_id: Optional[int]):
    temp_user_id_str = call.data[len(const.CB_REG_DECLINE_USER):]
    try:
        temp_user_id = int(temp_user_id_str)
    except ValueError:
        logger.error(f"Ошибка конвертации temp_user_id '{temp_user_id_str}' в int при отклонении.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID пользователя для отклонения.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} отклоняет регистрацию для temp_user_id {temp_user_id}")
    try:
        bot.answer_callback_query(call.id, "Отклоняю регистрацию...")
    except apihelper.ApiTelegramException:
        pass

    success = userService.decline_registration(db, temp_user_id)
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    if success:
        text_for_admin = f"🚫 Регистрация для ID `{temp_user_id}` отклонена."
        try:
            bot.send_message(temp_user_id, const.MSG_REGISTRATION_DECLINED)
            logger.info(f"Уведомление об отклонении отправлено пользователю {temp_user_id}")
        except apihelper.ApiTelegramException as e_notify:
            logger.warning(f"Не удалось отправить уведомление об отклонении пользователю {temp_user_id}: {e_notify}")
        except Exception as e_notify_other:
            logger.warning(
                f"Другая ошибка при отправке уведомления об отклонении пользователю {temp_user_id}: {e_notify_other}",
                exc_info=True)
    else:
        text_for_admin = f"❌ Ошибка при отклонении регистрации для ID `{temp_user_id}`."

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, text_for_admin, **kwargs_edit)


def handle_datebookings_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                               chat_id: Optional[int], message_id: Optional[int]):
    selected_date_str = call.data[len(const.CB_DATEB_SELECT_DATE):]
    logger.debug(f"Пользователь {user_id} запросил бронирования по дате: {selected_date_str}")
    # Убираем parse_mode из kwargs_edit, так как он будет установлен явно при вызове
    kwargs_edit = {'reply_markup': None, 'user_id_for_state_update': user_id}
    try:
        date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
        try:
            bot.answer_callback_query(call.id, f"Загружаю бронирования на {selected_date_str}...")
        except apihelper.ApiTelegramException:
            pass

        # --- ИЗМЕНЕНИЕ ЗДЕСЬ ---
        # Вместо bookingService.get_bookings_by_date_text(db, date_obj)
        # вызываем новую функцию, которая возвращает HTML
        # Предположим, она называется get_bookings_by_date_text_html и находится в bookingService
        html_response_text = bookingService.get_bookings_by_date_text_html(db, date_obj)

        if chat_id:
            # Устанавливаем parse_mode="HTML"
            _edit_or_send_message(bot, chat_id, message_id, html_response_text, parse_mode="HTML", **kwargs_edit)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    except ValueError:
        logger.warning(f"Неверный формат даты '{selected_date_str}' от пользователя {user_id}")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный формат даты.",
                                          **kwargs_edit)  # parse_mode не нужен для простого текста
        try:
            bot.answer_callback_query(call.id, "Неверный формат даты.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
    except Exception as e:
        logger.error(f"Ошибка при получении бронирований по дате '{selected_date_str}' для user {user_id}: {e}",
                     exc_info=True)
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL,
                                          **kwargs_edit)  # parse_mode не нужен
        try:
            bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
        except apihelper.ApiTelegramException:
            pass


def handle_wsb_category_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                               chat_id: Optional[int], message_id: Optional[int]):
    try:
        category_id = int(call.data[len(const.CB_WSPB_SELECT_CATEGORY):])
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID категории из callback '{call.data}' для /workspacebookings")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID категории.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.debug(f"Пользователь {user_id} выбрал категорию ID {category_id} для просмотра броней по рабочим местам.")
    try:
        bot.answer_callback_query(call.id)
    except apihelper.ApiTelegramException:
        pass

    kwargs_edit = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    equipment_list = equipmentService.get_equipment_by_category(db, category_id)
    category_info = equipmentService.get_category_by_id(db, category_id)
    category_name = category_info.get('name_cat', f'ID {category_id}') if category_info else f'ID {category_id}'

    if not equipment_list:
        msg_text = const.MSG_NO_EQUIPMENT_IN_CATEGORY.format(category_name=category_name)
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg_text, reply_markup=None, **kwargs_edit)
        return

    markup = keyboards.generate_equipment_keyboard(equipment_list, const.CB_WSPB_SELECT_EQUIPMENT)
    prompt_text = const.MSG_BOOKING_STEP_2_EQUIPMENT.format(category_name=category_name)

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, prompt_text, reply_markup=markup, **kwargs_edit)


def handle_wsb_equipment_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                                chat_id: Optional[int], message_id: Optional[int]):
    try:
        equipment_id = int(call.data[len(const.CB_WSPB_SELECT_EQUIPMENT):])
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID оборудования из callback '{call.data}' для /workspacebookings")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID оборудования.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.debug(f"Пользователь {user_id} выбрал оборудование ID {equipment_id} для просмотра его броней.")
    try:
        bot.answer_callback_query(call.id, "Загружаю информацию о бронированиях...")
    except apihelper.ApiTelegramException:
        pass

    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    equipment_name = equipmentService.get_equipment_name_by_id(db, equipment_id)
    if not equipment_name:
        logger.warning(f"Оборудование с ID {equipment_id} не найдено при просмотре броней по рабочим местам.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: оборудование не найдено.", **kwargs_edit)
        return

    text_response = bookingService.get_bookings_by_workspace_text(db, equipment_id, equipment_name)
    if chat_id: _edit_or_send_message(bot, chat_id, message_id, text_response, **kwargs_edit)


def handle_filter_type_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                              chat_id: Optional[int], message_id: Optional[int]):
    filter_type = call.data[len(const.CB_FILTER_BY_TYPE):]
    logger.debug(f"Админ {user_id} выбрал тип фильтра '{filter_type}' для отчета /all.")
    try:
        bot.answer_callback_query(call.id)
    except apihelper.ApiTelegramException:
        pass

    options_list: List[Tuple[str, Any]] = []
    callback_prefix = ""
    prompt_message = ""
    kwargs_edit = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    try:
        if filter_type == "users":
            users_data = userService.get_all_users(db, include_inactive=True)
            options_list = [(user.get('fi', f"ID {user.get('users_id')}"), user.get('users_id'))
                            for user in users_data if user.get('users_id') is not None]
            options_list.sort(key=lambda x: x[0])
            callback_prefix = const.CB_FILTER_SELECT_USER
            prompt_message = "Выберите пользователя для фильтрации отчета:"
        elif filter_type == "equipment":
            equipment_data = equipmentService.get_all_equipment(db)
            options_list = [(eq.get('name_equip', f"ID {eq.get('id')}"), eq.get('id'))
                            for eq in equipment_data if eq.get('id') is not None]
            options_list.sort(key=lambda x: x[0])
            callback_prefix = const.CB_FILTER_SELECT_EQUIPMENT
            prompt_message = "Выберите оборудование для фильтрации отчета:"
        elif filter_type == "category":  # Добавил фильтр по категории
            category_data = equipmentService.get_all_categories(db)
            options_list = [(cat.get('name_cat', f"ID {cat.get('id')}"), cat.get('id'))
                            for cat in category_data if cat.get('id') is not None]
            options_list.sort(key=lambda x: x[0])
            callback_prefix = const.CB_FILTER_SELECT_CATEGORY
            prompt_message = "Выберите категорию для фильтрации отчета:"
        elif filter_type == "dates":
            query = "SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month_year FROM bookings WHERE date IS NOT NULL ORDER BY month_year DESC;"
            months_result_raw: Optional[QueryResult] = db.execute_query(query, fetch_results=True)
            if months_result_raw:
                options_list = [(m['month_year'], m['month_year']) if isinstance(m, dict) else (str(m[0]), str(m[0]))
                                for m in months_result_raw]
            callback_prefix = const.CB_FILTER_SELECT_DATE
            prompt_message = "Выберите месяц (ГГГГ-ММ) для фильтрации отчета:"
        else:
            logger.warning(f"Неизвестный тип фильтра '{filter_type}' от админа {user_id}.")
            return

        if not options_list:
            msg_no_data = "Нет данных для выбранного типа фильтра."
            if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg_no_data, reply_markup=None, **kwargs_edit)
        else:
            markup = keyboards.generate_filter_selection_keyboard(options_list, callback_prefix)
            if chat_id: _edit_or_send_message(bot, chat_id, message_id, prompt_message, reply_markup=markup,
                                              **kwargs_edit)

    except Exception as e:
        logger.error(f"Ошибка при генерации опций фильтра '{filter_type}' для админа {user_id}: {e}", exc_info=True)
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, const.MSG_ERROR_GENERAL, reply_markup=None,
                                          **kwargs_edit)


def handle_filter_value_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                               chat_id: Optional[int], message_id: Optional[int]):
    filter_type_detected = ""
    filter_value_str = ""
    filter_value_int: Optional[int] = None
    filter_details_for_caption = "неизвестный фильтр"
    report_file_path: Optional[str] = None

    kwargs_edit = {'reply_markup': None, 'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    try:
        if call.data.startswith(const.CB_FILTER_SELECT_USER):
            filter_type_detected = "users"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_USER):]
            filter_value_int = int(filter_value_str)
            user_info_dict = userService.get_user_info(db, filter_value_int)
            filter_details_for_caption = f"пользователю: {user_info_dict.get('fi', f'ID {filter_value_int}')}" if user_info_dict else f'пользователю с ID {filter_value_int}'

        elif call.data.startswith(const.CB_FILTER_SELECT_EQUIPMENT):
            filter_type_detected = "equipment"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_EQUIPMENT):]
            filter_value_int = int(filter_value_str)
            equip_name_val = equipmentService.get_equipment_name_by_id(db, filter_value_int)
            filter_details_for_caption = f"оборудованию: {equip_name_val or f'ID {filter_value_int}'}"

        elif call.data.startswith(const.CB_FILTER_SELECT_CATEGORY):
            filter_type_detected = "category"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_CATEGORY):]
            filter_value_int = int(filter_value_str)
            category_info_dict = equipmentService.get_category_by_id(db, filter_value_int)
            filter_details_for_caption = f"категории: {category_info_dict.get('name_cat', f'ID {filter_value_int}')}" if category_info_dict else f'категории с ID {filter_value_int}'

        elif call.data.startswith(const.CB_FILTER_SELECT_DATE):
            filter_type_detected = "dates"
            filter_value_str = call.data[len(const.CB_FILTER_SELECT_DATE):]
            datetime.strptime(filter_value_str, '%Y-%m')
            filter_details_for_caption = f"месяцу: {filter_value_str}"
        else:
            logger.error(f"Неизвестный префикс значения фильтра в callback: '{call.data}'")
            if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неизвестный тип фильтра.",
                                              **kwargs_edit)
            return

    except (ValueError, TypeError, IndexError) as e_parse_val:
        logger.error(f"Ошибка парсинга значения фильтра из callback '{call.data}': {e_parse_val}", exc_info=True)
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверное значение для фильтра.",
                                          **kwargs_edit)
        return

    logger.info(f"Админ {user_id} запросил генерацию отчета /all по {filter_type_detected} = '{filter_value_str}'")
    try:
        bot.answer_callback_query(call.id, "Формирую отчет...")
    except apihelper.ApiTelegramException:
        pass

    if chat_id: _edit_or_send_message(bot, chat_id, message_id,
                                      f"⏳ Пожалуйста, подождите, формирую отчет по {filter_details_for_caption}...",
                                      **kwargs_edit)

    try:
        filter_value_for_service: Any = filter_value_int if filter_value_int is not None else filter_value_str

        bookings_list_data: List[Dict[str, Any]] = adminService.get_filtered_bookings(db, filter_type_detected,
                                                                                      filter_value_for_service)

        if not bookings_list_data:
            logger.info(f"Нет данных для отчета по {filter_details_for_caption}.")
            if chat_id: _edit_or_send_message(bot, chat_id, message_id,
                                              f"По {filter_details_for_caption} нет данных о бронированиях.",
                                              **kwargs_edit)
            return

        report_file_path = adminService.create_bookings_report_file(bookings_list_data,
                                                                    filter_details=filter_details_for_caption)

        if report_file_path and os.path.exists(report_file_path):
            try:
                with open(report_file_path, 'rb') as report_file:
                    if chat_id: bot.send_document(chat_id, report_file,
                                                  caption=f"Отчет по {filter_details_for_caption}")
                logger.info(f"Файл отчета {os.path.basename(report_file_path)} успешно отправлен админу {user_id}")
                if message_id and chat_id:
                    try:
                        bot.delete_message(chat_id, message_id)
                    except apihelper.ApiTelegramException:
                        pass
            except Exception as e_send_doc:
                logger.error(f"Ошибка при отправке файла отчета {report_file_path} админу {user_id}: {e_send_doc}",
                             exc_info=True)
                if chat_id: _edit_or_send_message(bot, chat_id, message_id, "❌ Ошибка при отправке файла отчета.",
                                                  **kwargs_edit)
        else:
            logger.error(
                f"Файл отчета не был создан или не найден для {filter_details_for_caption}. Path: {report_file_path}")
            if chat_id: _edit_or_send_message(bot, chat_id, message_id, "❌ Ошибка при создании файла отчета.",
                                              **kwargs_edit)

    except Exception as e_generate_report:
        logger.critical(
            f"Критическая ошибка при генерации отчета /all ({filter_type_detected}='{filter_value_str}'): {e_generate_report}",
            exc_info=True)
        if chat_id: _edit_or_send_message(bot, chat_id, message_id,
                                          "❌ Произошла критическая ошибка при формировании отчета.", **kwargs_edit)
    finally:
        if report_file_path and os.path.exists(report_file_path):
            try:
                os.remove(report_file_path)
                logger.debug(f"Временный файл отчета {report_file_path} удален.")
            except OSError as e_remove_file:
                logger.error(f"Ошибка при удалении временного файла отчета {report_file_path}: {e_remove_file}")


def handle_equip_delete_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                               chat_id: Optional[int], message_id: Optional[int]):
    try:
        equipment_id = int(call.data[len(const.CB_ADMIN_MANAGE_EQUIP_SELECT_EQUIP):])
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID оборудования из callback '{call.data}' для удаления.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID оборудования.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} выбрал оборудование ID {equipment_id} для возможного удаления.")
    try:
        bot.answer_callback_query(call.id)
    except apihelper.ApiTelegramException:
        pass

    kwargs_edit = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    equip_info = equipmentService.get_equipment_info_by_id(db, equipment_id)
    if not equip_info:
        logger.warning(f"Оборудование ID {equipment_id} не найдено при попытке удаления админом {user_id}.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, const.MSG_ADMIN_EQUIP_DELETE_FAIL_NOT_FOUND,
                                          reply_markup=None, **kwargs_edit)
        return

    equip_name = equip_info.get('name_equip', f'ID {equipment_id}')
    category_id = equip_info.get('category')
    category_name = "N/A"
    if category_id:
        cat_info = equipmentService.get_category_by_id(db, category_id)
        if cat_info: category_name = cat_info.get('name_cat', f'ID {category_id}')

    if equipmentService.check_equipment_usage(db, equipment_id):
        error_message = const.MSG_ADMIN_EQUIP_DELETE_FAIL_HAS_HISTORY.format(name_equip=equip_name)
        logger.info(
            f"Попытка удаления используемого оборудования '{equip_name}' (ID {equipment_id}) админом {user_id}.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, error_message, reply_markup=None, **kwargs_edit)
        return

    confirm_text = const.MSG_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE.format(equip_name=equip_name,
                                                                      category_name=category_name)
    markup = keyboards.generate_confirmation_keyboard(
        confirm_callback=f"{const.CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE}{equipment_id}",
        cancel_callback=f"{const.CB_ACTION_CANCEL}delete_equip_process_{equipment_id}",
        confirm_text="✅ Да, удалить",
        cancel_text="❌ Нет, отмена"
    )

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, confirm_text, reply_markup=markup, **kwargs_edit)


def handle_equip_delete_confirm(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                                chat_id: Optional[int], message_id: Optional[int]):
    try:
        equipment_id = int(call.data[len(const.CB_ADMIN_MANAGE_EQUIP_CONFIRM_DELETE):])
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID оборудования из callback '{call.data}' для подтверждения удаления.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID оборудования.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} подтвердил удаление оборудования ID {equipment_id}.")
    try:
        bot.answer_callback_query(call.id, "Удаляю оборудование...")
    except apihelper.ApiTelegramException:
        pass

    success, message_to_admin = equipmentService.delete_equipment_if_unused(db, equipment_id)
    kwargs_edit_confirm = {'reply_markup': None, 'user_id_for_state_update': user_id, 'parse_mode': 'Markdown'}

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, message_to_admin, **kwargs_edit_confirm)


def handle_manage_user_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                              chat_id: Optional[int], message_id: Optional[int]):
    try:
        target_user_id = int(call.data[len(const.CB_MANAGE_USER_SELECT):])
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID пользователя из callback '{call.data}' для управления.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID пользователя.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.debug(f"Админ {user_id} выбрал пользователя ID {target_user_id} для управления.")
    try:
        bot.answer_callback_query(call.id)
    except apihelper.ApiTelegramException:
        pass

    kwargs_edit = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    user_details = userService.get_user_details_for_management(db, target_user_id)

    if not user_details:
        logger.warning(f"Пользователь ID {target_user_id} не найден для управления админом {user_id}.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Пользователь не найден.", reply_markup=None,
                                          **kwargs_edit)
        return

    user_name, is_blocked, is_target_admin = user_details
    status_text = "🔴 Заблокирован" if is_blocked else "🟢 Активен"
    admin_status_text = "👑 Админ" if is_target_admin else "👤 Пользователь"

    markup = keyboards.generate_user_status_keyboard(target_user_id, is_blocked, is_target_admin)
    message_text_to_send = (
        f"Пользователь: *{user_name}* (ID: `{target_user_id}`)\n"
        f"Статус: {status_text}\n"
        f"Роль: {admin_status_text}\n\n"
        "Выберите действие:"
    )

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, message_text_to_send, reply_markup=markup,
                                      **kwargs_edit)


def handle_manage_user_action(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                              chat_id: Optional[int], message_id: Optional[int]):
    action_type = ""
    target_user_id_str = ""

    if call.data.startswith(const.CB_MANAGE_USER_ACTION_BLOCK):
        action_type = "block"
        target_user_id_str = call.data[len(const.CB_MANAGE_USER_ACTION_BLOCK):]
    elif call.data.startswith(const.CB_MANAGE_USER_ACTION_UNBLOCK):
        action_type = "unblock"
        target_user_id_str = call.data[len(const.CB_MANAGE_USER_ACTION_UNBLOCK):]
    elif call.data.startswith(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN):
        action_type = "make_admin"
        target_user_id_str = call.data[len(const.CB_MANAGE_USER_ACTION_MAKE_ADMIN):]
    elif call.data.startswith(const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN):
        action_type = "remove_admin"
        target_user_id_str = call.data[len(const.CB_MANAGE_USER_ACTION_REMOVE_ADMIN):]
    else:
        logger.error(f"Неизвестный action_type в callback '{call.data}' для управления пользователем.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неизвестное действие.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Неизвестное действие.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    try:
        target_user_id = int(target_user_id_str)
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID пользователя из callback '{call.data}' для действия '{action_type}'.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID пользователя.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} выполняет действие '{action_type}' для пользователя ID {target_user_id}.")
    action_in_progress_msg = "Выполняю действие..."
    if action_type == "block":
        action_in_progress_msg = "Блокирую пользователя..."
    elif action_type == "unblock":
        action_in_progress_msg = "Разблокирую пользователя..."
    elif action_type == "make_admin":
        action_in_progress_msg = "Назначаю администратором..."
    elif action_type == "remove_admin":
        action_in_progress_msg = "Снимаю права администратора..."

    try:
        bot.answer_callback_query(call.id, action_in_progress_msg)
    except apihelper.ApiTelegramException:
        pass

    success = False
    result_message_key = const.MSG_ERROR_GENERAL

    if action_type == "block":
        success = userService.update_user_block_status(db, target_user_id, block=True)
        result_message_key = const.MSG_USER_BLOCKED if success else "Ошибка блокировки."
    elif action_type == "unblock":
        success = userService.update_user_block_status(db, target_user_id, block=False)
        result_message_key = const.MSG_USER_UNBLOCKED if success else "Ошибка разблокировки."
    elif action_type == "make_admin":
        success = userService.update_user_admin_status(db, target_user_id, make_admin=True)
        result_message_key = const.MSG_USER_MADE_ADMIN if success else "Ошибка назначения админом."
    elif action_type == "remove_admin":
        success = userService.update_user_admin_status(db, target_user_id, make_admin=False)
        result_message_key = const.MSG_USER_REMOVED_ADMIN if success else "Ошибка снятия прав админа."

    user_details_after_action = userService.get_user_details_for_management(db, target_user_id)
    kwargs_edit_action = {'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    if user_details_after_action:
        user_name_after, is_blocked_after, is_admin_after = user_details_after_action
        status_text_after = "🔴 Заблокирован" if is_blocked_after else "🟢 Активен"
        admin_status_text_after = "👑 Админ" if is_admin_after else "👤 Пользователь"

        action_result_indicator = "✅" if success else "❌"

        text_to_send = (
            f"Пользователь: *{user_name_after}* (ID: `{target_user_id}`)\n"
            f"Статус: {status_text_after}\n"
            f"Роль: {admin_status_text_after}\n"
            f"({action_result_indicator} {result_message_key})\n\n"
            "Выберите следующее действие:"
        )
        markup_after = keyboards.generate_user_status_keyboard(target_user_id, is_blocked_after, is_admin_after)
        kwargs_edit_action['reply_markup'] = markup_after
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, text_to_send, **kwargs_edit_action)
    else:
        logger.error(
            f"Не удалось получить информацию о пользователе ID {target_user_id} после выполнения действия '{action_type}'.")
        error_msg_after = f"❌ Ошибка при обновлении статуса пользователя. {result_message_key}"
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, error_msg_after, reply_markup=None,
                                          **kwargs_edit_action)


def handle_admin_cancel_select(bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int,
                               chat_id: Optional[int], message_id: Optional[int], booking_id: int):
    logger.info(f"Админ {user_id} выбрал бронь ID {booking_id} для возможной отмены.")
    try:
        bot.answer_callback_query(call.id)
    except apihelper.ApiTelegramException:
        pass

    kwargs_edit = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}

    booking_details = bookingService.find_booking_by_id(db, booking_id)

    if not booking_details:
        logger.warning(f"Бронь ID {booking_id} не найдена при попытке отмены админом {user_id}.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: бронь не найдена.", reply_markup=None,
                                          **kwargs_edit)
        return

    is_already_cancelled = booking_details.get('cancel', False)
    is_already_finished = booking_details.get('finish') is not None

    equip_name_confirm = booking_details.get('equipment_name', f'Оборудование ID {booking_details.get("equip_id")}')
    user_fi_confirm = booking_details.get('user_fi', f'Пользователь ID {booking_details.get("user_id")}')
    booking_date_confirm = booking_details.get('date')
    time_start_confirm = booking_details.get('time_start')
    time_end_confirm = booking_details.get('time_end')

    date_str_confirm = bookingService._format_date(booking_date_confirm) if booking_date_confirm else "??.??.???"
    start_str_confirm = bookingService._format_time(time_start_confirm) if time_start_confirm else "??:??"
    end_str_confirm = bookingService._format_time(time_end_confirm) if time_end_confirm else "??:??"

    if is_already_cancelled:
        msg_edit_text = f"Бронь ID `{booking_id}` ({equip_name_confirm}) уже была отменена."
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg_edit_text, reply_markup=None, **kwargs_edit)
        return
    elif is_already_finished:
        msg_edit_text = f"Бронь ID `{booking_id}` ({equip_name_confirm}) уже была завершена."
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, msg_edit_text, reply_markup=None, **kwargs_edit)
        return

    confirmation_prompt_text = (
        f"Вы уверены, что хотите отменить бронирование ID `{booking_id}`?\n\n"
        f"👤 Пользователь: *{user_fi_confirm}*\n"
        f"🔬 Оборудование: *{equip_name_confirm}*\n"
        f"🗓️ Дата: {date_str_confirm}\n"
        f"⏰ Время: {start_str_confirm} - {end_str_confirm}\n\n"
        "Это действие необратимо."
    )
    markup_confirm = keyboards.generate_confirmation_keyboard(
        confirm_callback=f"{const.CB_ADMIN_CANCEL_CONFIRM}{booking_id}",
        cancel_callback=f"{const.CB_ACTION_CANCEL}admin_cancel_process_{booking_id}",
        confirm_text="✅ Да, отменить",
        cancel_text="❌ Нет, оставить"
    )

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, confirmation_prompt_text, reply_markup=markup_confirm,
                                      **kwargs_edit)


def handle_admin_cancel_confirm(
        bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: Optional[int],
        message_id: Optional[int],
        booking_id: int, scheduler: Optional[BackgroundScheduler],
        scheduled_jobs_registry: Optional[Set[Tuple[str, int]]]
):
    try:
        booking_id_to_cancel = int(call.data[len(const.CB_ADMIN_CANCEL_CONFIRM):])  # Перепроверка ID из call.data
        if booking_id != booking_id_to_cancel:  # Доп. проверка, что ID совпадает с переданным
            logger.error(f"Несовпадение ID брони: из параметра {booking_id}, из call.data {booking_id_to_cancel}")
            # Обработать ошибку
            return
    except (ValueError, TypeError):
        logger.error(f"Ошибка извлечения ID брони из callback '{call.data}' для подтверждения админской отмены.")
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, "Ошибка: неверный ID брони.",
                                          user_id_for_state_update=user_id)
        try:
            bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        return

    logger.info(f"Админ {user_id} подтвердил отмену брони ID {booking_id_to_cancel}.")
    try:
        bot.answer_callback_query(call.id, "Отменяю бронирование...")
    except apihelper.ApiTelegramException:
        pass

    kwargs_edit_result = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    success, message_to_admin, owner_of_booking_id = bookingService.cancel_booking(
        db, booking_id_to_cancel, user_id=user_id, is_admin_cancel=True
    )

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, message_to_admin, **kwargs_edit_result)

    if success:
        if scheduler and scheduled_jobs_registry is not None:
            logger.debug(f"Бронь {booking_id_to_cancel} отменена админом, очищаю связанные задачи планировщика.")
            notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)

        if owner_of_booking_id:
            try:
                booking_details_for_notify = bookingService.find_booking_by_id(db, booking_id_to_cancel)
                if booking_details_for_notify:
                    equip_name_notify = booking_details_for_notify.get('equipment_name', 'Неизвестное оборудование')
                    booking_date_notify = booking_details_for_notify.get('date')
                    time_start_notify = booking_details_for_notify.get('time_start')

                    date_str_notify = bookingService._format_date(
                        booking_date_notify) if booking_date_notify else "??.??.???"
                    start_str_notify = bookingService._format_time(time_start_notify) if time_start_notify else "??:??"

                    notification_text_to_user = (
                        f"❗️ Ваше бронирование оборудования '*{equip_name_notify}*' "
                        f"на *{date_str_notify} {start_str_notify}* было отменено администратором."
                    )
                    bot.send_message(owner_of_booking_id, notification_text_to_user, parse_mode="Markdown")
                    logger.info(
                        f"Уведомление об админской отмене отправлено пользователю {owner_of_booking_id} для брони {booking_id_to_cancel}.")
            except apihelper.ApiTelegramException as e_notify_user:
                logger.error(
                    f"Не удалось отправить уведомление об админской отмене пользователю {owner_of_booking_id}: {e_notify_user}")
            except Exception as e_notify_other_user:
                logger.error(
                    f"Другая ошибка при отправке уведомления об админской отмене пользователю {owner_of_booking_id}: {e_notify_other_user}",
                    exc_info=True)


def handle_extend_select_booking(
        bot: telebot.TeleBot,
        db: Database,
        call: types.CallbackQuery,
        user_id: int,
        chat_id: Optional[int],
        message_id: Optional[int],
        booking_id: int,
        is_fake_call: bool,
        source: str
):
    logger.info(
        f"Обработка выбора брони {booking_id} для продления (user: {user_id}, is_fake: {is_fake_call}, source: {source})")

    if not is_fake_call:
        try:
            bot.answer_callback_query(call.id, "Проверяю варианты продления...")
        except apihelper.ApiTelegramException as e:
            if "query is too old" in str(e).lower() or "query id is invalid" in str(e).lower():
                logger.warning(
                    f"Не удалось ответить на реальный callback {call.id} (слишком старый или невалидный): {e}")
            else:
                logger.error(f"Ошибка API при ответе на callback {call.id}: {e}", exc_info=True)
                if chat_id: bot.send_message(chat_id, const.MSG_ERROR_GENERAL)
                return
        except Exception as e_ans:
            logger.error(f"Непредвиденная ошибка при ответе на callback {call.id}: {e_ans}", exc_info=True)
            if chat_id: bot.send_message(chat_id, const.MSG_ERROR_GENERAL)
            return

    kwargs_edit = {'user_id_for_state_update': user_id, 'parse_mode': "Markdown"}
    target_message_id_for_edit = message_id
    if is_fake_call and call.message:
        target_message_id_for_edit = call.message.message_id

    if not chat_id:
        logger.error(f"chat_id не определен для user {user_id} при продлении брони {booking_id}.")
        return

    booking_info: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)

    owner_id = booking_info.get('user_id') if booking_info else None
    is_cancelled = booking_info.get('cancel', True) if booking_info else True
    is_finished = booking_info.get('finish') is not None if booking_info else True
    equip_id = booking_info.get('equip_id') if booking_info else None
    current_end_time_dt = booking_info.get('time_end') if booking_info else None

    error_message_text = None
    alert_message_text = None

    if not booking_info:
        error_message_text = const.MSG_EXTEND_FAIL_NOT_FOUND
        alert_message_text = "Бронь не найдена."
    elif owner_id != user_id:
        error_message_text = const.MSG_EXTEND_FAIL_NOT_YOURS
        alert_message_text = "Это не ваша бронь."
    elif is_cancelled:
        error_message_text = const.MSG_BOOKING_ALREADY_CANCELLED
        alert_message_text = "Бронь отменена."
    elif is_finished:
        error_message_text = const.MSG_BOOKING_ALREADY_FINISHED
        alert_message_text = "Бронь завершена."
    elif not isinstance(current_end_time_dt, datetime) or equip_id is None:
        error_message_text = const.MSG_ERROR_GENERAL
        alert_message_text = "Ошибка данных брони."
        logger.error(
            f"Некорректные данные для продления брони ID {booking_id}: current_end_time тип {type(current_end_time_dt)}, equip_id {equip_id}")
    elif current_end_time_dt.replace(tzinfo=None) <= datetime.now().replace(tzinfo=None):
        error_message_text = const.MSG_EXTEND_FAIL_ALREADY_ENDED
        alert_message_text = "Время брони уже истекло."
        logger.warning(
            f"Пользователь {user_id} пытается продлить уже завершившуюся по времени бронь ID {booking_id} (источник: {source}).")

    if error_message_text:
        if not is_fake_call and alert_message_text:
            try:
                bot.answer_callback_query(call.id, alert_message_text, show_alert=True)
            except apihelper.ApiTelegramException:
                pass

        _edit_or_send_message(bot, chat_id, target_message_id_for_edit, error_message_text, reply_markup=None,
                              **kwargs_edit)
        return

    current_end_naive = current_end_time_dt.replace(tzinfo=None)
    next_booking_info: Optional[Dict[str, Any]] = bookingService.find_next_booking(db, equip_id, current_end_naive)

    available_until_datetime_naive: datetime
    if next_booking_info and next_booking_info.get('time_start'):
        available_until_datetime_naive = next_booking_info['time_start'].replace(tzinfo=None)
    else:
        available_until_datetime_naive = datetime.combine(current_end_naive.date(), const.WORKING_HOURS_END)

    possible_extension_duration = timedelta(0)
    if available_until_datetime_naive > current_end_naive:
        max_possible_delta = available_until_datetime_naive - current_end_naive
        allowed_extension_minutes = (
                                                int(max_possible_delta.total_seconds() // 60) // const.BOOKING_TIME_STEP_MINUTES) * const.BOOKING_TIME_STEP_MINUTES
        if allowed_extension_minutes > 0:
            possible_extension_duration = timedelta(minutes=allowed_extension_minutes)

    logger.debug(
        f"Максимальное возможное продление для брони ID {booking_id} (источник: {source}): {possible_extension_duration} "
        f"(текущее окончание: {current_end_naive.strftime('%H:%M')}, доступно до: {available_until_datetime_naive.strftime('%H:%M')})")

    if possible_extension_duration > timedelta(0):
        extend_time_markup = keyboards.generate_extend_time_keyboard(booking_id,
                                                                     max_duration=possible_extension_duration)
        _edit_or_send_message(bot, chat_id, target_message_id_for_edit,
                              "На какое время вы хотите продлить бронирование?", reply_markup=extend_time_markup,
                              **kwargs_edit)
    else:
        _edit_or_send_message(bot, chat_id, target_message_id_for_edit, const.MSG_EXTEND_FAIL_NO_TIME,
                              reply_markup=None, **kwargs_edit)


def handle_extend_select_time(
        bot: telebot.TeleBot, db: Database, call: CallbackQuery, user_id: int, chat_id: Optional[int],
        message_id: Optional[int],
        booking_id: int, extension_str: str, scheduler: Optional[BackgroundScheduler],
        active_timers: Optional[Dict[int, Any]], scheduled_jobs_registry: Optional[Set[Tuple[str, int]]]
):
    kwargs_edit = {'reply_markup': None, 'parse_mode': "Markdown", 'user_id_for_state_update': user_id}

    booking_info_check: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)
    owner_id_check = booking_info_check.get('user_id') if booking_info_check else None
    is_cancelled_check = booking_info_check.get('cancel', True) if booking_info_check else True
    is_finished_check = booking_info_check.get('finish') is not None if booking_info_check else True
    current_end_time_check = booking_info_check.get('time_end') if booking_info_check else None

    error_message_check = None
    alert_message_check = None

    if not booking_info_check:
        error_message_check, alert_message_check = const.MSG_EXTEND_FAIL_NOT_FOUND, "Бронь не найдена."
    elif owner_id_check != user_id:
        error_message_check, alert_message_check = const.MSG_EXTEND_FAIL_NOT_YOURS, "Это не ваша бронь."
    elif is_cancelled_check:
        error_message_check, alert_message_check = const.MSG_BOOKING_ALREADY_CANCELLED, "Бронь отменена."
    elif is_finished_check:
        error_message_check, alert_message_check = const.MSG_BOOKING_ALREADY_FINISHED, "Бронь завершена."
    elif not isinstance(current_end_time_check, datetime):
        error_message_check, alert_message_check = const.MSG_ERROR_GENERAL, "Ошибка данных."
        logger.error(
            f"Ошибка данных (время окончания) для брони {booking_id} при попытке продления на {extension_str}.")
    elif current_end_time_check.replace(tzinfo=None) <= datetime.now().replace(tzinfo=None):
        error_message_check, alert_message_check = const.MSG_EXTEND_FAIL_ALREADY_ENDED, "Время брони истекло."

    if error_message_check:
        try:
            bot.answer_callback_query(call.id, alert_message_check, show_alert=True)
        except apihelper.ApiTelegramException:
            pass
        if chat_id: _edit_or_send_message(bot, chat_id, message_id, error_message_check, **kwargs_edit)
        return

    try:
        bot.answer_callback_query(call.id, "Продлеваю бронирование...")
    except apihelper.ApiTelegramException:
        pass

    success, message_to_user = bookingService.extend_booking(db, booking_id, user_id, extension_str)

    if chat_id: _edit_or_send_message(bot, chat_id, message_id, message_to_user, **kwargs_edit)

    if success:
        if scheduler and active_timers is not None and scheduled_jobs_registry is not None:
            logger.debug(f"Бронь ID {booking_id} успешно продлена, обновляю расписание уведомлений.")
            notificationService.schedule_all_notifications(db, bot, scheduler, active_timers, scheduled_jobs_registry)


def handle_cancel_delete_equip(bot: telebot.TeleBot, db: Database, chat_id: Optional[int], message_id: Optional[int],
                               **kwargs_edit_ignored):
    # kwargs_edit_ignored не используется, т.к. мы отправляем новые сообщения
    logger.debug(f"Отмена процесса удаления оборудования. Исходное сообщение для удаления (если есть): {message_id}")
    admin_reply_markup = keyboards.create_admin_reply_keyboard()
    user_id = kwargs_edit_ignored.get('user_id_for_state_update')  # Если передавалось

    if chat_id and message_id:
        try:
            bot.delete_message(chat_id, message_id)
            logger.info(f"Сообщение {message_id} (подтверждение удаления) удалено в чате {chat_id}.")
        except apihelper.ApiTelegramException as e_del:
            logger.warning(
                f"Не удалось удалить сообщение {message_id} в чате {chat_id} при отмене удаления оборудования: {e_del}")

    all_equipment = equipmentService.get_all_equipment(db)
    if chat_id:
        if all_equipment:
            # Нужна функция для генерации списка оборудования для управления (например, с кнопками "Удалить")
            # или просто текстовый список. Покажем кнопки выбора категории, т.к. это начало процесса.
            categories = equipmentService.get_all_categories(db)
            if categories:
                markup_cats = keyboards.generate_equipment_category_keyboard(categories,
                                                                             const.CB_ADMIN_MANAGE_EQUIP_SELECT_CAT)
                bot.send_message(chat_id, "Удаление отменено. Выберите категорию для управления оборудованием:",
                                 reply_markup=markup_cats)
            else:
                bot.send_message(chat_id, "Удаление отменено. Нет категорий для управления.",
                                 reply_markup=admin_reply_markup)
        else:
            bot.send_message(chat_id, "Удаление отменено. В системе нет оборудования.", reply_markup=admin_reply_markup)


def handle_cancel_admin_cancel(bot: telebot.TeleBot, db: Database, chat_id: Optional[int], message_id: Optional[int],
                               **kwargs_edit_ignored):
    logger.debug(f"Отмена процесса админской отмены брони. Исходное сообщение для удаления (если есть): {message_id}")
    admin_reply_markup = keyboards.create_admin_reply_keyboard()
    user_id = kwargs_edit_ignored.get('user_id_for_state_update')

    if chat_id and message_id:
        try:
            bot.delete_message(chat_id, message_id)
            logger.info(f"Сообщение {message_id} (подтверждение админской отмены) удалено в чате {chat_id}.")
        except apihelper.ApiTelegramException as e_del:
            logger.warning(
                f"Не удалось удалить сообщение {message_id} в чате {chat_id} при отмене админской отмены: {e_del}")

    active_bookings = bookingService.get_all_active_bookings_for_admin_keyboard(db)
    if chat_id:
        if active_bookings:
            markup_bookings = keyboards.generate_admin_cancel_keyboard(active_bookings)
            bot.send_message(chat_id, "Действие отменено. Выберите бронь для принудительной отмены:",
                             reply_markup=markup_bookings)
        else:
            bot.send_message(chat_id, "Действие отменено. Нет активных броней для отмены.",
                             reply_markup=admin_reply_markup)


def handle_cancel_manage_user(bot: telebot.TeleBot, db: Database, chat_id: Optional[int], message_id: Optional[int],
                              **kwargs_edit_ignored):
    logger.debug(f"Отмена процесса управления пользователем. Исходное сообщение для удаления (если есть): {message_id}")
    admin_reply_markup = keyboards.create_admin_reply_keyboard()
    user_id = kwargs_edit_ignored.get('user_id_for_state_update')

    if chat_id and message_id:
        try:
            bot.delete_message(chat_id, message_id)
            logger.info(f"Сообщение {message_id} (управление пользователем) удалено в чате {chat_id}.")
        except apihelper.ApiTelegramException as e_del:
            logger.warning(
                f"Не удалось удалить сообщение {message_id} в чате {chat_id} при отмене управления пользователем: {e_del}")

    users_list_data = userService.get_all_users(db, include_inactive=True)
    if chat_id:
        if users_list_data:
            markup_users = keyboards.generate_user_management_keyboard(users_list_data)
            bot.send_message(chat_id, "Действие отменено. Выберите пользователя для управления:",
                             reply_markup=markup_users)
        else:
            bot.send_message(chat_id, "Действие отменено. Нет зарегистрированных пользователей.",
                             reply_markup=admin_reply_markup)