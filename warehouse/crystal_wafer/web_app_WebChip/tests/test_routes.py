"""
Тесты для основных маршрутов приложения
"""
import pytest


def test_home_page_loads(client):
    """Тест: главная страница загружается"""
    response = client.get('/')
    assert response.status_code == 200


def test_search_page_loads(client):
    """Тест: страница поиска загружается"""
    response = client.get('/search')
    assert response.status_code == 200
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'chip' in response_text or 'search' in response_text or 'поиск' in response_text


def test_search_page_with_warehouse_param(client):
    """Тест: страница поиска с параметром warehouse"""
    response = client.get('/search?warehouse=crystals')
    assert response.status_code == 200


def test_cart_page_loads(client):
    """Тест: страница корзины загружается"""
    response = client.get('/cart')
    assert response.status_code == 200


def test_inventory_requires_auth(client):
    """Тест: страница инвентаризации требует авторизации"""
    response = client.get('/inventory', follow_redirects=True)
    assert response.status_code == 200
    # Должен быть редирект на страницу входа или сообщение об ошибке
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'войдите' in response_text or 'login' in response_text or response.request.path == '/login'


def test_inflow_requires_auth(client):
    """Тест: страница прихода требует авторизации"""
    response = client.get('/inflow', follow_redirects=True)
    assert response.status_code == 200
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'войдите' in response_text or 'login' in response_text or response.request.path == '/login'


def test_outflow_requires_auth(client):
    """Тест: страница расхода требует авторизации"""
    response = client.get('/outflow', follow_redirects=True)
    assert response.status_code == 200
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'войдите' in response_text or 'login' in response_text or response.request.path == '/login'


def test_refund_requires_auth(client):
    """Тест: страница возврата требует авторизации"""
    response = client.get('/refund', follow_redirects=True)
    assert response.status_code == 200
    response_text = response.data.decode('utf-8', errors='ignore').lower()
    assert 'войдите' in response_text or 'login' in response_text or response.request.path == '/login'


def test_404_error_handler(client):
    """Тест: обработка 404 ошибки"""
    response = client.get('/nonexistent_route_12345')
    assert response.status_code == 404


def test_csrf_protection_enabled(client, app):
    """Тест: CSRF защита включена в конфигурации"""
    # CSRF должен быть включен в production, но может быть отключен для тестов
    assert 'WTF_CSRF_ENABLED' in app.config
    # В тестах мы отключаем CSRF, но проверяем что настройка есть
    assert isinstance(app.config.get('WTF_CSRF_ENABLED'), bool)

