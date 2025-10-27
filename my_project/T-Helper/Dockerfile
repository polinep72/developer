FROM python:3.12.5

WORKDIR /app

# Установка локалей
RUN apt-get update && apt-get install -y \
    locales \
    cifs-utils \
    gcc \
    python3-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i '/en_US.UTF-8/s/^# //' /etc/locale.gen \
    && locale-gen \
    && pip install --upgrade pip

ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]