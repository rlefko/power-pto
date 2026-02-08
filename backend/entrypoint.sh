#!/bin/sh
set -e

if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "Running database migrations..."
  uv run alembic upgrade head
fi

echo "Starting application..."
exec "$@"
