# --- START OF FILE test_admin_service.py ---

# tests/services/test_admin_service.py
import unittest
from unittest.mock import MagicMock, patch, mock_open, call
import logging
from datetime import datetime, date
import json
import os
import sys

# Импорты модулей
from services import user_service, booking_service
import telebot
from telebot import apihelper
from services import admin_service

# Проверка существования модуля
try:
    from database import Database, QueryResult
except ImportError:
    Database = object
    QueryResult = None

if not admin_service:
    raise ImportError("Модуль services.admin_service не найден")

# Класс для мокинга datetime
class MockDateTime(datetime):
    _mock_now = None
    @classmethod
    def set_now(cls, dt_to_set): cls._mock_now = dt_to_set
    @classmethod
    def now(cls, tz=None): return cls._mock_now if cls._mock_now else datetime.now(tz)
    @classmethod
    def reset_now(cls): cls._mock_now = None

# Настройка захвата логов
class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

class TestAdminService(unittest.TestCase):
    def setUp(self):
        # Настраиваем мок для logger
        self.logger_patcher = patch('services.admin_service.logger')
        self.mock_logger = self.logger_patcher.start()
        self.log_handler = LogCaptureHandler()
        # --- ИЗМЕНЕНИЕ: Добавляем **kwargs в лямбды ---
        self.mock_logger.debug = MagicMock(side_effect=lambda msg, *args, **kwargs: self.log_handler.emit(logging.LogRecord('BookingBot', logging.DEBUG, '', 0, msg % args if args else msg, args, None)))
        self.mock_logger.info = MagicMock(side_effect=lambda msg, *args, **kwargs: self.log_handler.emit(logging.LogRecord('BookingBot', logging.INFO, '', 0, msg % args if args else msg, args, None)))
        self.mock_logger.warning = MagicMock(side_effect=lambda msg, *args, **kwargs: self.log_handler.emit(logging.LogRecord('BookingBot', logging.WARNING, '', 0, msg % args if args else msg, args, None)))
        self.mock_logger.error = MagicMock(side_effect=lambda msg, *args, **kwargs: self.log_handler.emit(logging.LogRecord('BookingBot', logging.ERROR, '', 0, msg % args if args else msg, args, None)))
        # ---------------------------------------------
        # Привязываем обработчик к моку логгера
        # Важно: Не переопределяйте .handlers напрямую, если хотите добавить, а не заменить
        # Но для тестов замена может быть ОК. Оставим как было, но учтем это.
        self.mock_logger.handlers = [self.log_handler]
        # Устанавливаем уровень, чтобы все сообщения захватывались
        self.mock_logger.setLevel(logging.DEBUG)


        # Мок для datetime
        self.datetime_patcher = patch('services.admin_service.datetime', MockDateTime)
        self.datetime_patcher.start()

        # Моки для зависимостей
        self.mock_db = MagicMock(spec=Database)
        self.mock_telebot = MagicMock(spec=telebot.TeleBot)
        self.mock_telebot.send_message = MagicMock()
        self.mock_telebot.send_document = MagicMock()
        self.mock_telebot.delete_message = MagicMock()

    def tearDown(self):
        self.logger_patcher.stop()
        self.datetime_patcher.stop()
        MockDateTime.reset_now()

    # Тестовые данные
    ADMIN_CHAT_ID = 999999
    USER_ID_1 = 101; USER_ID_2 = 102; USER_ID_3_BLOCKED = 103; USER_ID_4_ERROR = 104
    MOCK_USERS_LIST = [
        {'users_id': USER_ID_1, 'fi': 'User One'}, {'users_id': USER_ID_2, 'fi': 'User Two'},
        {'users_id': USER_ID_3_BLOCKED, 'fi': 'User Three Blocked'}, {'users_id': USER_ID_4_ERROR, 'fi': 'User Four Error'},
    ]
    MESSAGE_TEXT = "Тестовое сообщение для рассылки!"
    MOCK_BOOKINGS_FOR_FORMAT = [
        {'booking_id': 1, 'user_id': 100, 'equip_id': 1, 'date': date(2024, 5, 15), 'time_interval': '10:00-11:00', 'name_equip': 'EQ1', 'user_fi': 'User A', 'cancel': False, 'finish': None, 'time_start': datetime(2024,5,15,10), 'time_end': datetime(2024,5,15,11)},
        {'booking_id': 2, 'user_id': 101, 'equip_id': 2, 'date': date(2024, 5, 15), 'time_interval': '12:00-13:00', 'name_equip': 'EQ2', 'user_fi': 'User B', 'cancel': True, 'finish': None, 'time_start': datetime(2024,5,15,12), 'time_end': datetime(2024,5,15,13)},
        {'booking_id': 3, 'user_id': 100, 'equip_id': 1, 'date': date(2024, 5, 16), 'time_interval': '14:00-15:00', 'name_equip': 'EQ1', 'user_fi': 'User A', 'cancel': False, 'finish': datetime.now(), 'time_start': datetime(2024,5,16,14), 'time_end': datetime(2024,5,16,15)},
    ]

    def test_broadcast_success_all(self):
        """Тест успешной рассылки всем пользователям."""
        with patch.object(user_service, 'get_all_users', return_value=self.MOCK_USERS_LIST) as mock_get_users, \
             patch.object(user_service, 'handle_user_blocked_bot') as mock_handle_block, \
             patch('services.admin_service.time.sleep'):

            success_count, error_count = admin_service.broadcast_message_to_users(
                self.mock_db, self.mock_telebot, self.MESSAGE_TEXT, self.ADMIN_CHAT_ID
            )

        self.assertEqual(success_count, 4)
        self.assertEqual(error_count, 0)
        mock_get_users.assert_called_once_with(self.mock_db, include_inactive=False)
        self.assertEqual(self.mock_telebot.send_message.call_count, 6)

        calls = self.mock_telebot.send_message.call_args_list
        admin_call_start = call(self.ADMIN_CHAT_ID, "Начинаю рассылку сообщения 4 пользователям...")
        admin_call_end = call(self.ADMIN_CHAT_ID, "📢 Рассылка завершена.\n✅ Успешно: 4\n❌ Ошибки: 0")
        self.assertEqual(calls[0], admin_call_start)
        self.assertEqual(calls[-1], admin_call_end)

        user_calls_args = [c.args for c in calls[1:-1]]
        expected_user_calls = [(self.USER_ID_1, self.MESSAGE_TEXT), (self.USER_ID_2, self.MESSAGE_TEXT),
                               (self.USER_ID_3_BLOCKED, self.MESSAGE_TEXT), (self.USER_ID_4_ERROR, self.MESSAGE_TEXT)]
        self.assertCountEqual([c[:2] for c in user_calls_args], expected_user_calls)

        mock_handle_block.assert_not_called()

        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        log_messages = [record.getMessage() for record in self.log_handler.records]
        # -----------------------------------------
        self.assertIn(f"Начало рассылки '{self.MESSAGE_TEXT[:30]}...' {len(self.MOCK_USERS_LIST)} пользователям.", log_messages)
        self.assertIn("Рассылка завершена. Успешно: 4, Ошибки: 0.", log_messages)

    def test_broadcast_some_failed(self):
        """Тест рассылки с ошибками для некоторых пользователей."""
        with patch.object(user_service, 'get_all_users', return_value=self.MOCK_USERS_LIST) as mock_get_users, \
             patch.object(user_service, 'handle_user_blocked_bot') as mock_handle_block, \
             patch('services.admin_service.time.sleep'):

            json_blocked = '{"ok":false,"error_code":403,"description":"Forbidden: bot was blocked by the user"}'
            json_not_found = '{"ok":false,"error_code":400,"description":"Bad Request: chat not found"}'
            def send_message_side_effect(chat_id, text, **kwargs):
                if chat_id == self.ADMIN_CHAT_ID:
                    return MagicMock()
                elif chat_id == self.USER_ID_3_BLOCKED:
                    raise apihelper.ApiTelegramException('sendMessage', json_blocked, json.loads(json_blocked))
                elif chat_id == self.USER_ID_4_ERROR:
                    raise apihelper.ApiTelegramException('sendMessage', json_not_found, json.loads(json_not_found))
                return MagicMock()
            self.mock_telebot.send_message.side_effect = send_message_side_effect

            success_count, error_count = admin_service.broadcast_message_to_users(
                self.mock_db, self.mock_telebot, self.MESSAGE_TEXT, self.ADMIN_CHAT_ID
            )

        self.assertEqual(success_count, 2)
        self.assertEqual(error_count, 2)
        mock_get_users.assert_called_once_with(self.mock_db, include_inactive=False)
        self.assertEqual(self.mock_telebot.send_message.call_count, 6)
        # Этот ассерт должен теперь проходить, если логика в admin_service исправлена
        mock_handle_block.assert_called_once_with(self.mock_db, self.USER_ID_3_BLOCKED)

        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        warning_messages = [record.getMessage() for record in self.log_handler.records if record.levelno == logging.WARNING]
        # -----------------------------------------
        self.assertIn(f"(3/4) Ошибка отправки {self.USER_ID_3_BLOCKED}: бот заблокирован.", warning_messages)
        self.assertIn(f"(4/4) Ошибка отправки {self.USER_ID_4_ERROR}: чат не найден.", warning_messages)

    def test_broadcast_no_active_users(self):
        """Тест рассылки, когда нет активных пользователей."""
        with patch.object(user_service, 'get_all_users', return_value=[]) as mock_get_users, \
             patch.object(user_service, 'handle_user_blocked_bot') as mock_handle_block:

            success_count, error_count = admin_service.broadcast_message_to_users(
                self.mock_db, self.mock_telebot, self.MESSAGE_TEXT, self.ADMIN_CHAT_ID
            )

        self.assertEqual(success_count, 0)
        self.assertEqual(error_count, 0)
        mock_get_users.assert_called_once_with(self.mock_db, include_inactive=False)
        self.mock_telebot.send_message.assert_called_once_with(self.ADMIN_CHAT_ID, "В системе нет активных пользователей для рассылки.")
        mock_handle_block.assert_not_called()

        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        log_messages = [record.getMessage() for record in self.log_handler.records]
        # -----------------------------------------
        self.assertIn("Нет активных пользователей для рассылки.", log_messages)

    def test_broadcast_unexpected_error(self):
        """Тест рассылки с непредвиденной ошибкой."""
        with patch.object(user_service, 'get_all_users', return_value=[self.MOCK_USERS_LIST[0]]) as mock_get_users, \
             patch.object(user_service, 'handle_user_blocked_bot') as mock_handle_block, \
             patch('services.admin_service.time.sleep'):

            test_error_message = "Unexpected network issue"
            def send_message_side_effect(chat_id, text, **kwargs):
                if chat_id == self.ADMIN_CHAT_ID:
                    return MagicMock()
                raise Exception(test_error_message)
            self.mock_telebot.send_message.side_effect = send_message_side_effect

            success_count, error_count = admin_service.broadcast_message_to_users(
                self.mock_db, self.mock_telebot, self.MESSAGE_TEXT, self.ADMIN_CHAT_ID
            )

        self.assertEqual(success_count, 0)
        self.assertEqual(error_count, 1)
        mock_get_users.assert_called_once_with(self.mock_db, include_inactive=False)
        self.assertEqual(self.mock_telebot.send_message.call_count, 3)
        mock_handle_block.assert_not_called()

        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        error_messages = [record.getMessage() for record in self.log_handler.records if record.levelno == logging.ERROR]
        # -----------------------------------------
        self.assertIn(f"(1/1) Неожиданная ошибка отправки для {self.USER_ID_1}: {test_error_message}", error_messages)

    # Тесты для get_filtered_bookings
    def test_get_filtered_bookings_success_users(self):
        """Тест успешного получения броней по пользователю."""
        self.mock_db.execute_query.return_value = [{'booking_id': 1}]
        results = admin_service.get_filtered_bookings(self.mock_db, "users", 123)
        self.assertEqual(results, [{'booking_id': 1}])
        self.mock_db.execute_query.assert_called_once()
        call_args, call_kwargs = self.mock_db.execute_query.call_args
        query, params = call_args[0], call_args[1]
        self.assertIn("WHERE u.users_id = %s", query)
        self.assertIn("ORDER BY b.date DESC, b.time_start DESC", query)
        self.assertEqual(params, (123,))
        self.assertTrue(call_kwargs.get('fetch_results'))

    def test_get_filtered_bookings_success_equipment(self):
        """Тест успешного получения броней по оборудованию."""
        self.mock_db.execute_query.return_value = [{'booking_id': 1}]
        results = admin_service.get_filtered_bookings(self.mock_db, "equipment", 45)
        self.assertEqual(results, [{'booking_id': 1}])
        self.mock_db.execute_query.assert_called_once()
        call_args, call_kwargs = self.mock_db.execute_query.call_args
        query, params = call_args[0], call_args[1]
        self.assertIn("WHERE e.id = %s", query)
        self.assertIn("ORDER BY b.date DESC, b.time_start DESC", query)
        self.assertEqual(params, (45,))
        self.assertTrue(call_kwargs.get('fetch_results'))

    def test_get_filtered_bookings_success_dates(self):
        """Тест успешного получения броней по дате (месяцу)."""
        self.mock_db.execute_query.return_value = [{'booking_id': 1}]
        results = admin_service.get_filtered_bookings(self.mock_db, "dates", "2024-05")
        self.assertEqual(results, [{'booking_id': 1}])
        self.mock_db.execute_query.assert_called_once()
        call_args, call_kwargs = self.mock_db.execute_query.call_args
        query, params = call_args[0], call_args[1]
        self.assertIn("WHERE TO_CHAR(b.date, 'YYYY-MM') = %s", query)
        self.assertIn("ORDER BY b.date DESC, b.time_start DESC", query)
        self.assertEqual(params, ("2024-05",))
        self.assertTrue(call_kwargs.get('fetch_results'))

    def test_get_filtered_bookings_no_results(self):
        """Тест получения пустого списка броней."""
        self.mock_db.execute_query.return_value = []
        results = admin_service.get_filtered_bookings(self.mock_db, "users", 123)
        self.assertEqual(results, [])
        self.mock_db.execute_query.assert_called_once()

    def test_get_filtered_bookings_invalid_filter(self):
        """Тест с невалидными типами или значениями фильтра."""
        test_cases = [
            ("invalid_type", 123), ("dates", "2024/05"), ("users", "abc"), ("equipment", "xyz")
        ]
        for filter_type, filter_value in test_cases:
            with self.subTest(filter_type=filter_type, filter_value=filter_value):
                self.mock_db.execute_query.reset_mock()
                self.log_handler.records.clear()
                results = admin_service.get_filtered_bookings(self.mock_db, filter_type, filter_value)
                self.assertEqual(results, [])
                self.mock_db.execute_query.assert_not_called()
                # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
                log_messages = [record.getMessage() for record in self.log_handler.records]
                # -----------------------------------------
                expected_msg_fragment = (f"Неизвестный тип фильтра: {filter_type}" if filter_type == "invalid_type"
                                         else f"Некорректное значение фильтра '{filter_value}' для типа '{filter_type}'")
                self.assertTrue(any(expected_msg_fragment in msg for msg in log_messages),
                                f"Expected log fragment '{expected_msg_fragment}' not found in logs: {log_messages}")

    def test_get_filtered_bookings_db_error(self):
        """Тест ошибки базы данных при получении броней."""
        self.mock_db.execute_query.side_effect = Exception("DB Query Error")
        results = admin_service.get_filtered_bookings(self.mock_db, "equipment", 1)
        self.assertEqual(results, [])
        self.mock_db.execute_query.assert_called_once()
        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        error_messages = [record.getMessage() for record in self.log_handler.records if record.levelno == logging.ERROR]
        # -----------------------------------------
        self.assertIn("Ошибка при выполнении запроса get_filtered_bookings: DB Query Error", error_messages)

    # Тесты для format_bookings_to_file_content
    def test_format_bookings_to_file_content_success(self):
        """Тест успешного форматирования списка броней в текст."""
        filter_details = "Пользователь: User A"
        with patch.object(booking_service, 'format_booking_info',
                         side_effect=lambda eq, dt, ts, te, un: f"FMT: {eq}/{booking_service._format_date(dt)}/{booking_service._format_time(ts)}-{booking_service._format_time(te)}/{un}"):
            fixed_now = datetime(2024, 5, 15, 16, 30, 0)
            MockDateTime.set_now(fixed_now)

            content = admin_service.format_bookings_to_file_content(self.MOCK_BOOKINGS_FOR_FORMAT, filter_details)

            self.assertIn("Отчет по бронированиям", content)
            self.assertIn(f"Фильтр: {filter_details}", content)
            self.assertIn(f"Сформирован: {fixed_now.strftime('%Y-%m-%d %H:%M:%S')}", content)
            self.assertIn("="*50, content)
            self.assertIn("FMT: EQ1/15-05-2024/10:00-11:00/User A\n", content)
            self.assertIn("FMT: EQ2/15-05-2024/12:00-13:00/User B [ОТМЕНЕНО]\n", content)
            self.assertIn("FMT: EQ1/16-05-2024/14:00-15:00/User A [ЗАВЕРШЕНО]\n", content)
            self.assertEqual(booking_service.format_booking_info.call_count, len(self.MOCK_BOOKINGS_FOR_FORMAT))

    def test_format_bookings_to_file_content_empty_list(self):
        """Тест форматирования пустого списка броней."""
        with patch.object(booking_service, 'format_booking_info') as mock_formatter:
            fixed_now = datetime(2024, 5, 15, 16, 30, 0)
            MockDateTime.set_now(fixed_now)
            content = admin_service.format_bookings_to_file_content([], "Фильтр: Пусто")
            self.assertIn("Отчет по бронированиям", content)
            self.assertIn("Нет бронирований по выбранному фильтру.", content)
            mock_formatter.assert_not_called()

    def test_format_bookings_to_file_content_formatter_error(self):
        """Тест ошибки при форматировании отдельной строки брони."""
        with patch.object(booking_service, 'format_booking_info', side_effect=Exception("Formatter error")):
            fixed_now = datetime(2024, 5, 15, 16, 30, 0)
            MockDateTime.set_now(fixed_now)

            content = admin_service.format_bookings_to_file_content([self.MOCK_BOOKINGS_FOR_FORMAT[0]], "Фильтр: Ошибка")

            self.assertIn("Отчет по бронированиям", content)
            self.assertIn(f"Ошибка форматирования: ID={self.MOCK_BOOKINGS_FOR_FORMAT[0]['booking_id']}", content)
            # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
            error_messages = [record.getMessage() for record in self.log_handler.records if record.levelno == logging.ERROR]
            # -----------------------------------------
            self.assertIn(f"Ошибка форматирования строки для booking_id {self.MOCK_BOOKINGS_FOR_FORMAT[0]['booking_id']}: Formatter error", error_messages)

    # Тесты для create_bookings_report_file
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.path.abspath")
    @patch("services.admin_service.format_bookings_to_file_content")
    def test_create_bookings_report_file_success(self, mock_formatter, mock_abspath, mock_open_file):
        """Тест успешного создания файла отчета."""
        mock_bookings_data = [{'id': 1}]; filter_details = "Фильтр X"; formatted_content = "Контент"
        fixed_timestamp = "20240515_123000"; expected_filename = f"bookings_report_{fixed_timestamp}.txt"; expected_filepath = f"/fake/path/{expected_filename}"
        mock_formatter.return_value = formatted_content
        with patch('services.admin_service.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = fixed_timestamp
            mock_abspath.return_value = expected_filepath

            filepath = admin_service.create_bookings_report_file(mock_bookings_data, filter_details)

            self.assertEqual(filepath, expected_filepath)
            mock_formatter.assert_called_once_with(mock_bookings_data, filter_details)
            mock_open_file.assert_called_once_with(expected_filepath, "w", encoding="utf-8")
            handle = mock_open_file(); handle.write.assert_called_once_with(formatted_content)
            mock_abspath.assert_called_once_with(expected_filename)
            # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
            log_messages = [record.getMessage() for record in self.log_handler.records]
            # -----------------------------------------
            self.assertTrue(any(f"Отчет по бронированиям сохранен в файл: {expected_filepath}" in msg for msg in log_messages))

    @patch("services.admin_service.format_bookings_to_file_content", side_effect=Exception("Format error"))
    def test_create_bookings_report_file_formatter_error(self, mock_formatter):
        """Тест ошибки при форматировании контента для файла."""
        filepath = admin_service.create_bookings_report_file([{'id': 1}], "Фильтр")
        self.assertIsNone(filepath)
        mock_formatter.assert_called_once()
        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        error_messages = [record.getMessage() for record in self.log_handler.records if record.levelno == logging.ERROR]
        # -----------------------------------------
        self.assertIn("Неожиданная ошибка при создании файла отчета: Format error", error_messages)

    @patch("builtins.open", side_effect=IOError("Permission denied"))
    @patch("os.path.abspath", return_value="/fake/path/report.txt")
    @patch("services.admin_service.format_bookings_to_file_content", return_value="content")
    def test_create_bookings_report_file_io_error(self, mock_formatter, mock_abspath, mock_open_file):
        """Тест ошибки ввода-вывода при записи файла."""
        filepath = admin_service.create_bookings_report_file([{'id': 1}], "Фильтр")
        self.assertIsNone(filepath)
        mock_formatter.assert_called_once()
        mock_open_file.assert_called_once()
        # --- ИЗМЕНЕНИЕ: Используем getMessage() ---
        error_messages = [record.getMessage() for record in self.log_handler.records if record.levelno == logging.ERROR]
        # -----------------------------------------
        self.assertTrue(any("Ошибка записи отчета в файл" in msg and "Permission denied" in msg for msg in error_messages))

if __name__ == '__main__':
    unittest.main()

# --- END OF FILE test_admin_service.py ---