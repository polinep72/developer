# ChipDip/chipdip_parser/scraper.py
import logging
import time
import re  # Добавим re для поиска текста

from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


def get_product_details_from_site(url, driver, config):
    logger.debug(f"Запрос данных для URL: {url} с использованием существующего драйвера.")

    if not url or not isinstance(url, str) or not url.startswith(('http://', 'https://')):
        logger.warning(f"Некорректный URL предоставлен: {url}")
        return {
            "name": None, "notes": None, "stock_level": None,  # None вместо -1
            "raw_stock_text": "Invalid URL provided", "price": None,
            "error_flag": True, "status_override": "error_invalid_url",
            "page_not_found": False  # Новый флаг
        }

    # Получаем селекторы из конфигурации с fallback значениями
    xpath_stock = config.get('xpath_stock', '//span[contains(@class, "item__avail")]//b')
    xpath_product_name = config.get('xpath_product_name', '//h1')
    xpath_product_description = config.get('xpath_product_description')
    xpath_price = config.get('xpath_price', '//span[@class="ordering__value"]')
    wait_timeout = config.get('selenium_wait_timeout', 25)

    parsed_details = {
        "name": None, "notes": None, "stock_level": None,  # Начинаем с None вместо -1
        "raw_stock_text": None, "price": None, "error_flag": False,
        "status_override": None, "page_not_found": False  # Инициализируем новый флаг
    }

    try:
        logger.debug(f"Загрузка URL: {url}")
        driver.get(url)
        logger.debug(f"URL '{url}' загружен. Ожидание ключевых элементов...")

        # --- Проверка на страницу "Товар не найден" / 404 ---
        # Проверяем после загрузки страницы, но до основной логики парсинга.
        # Подберите ключевые фразы/селекторы для вашей страницы "не найдено" ChipDip.
        # Это может быть title, h1, или специфичный CSS класс.
        time.sleep(1)  # Небольшая пауза, чтобы JS успел отработать, если есть
        page_title_lower = driver.title.lower()
        # Примерные фразы, которые могут быть на странице 404 или "товар не найден"
        # Вы можете также искать определенный элемент, если он есть на таких страницах
        not_found_phrases = ["страница не найдена", "товар не найден", "error 404", "нет такой страницы",
                             "запрашиваемая страница не существует"]

        page_content_sample_for_check = ""
        try:
            # Попробуем получить H1 или основной контентный блок для проверки
            # Это более надежно, чем просто title
            body_text_lower = driver.find_element(By.TAG_NAME, "body").text.lower()
            page_content_sample_for_check = body_text_lower[:1500]  # Проверяем часть текста body
        except Exception:
            logger.debug("Не удалось получить body.text для проверки на 404, полагаемся на title.")
            page_content_sample_for_check = ""

        found_404_indicator = False
        for phrase in not_found_phrases:
            if phrase in page_title_lower or phrase in page_content_sample_for_check:
                found_404_indicator = True
                break

        if found_404_indicator:
            logger.warning(f"Обнаружены признаки отсутствия страницы для URL: {url}. Title: '{driver.title}'")
            parsed_details["page_not_found"] = True
            # stock_level и price остаются None или -1 по умолчанию, error_flag не ставим, т.к. это не ошибка парсинга
            parsed_details["raw_stock_text"] = f"Page or product not found (title: {driver.title})"
            parsed_details["status_override"] = config.get('status_product_not_found',
                                                           'product_not_found_on_site')  # Настраиваемый статус
            return parsed_details  # Выходим, дальше парсить нет смысла

        # --- Ожидание ключевого элемента (например, остатков) ПЕРЕД 5-секундной паузой ---
        element_to_wait_for_xpath = xpath_stock or xpath_price or xpath_product_name or "//body"
        if element_to_wait_for_xpath != "//body" or not xpath_stock:
            logger.debug(f"Ожидание элемента по XPath: '{element_to_wait_for_xpath}' (до {wait_timeout} сек)...")

        WebDriverWait(driver, wait_timeout).until(
            EC.presence_of_element_located((By.XPATH, element_to_wait_for_xpath))
        )
        logger.debug(f"Ключевой элемент для URL '{url}' найден (или //body присутствует).")

        logger.info(f"Пауза 5 секунд после загрузки страницы {url}...")
        time.sleep(5)
        logger.info(f"Пауза 5 секунд завершена. Сбор данных для {url}...")
        # --- Конец паузы ---

        # 1. Парсинг названия товара
        if xpath_product_name:
            try:
                name_element = driver.find_element(By.XPATH, xpath_product_name)
                parsed_details["name"] = name_element.text.strip()
                logger.info(f"Название товара: '{parsed_details['name']}'")
            except NoSuchElementException:
                logger.warning(f"Название товара не найдено по XPath: {xpath_product_name} на {url}")
            except Exception as e_name:
                logger.error(f"Ошибка при парсинге названия товара на {url}: {e_name}", exc_info=False)
        else:
            logger.debug("XPATH_PRODUCT_NAME не задан.")

        # 2. Парсинг описания/заметок + техпараметров + документации + доп. ссылок
        notes_parts = []

        # 2.1 Описание
        description_xpaths = []
        if xpath_product_description:
            description_xpaths.append(xpath_product_description)
        # Fallback из макета сайта
        description_xpaths.append("//div[contains(@class,'showhide') and contains(@class,'item_desc')]")

        desc_captured = False
        for dx in description_xpaths:
            if desc_captured:
                break
            try:
                desc_element = driver.find_element(By.XPATH, dx)
                desc_text = desc_element.text.strip()
                if desc_text:
                    notes_parts.append(desc_text)
                    desc_captured = True
            except Exception:
                continue

        # 2.2 Техпараметры (таблица с id=productparams)
        try:
            rows = driver.find_elements(By.XPATH, "//table[@id='productparams']//tr")
            tech_lines = []
            for r in rows:
                try:
                    name_el = r.find_element(By.XPATH, ".//td[contains(@class,'product__param-name')]")
                    val_el = r.find_element(By.XPATH, ".//td[contains(@class,'product__param-value')]")
                    name_text = name_el.text.strip()
                    val_text = val_el.text.strip()
                    if name_text or val_text:
                        tech_lines.append(f"{name_text}: {val_text}")
                except Exception:
                    continue
            if tech_lines:
                notes_parts.append("Технические параметры:\n" + "\n".join(tech_lines))
        except Exception:
            pass

        # 2.3 Документация (ссылки)
        try:
            doc_links = driver.find_elements(By.XPATH, "//div[contains(@class,'product__documentation')]//a[@href]")
            doc_lines = []
            for a in doc_links:
                try:
                    href = a.get_attribute("href") or ""
                    text = a.text.strip() or href
                    doc_lines.append(f"{text} - {href}")
                except Exception:
                    continue
            if doc_lines:
                notes_parts.append("Техническая документация:\n" + "\n".join(doc_lines))
        except Exception:
            pass

        # 2.4 Дополнительная информация (ссылки)
        try:
            add_links = driver.find_elements(By.XPATH, "//p[contains(@class,'item_addinfo')]//a[@href]")
            add_lines = []
            for a in add_links:
                try:
                    href = a.get_attribute("href") or ""
                    text = a.text.strip() or href
                    add_lines.append(f"{text} - {href}")
                except Exception:
                    continue
            if add_lines:
                notes_parts.append("Дополнительная информация:\n" + "\n".join(add_lines))
        except Exception:
            pass

        if notes_parts:
            combined = "\n\n".join([p for p in notes_parts if p])
            max_len = config.get('max_description_length', 2000)
            if len(combined) > max_len:
                combined = combined[:max_len] + "..."
            parsed_details["notes"] = combined
            logger.info(f"Описание/заметки (первые ~50): '{combined[:50] if combined else ''}'")
        else:
            logger.debug("Описание/заметки не найдены по известным шаблонам.")

        # 3. Парсинг остатков
        if xpath_stock:
            try:
                stock_element = driver.find_element(By.XPATH, xpath_stock)
                raw_text = stock_element.text.strip()
                parsed_details["raw_stock_text"] = raw_text
                logger.debug(f"Элемент остатков найден. Текст: '{raw_text}'")

                # Улучшенная логика извлечения числа для формата "3022 шт."
                import re
                # Ищем число перед "шт" или просто первое число
                match = re.search(r'(\d+)\s*шт', raw_text, re.IGNORECASE)
                if not match:
                    # Если не нашли "шт", ищем просто первое число
                    match = re.search(r'\d+', raw_text)
                
                if match:
                    parsed_details["stock_level"] = int(match.group(1) if len(match.groups()) > 0 else match.group(0))
                    logger.info(f"Извлечено количество: {parsed_details['stock_level']} из текста '{raw_text}'")
                elif "нет в наличии" in raw_text.lower() or "под заказ" in raw_text.lower() or "0" in raw_text:
                    parsed_details["stock_level"] = 0
                    logger.info(f"Товар не в наличии: '{raw_text}'")
                else:  # Если не нашли цифр и нет явных текстовых указаний на 0
                    logger.warning(
                        f"Текст элемента остатков '{raw_text}' не содержит понятных цифр или ключевых слов. URL: {url}")
                    # Не устанавливаем stock_level - оставляем None
                    logger.info(f"Остатки не определены для URL '{url}' (текст: '{raw_text}')")

            except NoSuchElementException:
                logger.warning(f"Элемент остатков не найден по XPath: {xpath_stock} на {url}")
                # Fallback: пробуем общий контейнер доступности и текстовые индикаторы
                try:
                    avail_el = driver.find_element(By.XPATH, "//span[contains(@class,'item__avail')]")
                    avail_text = (avail_el.text or "").strip().lower()
                    parsed_details["raw_stock_text"] = avail_el.text.strip()
                    if ("нет в наличии" in avail_text) or ("под заказ" in avail_text):
                        parsed_details["stock_level"] = 0
                        parsed_details["status_override"] = "out_of_stock"
                        logger.info(f"Определено отсутствие товара по тексту: '{avail_el.text.strip()}' → stock=0")
                    else:
                        # Иного текста нет — считаем, что элемент недоступен для парсинга
                        parsed_details["status_override"] = "not_found_on_site"
                except NoSuchElementException:
                    parsed_details["raw_stock_text"] = "Stock element not found (NoSuchElement)"
                    parsed_details["status_override"] = "not_found_on_site"
            except Exception as e_stock:
                logger.error(f"Ошибка при парсинге остатков на {url}: {e_stock}", exc_info=False)
                parsed_details["raw_stock_text"] = f"Error parsing stock: {str(e_stock)}"
                parsed_details["error_flag"] = True
                # Не устанавливаем stock_level - оставляем None
        else:
            logger.warning("XPATH_STOCK не задан в конфигурации. Остатки не будут спарсены.")
            parsed_details["raw_stock_text"] = "Stock XPath not configured"
            parsed_details["status_override"] = "config_error_xpath"
            # Не устанавливаем stock_level - оставляем None

        # 4. Парсинг цены
        if xpath_price:
            try:
                price_element = driver.find_element(By.XPATH, xpath_price)
                price_text_raw = price_element.text.strip()
                price_text_cleaned = ''.join(c for c in price_text_raw if c.isdigit() or c in ['.', ','])
                price_text_cleaned = price_text_cleaned.replace(',', '.')

                if price_text_cleaned:  # Убедимся, что после очистки что-то осталось
                    # Дополнительная проверка, что строка стала валидным числом
                    # (например, не осталось только точки или запятой)
                    try:
                        parsed_details["price"] = float(price_text_cleaned)
                        logger.info(f"Цена найдена: {parsed_details['price']} (из сырого текста: '{price_text_raw}')")
                    except ValueError:
                        logger.warning(
                            f"Не удалось преобразовать очищенный текст цены '{price_text_cleaned}' во float. URL: {url}")
                        # Не устанавливаем price - оставляем None
                else:
                    logger.warning(f"Не удалось извлечь число из текста цены: '{price_text_raw}'. URL: {url}")
                    # Не устанавливаем price - оставляем None

            except NoSuchElementException:
                logger.warning(f"Цена не найдена по XPath: {xpath_price} на {url}")
            except Exception as e_price:
                logger.error(f"Ошибка при парсинге цены на {url}: {e_price}", exc_info=False)
        else:
            logger.debug("XPATH_PRICE не задан.")

    # Обработка TimeoutException от driver.get() или основного WebDriverWait
    except TimeoutException as e_timeout:
        logger.error(f"Тайм-аут при загрузке или ожидании основного элемента для URL '{url}': {e_timeout}",
                     exc_info=False)
        parsed_details["raw_stock_text"] = f"Page load or main element Timeout: {str(e_timeout)[:200]}"
        parsed_details["error_flag"] = True
        # Если таймаут загрузки страницы, это можно считать как "страница не найдена"
        # НО! Это может быть и просто медленный сайт. Различать сложно без HTTP статуса.
        # Пока оставляем как общий таймаут. Если хотите, можно и здесь выставить page_not_found = True
        parsed_details["status_override"] = "not_found_on_site_timeout"
    except WebDriverException as e_wd:
        logger.error(f"Ошибка WebDriver при обработке URL '{url}': {e_wd}", exc_info=True)
        parsed_details["raw_stock_text"] = f"WebDriver Error: {str(e_wd)[:200]}"
        parsed_details["error_flag"] = True
    except Exception as e_general:
        logger.error(f"Общая ошибка парсинга для URL '{url}': {e_general}", exc_info=True)
        parsed_details["raw_stock_text"] = f"General Scraper Error: {str(e_general)[:200]}"
        parsed_details["error_flag"] = True

    logger.debug(f"Результат парсинга для {url}: {parsed_details}")
    return parsed_details