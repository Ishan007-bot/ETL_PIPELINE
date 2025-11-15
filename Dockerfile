FROM python:3.11-slim

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY backend/requirements.txt /code/backend/requirements.txt
RUN pip install --no-cache-dir -r /code/backend/requirements.txt

# Copy application code (will be overridden by volume mount in docker-compose)
COPY . /code

# Default command (can be overridden in docker-compose)
CMD ["python", "--version"]

