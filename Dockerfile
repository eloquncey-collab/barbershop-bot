FROM python:3.10-slim
# UTF-8 - production Dockerfile

WORKDIR /app

# Railway: create directories at build time.
# entrypoint.sh initializes DB path and volume at runtime.
RUN mkdir -p /app/data /app/backups /app/logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os,sys; db=os.getenv('DB_PATH','/app/data/barbershop.db'); sys.exit(0 if os.path.exists(db) else 1)"

# NOTE: Running as root intentionally.
# Railway mounts volumes as root:root 755. A non-root user cannot write to them,
# causing sqlite3.OperationalError on first write. Use root for Railway deploys.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "bot.py"]
