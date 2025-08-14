FROM python:3.12-alpine

# Update system and install system packages including bash
RUN apk update && \
    apk upgrade && \
    apk add --no-cache \
    bash \
    nano \
    curl \
    wget \
    jq

# Update pip and setuptools
RUN pip install --upgrade pip setuptools

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user for running the application with common UID/GID
RUN addgroup -g 100 -S appgroup && \
    adduser -u 99 -S appuser -G appgroup -s /bin/bash

# Change ownership of the app directory
RUN chown -R appuser:appgroup /app

# Set bash as default shell and keep root as login user
SHELL ["/bin/bash", "-c"]

# Switch to non-root user for running the application
USER appuser

# Expose the port the app runs on
EXPOSE 9009

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:9009/api?t=caps || exit 1

# Command to run the application
CMD ["python", "app.py"]
