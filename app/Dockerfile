FROM python:3.11-alpine

RUN apk add --no-cache docker-cli docker-cli-compose git

WORKDIR /app

COPY backend /app/app/backend
COPY frontend /app/app/frontend

ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "app.backend"]
