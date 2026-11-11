FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home flowbridge \
    && mkdir -p /app/private_media /app/staticfiles \
    && chown -R flowbridge:flowbridge /app \
    && chmod +x /app/docker/web-entrypoint.sh
USER flowbridge

EXPOSE 8000
CMD ["/app/docker/web-entrypoint.sh"]
