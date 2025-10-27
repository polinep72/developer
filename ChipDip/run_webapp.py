# run_webapp.py (в корне проекта)
from webapp import create_app
import os
import logging # Добавим логирование для информации о запуске

# Настроим базовое логирование, если оно еще не настроено из webapp.__init__
# (хотя webapp.__init__ должен это делать через config_loader и utils)
logger = logging.getLogger(__name__)
if not logger.hasHandlers(): # Проверяем, есть ли уже обработчики
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


app = create_app()

if __name__ == '__main__':
    # Считываем хост и порт из переменных окружения
    host_ip = os.environ.get("FLASK_RUN_HOST", '0.0.0.0')
    port_number = int(os.environ.get("FLASK_RUN_PORT", 8085))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    logger.info(f"Запуск Flask веб-приложения на http://{host_ip}:{port_number}/")
    if debug_mode:
        logger.warning("Режим отладки Flask (debug=True) включен. НЕ ИСПОЛЬЗУЙТЕ В ПРОДАКШЕНЕ!")
    logger.info("Для доступа из других устройств в сети убедитесь, что файрвол разрешает входящие подключения на порт {port_number}.")

    try:
        app.run(debug=debug_mode, host=host_ip, port=port_number)
    except OSError as e:
        if e.errno == 98: # Address already in use
            logger.error(f"ОШИБКА: Порт {port_number} на хосте {host_ip} уже занят. "
                           "Пожалуйста, освободите порт или выберите другой.")
        elif e.errno == 99: # Cannot assign requested address
             logger.error(f"ОШИБКА: Не удается назначить адрес {host_ip}. "
                           "Убедитесь, что этот IP-адрес корректен для данной машины "
                           "или используйте '0.0.0.0' для прослушивания на всех интерфейсах.")
        else:
            logger.error(f"Не удалось запустить Flask приложение: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при запуске Flask приложения: {e}", exc_info=True)