import logging
from telebot import types
from database import execute_query
from database_config import DB_CONFIG
from auth import is_admin

logger = logging.getLogger('start')
logger.setLevel(logging.INFO)


class StartHandler:
    def __init__(self, bot, admin_id):
        self.bot = bot
        self.admin_id = admin_id
        self.user_temp_data = {}  # Для временного хранения данных регистрации

    def handle_start(self, message):
        """Обработка команды /start"""
        user_id = message.from_user.id
        user_status = self._check_user_status(user_id)

        if user_status == "registered":
            self._welcome_registered_user(message)
        elif user_status == "blocked":
            self._notify_blocked_user(message)
        else:
            self._start_registration(message)

    def _check_user_status(self, user_id) -> str:
        """Проверяет статус пользователя"""
        query = """
            SELECT is_blocked, first_name, last_name 
            FROM users 
            WHERE users_id = %s
        """
        result = execute_query(query, (user_id,))

        if not result:
            return "not_registered"
        return "blocked" if result[0][0] else "registered"

    def _welcome_registered_user(self, message):
        """Приветствие зарегистрированного пользователя"""
        query = "SELECT first_name, last_name FROM users WHERE users_id = %s"
        first_name, last_name = execute_query(query, (message.from_user.id,))[0]

        self.bot.send_message(
            message.chat.id,
            f"С возвращением, {first_name} {last_name}! Я бот для резервирования оборудования.\n"
            "Используй /help для получения списка команд.",
            reply_markup=self._get_main_keyboard()
        )

    def _notify_blocked_user(self, message):
        """Уведомление заблокированного пользователя"""
        self.bot.send_message(
            message.chat.id,
            "⛔ Вы заблокированы. Обратитесь к администратору."
        )

    def _start_registration(self, message):
        """Начало процесса регистрации"""
        self.user_temp_data[message.from_user.id] = {}
        msg = self.bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать! Для регистрации введите ваше имя и отчество:"
        )
        self.bot.register_next_step_handler(msg, self._process_first_name)

    def _process_first_name(self, message):
        """Обработка ввода имени"""
        user_id = message.from_user.id
        self.user_temp_data[user_id]['first_name'] = message.text

        msg = self.bot.send_message(
            message.chat.id,
            "Теперь введите вашу фамилию:"
        )
        self.bot.register_next_step_handler(msg, self._process_last_name)

    def _process_last_name(self, message):
        """Обработка ввода фамилии"""
        user_id = message.from_user.id
        self.user_temp_data[user_id]['last_name'] = message.text

        # Сохраняем во временную таблицу (или словарь)
        self._save_temp_user(user_id)

        # Отправляем администратору на подтверждение
        self._send_admin_confirmation(user_id)

        self.bot.send_message(
            message.chat.id,
            "✅ Ваши данные отправлены на подтверждение администратору.\n"
            "Вы получите уведомление, когда ваша регистрация будет подтверждена."
        )

    def _save_temp_user(self, user_id):
        """Сохраняет временные данные пользователя (можно заменить на запись в БД)"""
        # В реальной реализации следует сохранять в таблицу users_temp
        logger.info(f"Temp user data saved: {user_id} - {self.user_temp_data[user_id]}")

    def _send_admin_confirmation(self, user_id):
        """Отправляет запрос подтверждения администратору"""
        user_data = self.user_temp_data[user_id]
        markup = types.InlineKeyboardMarkup()
        confirm_btn = types.InlineKeyboardButton(
            "✅ Подтвердить",
            callback_data=f"confirm_user_{user_id}"
        )
        reject_btn = types.InlineKeyboardButton(
            "❌ Отклонить",
            callback_data=f"reject_user_{user_id}"
        )
        markup.add(confirm_btn, reject_btn)

        self.bot.send_message(
            self.admin_id,
            f"🆕 Новая регистрация:\n\n"
            f"ID: {user_id}\n"
            f"Имя: {user_data['first_name']}\n"
            f"Фамилия: {user_data['last_name']}\n\n"
            f"Подтвердить регистрацию?",
            reply_markup=markup
        )

    def handle_admin_confirmation(self, call):
        """Обработка подтверждения администратора"""
        action, user_id = call.data.split('_')[1], int(call.data.split('_')[2])

        if action == "confirm":
            self._complete_registration(user_id)
            self.bot.edit_message_text(
                "✅ Пользователь подтвержден",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            self._reject_registration(user_id)
            self.bot.edit_message_text(
                "❌ Регистрация отклонена",
                call.message.chat.id,
                call.message.message_id
            )

    def _complete_registration(self, user_id):
        """Завершение регистрации пользователя"""
        user_data = self.user_temp_data.get(user_id, {})

        # Сохраняем в основную таблицу
        query = """
            INSERT INTO users 
            (users_id, first_name, last_name, is_blocked, registration_date) 
            VALUES (%s, %s, %s, FALSE, NOW())
        """
        execute_query(
            query,
            (user_id, user_data['first_name'], user_data['last_name']),
            fetch=False
        )

        # Отправляем приветствие пользователю
        self.bot.send_message(
            user_id,
            f"Добро пожаловать, {user_data['first_name']} {user_data['last_name']}!\n"
            "Я бот для резервирования оборудования. Используй /help для получения списка команд.",
            reply_markup=self._get_main_keyboard()
        )

        # Очищаем временные данные
        if user_id in self.user_temp_data:
            del self.user_temp_data[user_id]

    def _reject_registration(self, user_id):
        """Отклонение регистрации"""
        self.bot.send_message(
            user_id,
            "⛔ Ваша регистрация была отклонена администратором."
        )
        if user_id in self.user_temp_data:
            del self.user_temp_data[user_id]

    def _get_main_keyboard(self):
    # """Главная клавиатура для зарегистрированных пользователей"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)

        # Первая строка
        btn_help = types.KeyboardButton('/help')

        # Вторая строка
        btn_booking = types.KeyboardButton('/booking')
        btn_cancel = types.KeyboardButton('/cancel')
        btn_finish = types.KeyboardButton('/finish')
        btn_extend = types.KeyboardButton('/продлить')

        # Третья строка
        btn_mybookings = types.KeyboardButton('/mybookings')
        btn_wsbookings = types.KeyboardButton('/workspacebookings')
        btn_datebookings = types.KeyboardButton('/datebookings')

        markup.add(btn_help)
        markup.add(btn_booking, btn_cancel, btn_finish, btn_extend)
        markup.add(btn_mybookings, btn_wsbookings, btn_datebookings)

        return markup