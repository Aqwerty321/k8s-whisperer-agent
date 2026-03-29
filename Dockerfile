FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8010

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

RUN mkdir -p /app/data /app/audit_log

EXPOSE 8010

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8010"]
