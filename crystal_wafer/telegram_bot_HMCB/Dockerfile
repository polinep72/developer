FROM python:3.9
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y iputils-ping && \
    pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-u", "app.py"]