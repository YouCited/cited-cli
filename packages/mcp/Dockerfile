FROM python:3.12-slim

WORKDIR /app

# Install core first (dependency), then mcp
COPY packages/core/ /app/packages/core/
COPY packages/mcp/ /app/packages/mcp/

RUN pip install --no-cache-dir /app/packages/core /app/packages/mcp

ENV PORT=8080
EXPOSE 8080

CMD ["cited-mcp-remote"]
