# ChipDip/Dockerfile (для Firefox)
FROM python:3.11-slim-bullseye

LABEL maintainer="Your Name <your.email@example.com>"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Moscow

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    wget \
    curl \
    tar \
    supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && echo "Версия Firefox ESR:" && firefox-esr --version

# Установка geckodriver
ARG GECKODRIVER_VERSION="0.36.0" # Проверьте актуальную стабильную версию
RUN TEMP_GECKODRIVER_ARCHIVE="/tmp/geckodriver.tar.gz" \
    && GECKODRIVER_DOWNLOAD_URL="https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz" \
    && echo "Скачивание geckodriver v${GECKODRIVER_VERSION} из ${GECKODRIVER_DOWNLOAD_URL} в ${TEMP_GECKODRIVER_ARCHIVE}" \
    && curl -L -o "${TEMP_GECKODRIVER_ARCHIVE}" "${GECKODRIVER_DOWNLOAD_URL}" \
    && echo "Проверка скачанного файла..." \
    && if ! gzip -t "${TEMP_GECKODRIVER_ARCHIVE}"; then \
         echo "ОШИБКА: Скачанный архив geckodriver поврежден или не является gzip архивом."; \
         ls -l /tmp; \
         exit 1; \
       fi \
    && echo "Распаковка geckodriver..." \
    && tar -xzf "${TEMP_GECKODRIVER_ARCHIVE}" -C /usr/local/bin \
    && rm "${TEMP_GECKODRIVER_ARCHIVE}" \
    && chmod +x /usr/local/bin/geckodriver \
    && echo "Версия geckodriver:" \
    && geckodriver --version

WORKDIR /app
ENV PYTHONPATH="/app:${PYTHONPATH}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN mkdir -p /var/log/supervisor

EXPOSE 8085

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]