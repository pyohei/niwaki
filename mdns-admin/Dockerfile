FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends avahi-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --chmod=755 entrypoint.sh /app/entrypoint.sh
COPY server.py /app/server.py
COPY template.html /app/template.html

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
