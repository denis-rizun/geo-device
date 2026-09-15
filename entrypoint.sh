#!/bin/sh
set -e

case "$1" in
  api)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" --workers "${API_WORKERS:-1}"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  generate)
    shift
    exec python -m app.generator "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
