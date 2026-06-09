#!/bin/sh
set -e

# ─────────────────────────────────────────────────────────────────────────────
# Railway Fix: volume монтируется ПОСЛЕ Docker build-слоёв, поэтому
# permissions директории /app/data сбрасываются до root:root 755.
# Этот скрипт запускается как root и явно выставляет нужные права ДО старта бота.
# ─────────────────────────────────────────────────────────────────────────────

mkdir -p /app/data /app/backups /app/logs
chmod 777 /app/data /app/backups /app/logs

echo "[entrypoint] Permissions fixed:"
ls -la /app/ | grep -E "data|backups|logs"

exec "$@"
