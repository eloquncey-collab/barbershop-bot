FROM python:3.10-slim

WORKDIR /app

# Railway Fix: директории создаются на этапе build,
# entrypoint.sh исправит права при монтировании volume в рантайме
RUN mkdir -p /app/data /app/backups /app/logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import asyncio, aiosqlite, os; asyncio.run(aiosqlite.connect(os.getenv('DB_PATH','/app/data/barbershop.db')).__aenter__())" || exit 1

# USER botuser УДАЛЁН: Railway монтирует volume как root:root 755,
# non-root процесс не может писать в него -> sqlite3.OperationalError.
# Контейнеры Railway изолированы, root внутри безопасен.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "bot.py"]
