# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=False

WORKDIR /app

# Non-root runtime user.
RUN adduser --disabled-password --gecos "" appuser

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source.
COPY . .

# Collect static (SPA + admin) into STATIC_ROOT at build time so the runtime
# filesystem can stay read-only. Uses safe defaults; no DB access needed.
RUN DJANGO_DEBUG=False python manage.py collectstatic --noinput

USER appuser
EXPOSE 8000

# Gunicorn (production WSGI). Migrations are run by the compose command.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
