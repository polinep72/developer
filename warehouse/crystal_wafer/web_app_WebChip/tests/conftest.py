"""
Конфигурация pytest для тестирования Flask приложения
"""
import pytest
import os
import sys

# Добавляем путь к корню проекта для импорта app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Настройка переменных окружения для тестов
os.environ['TESTING'] = 'True'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'
os.environ['CSRF_ENABLED'] = 'False'  # Отключаем CSRF для тестов

@pytest.fixture(scope='session', autouse=True)
def setup_test_environment():
    """Настройка тестового окружения перед запуском всех тестов"""
    # Можно добавить инициализацию тестовой БД здесь
    yield
    # Очистка после всех тестов

@pytest.fixture
def app():
    """
    Создает экземпляр Flask приложения для тестирования
    """
    # Импортируем app после настройки переменных окружения
    from app import _flask_app
    
    # Настраиваем приложение для тестирования
    _flask_app.config['TESTING'] = True
    _flask_app.config['WTF_CSRF_ENABLED'] = False  # Отключаем CSRF для тестов
    _flask_app.config['SECRET_KEY'] = 'test-secret-key'
    
    # Можно использовать тестовую БД, если нужно
    # _flask_app.config['DB_NAME'] = os.getenv('TEST_DB_NAME', 'test_db')
    
    yield _flask_app

@pytest.fixture
def client(app):
    """Создает тестовый клиент Flask"""
    return app.test_client()

@pytest.fixture
def runner(app):
    """Создает CLI runner для тестирования команд"""
    return app.test_cli_runner()

@pytest.fixture
def auth_headers(client):
    """
    Создает заголовки с авторизацией для тестов
    Использует сессию для авторизации
    """
    def _get_auth_headers(username='testuser', password='testpass'):
        # Попытка входа через POST запрос
        with client.session_transaction() as sess:
            # Для тестов можем напрямую установить сессию
            # В реальных тестах лучше делать настоящий login
            sess['user_id'] = 1
            sess['username'] = username
            sess['is_admin'] = False
        return {}
    return _get_auth_headers

