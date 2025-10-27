import logging
from datetime import datetime, timedelta
from telebot import types
from database import execute_query

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BookingSystem:
    def __init__(self, bot, db_config):
        self.bot = bot
        self.db_config = db_config
        self.working_hours = {'start': '09:00', 'end': '21:00'}
        self.time_slot_duration = 30  # минуты

    def start_booking(self, message):
        """Начало процесса бронирования"""
        markup = self._generate_date_keyboard()
        self.bot.send_message(
            message.chat.id,
            "📅 Выберите дату для бронирования:",
            reply_markup=markup
        )

    def _generate_date_keyboard(self, days=7):
        """Генерация клавиатуры с датами"""
        markup = types.InlineKeyboardMarkup(row_width=3)
        today = datetime.now().date()

        for day in range(days):
            date = today + timedelta(days=day)
            button_text = date.strftime('%d.%m (%a)')
            callback_data = f"select_date:{date.strftime('%Y-%m-%d')}"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=callback_data))

        return markup

    def _generate_time_keyboard(self, date_str):
        """Генерация клавиатуры со временем"""
        markup = types.InlineKeyboardMarkup(row_width=4)
        start_time = datetime.strptime(self.working_hours['start'], "%H:%M")
        end_time = datetime.strptime(self.working_hours['end'], "%H:%M")
        current_time = start_time

        while current_time <= end_time:
            time_str = current_time.strftime("%H:%M")
            if self._is_time_available(date_str, time_str):
                callback_data = f"select_time:{date_str}:{time_str}"
                markup.add(types.InlineKeyboardButton(time_str, callback_data=callback_data))
            current_time += timedelta(minutes=self.time_slot_duration)

        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_dates"))
        return markup

    def _generate_duration_keyboard(self, date_str, time_str):
        """Генерация клавиатуры с длительностью"""
        markup = types.InlineKeyboardMarkup(row_width=3)
        durations = [
            ("30 мин", 30),
            ("1 час", 60),
            ("2 часа", 120),
            ("3 часа", 180),
            ("4 часа", 240)
        ]

        for text, minutes in durations:
            if self._is_time_available(date_str, time_str, minutes):
                callback_data = f"confirm_booking:{date_str}:{time_str}:{minutes}"
                markup.add(types.InlineKeyboardButton(text, callback_data=callback_data))

        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"back_to_times:{date_str}"))
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking"))
        return markup

    def _is_time_available(self, date_str, time_str, duration_minutes=30):
        """Проверка доступности времени"""
        query = """
            SELECT COUNT(*) FROM bookings 
            WHERE date = %s 
            AND time_start <= %s 
            AND time_end > %s
            AND cancel = FALSE
            AND finish IS NULL
        """
        start_datetime = f"{date_str} {time_str}"
        end_datetime = (datetime.strptime(start_datetime, "%Y-%m-%d %H:%M") +
                        timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M")

        count = execute_query(
            query,
            (date_str, end_datetime, start_datetime),
            db_config=self.db_config
        )

        return count[0][0] == 0 if count else True

    def handle_date_selection(self, call):
        """Обработчик выбора даты"""
        date_str = call.data.split(':')[1]
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🕒 Выберите время для {date_str}:",
            reply_markup=self._generate_time_keyboard(date_str)
        )

    def handle_time_selection(self, call):
        """Обработчик выбора времени"""
        _, date_str, time_str = call.data.split(':')
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⏳ Выберите длительность для {date_str} в {time_str}:",
            reply_markup=self._generate_duration_keyboard(date_str, time_str)
        )

    def handle_back_to_dates(self, call):
        """Обработчик возврата к выбору даты"""
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="📅 Выберите дату для бронирования:",
            reply_markup=self._generate_date_keyboard()
        )

    def handle_back_to_times(self, call):
        """Обработчик возврата к выбору времени"""
        date_str = call.data.split(':')[1]
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🕒 Выберите время для {date_str}:",
            reply_markup=self._generate_time_keyboard(date_str)
        )

    def confirm_booking(self, call):
        """Подтверждение и сохранение бронирования"""
        _, date_str, time_str, duration = call.data.split(':')
        duration = int(duration)

        start_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        end_datetime = start_datetime + timedelta(minutes=duration)

        query = """
            INSERT INTO bookings 
            (user_id, equip_id, date, time_start, time_end) 
            VALUES (%s, %s, %s, %s, %s)
        """
        try:
            execute_query(
                query,
                (call.from_user.id, 1, date_str, start_datetime, end_datetime),
                db_config=self.db_config
            )
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Бронирование подтверждено!\n\n"
                     f"📅 Дата: {date_str}\n"
                     f"🕒 Время: {time_str}-{end_datetime.strftime('%H:%M')}\n"
                     f"⏳ Длительность: {duration} минут"
            )
            logger.info(f"New booking created by user {call.from_user.id}")
        except Exception as e:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ Ошибка при создании бронирования"
            )
            logger.error(f"Booking error: {e}")

    def cancel_booking(self, call):
        """Отмена процесса бронирования"""
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ Бронирование отменено"
        )