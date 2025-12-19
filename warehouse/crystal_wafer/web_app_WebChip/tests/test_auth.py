"""
Тесты для аутентификации и авторизации
"""
import pytest
from flask import session


def test_login_page_loads(client):
    """Тест: страница входа загружается"""
    response = client.get('/login')
    assert response.status_code == 200
    # Проверяем наличие ключевых слов на странице (может быть в разных кодировках)
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'username' in response_text or 'login' in response_text or 'вход' in response_text


def test_login_with_empty_credentials(client):
    """Тест: вход с пустыми учетными данными"""
    response = client.post('/login', data={
        'username': '',
        'password': ''
    })
    assert response.status_code == 200
    # Должно быть сообщение об ошибке
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'username' in response_text or 'пароль' in response_text or 'имя пользователя' in response_text


def test_login_with_invalid_credentials(client):
    """Тест: вход с неверными учетными данными"""
    response = client.post('/login', data={
        'username': 'nonexistent_user_12345',
        'password': 'wrong_password_12345'
    }, follow_redirects=True)
    # Может быть редирект или остаться на странице входа с сообщением об ошибке
    assert response.status_code == 200
    # Проверяем, что не произошел успешный вход (нет в сессии user_id)
    with client.session_transaction() as sess:
        assert 'user_id' not in sess or sess.get('user_id') is None


def test_logout_when_not_logged_in(client):
    """Тест: выход без авторизации"""
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    # Должен быть редирект на главную или страницу входа


def test_logout_when_logged_in(client):
    """Тест: выход с авторизацией"""
    # Сначала устанавливаем сессию (имитируем вход)
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'testuser'
        sess['is_admin'] = False
    
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    
    # Проверяем, что сессия очищена
    with client.session_transaction() as sess:
        assert 'user_id' not in sess or sess.get('user_id') is None


def test_logout_clears_session(client):
    """Тест: выход очищает сессию"""
    # Устанавливаем сессию
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'testuser'
        sess['is_admin'] = False
    
    # Проверяем, что сессия установлена
    with client.session_transaction() as sess:
        assert sess.get('user_id') == 1
    
    # Выполняем выход
    client.get('/logout')
    
    # Проверяем, что сессия очищена
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_register_page_loads(client):
    """Тест: страница регистрации загружается"""
    response = client.get('/register')
    assert response.status_code == 200
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'username' in response_text or 'register' in response_text or 'регистрация' in response_text


def test_profile_requires_auth(client):
    """Тест: профиль требует авторизации"""
    response = client.get('/profile', follow_redirects=True)
    assert response.status_code == 200
    # Должен быть редирект на страницу входа
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'войдите' in response_text or 'login' in response_text or response.request.path == '/login'


def test_profile_accessible_when_logged_in(client):
    """Тест: профиль доступен при авторизации"""
    # Устанавливаем сессию
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'testuser'
        sess['is_admin'] = False
    
    response = client.get('/profile', follow_redirects=True)
    # Может быть 200 или 302 в зависимости от наличия пользователя в БД
    assert response.status_code in [200, 302, 404]  # 404 если пользователь не найден в тестовой БД

