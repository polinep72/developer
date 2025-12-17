"""
Тесты для REST API endpoints
"""
import pytest
import json


def test_api_v1_search_get(client):
    """Тест: GET /api/v1/search возвращает результаты"""
    response = client.get('/api/v1/search')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'success' in data
    assert 'version' in data
    assert data['version'] == '1.0'
    assert 'data' in data
    assert 'results' in data['data']
    assert 'pagination' in data['data']


def test_api_v1_search_with_filters(client):
    """Тест: GET /api/v1/search с фильтрами"""
    response = client.get('/api/v1/search?warehouse=crystals&chip_name=HJB&page=1&per_page=10')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'results' in data['data']
    assert 'pagination' in data['data']
    assert data['data']['pagination']['page'] == 1
    assert data['data']['pagination']['per_page'] == 10


def test_api_v1_chip_codes_get(client):
    """Тест: GET /api/v1/chip-codes возвращает список шифров"""
    response = client.get('/api/v1/chip-codes')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'chip_codes' in data['data']
    assert isinstance(data['data']['chip_codes'], list)


def test_api_v1_chip_codes_with_query(client):
    """Тест: GET /api/v1/chip-codes с параметром q"""
    response = client.get('/api/v1/chip-codes?q=HJB')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'chip_codes' in data['data']
    assert isinstance(data['data']['chip_codes'], list)


def test_api_v1_manufacturers_get(client):
    """Тест: GET /api/v1/manufacturers возвращает список производителей"""
    response = client.get('/api/v1/manufacturers')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'manufacturers' in data['data']
    assert isinstance(data['data']['manufacturers'], list)


def test_api_v1_lots_get(client):
    """Тест: GET /api/v1/lots возвращает список партий"""
    response = client.get('/api/v1/lots')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'lots' in data['data']
    assert isinstance(data['data']['lots'], list)


def test_api_v1_lots_with_filters(client):
    """Тест: GET /api/v1/lots с фильтрами"""
    response = client.get('/api/v1/lots?warehouse=crystals&manufacturer=all')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'lots' in data['data']


def test_api_v1_cart_get(client):
    """Тест: GET /api/v1/cart возвращает корзину"""
    response = client.get('/api/v1/cart')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'data' in data
    assert 'cart_items' in data['data']
    assert isinstance(data['data']['cart_items'], list)
    assert 'warehouse_type' in data['data']


def test_api_v1_cart_delete_without_item_id(client):
    """Тест: DELETE /api/v1/cart/<item_id> с несуществующим item_id"""
    response = client.delete('/api/v1/cart/nonexistent_item_id_12345')
    # Может вернуть 200 (если товар не найден) или 404
    assert response.status_code in [200, 404]
    
    data = json.loads(response.data)
    assert 'success' in data


def test_api_response_format(client):
    """Тест: все API endpoints возвращают стандартный формат ответа"""
    endpoints = [
        '/api/v1/search',
        '/api/v1/chip-codes',
        '/api/v1/manufacturers',
        '/api/v1/lots',
        '/api/v1/cart'
    ]
    
    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 200
        
        data = json.loads(response.data)
        # Стандартный формат ответа
        assert 'success' in data
        assert 'version' in data
        assert data['version'] == '1.0'
        assert 'data' in data or 'message' in data

