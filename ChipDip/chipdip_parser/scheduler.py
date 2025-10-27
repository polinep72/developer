# ChipDip/chipdip_parser/scheduler.py
import datetime
import time
import random
import pytz
import logging
import holidays  # <--- ИМПОРТ БИБЛИОТЕКИ
from chipdip_parser.config_loader import get_config

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self):
        self.config = get_config()
        self.timezone_str = self.config.get('timezone', 'Europe/Moscow')
        try:
            self.timezone = pytz.timezone(self.timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            logger.error(f"Неизвестная временная зона: '{self.timezone_str}'. Используется UTC по умолчанию.")
            self.timezone = pytz.utc
            self.timezone_str = 'UTC'

        self.processed_this_hour_count = 0
        self.last_hour_check = datetime.datetime.now(self.timezone).hour

        # Инициализация объекта праздников для России
        # Можно сделать страну конфигурируемой, если нужно
        self.country_holidays_code = self.config.get('holidays_country_code', 'RU')
        try:
            self.ru_holidays = holidays.CountryHoliday(self.country_holidays_code, prov=None, state=None)
            # Для России можно также указать конкретный субъект (регион), если праздники отличаются,
            # но общегосударственные будут включены в любом случае.
            # Например, для Москвы: self.ru_holidays = holidays.RU(prov='MOW')
            # Или просто: self.ru_holidays = holidays.RU()
            logger.info(f"Загружен календарь праздников для страны: {self.country_holidays_code}")
        except KeyError:
            logger.error(
                f"Не удалось загрузить календарь праздников для кода страны: {self.country_holidays_code}. Проверка на праздники будет отключена.")
            self.ru_holidays = None

    def is_holiday(self, date_to_check):
        """Проверяет, является ли указанная дата праздником."""
        if not self.ru_holidays:
            return False  # Если календарь не загружен, считаем, что не праздник

        is_holiday_flag = date_to_check in self.ru_holidays
        if is_holiday_flag:
            holiday_name = self.ru_holidays.get(date_to_check)
            logger.info(f"Дата {date_to_check.strftime('%Y-%m-%d')} является праздником: {holiday_name}")
        return is_holiday_flag

    def is_work_time(self):
        now_local = datetime.datetime.now(self.timezone)
        current_date_local = now_local.date()  # Получаем только дату для проверки праздника

        # --- НОВАЯ ПРОВЕРКА НА ПРАЗДНИК ---
        if self.is_holiday(current_date_local):
            logger.info(
                f"Текущий день ({now_local.strftime('%A')}, {current_date_local.strftime('%Y-%m-%d')}) - государственный праздник. Парсинг неактивен.")
            return False
        # --- КОНЕЦ НОВОЙ ПРОВЕРКИ ---

        # Проверка на выходные дни (понедельник=0, ..., суббота=5, воскресенье=6)
        if now_local.weekday() >= 5:  # 5 = Суббота, 6 = Воскресенье
            logger.info(
                f"Текущий день ({now_local.strftime('%A')}, {current_date_local.strftime('%Y-%m-%d')}) - выходной. Парсинг неактивен.")
            return False

        work_start_hour = self.config.get('work_start_hour', 8)
        work_end_hour = self.config.get('work_end_hour', 17)

        start_time = datetime.time(work_start_hour, 0)
        is_working_hours = start_time <= now_local.time() and now_local.hour < work_end_hour

        if not is_working_hours:
            logger.info(f"Нерабочие часы ({now_local.strftime('%H:%M:%S %Z')}). "
                        f"График: {start_time.strftime('%H:%M')}-{work_end_hour:02d}:00 (будни, не праздники).")
        return is_working_hours

    def wait_if_needed(self):
        """Проверяет рабочее время, праздники и лимиты, при необходимости ожидает."""
        now_local = datetime.datetime.now(self.timezone)
        current_hour_local = now_local.hour

        if current_hour_local != self.last_hour_check:
            logger.info(f"Новый час ({current_hour_local:02d}:00 {self.timezone_str}). Сброс счетчика запросов.")
            self.processed_this_hour_count = 0
            self.last_hour_check = current_hour_local

        if not self.is_work_time():  # Включает проверку на выходные, праздники и рабочие часы
            sleep_duration_min = self.config.get('sleep_non_work_time_min', 30)
            actual_sleep_sec = sleep_duration_min * 60 + random.uniform(0, 60)
            logger.info(
                f"Пауза в нерабочее время/выходной/праздник. Следующая проверка через ~{actual_sleep_sec / 60:.1f} минут.")
            time.sleep(actual_sleep_sec)
            return False

        max_req_per_hour = self.config.get('max_requests_per_hour', 25)
        if self.processed_this_hour_count >= max_req_per_hour:
            next_hour_dt = (now_local + datetime.timedelta(hours=1)).replace(minute=1, second=0, microsecond=0)
            time_to_next_hour_sec = (next_hour_dt - now_local).total_seconds()

            if time_to_next_hour_sec <= 0:  # На случай, если что-то пошло не так с расчетами
                time_to_next_hour_sec = 60

            actual_sleep_sec = time_to_next_hour_sec + random.uniform(1, 10)
            logger.info(f"Достигнут лимит запросов в час ({self.processed_this_hour_count}/{max_req_per_hour}). "
                        f"Ожидание до следующего часа (~{actual_sleep_sec / 60:.1f} мин).")
            time.sleep(actual_sleep_sec)
            return False

        return True

    def record_request_processed(self):
        self.processed_this_hour_count += 1
        max_req = self.config.get('max_requests_per_hour', 25)
        # Уменьшим частоту этого лога, чтобы не спамить, или сделаем его DEBUG
        logger.debug(f"Обработан запрос. Всего в текущем часу: {self.processed_this_hour_count}/{max_req}")

    def get_random_delay(self):
        min_delay = self.config.get('min_request_delay_sec', 70)
        max_delay = self.config.get('max_request_delay_sec', 200)
        delay = random.uniform(min_delay, max_delay)
        # Это сообщение тоже можно сделать DEBUG, чтобы не засорять INFO лог
        logger.debug(f"Задержка перед следующим запросом: {delay:.1f} сек.")
        return delay