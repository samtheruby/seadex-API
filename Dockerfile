FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Install system dependencies and clean cache
RUN apk add --no-cache \
        bash \
        nano \
        curl \
        wget \
        jq \
    && apk update \
    && apk upgrade --no-cache

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip/setuptools and install Python dependencies
RUN pip install --upgrade pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set bash as default shell
SHELL ["/bin/bash", "-c"]

# Expose port
EXPOSE 9009

# Run app
CMD ["python", "app.py"]
