FROM python:3.11-alpine

RUN apk add --no-cache avahi-tools docker-cli docker-cli-compose git

WORKDIR /app

COPY --chmod=755 entrypoint.sh /app/entrypoint.sh
COPY backend /app/app/backend
COPY frontend /app/app/frontend

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
