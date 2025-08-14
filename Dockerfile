FROM python:3.12-alpine

# Update system and install packages
RUN apk update && \
    apk upgrade && \
    apk add --no-cache \
    bash \
    nano \
    curl \
    wget \
    jq \
# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install requirements
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
