FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# minimal OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    build-essential \
    pkg-config \
    libcairo2-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY . /app/

RUN mkdir -p /data

EXPOSE 8000

CMD ["bash","-lc","python manage.py migrate && python manage.py collectstatic --noinput && gunicorn llama_inc.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - --capture-output --log-level info"]
