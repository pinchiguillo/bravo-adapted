FROM alpine:3.20

RUN apk add --no-cache graphviz

WORKDIR /app

COPY docs/db/database_schema.dot /templates/database_schema.dot
COPY docker/db-diagram-exporter/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
