# tests/services/test_user_service.py

import pytest
from unittest.mock import MagicMock, call, patch # Добавили patch
from datetime import datetime
import datetime as dt_original # Для MockDateTime
import logging
from typing import List, Tuple, Optional, Dict, Any # Добавили импорты

# Импортируем тестируемый модуль
from services import user_service

# Импортируем QueryResult для type hinting
try:
    from database import QueryResult
except ImportError:
     QueryResult = Optional[List[Dict[str, Any]]] # Fallback


# --- Класс для мокинга datetime ---
class MockDateTime(dt_original.datetime):
    _mock_now = None
    @classmethod
    def set_now(cls, dt_to_set):
        if not isinstance(dt_to_set, dt_original.datetime):
            raise TypeError(f"MockDateTime.set_now ожидает datetime, получил {type(dt_to_set)}")
        cls._mock_now = dt_to_set
        # log.debug(f"MockDateTime.now установлен на: {cls._mock_now}") # Раскомментировать для отладки тестов
    @classmethod
    def now(cls, tz=None):
        dt_now = cls._mock_now if cls._mock_now else dt_original.datetime.now(tz)
        # log.debug(f"MockDateTime.now() вызван, возвращает: {dt_now}") # Раскомментировать для отладки тестов
        return dt_now
    @classmethod
    def reset_now(cls):
        # log.debug(f"MockDateTime.now сброшен (был: {cls._mock_now})") # Раскомментировать для отладки тестов
        cls._mock_now = None

@pytest.fixture(autouse=True)
def auto_mock_datetime_now(mocker):
    """Автоматически патчит datetime.datetime на MockDateTime в user_service."""
    # Патчим datetime внутри модуля user_service
    mock = mocker.patch('services.user_service.datetime', MockDateTime)
    yield mock
    MockDateTime.reset_now() # Сбрасываем после теста
# --- Конец MockDateTime ---

try:
    from database import Database
except ImportError:
    Database = object # Заглушка, если класс не импортируется напрямую

# Настройка логирования для тестов
log = logging.getLogger("TestUserService")

# --- Тестовые данные ---
TEST_USER_ID_ACTIVE = 100
TEST_USER_ID_BLOCKED = 101
TEST_USER_ID_ADMIN = 200
TEST_USER_ID_NOT_ADMIN = 201
TEST_USER_ID_TEMP = 300
TEST_USER_ID_NON_EXISTENT = 999

MOCK_USER_ACTIVE = {
    'users_id': TEST_USER_ID_ACTIVE, 'first_name': 'Иван', 'last_name': 'Петров',
    'fi': 'Иван Петров', 'is_blocked': False, 'is_admin': False, 'date': datetime(2024, 1, 1)
}
MOCK_USER_BLOCKED = {
    'users_id': TEST_USER_ID_BLOCKED, 'first_name': 'Сидор', 'last_name': 'Иванов',
    'fi': 'Сидор Иванов', 'is_blocked': True, 'is_admin': False, 'date': datetime(2024, 1, 2)
}
MOCK_USER_ADMIN = {
    'users_id': TEST_USER_ID_ADMIN, 'first_name': 'Admin', 'last_name': 'Adminson',
    'fi': 'Admin Adminson', 'is_blocked': False, 'is_admin': True, 'date': datetime(2024, 1, 3)
}
MOCK_USER_NOT_ADMIN = {
    'users_id': TEST_USER_ID_NOT_ADMIN, 'first_name': 'Не', 'last_name': 'Админ',
    'fi': 'Не Админ', 'is_blocked': False, 'is_admin': False, 'date': datetime(2024, 1, 4)
}
MOCK_USER_TEMP = {
    'users_id': TEST_USER_ID_TEMP, 'first_name': 'Временный', 'last_name': 'Пользователь',
    'fi': 'Временный Пользователь', 'date': datetime(2024, 1, 5)
}


