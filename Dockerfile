FROM python:3.10-slim

WORKDIR /app

# Railway Fix: ���������� ��������� �� ����� build,
# entrypoint.sh �������� ����� ��� ������������ volume � ��������
RUN mkdir -p /app/data /app/backups /app/logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh

HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os,sys; db=os.getenv('DB_PATH','/app/data/barbershop.db'); sys.exit(0 if os.path.exists(db) else 1)"

# USER botuser ���˨�: Railway ��������� volume ��� root:root 755,
# non-root ������� �� ����� ������ � ���� -> sqlite3.OperationalError.
# ���������� Railway �����������, root ������ ���������.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "bot.py"]
