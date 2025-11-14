FROM python:3.13-slim

WORKDIR /app

# Install system deps used by the scripts (curl, unzip) and build tools if needed
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl unzip build-essential postgresql-client && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure our scripts are executable inside the image
RUN chmod +x /app/scripts/*.sh || true
RUN chmod +x /app/scripts/*.py || true

EXPOSE 80

CMD ["sh", "-c", "python setup_bd.py && python app.py"]