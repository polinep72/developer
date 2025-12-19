# Тесты для Crystal Wafer Management System

## Описание

Этот каталог содержит тесты для веб-приложения управления складом кристаллов и пластин.

## Структура тестов

- `conftest.py` - Конфигурация pytest, фикстуры
- `test_auth.py` - Тесты аутентификации и авторизации
- `test_api.py` - Тесты REST API endpoints
- `test_routes.py` - Тесты основных маршрутов приложения

## Запуск тестов

### Установка зависимостей

```bash
pip install -r requirements.txt
```

### Запуск всех тестов

```bash
pytest
```

### Запуск с подробным выводом

```bash
pytest -v
```

### Запуск конкретного файла тестов

```bash
pytest tests/test_auth.py
```

### Запуск конкретного теста

```bash
pytest tests/test_auth.py::test_login_page_loads
```

### Запуск с покрытием кода

```bash
pytest --cov=app --cov-report=html
```

Отчет о покрытии будет в `htmlcov/index.html`

### Запуск тестов по категориям (маркерам)

```bash
# Только unit тесты
pytest -m unit

# Только тесты API
pytest -m api

# Только тесты аутентификации
pytest -m auth
```

## Добавление новых тестов

При добавлении новых тестов:

1. Создайте файл `test_*.py` в папке `tests/`
2. Импортируйте необходимые фикстуры из `conftest.py`
3. Используйте маркеры для категоризации тестов (например, `@pytest.mark.unit`)
4. Следуйте существующим паттернам в тестах

## Пример теста

```python
def test_example(client):
    """Описание теста"""
    response = client.get('/some-route')
    assert response.status_code == 200
    assert b'expected content' in response.data
```

## Фикстуры

### client
Тестовый клиент Flask для выполнения HTTP запросов

```python
def test_example(client):
    response = client.get('/')
    assert response.status_code == 200
```

### app
Экземпляр Flask приложения с настройками для тестирования

```python
def test_config(app):
    assert app.config['TESTING'] is True
```

### auth_headers
Фикстура для создания заголовков авторизации (в разработке)

## Примечания

- Для тестов используется отдельная конфигурация (CSRF отключен, тестовый SECRET_KEY)
- Тесты не требуют реальной базы данных для базовой функциональности
- Для тестов с БД можно использовать тестовую БД через переменные окружения

