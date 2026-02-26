FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies (includes pg_isready for entrypoint health check)
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser and its OS-level dependencies
RUN playwright install --with-deps chromium

# Copy the rest of the project
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Create runtime directories
RUN mkdir -p downloads videos cache static/js templates/partials

# Default port; Railway sets $PORT at runtime
EXPOSE ${PORT:-8000}

ENTRYPOINT ["./entrypoint.sh"]
