from typing import List, Tuple  # Добавлен импорт Tuple
from database import execute_query
from auth import is_admin
import logging

logger = logging.getLogger('broadcast')


def broadcast_message(bot, message):
    """Обработчик команды /broadcast"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Только администраторы могут использовать эту команду")
        return

    msg = bot.reply_to(message, "📢 Введите текст объявления:")
    bot.register_next_step_handler(msg, lambda m: process_announcement(bot, m))


def process_announcement(bot, message):
    """Отправляет сообщение всем пользователям"""
    announcement = message.text
    users = get_active_users()

    if not users:
        bot.reply_to(message, "ℹ️ Нет активных пользователей для рассылки")
        return

    failed_sends = []
    for user_id, in users:  # Обратите внимание на запятую - распаковка кортежа
        try:
            bot.send_message(user_id, announcement)
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            failed_sends.append(user_id)

    # Формирование отчета
    success_count = len(users) - len(failed_sends)
    report = f"✅ Отправлено: {success_count}/{len(users)}"

    if failed_sends:
        failed_list = ", ".join(map(str, failed_sends[:10]))  # Показываем первые 10 ошибок
        if len(failed_sends) > 10:
            failed_list += "..."
        report += f"\n❌ Ошибки: {failed_list}"

    bot.reply_to(message, report)


def get_active_users() -> List[Tuple[int]]:
    """Возвращает список активных пользователей"""
    query = "SELECT users_id FROM users WHERE is_blocked = FALSE"
    return execute_query(query) or []

# Можно также использовать более современный синтаксис:
# from typing import List
# def get_active_users() -> list[tuple[int]]:
#     ...