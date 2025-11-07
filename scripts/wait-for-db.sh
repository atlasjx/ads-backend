#!/usr/bin/env bash
# Wait for Postgres to be ready using pg_isready
set -euo pipefail
HOST=${DATABASE_HOST:-db}
PORT=${DATABASE_PORT:-5432}
USER=${DATABASE_USER:-postgres}

echo "Waiting for postgres at $HOST:$PORT..."
for i in {1..30}; do
  if pg_isready -h "$HOST" -p "$PORT" -U "$USER" >/dev/null 2>&1; then
    echo "Postgres is ready"
    exit 0
  fi
  sleep 1
done

echo "Postgres did not become ready in time"
exit 1