# --- Фикстура для мока DB ---
@pytest.fixture
def mock_db(mocker):
    """Фикстура для создания мока Database."""
    return mocker.Mock(spec=Database)


# --- Тесты для is_user_registered_and_active ---

def test_is_user_registered_and_active_true(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [{'exists': True}]
    user_id = TEST_USER_ID_ACTIVE
    # Act
    result = user_service.is_user_registered_and_active(mock_db, user_id)
    # Assert
    assert result is True
    mock_db.execute_query.assert_called_once_with(
        "SELECT EXISTS (SELECT 1 FROM users WHERE users_id = %s AND is_blocked = FALSE);",
        (user_id,),
        fetch_results=True
    )

def test_is_user_registered_and_active_false_blocked(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [{'exists': False}] # Запрос вернет false, т.к. is_blocked=TRUE
    user_id = TEST_USER_ID_BLOCKED
    # Act
    result = user_service.is_user_registered_and_active(mock_db, user_id)
    # Assert
    assert result is False
    mock_db.execute_query.assert_called_once_with(
        "SELECT EXISTS (SELECT 1 FROM users WHERE users_id = %s AND is_blocked = FALSE);",
        (user_id,),
        fetch_results=True
    )

def test_is_user_registered_and_active_false_non_existent(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [{'exists': False}] # Запрос вернет false
    user_id = TEST_USER_ID_NON_EXISTENT
    # Act
    result = user_service.is_user_registered_and_active(mock_db, user_id)
    # Assert
    assert result is False
    mock_db.execute_query.assert_called_once()

def test_is_user_registered_and_active_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Connection Error")
    user_id = TEST_USER_ID_ACTIVE
    # Act
    result = user_service.is_user_registered_and_active(mock_db, user_id)
    # Assert
    assert result is False
    assert "Ошибка при проверке статуса пользователя" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для is_admin ---

def test_is_admin_true(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [{'is_admin': True}]
    user_id = TEST_USER_ID_ADMIN
    # Act
    result = user_service.is_admin(mock_db, user_id)
    # Assert
    assert result is True
    mock_db.execute_query.assert_called_once_with(
        "SELECT is_admin FROM users WHERE users_id = %s AND is_blocked = FALSE;",
        (user_id,),
        fetch_results=True
    )

def test_is_admin_false_not_admin(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [{'is_admin': False}]
    user_id = TEST_USER_ID_NOT_ADMIN
    # Act
    result = user_service.is_admin(mock_db, user_id)
    # Assert
    assert result is False
    mock_db.execute_query.assert_called_once()

def test_is_admin_false_blocked_admin(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [] # Активный админ не найден (т.к. is_blocked=TRUE)
    user_id = TEST_USER_ID_ADMIN # ID админа, но он заблокирован
    # Act
    result = user_service.is_admin(mock_db, user_id)
    # Assert
    assert result is False
    mock_db.execute_query.assert_called_once()

def test_is_admin_false_non_existent(mock_db):
    # Arrange
    mock_db.execute_query.return_value = []
    user_id = TEST_USER_ID_NON_EXISTENT
    # Act
    result = user_service.is_admin(mock_db, user_id)
    # Assert
    assert result is False
    mock_db.execute_query.assert_called_once()

def test_is_admin_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    user_id = TEST_USER_ID_ADMIN
    # Act
    result = user_service.is_admin(mock_db, user_id)
    # Assert
    assert result is False
    assert "Ошибка при проверке прав админа" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для get_user_info ---

def test_get_user_info_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [MOCK_USER_ACTIVE]
    user_id = TEST_USER_ID_ACTIVE
    # Act
    result = user_service.get_user_info(mock_db, user_id)
    # Assert
    assert result == MOCK_USER_ACTIVE
    mock_db.execute_query.assert_called_once_with(
        "SELECT users_id, first_name, last_name, fi, is_blocked, is_admin, date FROM users WHERE users_id = %s;",
        (user_id,),
        fetch_results=True
    )

def test_get_user_info_not_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = []
    user_id = TEST_USER_ID_NON_EXISTENT
    # Act
    result = user_service.get_user_info(mock_db, user_id)
    # Assert
    assert result is None
    mock_db.execute_query.assert_called_once()

def test_get_user_info_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    user_id = TEST_USER_ID_ACTIVE
    # Act
    result = user_service.get_user_info(mock_db, user_id)
    # Assert
    assert result is None
    assert "Ошибка при получении информации о пользователе" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для get_all_users ---

def test_get_all_users_active_only_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [MOCK_USER_ACTIVE, MOCK_USER_ADMIN, MOCK_USER_NOT_ADMIN]
    # Act
    result = user_service.get_all_users(mock_db, include_inactive=False)
    # Assert
    assert result == [MOCK_USER_ACTIVE, MOCK_USER_ADMIN, MOCK_USER_NOT_ADMIN]
    mock_db.execute_query.assert_called_once_with(
        "SELECT users_id, first_name, last_name, fi, is_blocked, is_admin, date FROM users WHERE is_blocked = FALSE ORDER BY fi;",
        fetch_results=True
    )

def test_get_all_users_active_only_not_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = []
    # Act
    result = user_service.get_all_users(mock_db) # include_inactive=False по умолчанию
    # Assert
    assert result == []
    mock_db.execute_query.assert_called_once()

def test_get_all_users_include_inactive_found(mock_db):
    # Arrange
    expected_users = [MOCK_USER_ACTIVE, MOCK_USER_ADMIN, MOCK_USER_BLOCKED, MOCK_USER_NOT_ADMIN]
    # Сортируем ожидаемый результат по 'fi' для сравнения
    expected_users_sorted = sorted(expected_users, key=lambda x: x.get('fi') or '')
    mock_db.execute_query.return_value = expected_users_sorted
    # Act
    result = user_service.get_all_users(mock_db, include_inactive=True)
    # Assert
    assert result == expected_users_sorted
    mock_db.execute_query.assert_called_once_with(
        "SELECT users_id, first_name, last_name, fi, is_blocked, is_admin, date FROM users ORDER BY fi;",
        fetch_results=True
    )

def test_get_all_users_include_inactive_not_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = []
    # Act
    result = user_service.get_all_users(mock_db, include_inactive=True)
    # Assert
    assert result == []
    mock_db.execute_query.assert_called_once()

def test_get_all_users_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    # Act
    result_active = user_service.get_all_users(mock_db)
    result_all = user_service.get_all_users(mock_db, include_inactive=True)
    # Assert
    assert result_active == []
    assert result_all == []
    assert "Ошибка получения списка пользователей" in caplog.text
    assert mock_db.execute_query.call_count == 2

# --- Тесты для get_user_details_for_management ---

@pytest.mark.parametrize("user_data, expected_fi, expected_blocked", [
    (MOCK_USER_ACTIVE, MOCK_USER_ACTIVE['fi'], MOCK_USER_ACTIVE['is_blocked']),
    (MOCK_USER_BLOCKED, MOCK_USER_BLOCKED['fi'], MOCK_USER_BLOCKED['is_blocked']),
    (MOCK_USER_ADMIN, MOCK_USER_ADMIN['fi'], MOCK_USER_ADMIN['is_blocked']),
    ({'users_id': 5, 'first_name': 'Тест', 'last_name': 'Тестов', 'is_blocked': False, 'fi': None}, "Тест Тестов", False), # fi is None
    ({'users_id': 6, 'first_name': 'Одинокий', 'last_name': None, 'is_blocked': True, 'fi': 'Одинокий'}, "Одинокий", True), # last_name is None, fi exists
    ({'users_id': 7, 'is_blocked': False, 'first_name': None, 'last_name': None, 'fi': None}, "ID 7", False), # All names None
    ({'users_id': 8, 'fi': 'Нет Статуса'}, "Нет Статуса", True), # is_blocked missing, defaults to True
])
def test_get_user_details_for_management_found(mocker, user_data, expected_fi, expected_blocked):
    # Arrange
    mock_db = mocker.Mock(spec=Database)
    # Мокируем get_user_info, так как эта функция его использует
    mocker.patch('services.user_service.get_user_info', return_value=user_data)
    user_id = user_data['users_id']
    # Act
    result = user_service.get_user_details_for_management(mock_db, user_id)
    # Assert
    assert result == (expected_fi, expected_blocked)
    user_service.get_user_info.assert_called_once_with(mock_db, user_id)

def test_get_user_details_for_management_not_found(mocker):
    # Arrange
    mock_db = mocker.Mock(spec=Database)
    # Мокируем get_user_info
    mocker.patch('services.user_service.get_user_info', return_value=None)
    user_id = TEST_USER_ID_NON_EXISTENT
    # Act
    result = user_service.get_user_details_for_management(mock_db, user_id)
    # Assert
    assert result is None
    user_service.get_user_info.assert_called_once_with(mock_db, user_id)

# --- Тесты для get_admin_ids ---

def test_get_admin_ids_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [{'users_id': TEST_USER_ID_ADMIN}, {'users_id': 555}]
    # Act
    result = user_service.get_admin_ids(mock_db)
    # Assert
    assert result == [TEST_USER_ID_ADMIN, 555]
    mock_db.execute_query.assert_called_once_with(
        "SELECT users_id FROM users WHERE is_admin = TRUE AND is_blocked = FALSE;",
        fetch_results=True
    )

def test_get_admin_ids_not_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = []
    # Act
    result = user_service.get_admin_ids(mock_db)
    # Assert
    assert result == []
    mock_db.execute_query.assert_called_once()

def test_get_admin_ids_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    # Act
    result = user_service.get_admin_ids(mock_db)
    # Assert
    assert result == []
    assert "Ошибка при получении ID администраторов" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для find_temp_user ---

def test_find_temp_user_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = [MOCK_USER_TEMP]
    user_id = TEST_USER_ID_TEMP
    # Act
    result = user_service.find_temp_user(mock_db, user_id)
    # Assert
    assert result == MOCK_USER_TEMP
    mock_db.execute_query.assert_called_once_with(
        "SELECT users_id, first_name, last_name, fi, date FROM users_temp WHERE users_id = %s;",
        (user_id,),
        fetch_results=True
    )

def test_find_temp_user_not_found(mock_db):
    # Arrange
    mock_db.execute_query.return_value = []
    user_id = TEST_USER_ID_NON_EXISTENT
    # Act
    result = user_service.find_temp_user(mock_db, user_id)
    # Assert
    assert result is None
    mock_db.execute_query.assert_called_once()

def test_find_temp_user_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    user_id = TEST_USER_ID_TEMP
    # Act
    result = user_service.find_temp_user(mock_db, user_id)
    # Assert
    assert result is None
    assert "Ошибка при поиске временного пользователя" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для register_temporary_user ---

def test_register_temporary_user_success(mock_db):
    # Arrange
    mock_db.execute_query.return_value = None # INSERT без RETURNING (или мы не проверяем)
    fixed_time = datetime(2024, 5, 1, 12, 0, 0)
    MockDateTime.set_now(fixed_time) # Устанавливаем мок времени

    user_id = TEST_USER_ID_TEMP
    first = MOCK_USER_TEMP['first_name']
    last = MOCK_USER_TEMP['last_name']
    fi = MOCK_USER_TEMP['fi']
    # Act
    result = user_service.register_temporary_user(mock_db, user_id, first, last, fi)
    # Assert
    assert result is True
    expected_query_start = "INSERT INTO users_temp"
    expected_on_conflict = "ON CONFLICT (users_id) DO UPDATE SET"
    mock_db.execute_query.assert_called_once()
    call_args, call_kwargs = mock_db.execute_query.call_args
    # Проверяем части запроса и параметры
    actual_query = " ".join(call_args[0].split()) # Нормализуем пробелы
    assert actual_query.startswith(expected_query_start)
    assert expected_on_conflict in actual_query
    assert call_args[1] == (user_id, first, last, fixed_time, fi)
    assert call_kwargs.get('commit') is True # Проверяем commit=True

def test_register_temporary_user_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    user_id = TEST_USER_ID_TEMP
    first = MOCK_USER_TEMP['first_name']
    last = MOCK_USER_TEMP['last_name']
    fi = MOCK_USER_TEMP['fi']
    # Act
    result = user_service.register_temporary_user(mock_db, user_id, first, last, fi)
    # Assert
    assert result is False
    assert "Ошибка при временной регистрации пользователя" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для confirm_registration ---
def test_confirm_registration_success(mocker, mock_db):
    # Arrange
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # Мокируем find_temp_user, чтобы он вернул данные
    mocker.patch('services.user_service.find_temp_user', return_value=MOCK_USER_TEMP)
    # Настраиваем мок для транзакции
    mock_db.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor # Для with context manager

    user_id = MOCK_USER_TEMP['users_id']; first = MOCK_USER_TEMP['first_name']; last = MOCK_USER_TEMP['last_name']; date_reg = MOCK_USER_TEMP['date']; fi = MOCK_USER_TEMP['fi']

    # Act
    success, user_data = user_service.confirm_registration(mock_db, user_id)

    # Assert
    assert success is True
    assert user_data is not None
    assert user_data['users_id'] == user_id
    assert user_data['fi'] == fi
    user_service.find_temp_user.assert_called_once_with(mock_db, user_id)
    mock_db.get_connection.assert_called_once()
    # Проверяем вызовы курсора
    assert mock_cursor.execute.call_count == 2
    # Проверяем первый вызов (INSERT)
    insert_call = mock_cursor.execute.call_args_list[0]
    insert_query_called = " ".join(insert_call.args[0].split())
    assert insert_query_called.startswith("INSERT INTO users")
    assert insert_query_called.endswith("is_blocked = FALSE;")
    assert insert_call.args[1] == (user_id, first, last, date_reg, fi)
    # Проверяем второй вызов (DELETE)
    delete_call = mock_cursor.execute.call_args_list[1]
    delete_query_called = " ".join(delete_call.args[0].split())
    assert delete_query_called == "DELETE FROM users_temp WHERE users_id = %s;"
    assert delete_call.args[1] == (user_id,)
    # Проверяем commit и release
    mock_conn.commit.assert_called_once()
    mock_conn.rollback.assert_not_called()
    mock_db.release_connection.assert_called_once_with(mock_conn)

def test_confirm_registration_temp_not_found(mocker):
    # Arrange
    mock_db = mocker.Mock(spec=Database)
    # find_temp_user вернет None
    mocker.patch('services.user_service.find_temp_user', return_value=None)
    mock_db.get_connection = MagicMock() # Мокаем, чтобы проверить, что он не вызывается
    # Act
    success, user_data = user_service.confirm_registration(mock_db, TEST_USER_ID_TEMP)
    # Assert
    assert success is False
    assert user_data is None
    user_service.find_temp_user.assert_called_once_with(mock_db, TEST_USER_ID_TEMP)
    mock_db.get_connection.assert_not_called() # Транзакция не должна начаться

def test_confirm_registration_insert_error(mocker, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db = mocker.Mock(spec=Database); mock_conn = MagicMock(); mock_cursor = MagicMock()
    mocker.patch('services.user_service.find_temp_user', return_value=MOCK_USER_TEMP)
    mock_db.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    # Имитируем ошибку при первом execute (INSERT)
    mock_cursor.execute.side_effect = Exception("Insert Error")
    user_id = MOCK_USER_TEMP['users_id']
    # Act
    success, user_data = user_service.confirm_registration(mock_db, user_id)
    # Assert
    assert success is False; assert user_data is None; assert "Ошибка при подтверждении регистрации" in caplog.text
    mock_db.get_connection.assert_called_once(); mock_cursor.execute.assert_called_once() # Только один вызов execute
    mock_conn.commit.assert_not_called(); mock_conn.rollback.assert_called_once() # Должен быть rollback
    mock_db.release_connection.assert_called_once_with(mock_conn)

def test_confirm_registration_delete_error(mocker, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db = mocker.Mock(spec=Database); mock_conn = MagicMock(); mock_cursor = MagicMock()
    mocker.patch('services.user_service.find_temp_user', return_value=MOCK_USER_TEMP)
    mock_db.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    # Имитируем ошибку при втором execute (DELETE)
    mock_cursor.execute.side_effect = [None, Exception("Delete Error")]
    user_id = MOCK_USER_TEMP['users_id']
    # Act
    success, user_data = user_service.confirm_registration(mock_db, user_id)
    # Assert
    assert success is False; assert user_data is None; assert "Ошибка при подтверждении регистрации" in caplog.text
    mock_db.get_connection.assert_called_once(); assert mock_cursor.execute.call_count == 2 # Оба вызова были
    mock_conn.commit.assert_not_called(); mock_conn.rollback.assert_called_once() # Должен быть rollback
    mock_db.release_connection.assert_called_once_with(mock_conn)

# --- Тесты для decline_registration ---
def test_decline_registration_success(mock_db):
    # Arrange
    mock_db.execute_query.return_value = 1 # Предполагаем, что execute_query возвращает rowcount
    user_id = TEST_USER_ID_TEMP
    # Act
    result = user_service.decline_registration(mock_db, user_id)
    # Assert
    assert result is True
    mock_db.execute_query.assert_called_once_with("DELETE FROM users_temp WHERE users_id = %s;", (user_id,), commit=True)

def test_decline_registration_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    user_id = TEST_USER_ID_TEMP
    # Act
    result = user_service.decline_registration(mock_db, user_id)
    # Assert
    assert result is False; assert "Ошибка при отклонении регистрации" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для find_or_register_user ---
def test_find_or_register_user_found_in_users(mocker, mock_db):
    # Arrange
    # get_user_info находит пользователя
    mocker.patch('services.user_service.get_user_info', return_value=MOCK_USER_ACTIVE)
    mock_find_temp = mocker.patch('services.user_service.find_temp_user')
    # Act
    is_pending, user_info = user_service.find_or_register_user(mock_db, TEST_USER_ID_ACTIVE, "ivan", "Иван", "Петров")
    # Assert
    assert is_pending is False; assert user_info == MOCK_USER_ACTIVE
    user_service.get_user_info.assert_called_once_with(mock_db, TEST_USER_ID_ACTIVE)
    mock_find_temp.assert_not_called() # find_temp_user не должен вызываться

def test_find_or_register_user_found_in_temp(mocker, mock_db):
    # Arrange
    # get_user_info не находит
    mocker.patch('services.user_service.get_user_info', return_value=None)
    # find_temp_user находит
    mocker.patch('services.user_service.find_temp_user', return_value=MOCK_USER_TEMP)
    # Act
    is_pending, user_info = user_service.find_or_register_user(mock_db, TEST_USER_ID_TEMP, "temp", "Временный", "Пользователь")
    # Assert
    assert is_pending is True; assert user_info is None
    user_service.get_user_info.assert_called_once_with(mock_db, TEST_USER_ID_TEMP)
    user_service.find_temp_user.assert_called_once_with(mock_db, TEST_USER_ID_TEMP)

def test_find_or_register_user_not_found_anywhere(mocker, mock_db):
    # Arrange
    mocker.patch('services.user_service.get_user_info', return_value=None)
    mocker.patch('services.user_service.find_temp_user', return_value=None)
    # Act
    is_pending, user_info = user_service.find_or_register_user(mock_db, TEST_USER_ID_NON_EXISTENT, "new", "Новый", "Юзер")
    # Assert
    assert is_pending is True; assert user_info is None
    user_service.get_user_info.assert_called_once_with(mock_db, TEST_USER_ID_NON_EXISTENT)
    user_service.find_temp_user.assert_called_once_with(mock_db, TEST_USER_ID_NON_EXISTENT)

def test_find_or_register_user_get_info_error(mocker, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    # get_user_info выбрасывает исключение
    mocker.patch('services.user_service.get_user_info', side_effect=Exception("DB Error during get_user_info"))
    mock_find_temp = mocker.patch('services.user_service.find_temp_user')
    # Act
    is_pending, user_info = user_service.find_or_register_user(mock_db, TEST_USER_ID_ACTIVE, "ivan", "Иван", "Петров")
    # Assert
    assert is_pending is False # Ожидаем False, т.к. ошибка произошла до проверки temp
    assert user_info is None
    assert "Ошибка в find_or_register_user" in caplog.text # Проверяем лог основной функции
    user_service.get_user_info.assert_called_once()
    mock_find_temp.assert_not_called() # find_temp_user не должен был вызваться

def test_find_or_register_user_find_temp_error(mocker, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    # get_user_info возвращает None (не найден)
    mocker.patch('services.user_service.get_user_info', return_value=None)
    # find_temp_user выбрасывает исключение
    mocker.patch('services.user_service.find_temp_user', side_effect=Exception("DB Error during find_temp_user"))
    # Act
    is_pending, user_info = user_service.find_or_register_user(mock_db, TEST_USER_ID_TEMP, "temp", "Временный", "Пользователь")
    # Assert
    assert is_pending is False # Ожидаем False при ошибке
    assert user_info is None
    assert "Ошибка в find_or_register_user" in caplog.text # Проверяем лог основной функции
    user_service.get_user_info.assert_called_once()
    user_service.find_temp_user.assert_called_once()

# --- Тесты для update_user_block_status ---
@pytest.mark.parametrize("block_status", [True, False])
def test_update_user_block_status_success(mock_db, block_status):
    # Arrange
    mock_db.execute_query.return_value = 1 # Предполагаем возврат rowcount
    user_id = TEST_USER_ID_ACTIVE
    # Act
    result = user_service.update_user_block_status(mock_db, user_id, block=block_status)
    # Assert
    assert result is True
    mock_db.execute_query.assert_called_once_with(
        "UPDATE users SET is_blocked = %s WHERE users_id = %s;",
        (block_status, user_id),
        commit=True
    )

def test_update_user_block_status_db_error(mock_db, caplog):
    # Arrange
    caplog.set_level(logging.ERROR)
    mock_db.execute_query.side_effect = Exception("DB Error")
    user_id = TEST_USER_ID_ACTIVE
    # Act
    result = user_service.update_user_block_status(mock_db, user_id, block=True)
    # Assert
    assert result is False; assert "Ошибка при обновлении статуса блокировки" in caplog.text
    mock_db.execute_query.assert_called_once()

# --- Тесты для handle_user_blocked_bot ---
def test_handle_user_blocked_bot_calls_update(mocker, caplog):
    # Arrange
    caplog.set_level(logging.WARNING)
    mock_db = mocker.Mock(spec=Database)
    # Патчим update_user_block_status внутри модуля user_service
    mock_update = mocker.patch('services.user_service.update_user_block_status', return_value=True)
    user_id = TEST_USER_ID_ACTIVE
    # Act
    user_service.handle_user_blocked_bot(mock_db, user_id)
    # Assert
    mock_update.assert_called_once_with(mock_db, user_id, block=True)
    assert f"Пользователь {user_id} заблокировал бота" in caplog.text