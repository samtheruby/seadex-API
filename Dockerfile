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
# Use existing group with GID 100 if it exists, or create our own
# Also check if UID 99 exists and handle appropriately
RUN EXISTING_GROUP=$(getent group 100 | cut -d: -f1) && \
    if [ -n "$EXISTING_GROUP" ]; then \
        echo "Using existing group: $EXISTING_GROUP (GID 100)"; \
        GROUP_NAME="$EXISTING_GROUP"; \
    else \
        addgroup -g 100 -S appgroup; \
        GROUP_NAME="appgroup"; \
    fi && \
    EXISTING_USER=$(getent passwd 99 | cut -d: -f1) && \
    if [ -n "$EXISTING_USER" ]; then \
        echo "UID 99 already exists for user: $EXISTING_USER"; \
        echo "Adding $EXISTING_USER to group $GROUP_NAME"; \
        addgroup "$EXISTING_USER" "$GROUP_NAME" 2>/dev/null || true; \
        USER_NAME="$EXISTING_USER"; \
    else \
        adduser -u 99 -S appuser -G "$GROUP_NAME" -s /bin/bash; \
        USER_NAME="appuser"; \
    fi && \
    echo "Application will run as user: $USER_NAME (UID 99) in group: $GROUP_NAME (GID 100)"

# Change ownership of the app directory to the user we're using
RUN USER_NAME=$(getent passwd 99 | cut -d: -f1) && \
    GROUP_NAME=$(getent group 100 | cut -d: -f1) && \
    chown -R "$USER_NAME:$GROUP_NAME" /app

# Set bash as default shell and keep root as login user
SHELL ["/bin/bash", "-c"]

# Switch to the user with UID 99 for running the application
RUN USER_NAME=$(getent passwd 99 | cut -d: -f1) && echo "USER $USER_NAME" > /tmp/user_directive
RUN cat /tmp/user_directive
USER $(getent passwd 99 | cut -d: -f1)

# Expose the port the app runs on
EXPOSE 9009

# Command to run the application
CMD ["python", "app.py"]
