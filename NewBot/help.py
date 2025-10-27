from telebot import types
from auth import is_admin
import logging

logger = logging.getLogger('help')


class HelpSystem:
    def __init__(self, bot):
        self.bot = bot
        self.commands = {
            'user': {
                '/booking': 'Резервирование оборудования',
                '/cancel': 'Отмена будущих бронирований',
                '/продлить': 'Продление текущего бронирования',
                '/finish': 'Завершение работы на оборудовании',
                '/mybookings': 'Ваши активные бронирования',
                '/workspacebookings': 'Бронирования по оборудованию',
                '/datebookings': 'Бронирования на конкретную дату',
                '/help': 'Показать эту справку'
            },
            'admin': {
                '/add_equipment': 'Добавление оборудования',
                '/view_equipment': 'Просмотр оборудования',
                '/admin_cancel': 'Отмена любых бронирований',
                '/all': 'Расширенный просмотр бронирований',
                '/broadcast': 'Рассылка сообщений',
                '/schedule': 'Управление расписанием',
                '/manage_user': 'Управление пользователями',
                '/users': 'Список пользователей'
            }
        }

    def generate_help_message(self, is_admin_user=False):
        """Генерирует сообщение справки"""
        message = "📚 <b>Основные команды:</b>\n\n"

        # Команды для обычных пользователей
        for cmd, desc in self.commands['user'].items():
            message += f"▪️ <code>{cmd}</code> - {desc}\n"

        # Команды для администраторов
        if is_admin_user:
            message += "\n👨‍💼 <b>Административные команды:</b>\n\n"
            for cmd, desc in self.commands['admin'].items():
                message += f"▫️ <code>{cmd}</code> - {desc}\n"

        message += "\nℹ️ Для подробностей введите команду без параметров"
        return message

    def handle_help(self, message):
        """Обработка команды /help"""
        try:
            user_id = message.from_user.id
            help_text = self.generate_help_message(is_admin(user_id))

            markup = types.InlineKeyboardMarkup()
            if is_admin(user_id):
                markup.add(types.InlineKeyboardButton(
                    "Админ-справка",
                    callback_data="admin_help"
                ))

            self.bot.send_message(
                message.chat.id,
                help_text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error in handle_help: {e}")
            self.bot.reply_to(message, "⚠️ Произошла ошибка при получении справки")

    def handle_admin_help(self, message):
        """Обработка команды /adminhelp"""
        if not is_admin(message.from_user.id):
            self.bot.reply_to(message, "⛔ Недостаточно прав")
            return

        try:
            admin_help = "👨‍💼 <b>Административные команды:</b>\n\n"
            for cmd, desc in self.commands['admin'].items():
                admin_help += f"▫️ <code>{cmd}</code> - {desc}\n"

            self.bot.send_message(
                message.chat.id,
                admin_help,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error in handle_admin_help: {e}")
            self.bot.reply_to(message, "⚠️ Ошибка при получении админ-справки")

    def handle_callback(self, call):
        """Обработка inline-кнопок"""
        if call.data == "admin_help":
            self.handle_admin_help(call.message)
            self.bot.answer_callback_query(call.id)

    def setup_commands(self):
        """Установка списка команд для меню бота"""
        commands = []
        for cmd, desc in self.commands['user'].items():
            commands.append(types.BotCommand(cmd[1:], desc))

        try:
            self.bot.set_my_commands(commands)
            logger.info("Bot commands set up successfully")
        except Exception as e:
            logger.error(f"Error setting bot commands: {e}")