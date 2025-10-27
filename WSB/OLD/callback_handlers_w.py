# handlers/callback_handlers.py
import telebot
from telebot.types import CallbackQuery
from database import Database, QueryResult # QueryResult может быть полезен
from logger import logger
# import config # Не используется напрямую
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
from typing import Dict, Any, Set, Tuple, Optional # Добавили Optional
import logging # Добавили logging для ApiTelegramException

# --- Регистрация обработчиков ---
def register_callback_handlers(
    bot: telebot.TeleBot,
    db: Database,
    scheduler: Optional[BackgroundScheduler], # Scheduler может быть None при вызове
    active_timers: Dict[int, Any],
    scheduled_jobs_registry: Set[Tuple[str, int]]
    ):
    """Регистрирует обработчики для всех inline кнопок."""

    # Внутренняя функция проверки прав админа
    def _is_admin_user(user_id: int) -> bool:
        try:
            is_admin = userService.is_admin(db, user_id)
            if not is_admin:
                logger.warning(f"Пользователь {user_id} попытался использовать админский callback без прав.")
            return is_admin
        except Exception as e:
            logger.error(f"Ошибка при проверке прав админа для user_id {user_id} в callback: {e}", exc_info=True)
            return False

    # Основной обработчик callback-запросов
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call: CallbackQuery):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        cb_data = call.data
        logger.debug(f"Callback: user={user_id}, chat={chat_id}, msg={message_id}, data='{cb_data}'")

        # --- Проверка регистрации и активности пользователя (для большинства действий) ---
        # Вынесем её повыше для колбэков, которые требуют активного пользователя
        # но не для админских действий типа регистрации или управления
        needs_active_user_check = not (
            cb_data.startswith(const.CB_REG_CONFIRM_USER) or
            cb_data.startswith(const.CB_REG_DECLINE_USER) or
            cb_data.startswith(const.CB_MANAGE_SELECT_USER) or # Админ выбирает пользователя
            cb_data.startswith(const.CB_MANAGE_BLOCK_USER) or
            cb_data.startswith(const.CB_MANAGE_UNBLOCK_USER) or
            cb_data.startswith(const.CB_ADMIN_CANCEL_SELECT) or # Админские действия
            cb_data.startswith(const.CB_ADMIN_CANCEL_CONFIRM) or
            cb_data.startswith(const.CB_FILTER_BY_TYPE) or
            cb_data.startswith(const.CB_FILTER_SELECT_USER) or
            cb_data.startswith(const.CB_FILTER_SELECT_EQUIPMENT) or
            cb_data.startswith(const.CB_FILTER_SELECT_DATE) or
            cb_data.startswith(const.CB_EQUIP_DELETE_SELECT) or
            cb_data.startswith(const.CB_EQUIP_DELETE_CONFIRM) or
            cb_data == const.CB_IGNORE or
            cb_data.startswith(const.CB_ACTION_CANCEL) # Отмена не требует активного статуса
        )

        if needs_active_user_check:
            try:
                if not userService.is_user_registered_and_active(db, user_id):
                    bot.answer_callback_query(call.id, const.MSG_ERROR_NOT_REGISTERED, show_alert=True)
                    try: # Пытаемся отредактировать сообщение об ошибке
                        bot.edit_message_text(const.MSG_ERROR_NOT_REGISTERED, chat_id, message_id, reply_markup=None)
                    except Exception: pass
                    return # Выходим, если пользователь не активен
            except Exception as e_check:
                 logger.error(f"Ошибка при проверке статуса пользователя {user_id} в callback: {e_check}", exc_info=True)
                 bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
                 return

        # --- Обработка конкретных колбэков ---
        try:
            # Шаг 1: Выбор категории
            if cb_data.startswith(const.CB_BOOK_SELECT_CATEGORY):
                category_id = int(cb_data[len(const.CB_BOOK_SELECT_CATEGORY):])
                logger.debug(f"User {user_id} выбрал категорию {category_id} для бронирования")
                # Сервис возвращает List[Dict[str, Any]]
                equipment = equipmentService.get_equipment_by_category(db, category_id)
                if not equipment:
                    bot.answer_callback_query(call.id, "Нет оборудования")
                    try:
                        bot.edit_message_text("В этой категории нет доступного оборудования.", chat_id, message_id, reply_markup=None)
                    except Exception: pass
                    return

                # Клавиатура ожидает List[Dict[str, Any]]
                markup = keyboards.generate_equipment_keyboard(equipment, const.CB_BOOK_SELECT_EQUIPMENT)
                bot.edit_message_text("Шаг 2: Выберите оборудование:", chat_id, message_id, reply_markup=markup)

            # Шаг 2: Выбор оборудования
            elif cb_data.startswith(const.CB_BOOK_SELECT_EQUIPMENT):
                equipment_id = int(cb_data[len(const.CB_BOOK_SELECT_EQUIPMENT):])
                logger.debug(f"User {user_id} выбрал оборудование {equipment_id} для бронирования")
                # ID оборудования передается дальше
                markup = keyboards.generate_date_keyboard(equipment_id, const.CB_BOOK_SELECT_DATE, single_column=True)
                bot.edit_message_text("Шаг 3: Выберите дату:", chat_id, message_id, reply_markup=markup)

            # Шаг 3: Выбор даты
            elif cb_data.startswith(const.CB_BOOK_SELECT_DATE):
                data_part = cb_data[len(const.CB_BOOK_SELECT_DATE):]
                parts = data_part.split('_')
                if len(parts) != 2: raise ValueError("Неверный формат callback даты")
                selected_date_str = parts[0]
                equipment_id = int(parts[1])
                logger.debug(f"User {user_id} выбрал дату {selected_date_str} для equip {equipment_id}")
                markup = keyboards.generate_time_keyboard(selected_date_str, equipment_id, const.CB_BOOK_SELECT_TIME)
                bot.edit_message_text("Шаг 4: Выберите время начала:", chat_id, message_id, reply_markup=markup)

            # Шаг 4: Выбор времени начала
            elif cb_data.startswith(const.CB_BOOK_SELECT_TIME):
                data_part = cb_data[len(const.CB_BOOK_SELECT_TIME):]
                parts = data_part.split('_')
                if len(parts) != 3: raise ValueError("Неверный формат callback времени")
                start_time_str = parts[0]
                selected_date_str = parts[1]
                equipment_id = int(parts[2])
                logger.debug(f"User {user_id} выбрал время {start_time_str} (дата {selected_date_str}, equip {equipment_id})")
                markup = keyboards.generate_duration_keyboard(start_time_str, selected_date_str, equipment_id, const.CB_BOOK_SELECT_DURATION)
                bot.edit_message_text("Шаг 5: Выберите длительность:", chat_id, message_id, reply_markup=markup)

            # Шаг 5: Выбор длительности и финализация
            elif cb_data.startswith(const.CB_BOOK_SELECT_DURATION):
                data_part = cb_data[len(const.CB_BOOK_SELECT_DURATION):]
                parts = data_part.split('_')
                if len(parts) != 4: raise ValueError("Неверный формат callback длительности")
                duration_str = parts[0]
                start_time_str = parts[1]
                selected_date_str = parts[2]
                equipment_id = int(parts[3])
                logger.info(f"User {user_id} финализирует бронь: equip={equipment_id}, date={selected_date_str}, time={start_time_str}, duration={duration_str}")
                bot.answer_callback_query(call.id, "Проверяем и сохраняем...")
                try:
                    bot.edit_message_text(f"⏳ Проверяем доступность и сохраняем бронь...", chat_id, message_id, reply_markup=None)
                except Exception: pass

                # Сервис create_booking возвращает (success, msg, new_booking_id)
                # msg будет константой из constants.py
                success, msg, new_booking_id = bookingService.create_booking(
                    db, user_id, equipment_id, selected_date_str, start_time_str, duration_str
                )

                try:
                    bot.edit_message_text(msg, chat_id, message_id, parse_mode="Markdown") # Используем Markdown для возможных форматов
                except Exception:
                    bot.send_message(chat_id, msg, parse_mode="Markdown") # Отправляем новым, если редактирование не удалось

                # Запускаем обновление уведомлений ТОЛЬКО если есть планировщик
                if success and new_booking_id and scheduler:
                    logger.debug(f"Бронь {new_booking_id} создана, запускаем schedule_all_notifications...")
                    notificationService.schedule_all_notifications(db, bot, scheduler, active_timers, scheduled_jobs_registry)
                elif success and new_booking_id and not scheduler:
                     logger.warning("Планировщик не передан в callback_handlers, уведомления для новой брони не будут запланированы.")

            # Подтверждение начала бронирования (пользователем)
            elif cb_data.startswith(const.CB_BOOK_CONFIRM_START):
                 booking_id = int(cb_data[len(const.CB_BOOK_CONFIRM_START):])
                 logger.info(f"User {user_id} подтвердил бронь {booking_id}")
                 # Логика подтверждения
                 success = notificationService.confirm_booking_callback_logic(db, active_timers, booking_id, user_id)
                 if success:
                     bot.answer_callback_query(call.id, const.MSG_BOOKING_CONFIRMED)
                     try:
                         bot.edit_message_text(f"✅ {const.MSG_BOOKING_CONFIRMED}", chat_id, message_id, reply_markup=None)
                     except Exception: pass
                 else:
                     # Сообщение об ошибке или неактивности
                     bot.answer_callback_query(call.id, "Не удалось подтвердить. Возможно, бронь уже неактивна.", show_alert=True)
                     try: # Пытаемся удалить старое сообщение с кнопкой
                         bot.delete_message(chat_id, message_id)
                     except Exception: pass

            # Отмена бронирования (пользователем)
            elif cb_data.startswith(const.CB_CANCEL_SELECT_BOOKING):
                booking_id = int(cb_data[len(const.CB_CANCEL_SELECT_BOOKING):])
                logger.info(f"User {user_id} отменяет бронь {booking_id}")
                bot.answer_callback_query(call.id, "Отменяем...")
                # Сервис возвращает (success, msg, owner_user_id)
                success, msg, _ = bookingService.cancel_booking(db, booking_id, user_id=user_id, is_admin_cancel=False)
                try:
                    bot.edit_message_text(msg, chat_id, message_id, reply_markup=None, parse_mode="Markdown")
                except Exception:
                    bot.send_message(chat_id, msg, parse_mode="Markdown")

                if success and scheduler:
                     logger.debug(f"Бронь {booking_id} отменена user, чистим задачи...")
                     notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
                elif success and not scheduler:
                     logger.warning("Планировщик не передан, задачи уведомлений для отмененной брони не очищены.")


            # Админ-отмена: Шаг 1 - выбор брони
            elif cb_data.startswith(const.CB_ADMIN_CANCEL_SELECT):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                 booking_id = int(cb_data[len(const.CB_ADMIN_CANCEL_SELECT):])
                 logger.info(f"Admin {user_id} выбрал бронь {booking_id} для админ-отмены")
                 # Сервис find_booking_by_id должен возвращать словарь DictRow или None
                 booking_info: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)

                 if booking_info:
                     # --- ИСПОЛЬЗУЕМ ДОСТУП ПО КЛЮЧАМ ---
                     is_cancelled = booking_info.get('cancel', False) # Используем .get с default
                     is_finished = booking_info.get('finish', False)
                     equip_name = booking_info.get('equipment_name', '???') # Имя оборудования из JOIN
                     user_fi = booking_info.get('user_fi', '???') # ФИ пользователя из JOIN
                     date_val = booking_info.get('date')
                     start_time = booking_info.get('time_start')
                     end_time = booking_info.get('time_end')
                     # ---------------------------------

                     if is_cancelled:
                         bot.answer_callback_query(call.id, "Бронь уже отменена.")
                         try: bot.edit_message_text(f"Бронь ID {booking_id} уже отменена.", chat_id, message_id, reply_markup=None)
                         except Exception: pass
                         return
                     if is_finished:
                         bot.answer_callback_query(call.id, "Бронь уже завершена.")
                         try: bot.edit_message_text(f"Бронь ID {booking_id} уже завершена.", chat_id, message_id, reply_markup=None)
                         except Exception: pass
                         return

                     # Форматирование даты/времени (если они есть)
                     date_str = bookingService._format_date(date_val) if date_val else '??.??'
                     start_str = bookingService._format_time(start_time) if start_time else '??:??'
                     end_str = bookingService._format_time(end_time) if end_time else '??:??'

                     confirm_text = (f"❓ Отменить бронь ID `{booking_id}`?\n"
                                     f"👤 {user_fi}\n"
                                     f"🔬 {equip_name}\n"
                                     f"🗓️ {date_str} {start_str}-{end_str}")
                     markup = keyboards.generate_confirmation_keyboard(
                         f"{const.CB_ADMIN_CANCEL_CONFIRM}{booking_id}",
                         const.CB_ACTION_CANCEL + "admin_cancel" # Контекст для отмены
                     )
                     bot.edit_message_text(confirm_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
                 else:
                     bot.answer_callback_query(call.id, "Бронь не найдена.", show_alert=True)
                     try: bot.edit_message_text("Бронирование не найдено.", chat_id, message_id, reply_markup=None)
                     except Exception: pass

            # Админ-отмена: Шаг 2 - подтверждение
            elif cb_data.startswith(const.CB_ADMIN_CANCEL_CONFIRM):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                 booking_id = int(cb_data[len(const.CB_ADMIN_CANCEL_CONFIRM):])
                 logger.info(f"Admin {user_id} подтвердил админ-отмену {booking_id}")
                 bot.answer_callback_query(call.id, "Выполняю отмену...")

                 success, msg, owner_user_id = bookingService.cancel_booking(db, booking_id, user_id=user_id, is_admin_cancel=True)

                 try: bot.edit_message_text(msg, chat_id, message_id, reply_markup=None, parse_mode="Markdown")
                 except Exception: bot.send_message(chat_id, msg, parse_mode="Markdown")

                 if success and owner_user_id:
                     # Чистим задачи планировщика
                     if scheduler:
                         logger.debug(f"Бронь {booking_id} отменена admin, чистим задачи...")
                         notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
                     else:
                          logger.warning("Планировщик не передан, задачи для админ-отмены не очищены.")

                     # Уведомляем пользователя об отмене
                     try:
                         # Получаем обновленную инфо для уведомления
                         booking_info_notify: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)
                         if booking_info_notify:
                              # --- ДОСТУП ПО КЛЮЧАМ ---
                              equip_name_n = booking_info_notify.get('equipment_name', '???')
                              date_val_n = booking_info_notify.get('date')
                              start_time_n = booking_info_notify.get('time_start')
                              # ------------------------
                              date_str_n = bookingService._format_date(date_val_n) if date_val_n else '??.??'
                              start_str_n = bookingService._format_time(start_time_n) if start_time_n else '??:??'
                              notify_text = f"❗️ Ваше бронирование на '{equip_name_n}' ({date_str_n} {start_str_n}) было отменено администратором."
                              bot.send_message(owner_user_id, notify_text)
                              logger.info(f"Уведомление об админ-отмене отправлено пользователю {owner_user_id}")
                         else:
                             logger.warning(f"Не найдены детали брони {booking_id} для уведомления пользователя {owner_user_id} после админ-отмены.")
                     except Exception as e_notify:
                         logger.error(f"Не удалось уведомить пользователя {owner_user_id} об админ-отмене брони {booking_id}: {e_notify}")


            # Завершение бронирования (пользователем)
            elif cb_data.startswith(const.CB_FINISH_SELECT_BOOKING):
                 booking_id = int(cb_data[len(const.CB_FINISH_SELECT_BOOKING):])
                 logger.info(f"User {user_id} завершает бронь {booking_id} через кнопку")
                 bot.answer_callback_query(call.id, "Завершаю...")

                 success, msg = bookingService.finish_booking(db, booking_id, user_id) # Сервис возвращает (success, msg)

                 try: bot.edit_message_text(msg, chat_id, message_id, reply_markup=None, parse_mode="Markdown")
                 except Exception: bot.send_message(chat_id, msg, parse_mode="Markdown")

                 if success and scheduler:
                      logger.debug(f"Бронь {booking_id} завершена user, чистим задачи...")
                      notificationService.cleanup_completed_jobs(db, scheduler, scheduled_jobs_registry)
                 elif success and not scheduler:
                      logger.warning("Планировщик не передан, задачи для завершенной брони не очищены.")


            # Продление: Шаг 1 - выбор брони (из /продлить или уведомления)
            elif cb_data.startswith(const.CB_EXTEND_SELECT_BOOKING) or cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT):
                 is_from_notify = cb_data.startswith(const.CB_NOTIFY_EXTEND_PROMPT)
                 prefix_len = len(const.CB_NOTIFY_EXTEND_PROMPT) if is_from_notify else len(const.CB_EXTEND_SELECT_BOOKING)
                 booking_id = int(cb_data[prefix_len:])

                 source = "из уведомления" if is_from_notify else "из команды /продлить"
                 logger.info(f"User {user_id} выбрал бронь {booking_id} для продления ({source})")
                 bot.answer_callback_query(call.id, "Проверяю возможность продления...")

                 # Получаем инфо о брони
                 booking_info: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)

                 # --- ПРОВЕРКИ С ДОСТУПОМ ПО КЛЮЧАМ ---
                 owner_id = booking_info.get('user_id') if booking_info else None
                 is_cancelled = booking_info.get('cancel', True) if booking_info else True # Считаем отмененной, если не найдена
                 is_finished = booking_info.get('finish', True) if booking_info else True
                 equip_id = booking_info.get('equip_id') if booking_info else None
                 current_end_time = booking_info.get('time_end') if booking_info else None
                 # ------------------------------------

                 # Проверка: бронь существует, принадлежит пользователю, не отменена, не завершена
                 if not booking_info or owner_id != user_id or is_cancelled or is_finished:
                     msg_err = const.MSG_EXTEND_FAIL_NOT_ACTIVE
                     bot.answer_callback_query(call.id, "Бронь неактивна.", show_alert=True)
                     try: bot.edit_message_text(msg_err, chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return

                 # Проверка типа времени и ID оборудования
                 if not isinstance(current_end_time, datetime) or equip_id is None or scheduler is None:
                     err_detail = "некорректное время" if not isinstance(current_end_time, datetime) else "не найден ID оборудования" if equip_id is None else "планировщик не доступен"
                     logger.error(f"Ошибка данных для продления брони {booking_id} ({err_detail})")
                     bot.answer_callback_query(call.id, "Ошибка данных брони.", show_alert=True)
                     try: bot.edit_message_text(const.MSG_ERROR_GENERAL, chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return

                 # --- Логика расчета доступного времени (без изменений, но с доступом по ключам) ---
                 current_end_time_aware = current_end_time.astimezone(scheduler.timezone) if current_end_time.tzinfo else scheduler.timezone.localize(current_end_time)
                 now_aware = datetime.now(scheduler.timezone)

                 # Проверка, не истекло ли уже время
                 if now_aware >= current_end_time_aware:
                     logger.warning(f"User {user_id} пытается продлить {booking_id} {source} ПОСЛЕ окончания.")
                     bot.answer_callback_query(call.id, "Время истекло.", show_alert=True)
                     try: bot.edit_message_text("Не продлить: время бронирования уже истекло.", chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return

                 # Поиск следующей брони
                 next_booking: Optional[Dict[str, Any]] = bookingService.find_next_booking(db, equip_id, current_end_time_aware)
                 available_until: datetime
                 if next_booking and next_booking.get('time_start'):
                     # --- ДОСТУП ПО КЛЮЧУ ---
                     next_booking_start_time = next_booking['time_start']
                     # ---------------------
                     available_until = next_booking_start_time.astimezone(scheduler.timezone) if next_booking_start_time.tzinfo else scheduler.timezone.localize(next_booking_start_time)
                 else:
                     # Ограничиваем концом рабочего дня
                     end_of_day = time(const.END_OF_WORKDAY_HOUR, const.END_OF_WORKDAY_MINUTE)
                     available_until_naive = datetime.combine(current_end_time_aware.date(), end_of_day)
                     available_until = scheduler.timezone.localize(available_until_naive)
                     available_until = max(available_until, current_end_time_aware)

                 # Расчет максимальной длительности
                 max_duration_rounded = timedelta(0)
                 if available_until > current_end_time_aware:
                     max_delta = available_until - current_end_time_aware
                     total_mins = int(max_delta.total_seconds() // 60)
                     allowed_mins = (total_mins // const.BOOKING_TIME_STEP_MINUTES) * const.BOOKING_TIME_STEP_MINUTES
                     if allowed_mins > 0:
                         max_duration_rounded = timedelta(minutes=allowed_mins)

                 logger.debug(f"Макс. продление для брони {booking_id} ({source}): {max_duration_rounded}")

                 # Генерация клавиатуры или сообщение об ошибке
                 if max_duration_rounded > timedelta(0):
                     # Передаем рассчитанную максимальную длительность
                     markup = keyboards.generate_extend_time_keyboard(booking_id, max_duration=max_duration_rounded)
                     bot.edit_message_text("На сколько продлить:", chat_id, message_id, reply_markup=markup)
                 else:
                     # Используем константу
                     try: bot.edit_message_text(const.MSG_EXTEND_FAIL_NO_TIME, chat_id, message_id, reply_markup=None)
                     except Exception: pass


            # Продление: Шаг 2 - выбор времени
            elif cb_data.startswith(const.CB_EXTEND_SELECT_TIME):
                 data_part = cb_data[len(const.CB_EXTEND_SELECT_TIME):]
                 parts = data_part.split('_')
                 if len(parts) != 2: raise ValueError("Неверный формат callback времени продления")
                 booking_id = int(parts[0])
                 extension_str = parts[1] # Время вида "H:MM"
                 logger.info(f"User {user_id} выбрал продление на {extension_str} для брони {booking_id}")

                 # Доп. проверка времени перед реальным продлением (повторяется частично)
                 booking_info: Optional[Dict[str, Any]] = bookingService.find_booking_by_id(db, booking_id)
                 owner_id = booking_info.get('user_id') if booking_info else None
                 is_cancelled = booking_info.get('cancel', True) if booking_info else True
                 is_finished = booking_info.get('finish', True) if booking_info else True
                 current_end_time = booking_info.get('time_end') if booking_info else None

                 if not booking_info or owner_id != user_id or is_cancelled or is_finished:
                     bot.answer_callback_query(call.id, "Бронь неактивна.", show_alert=True)
                     try: bot.edit_message_text(const.MSG_EXTEND_FAIL_NOT_ACTIVE, chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return

                 if not isinstance(current_end_time, datetime) or scheduler is None:
                     logger.error(f"Некорректный тип time_end или scheduler=None у {booking_id} при подтверждении продления")
                     bot.answer_callback_query(call.id, "Ошибка времени.", show_alert=True)
                     return

                 current_end_time_aware = current_end_time.astimezone(scheduler.timezone) if current_end_time.tzinfo else scheduler.timezone.localize(current_end_time)
                 now_aware = datetime.now(scheduler.timezone)

                 if now_aware >= current_end_time_aware:
                     logger.warning(f"User {user_id} пытается подтвердить продление {booking_id} после окончания.")
                     bot.answer_callback_query(call.id, "Время истекло.", show_alert=True)
                     try: bot.edit_message_text("Не продлить: время бронирования уже истекло.", chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return

                 bot.answer_callback_query(call.id, "Продлеваю...")
                 # Сервис extend_booking возвращает (success, msg)
                 success, msg = bookingService.extend_booking(db, booking_id, user_id, extension_str)

                 try: bot.edit_message_text(msg, chat_id, message_id, reply_markup=None, parse_mode="Markdown")
                 except Exception: bot.send_message(chat_id, msg, parse_mode="Markdown")

                 # Обновляем уведомления, если успешно и есть планировщик
                 if success and scheduler:
                     logger.debug(f"Бронь {booking_id} продлена, обновляем задачи уведомлений...")
                     notificationService.schedule_all_notifications(db, bot, scheduler, active_timers, scheduled_jobs_registry)
                 elif success and not scheduler:
                      logger.warning("Планировщик не передан, уведомления для продленной брони не обновлены.")


            # Уведомление об окончании: Нажата кнопка "Нет, спасибо"
            elif cb_data.startswith(const.CB_NOTIFY_DECLINE_EXT):
                 booking_id = int(cb_data[len(const.CB_NOTIFY_DECLINE_EXT):])
                 logger.info(f"User {user_id} отказался продлевать {booking_id} из уведомления.")
                 bot.answer_callback_query(call.id, "Хорошо!")
                 try:
                      original_text = call.message.text or f"Бронь {booking_id}"
                      # Добавляем константу к тексту сообщения
                      bot.edit_message_text(f"{original_text}\n\n{const.MSG_EXTEND_DECLINED}", chat_id, message_id, reply_markup=None)
                 except Exception as e:
                      logger.warning(f"Не удалось отредактировать сообщение {message_id} (бронь {booking_id}) после отказа от продления: {e}")

            # Регистрация (админом) - Подтверждение
            elif cb_data.startswith(const.CB_REG_CONFIRM_USER):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                 temp_user_id = int(cb_data[len(const.CB_REG_CONFIRM_USER):])
                 logger.info(f"Admin {user_id} подтверждает регистрацию для temp_user_id {temp_user_id}")
                 bot.answer_callback_query(call.id, "Регистрирую...")

                 success, user_info = userService.confirm_registration(db, temp_user_id) # Ожидаем (success, user_info_dict or None)

                 if success and user_info:
                     first_name = user_info.get('first_name', '')
                     try: bot.edit_message_text(f"✅ Пользователь {first_name} (ID: `{temp_user_id}`) зарегистрирован.", chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                     except Exception: pass
                     try: bot.send_message(temp_user_id, const.MSG_REGISTRATION_APPROVED)
                     except Exception as e_notify: logger.error(f"Не удалось уведомить {temp_user_id} о подтверждении регистрации: {e_notify}")
                 elif success and not user_info: # Успешно, но не получили данные - странно
                      logger.warning(f"Регистрация temp_user_id {temp_user_id} подтверждена, но данные пользователя не получены.")
                      try: bot.edit_message_text(f"✅ Пользователь ID `{temp_user_id}` зарегистрирован (данные не получены).", chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                      except Exception: pass
                 else: # Ошибка регистрации
                     try: bot.edit_message_text(f"❌ Ошибка регистрации пользователя ID `{temp_user_id}`.", chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                     except Exception: pass

            # Регистрация (админом) - Отклонение
            elif cb_data.startswith(const.CB_REG_DECLINE_USER):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                 temp_user_id = int(cb_data[len(const.CB_REG_DECLINE_USER):])
                 logger.info(f"Admin {user_id} отклоняет регистрацию для temp_user_id {temp_user_id}")
                 bot.answer_callback_query(call.id, "Отклоняю...")

                 success = userService.decline_registration(db, temp_user_id) # Возвращает bool

                 if success:
                     try: bot.edit_message_text(f"🚫 Регистрация пользователя ID `{temp_user_id}` отклонена.", chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                     except Exception: pass
                     try: bot.send_message(temp_user_id, const.MSG_REGISTRATION_DECLINED)
                     except Exception as e_notify: logger.warning(f"Не удалось уведомить {temp_user_id} об отклонении регистрации: {e_notify}")
                 else:
                     try: bot.edit_message_text(f"❌ Ошибка отклонения регистрации пользователя ID `{temp_user_id}`.", chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                     except Exception: pass

            # Просмотр броней по дате (/datebookings)
            elif cb_data.startswith(const.CB_DATEB_SELECT_DATE):
                 data_part = cb_data[len(const.CB_DATEB_SELECT_DATE):]
                 parts = data_part.split('_')
                 # equipment_id в этом колбэке не используется, поэтому может быть 1 или 2 части
                 if not 1 <= len(parts) <= 2: raise ValueError("Неверный формат callback /datebookings")
                 selected_date_str = parts[0]
                 logger.debug(f"User {user_id} запросил /datebookings на {selected_date_str}")
                 try:
                     date_obj = datetime.strptime(selected_date_str, '%d-%m-%Y').date()
                     bot.answer_callback_query(call.id, f"Загружаю бронирования на {selected_date_str}...")
                     # Сервис возвращает готовый текст
                     text = bookingService.get_bookings_by_date_text(db, date_obj)
                     try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                     except Exception: bot.send_message(chat_id, text, parse_mode="Markdown")
                 except ValueError:
                     logger.warning(f"Неверный формат даты '{selected_date_str}' в callback /datebookings")
                     bot.answer_callback_query(call.id, "Ошибка формата даты.", show_alert=True)
                 except Exception as e:
                     logger.error(f"Ошибка при обработке /datebookings для даты {selected_date_str}: {e}", exc_info=True)
                     bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)

            # Просмотр броней по рабочему месту (/workspacebookings) - Шаг 1
            elif cb_data.startswith(const.CB_WSB_SELECT_CATEGORY):
                cat_id = int(cb_data[len(const.CB_WSB_SELECT_CATEGORY):])
                logger.debug(f"User {user_id} выбрал категорию {cat_id} для /workspacebookings")
                # Сервис возвращает List[Dict]
                equip = equipmentService.get_equipment_by_category(db, cat_id)
                if not equip:
                    bot.answer_callback_query(call.id, "Нет оборудования")
                    try: bot.edit_message_text("Нет доступного оборудования в этой категории.", chat_id, message_id, reply_markup=None)
                    except Exception: pass
                    return
                # Клавиатура ожидает List[Dict]
                markup = keyboards.generate_equipment_keyboard(equip, const.CB_WSB_SELECT_EQUIPMENT)
                bot.edit_message_text("Выберите оборудование для просмотра бронирований:", chat_id, message_id, reply_markup=markup)

            # Просмотр броней по рабочему месту (/workspacebookings) - Шаг 2
            elif cb_data.startswith(const.CB_WSB_SELECT_EQUIPMENT):
                 equip_id = int(cb_data[len(const.CB_WSB_SELECT_EQUIPMENT):])
                 logger.debug(f"User {user_id} выбрал оборудование {equip_id} для /workspacebookings")
                 bot.answer_callback_query(call.id, "Загружаю бронирования...")
                 # Получаем имя
                 name = equipmentService.get_equipment_name_by_id(db, equip_id)
                 if not name:
                     try: bot.edit_message_text("Оборудование не найдено.", chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return
                 # Сервис возвращает готовый текст
                 text = bookingService.get_bookings_by_workspace_text(db, equip_id, name)
                 try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=None)
                 except Exception: bot.send_message(chat_id, text, parse_mode="Markdown")

            # Фильтр /all (Админ) - Шаг 1: выбор типа
            elif cb_data.startswith(const.CB_FILTER_BY_TYPE):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                 f_type = cb_data[len(const.CB_FILTER_BY_TYPE):]
                 logger.debug(f"Admin {user_id} выбрал тип фильтра '{f_type}' для /all")
                 opts = []
                 cb_pfx = ""
                 prompt = ""
                 try:
                      if f_type == "users":
                          # Сервис возвращает List[Dict]
                          users_data = userService.get_all_users(db, include_inactive=True)
                          # Формируем [(Текст кнопки, callback_data_value)]
                          opts = [(user.get('fi', f"ID {user.get('users_id')}"), user.get('users_id'))
                                  for user in users_data if user.get('users_id')]
                          opts.sort()
                          cb_pfx = const.CB_FILTER_SELECT_USER
                          prompt = "Выберите пользователя:"
                      elif f_type == "equipment":
                          # Сервис возвращает List[Dict]
                          equip_data = equipmentService.get_all_equipment(db)
                          opts = [(eq.get('name_equip', f"ID {eq.get('id')}"), eq.get('id'))
                                  for eq in equip_data if eq.get('id')]
                          opts.sort()
                          cb_pfx = const.CB_FILTER_SELECT_EQUIPMENT
                          prompt = "Выберите оборудование:"
                      elif f_type == "dates":
                          # Запрос на уникальные месяцы (возвращает List[Dict] или List[Tuple])
                          query = "SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month_year FROM bookings WHERE date IS NOT NULL ORDER BY month_year DESC;"
                          # Уточним тип результата
                          months_result: Optional[QueryResult] = db.execute_query(query, fetch_results=True)
                          # Если DictCursor, доступ по ключу 'month_year', иначе по индексу [0]
                          opts = [(m['month_year'], m['month_year']) if isinstance(m, dict) else (m[0], m[0])
                                  for m in months_result] if months_result else []
                          cb_pfx = const.CB_FILTER_SELECT_DATE
                          prompt = "Выберите месяц (ГГГГ-ММ):"
                      else:
                          logger.warning(f"Неизвестный тип фильтра '{f_type}' от admin {user_id}")
                          bot.answer_callback_query(call.id, "Неизвестный тип фильтра.")
                          return

                      if not opts:
                          bot.answer_callback_query(call.id, "Нет данных для фильтра.")
                          try: bot.edit_message_text("Нет доступных данных для этого фильтра.", chat_id, message_id, reply_markup=None)
                          except Exception: pass
                      else:
                          # Клавиатура ожидает List[Tuple]
                          markup = keyboards.generate_filter_selection_keyboard(opts, cb_pfx)
                          bot.edit_message_text(prompt, chat_id, message_id, reply_markup=markup)

                 except Exception as e:
                     logger.error(f"Ошибка при получении опций для фильтра '{f_type}' (/all): {e}", exc_info=True)
                     bot.answer_callback_query(call.id, "Ошибка получения данных.", show_alert=True)
                     try: bot.edit_message_text(const.MSG_ERROR_GENERAL, chat_id, message_id, reply_markup=None)
                     except Exception: pass

            # Фильтр /all (Админ) - Шаг 2: выбор значения и генерация отчета
            elif cb_data.startswith((const.CB_FILTER_SELECT_USER, const.CB_FILTER_SELECT_EQUIPMENT, const.CB_FILTER_SELECT_DATE)):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return

                 f_type = ""
                 f_val_str = ""
                 f_val_int: Optional[int] = None
                 f_details = "неизвестно"
                 path = None

                 try:
                      if cb_data.startswith(const.CB_FILTER_SELECT_USER):
                          f_type = "users"
                          f_val_str = cb_data[len(const.CB_FILTER_SELECT_USER):]
                          f_val_int = int(f_val_str)
                          # Сервис get_user_info возвращает Dict или None
                          user_info = userService.get_user_info(db, f_val_int)
                          f_details = f"Пользователь: {user_info.get('fi', f'ID {f_val_int}')}" if user_info else f'ID {f_val_int}'
                      elif cb_data.startswith(const.CB_FILTER_SELECT_EQUIPMENT):
                          f_type = "equipment"
                          f_val_str = cb_data[len(const.CB_FILTER_SELECT_EQUIPMENT):]
                          f_val_int = int(f_val_str)
                          name = equipmentService.get_equipment_name_by_id(db, f_val_int) # Возвращает str или None
                          f_details = f"Оборудование: {name or f'ID {f_val_int}'}"
                      elif cb_data.startswith(const.CB_FILTER_SELECT_DATE):
                          f_type = "dates"
                          f_val_str = cb_data[len(const.CB_FILTER_SELECT_DATE):]
                          datetime.strptime(f_val_str, '%Y-%m') # Проверка формата
                          f_details = f"Месяц: {f_val_str}"

                 except (ValueError, TypeError, IndexError) as e:
                     logger.error(f"Ошибка парсинга значения фильтра из callback '{cb_data}': {e}")
                     bot.answer_callback_query(call.id, "Ошибка в данных фильтра.", show_alert=True)
                     return
                 except Exception as e: # Ловим прочие ошибки парсинга
                     logger.error(f"Непредвиденная ошибка при парсинге фильтра '{cb_data}': {e}", exc_info=True)
                     bot.answer_callback_query(call.id, "Ошибка обработки фильтра.", show_alert=True)
                     return

                 logger.info(f"Admin {user_id} запросил отчет /all bookings с фильтром: {f_type}={f_val_str}")
                 bot.answer_callback_query(call.id, "Формирую отчет...")
                 try: bot.edit_message_text(f"⏳ Формирую отчет ({f_details})...", chat_id, message_id, reply_markup=None)
                 except Exception: pass

                 try:
                     # Передаем int или str в сервис
                     filter_value: Any = f_val_int if f_val_int is not None else f_val_str
                     # Сервис возвращает List[Dict]
                     bookings_data: List[Dict[str, Any]] = adminService.get_filtered_bookings(db, f_type, filter_value)
                     # Сервис создает файл и возвращает путь
                     path = adminService.create_bookings_report_file(bookings_data, filter_details=f_details)

                     if path and os.path.exists(path):
                         try:
                             with open(path, 'rb') as f:
                                 bot.send_document(chat_id, f, caption=f"Отчет по бронированиям ({f_details})")
                             logger.info(f"Отчет {os.path.basename(path)} успешно отправлен admin {user_id}")
                             try: bot.delete_message(chat_id, message_id)
                             except Exception: pass
                         except Exception as e_send:
                             logger.error(f"Ошибка отправки файла отчета {path} admin {user_id}: {e_send}")
                             try: bot.edit_message_text(f"❌ Ошибка отправки файла отчета.", chat_id, message_id, reply_markup=None)
                             except Exception: bot.send_message(chat_id, f"❌ Ошибка отправки файла отчета.")
                     elif not bookings_data:
                          logger.info(f"Для фильтра {f_type}={f_val_str} нет бронирований.")
                          try: bot.edit_message_text(f"По фильтру '{f_details}' бронирований не найдено.", chat_id, message_id, reply_markup=None)
                          except Exception: bot.send_message(chat_id, f"По фильтру '{f_details}' бронирований не найдено.")
                     else: # Ошибка создания файла
                         logger.error(f"Ошибка создания файла отчета для фильтра {f_type}={f_val_str} (path={path})")
                         try: bot.edit_message_text(f"❌ Не удалось создать файл отчета.", chat_id, message_id, reply_markup=None)
                         except Exception: bot.send_message(chat_id, f"❌ Не удалось создать файл отчета.")

                 except Exception as e_report:
                     logger.error(f"Критическая ошибка при генерации отчета /all ({f_type}={f_val_str}): {e_report}", exc_info=True)
                     try: bot.edit_message_text(f"❌ Ошибка при генерации отчета.", chat_id, message_id, reply_markup=None)
                     except Exception: bot.send_message(chat_id, f"❌ Ошибка при генерации отчета.")

                 finally:
                     if path and os.path.exists(path):
                         try:
                             os.remove(path)
                             logger.debug(f"Временный файл отчета {path} удален.")
                         except OSError as e_remove:
                             logger.error(f"Ошибка удаления временного файла отчета {path}: {e_remove}")

            # Удаление оборудования (Админ) - Шаг 1: выбор
            elif cb_data.startswith(const.CB_EQUIP_DELETE_SELECT):
                if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                try: equipment_id = int(cb_data[len(const.CB_EQUIP_DELETE_SELECT):])
                except (ValueError, TypeError): logger.error(f"Ошибка извлечения ID оборудования из callback '{cb_data}'"); bot.answer_callback_query(call.id, "Ошибка ID оборудования.", show_alert=True); return

                logger.info(f"Admin {user_id} инициировал удаление оборудования ID {equipment_id}")
                # Сервис возвращает Dict или None
                equip_info = equipmentService.get_equipment_info_by_id(db, equipment_id)

                if not equip_info:
                    bot.answer_callback_query(call.id, "Оборудование не найдено.", show_alert=True)
                    try: bot.edit_message_text(const.MSG_EQUIP_DELETE_FAIL_NOT_FOUND, chat_id, message_id, reply_markup=None)
                    except Exception: pass
                    return

                # --- ДОСТУП ПО КЛЮЧУ ---
                equip_name = equip_info.get('name_equip', f'ID {equipment_id}')
                # ----------------------

                # Проверка использования ПЕРЕД запросом подтверждения
                if equipmentService.check_equipment_usage(db, equipment_id):
                    error_msg = const.MSG_EQUIP_DELETE_FAIL_USED.replace('{equipment_name}', f"'{equip_name}'") # Используем константу
                    bot.answer_callback_query(call.id, "Оборудование используется!", show_alert=True)
                    try: bot.edit_message_text(error_msg, chat_id, message_id, reply_markup=None)
                    except Exception: bot.send_message(chat_id, error_msg) # Отправляем новым, если редактирование не удалось
                    return

                # Запрос подтверждения
                confirm_text = f"❓ Удалить оборудование '{equip_name}' (ID: {equipment_id})?\n\n❗**Внимание:** Действие **необратимо**!"
                markup = keyboards.generate_confirmation_keyboard(
                    confirm_callback=f"{const.CB_EQUIP_DELETE_CONFIRM}{equipment_id}",
                    cancel_callback=const.CB_ACTION_CANCEL + "delete_equip",
                    confirm_text="✅ Да, удалить",
                    cancel_text="❌ Отмена"
                )
                try: bot.edit_message_text(confirm_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
                except Exception: bot.send_message(chat_id, confirm_text, reply_markup=markup, parse_mode="Markdown")


            # Удаление оборудования (Админ) - Шаг 2: подтверждение
            elif cb_data.startswith(const.CB_EQUIP_DELETE_CONFIRM):
                if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                try: equipment_id = int(cb_data[len(const.CB_EQUIP_DELETE_CONFIRM):])
                except (ValueError, TypeError): logger.error(f"Ошибка извлечения ID из callback '{cb_data}' при подтверждении удаления"); bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True); return

                logger.info(f"Admin {user_id} подтвердил удаление оборудования ID {equipment_id}")
                bot.answer_callback_query(call.id, "Удаляю оборудование...")

                # Сервис возвращает (success, msg)
                success, msg = equipmentService.delete_equipment_if_unused(db, equipment_id)

                try: bot.edit_message_text(msg, chat_id, message_id, reply_markup=None) # Сообщение уже содержит статус
                except Exception: bot.send_message(chat_id, msg)


            # Управление пользователями (Админ) - Шаг 1: выбор
            elif cb_data.startswith(const.CB_MANAGE_SELECT_USER):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return
                 try: target_user_id = int(cb_data[len(const.CB_MANAGE_SELECT_USER):])
                 except (ValueError, TypeError): logger.error(f"Ошибка извлечения ID из callback '{cb_data}' для управления"); bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True); return

                 logger.debug(f"Admin {user_id} выбрал пользователя {target_user_id} для управления.")
                 # Сервис возвращает кортеж (name, is_blocked) или None
                 details = userService.get_user_details_for_management(db, target_user_id)

                 if not details:
                     bot.answer_callback_query(call.id, "Пользователь не найден.", show_alert=True)
                     try: bot.edit_message_text("Пользователь не найден.", chat_id, message_id, reply_markup=None)
                     except Exception: pass
                     return

                 # Здесь используем индексы, т.к. сервис возвращает кортеж
                 name, is_blocked = details
                 status_text = "🔴 Заблокирован" if is_blocked else "🟢 Активен"
                 markup = keyboards.generate_user_status_keyboard(target_user_id, is_blocked) # Клавиатура Блок/Разблок/Отмена
                 message_text = f"Пользователь: {name} (ID: `{target_user_id}`)\nСтатус: {status_text}\n\nВыберите действие:"
                 bot.edit_message_text(message_text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")

            # Управление пользователями (Админ) - Шаг 2: действие (блок/разблок)
            elif cb_data.startswith(const.CB_MANAGE_BLOCK_USER) or cb_data.startswith(const.CB_MANAGE_UNBLOCK_USER):
                 if not _is_admin_user(user_id): bot.answer_callback_query(call.id, const.MSG_ERROR_NO_PERMISSION, show_alert=True); return

                 block_action = cb_data.startswith(const.CB_MANAGE_BLOCK_USER)
                 try: target_user_id = int(cb_data.split('_')[-1]) # ID в конце
                 except (ValueError, TypeError, IndexError): logger.error(f"Ошибка извлечения ID из callback '{cb_data}' при (раз)блокировке"); bot.answer_callback_query(call.id, "Ошибка ID.", show_alert=True); return

                 action_verb = "блокирует" if block_action else "разблокирует"
                 action_past = "заблокирован" if block_action else "разблокирован"
                 action_infinitive = "заблокировать" if block_action else "разблокировать"

                 logger.info(f"Admin {user_id} {action_verb} пользователя {target_user_id}")
                 bot.answer_callback_query(call.id, f"{'Блокирую' if block_action else 'Разблокирую'}...")

                 # Сервис возвращает bool
                 success = userService.update_user_block_status(db, target_user_id, block=block_action)

                 # Получаем обновленные данные для отображения
                 details_after = userService.get_user_details_for_management(db, target_user_id)

                 if details_after:
                      name, blocked_after = details_after # Опять кортеж
                      status_text = "🔴 Заблокирован" if blocked_after else "🟢 Активен"
                      # Используем константы для сообщения
                      result_message = const.MSG_USER_BLOCKED if block_action else const.MSG_USER_UNBLOCKED
                      markup = keyboards.generate_user_status_keyboard(target_user_id, blocked_after)
                      text = (f"Пользователь: {name} (ID: `{target_user_id}`)\n"
                              f"Статус: {status_text}\n"
                              f"({'✅ ' + result_message if success else '❌ Ошибка при обновлении статуса!'})\n\n"
                              f"Выберите действие:")
                      try: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
                      except Exception as e_edit: logger.warning(f"Не удалось отредактировать сообщение {message_id} после {action_verb} user {target_user_id}: {e_edit}")
                 else:
                     logger.error(f"Не удалось найти пользователя {target_user_id} ПОСЛЕ попытки {action_infinitive}")
                     try: bot.edit_message_text(f"❌ Не удалось {action_infinitive} пользователя {target_user_id} (не найден после выполнения).", chat_id, message_id, reply_markup=None)
                     except Exception: pass

            # Общая кнопка Отмены действия
            elif cb_data.startswith(const.CB_ACTION_CANCEL):
                 context = cb_data[len(const.CB_ACTION_CANCEL):] # Извлекаем контекст (delete_equip, admin_cancel, manage_user_list и т.д.)
                 logger.debug(f"User {user_id} отменил действие (контекст: '{context}'). Message_id: {message_id}")
                 bot.answer_callback_query(call.id, const.MSG_ACTION_CANCELLED)
                 try:
                     # Возвращаем пользователя к предыдущему шагу в зависимости от контекста
                     if context == "delete_equip":
                         logger.debug("Возврат к списку оборудования для удаления...")
                         # Сервис возвращает List[Dict]
                         all_equipment = equipmentService.get_all_equipment(db)
                         if all_equipment:
                             # Клавиатура ожидает List[Dict]
                             markup = keyboards.generate_equipment_list_with_delete_keyboard(all_equipment)
                             bot.edit_message_text("Удаление отменено. Выберите оборудование для удаления:", chat_id, message_id, reply_markup=markup)
                         else:
                             bot.edit_message_text("Удаление отменено. Нет оборудования.", chat_id, message_id, reply_markup=None)

                     elif context == "admin_cancel":
                         logger.debug("Возврат к списку броней для админ-отмены...")
                         # Сервис возвращает List[Dict]
                         active_bookings = bookingService.get_all_active_bookings_for_admin_keyboard(db)
                         if active_bookings:
                             # Клавиатура ожидает List[Dict]
                             markup = keyboards.generate_admin_cancel_keyboard(active_bookings)
                             bot.edit_message_text("Отмена отменена. Выберите бронь для отмены:", chat_id, message_id, reply_markup=markup)
                         else:
                             bot.edit_message_text("Отмена отменена. Нет активных бронирований для отмены.", chat_id, message_id, reply_markup=None)

                     elif context == "manage_user_list": # Контекст из generate_user_status_keyboard
                          logger.debug("Возврат к списку пользователей для управления...")
                          # Сервис возвращает List[Dict]
                          users_list = userService.get_all_users(db, include_inactive=True)
                          if users_list:
                               # Клавиатура ожидает List[Dict]
                               markup = keyboards.generate_user_management_keyboard(users_list)
                               bot.edit_message_text("Выберите пользователя для управления:", chat_id, message_id, reply_markup=markup)
                          else:
                               bot.edit_message_text("Нет пользователей для управления.", chat_id, message_id, reply_markup=None)

                     # Добавить другие контексты отмены по необходимости...

                     else: # Общий случай отмены - просто удаляем сообщение с кнопками
                          logger.debug(f"Общая отмена (контекст '{context}'), удаляем сообщение {message_id}")
                          bot.delete_message(chat_id, message_id)

                 except Exception as e_cancel:
                      logger.warning(f"Не удалось обработать отмену (контекст: {context}, msg_id: {message_id}): {e_cancel}")
                      # Пытаемся хотя бы отредактировать текст
                      try: bot.edit_message_text(const.MSG_ACTION_CANCELLED, chat_id, message_id, reply_markup=None)
                      except Exception: pass

            # Callback для игнорирования
            elif cb_data == const.CB_IGNORE:
                bot.answer_callback_query(call.id) # Просто отвечаем, ничего не делая

            # Неизвестный колбэк
            else:
                logger.warning(f"Получен неизвестный или необработанный callback от user {user_id}: '{cb_data}'")
                bot.answer_callback_query(call.id, "Неизвестное действие.")

        # --- Обработка ошибок ---
        except (ValueError, TypeError) as e_parse: # Ошибки парсинга данных из callback
            logger.error(f"Ошибка парсинга данных в callback '{cb_data}' от user {user_id}: {e_parse}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка в формате данных callback.", show_alert=True)
            try: bot.edit_message_text("Произошла ошибка обработки данных.", chat_id, message_id, reply_markup=None)
            except Exception: pass
        except IndexError as e_index: # Ошибки индекса (менее вероятны со словарями)
            logger.error(f"IndexError при обработке callback '{cb_data}' от user {user_id}: {e_index}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка доступа к данным.", show_alert=True)
            try: bot.edit_message_text("Произошла ошибка доступа к данным.", chat_id, message_id, reply_markup=None)
            except Exception: pass
        except telebot.apihelper.ApiTelegramException as e_api: # Ошибки Telegram API
            if "message is not modified" in str(e_api).lower():
                 logger.debug(f"Сообщение {message_id} не изменено.")
                 bot.answer_callback_query(call.id)
            elif "message to edit not found" in str(e_api).lower():
                 logger.warning(f"Сообщение {message_id} для редактирования не найдено.")
                 bot.answer_callback_query(call.id, "Сообщение устарело.", show_alert=True)
            elif "message to delete not found" in str(e_api).lower():
                  logger.warning(f"Сообщение {message_id} для удаления не найдено.")
                  bot.answer_callback_query(call.id)
            elif "bot was blocked by the user" in str(e_api).lower() or "user is deactivated" in str(e_api).lower():
                 logger.warning(f"Бот заблокирован или пользователь {user_id} деактивирован.")
                 bot.answer_callback_query(call.id)
                 try: userService.handle_user_blocked_bot(db, user_id) # Пытаемся деактивировать
                 except Exception as e_deactivate: logger.error(f"Ошибка при деактивации заблокировавшего пользователя {user_id}: {e_deactivate}")
            else: # Другие ошибки API
                 logger.error(f"Ошибка Telegram API при обработке callback '{cb_data}' от user {user_id}: {e_api}", exc_info=True)
                 try: bot.answer_callback_query(call.id, "Произошла ошибка Telegram.", show_alert=True)
                 except Exception: pass
        except Exception as e_global: # Все остальные ошибки
            logger.critical(f"Критическая ошибка при обработке callback '{cb_data}' от user {user_id}: {e_global}", exc_info=True)
            try: bot.answer_callback_query(call.id, const.MSG_ERROR_GENERAL, show_alert=True)
            except Exception: pass
            try: # Пытаемся показать ошибку в сообщении
                error_info = f"{const.MSG_ERROR_GENERAL}\n`{type(e_global).__name__}: {e_global}`"
                bot.edit_message_text(error_info, chat_id, message_id, parse_mode="Markdown", reply_markup=None)
            except Exception: pass

    logger.info("Обработчики callback-запросов успешно зарегистрированы.")