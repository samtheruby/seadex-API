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
    shadow  # needed for usermod/groupmod

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install requirements
RUN pip install --upgrade pip setuptools && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user/group with UID=99 and GID=100 if not already present
# Resolve the username at build time so USER can be set literally
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
    echo "$USER_NAME" > /tmp/appuser && \
    chown -R "$USER_NAME:$GROUP_NAME" /app

# Set bash as default shell
SHELL ["/bin/bash", "-c"]

# Read username from /tmp/appuser and set USER instruction literally
ARG APPUSER
RUN APPUSER=$(cat /tmp/appuser) && echo "Using USER=$APPUSER" && echo "$APPUSER" > /tmp/finaluser
USER $(cat /tmp/finaluser)

# Expose port
EXPOSE 9009

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:9009/api?t=caps || exit 1

# Run app
CMD ["python", "app.py"]
