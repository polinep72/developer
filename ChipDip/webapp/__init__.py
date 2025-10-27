# webapp/__init__.py
from flask import Flask
import os
import sys
import datetime # Импортируем datetime для context_processor
from flask_login import LoginManager

# Добавляем корневую директорию проекта в sys.path, чтобы найти chipdip_parser.config_loader
# Это нужно, если webapp запускается как отдельное приложение, и chipdip_parser не в PYTHONPATH
# Предполагаем, что __init__.py веб-приложения находится в project_root/webapp/
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path: # Добавляем, только если еще не там
    sys.path.insert(0, project_root)

# Импортируем из нашего общего модуля конфигурации
try:
    from chipdip_parser.config_loader import load_app_config, get_config
except ImportError as e:
    # Эта ошибка критична, так как без конфига приложение не запустится.
    # Логирование здесь может еще не работать, поэтому используем print.
    print(f"CRITICAL [webapp/__init__.py]: Ошибка импорта config_loader: {e}. "
          f"Убедитесь в правильности структуры проекта и PYTHONPATH. "
          f"Текущий sys.path: {sys.path}")
    # Выбрасываем исключение, чтобы create_app не вызывался или run_webapp.py мог это обработать
    raise RuntimeError(f"Не удалось импортировать config_loader: {e}")


def create_app():
    # Загружаем конфигурацию здесь, чтобы она была доступна при создании app
    # Это гарантирует, что config_loader.APP_CONFIG будет заполнен
    try:
        load_app_config() 
        app_config = get_config()
    except SystemExit as e_conf_sys_exit: # config_loader может вызвать SystemExit
        print(f"CRITICAL [webapp/create_app]: Не удалось загрузить конфигурацию: {e_conf_sys_exit}")
        raise RuntimeError(f"Ошибка конфигурации Flask при вызове SystemExit: {e_conf_sys_exit}")
    except Exception as e_conf_generic:
        print(f"CRITICAL [webapp/create_app]: Неизвестная ошибка при загрузке конфигурации: {e_conf_generic}")
        raise RuntimeError(f"Неизвестная ошибка конфигурации Flask: {e_conf_generic}")

    app = Flask(__name__) # Flask приложение создается здесь

    # Настройка конфигурации Flask из нашего общего конфига
    app.config['SECRET_KEY'] = app_config.get('FLASK_SECRET_KEY', 'default_dev_secret_key_change_me_3498723')
    app.config['DB_CONFIG'] = {
        'dbname': app_config.get('db_name'),
        'user': app_config.get('db_user'),
        'password': app_config.get('db_password'),
        'host': app_config.get('db_host'),
        'port': app_config.get('db_port'),
    }
    
    # Настройка Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    login_manager.login_message_category = 'info'
    
    # Установка режима DEBUG для Flask из переменной окружения, если она есть,
    # иначе из нашего конфига (если бы мы его там хранили), или по умолчанию False для продакшена.
    # Flask сам смотрит FLASK_DEBUG и FLASK_ENV.
    # app.debug = app_config.get('flask_debug_mode', False) # Пример, если бы хранили в .env

    # Логирование Flask: Flask использует стандартный logging.
    # Если utils.setup_logging() был вызван в run_webapp.py до create_app,
    # то app.logger будет использовать уже настроенные обработчики.
    # Если вы хотите специфичные настройки для Flask логгера:
    if not app.debug: # Пример: не настраивать дополнительно в режиме отладки
        # import logging
        # from logging.handlers import RotatingFileHandler
        # file_handler = RotatingFileHandler('webapp.log', maxBytes=10240, backupCount=10)
        # file_handler.setFormatter(logging.Formatter(
        #    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        # ))
        # file_handler.setLevel(logging.INFO)
        # app.logger.addHandler(file_handler)
        # app.logger.setLevel(logging.INFO)
        pass # Пока оставляем стандартное поведение, которое подхватит настройки из utils.py
    
    # --- Контекстный процессор для передачи переменных во все шаблоны ---
    @app.context_processor
    def inject_template_vars():
        # Передаем current_year для использования в шаблонах, например, в футере
        return {'current_year': datetime.datetime.utcnow().year}

    # Регистрация маршрутов (blueprints)
    try:
        from . import routes # Используем относительный импорт для Blueprint из текущего пакета
        app.register_blueprint(routes.bp)
        app.logger.info("Blueprint 'main' (routes.bp) успешно зарегистрирован.")
        
        from . import auth # Импортируем модуль аутентификации
        app.register_blueprint(auth.auth_bp, url_prefix='/auth')
        app.logger.info("Blueprint 'auth' успешно зарегистрирован.")
        
        # Инициализируем login_manager
        from .auth import login_manager
        login_manager.init_app(app)
        
    except ImportError as e_routes:
        # Используем app.logger, так как он должен быть уже доступен
        app.logger.error(f"Не удалось импортировать или зарегистрировать routes: {e_routes}", exc_info=True)
        raise RuntimeError(f"Ошибка импорта/регистрации маршрутов: {e_routes}")


    app.logger.info("Flask приложение успешно создано и сконфигурировано.")
    return app