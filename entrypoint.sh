#!/bin/bash
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}..."

while ! pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -q 2>/dev/null; do
  sleep 1
done

echo "PostgreSQL is ready. Starting application on port ${PORT:-8000}..."
exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
