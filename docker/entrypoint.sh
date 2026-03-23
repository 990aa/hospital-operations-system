#!/bin/sh
set -eu

# Ensure runtime directories exist for SQLite DB, exports, and celery beat schedule.
mkdir -p /app/instance /app/exports /app/celery

if [ "$(id -u)" = "0" ]; then
  # Named volumes can be root-owned on first mount; fix and then drop privileges.
  chown -R "${APP_UID}:${APP_GID}" /app/instance /app/exports /app/celery
  exec gosu "${APP_UID}:${APP_GID}" "$@"
fi

exec "$@"
