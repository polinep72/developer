# TeleBot+PostgreSQL Бот для поиска кристаллов в базе данных

Этот проект — Telegram-бот, который помогает искать информацию о кристаллах в базе данных. Пользователи могут вводить полное или частичное название кристалла, и бот вернет информацию о доступном остатке для найденных позиций. Работу бота можно посмотреть в Telegram: **@HowManyCrystals_bot**

## Возможности
- **Взаимодействие с пользователем**: Отвечает на команду `/start` приветственным сообщением.
- **Поиск кристаллов**: Принимает текстовый ввод и выполняет запрос в базу данных PostgreSQL для поиска кристаллов.
- **Частичный поиск**: Поддерживает частичный поиск с помощью SQL `LIKE`.
- **Вывод результата**: Показывает суммарный остаток для каждого найденного кристалла.

---

## Инструкция по установке

### Необходимые условия
- Python 3.8+
- PostgreSQL с необходимой структурой таблиц.
- Файл `.env` для хранения данных подключения и токена Telegram-бота.

### Установка

1. **Клонируйте репозиторий**:
   ```bash
   git clone <ссылка_на_репозиторий>
   cd <папка_репозитория>

2. **Установите зависимости**: Установите необходимые библиотеки Python с помощью pip:

   ```bash
   pip install -r requirements.txt

3. **Настройте файл .env**: Создайте файл .env в корневой папке проекта и добавьте в него данные:

   DB_USER=<пользователь_БД>
   DB_PASSWORD=<пароль_БД>
   DB_NAME=<название_БД>
   DB_HOST=<адрес_сервера_БД>
   TELEGRAM_BOT_TOKEN=<токен_вашего_бота>

4. **Запустите бота**: Выполните команду для запуска:
   
   python HowManyCrystals_bot.py

## Структура базы данных

Бот ожидает базу данных PostgreSQL со следующими таблицами и связями:
   - **invoice**: Основная таблица с информацией о поступлении кристаллах.
   - **consumption**: Таблица учета расхода кристаллов.
   - **start_p, tech, chip и другие**: Вспомогательные таблицы, описывающие характеристики кристаллов.

## Как пользоваться
   
   - **Запустите бота**: Откройте Telegram-бота и отправьте команду /start, чтобы получить приветственное сообщение.

   - **Выполните поиск**: Введите полное или частичное название кристалла (например, W0.130.0 или 130).

   - **Получите результат**: Бот вернет список найденных кристаллов с их остатками. Если совпадений не найдено, бот сообщит: "К сожалению, кристалл не найден или остаток равен 0."

## Зависимости

   - **telebot**: Для взаимодействия с Telegram Bot API.
   - **pandas**: Для возможной обработки данных (в данном скрипте не используется).
   - **psycopg2**: Для подключения к базе данных PostgreSQL.
   - **python-dotenv**: Для загрузки переменных окружения.

## Обработка ошибок

   - Если пользователь вводит название кристалла, которого нет в базе данных или остаток равен 0, бот отправляет сообщение: "К сожалению, кристалл не найден или остаток равен 0."

## Примечания

   - Убедитесь, что база данных заполнена данными и соответствует ожидаемой структуре.
   - Замените <ссылка_на_репозиторий> и <папка_репозитория> в инструкции на ваши значения.
   - При необходимости измените SQL-запрос в коде, если структура базы данных отличается.

## Лицензия

   - Проект распространяется под лицензией MIT. Подробнее: https://mit-license.org/.