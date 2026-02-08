FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io docker-cli golang-go git ca-certificates \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && git clone --depth 1 --branch v0.39.0 https://github.com/docker/mcp-gateway.git /tmp/mcp-gateway \
    && cd /tmp/mcp-gateway \
    && GOTOOLCHAIN=auto go build -o /usr/local/lib/docker/cli-plugins/docker-mcp ./cmd/docker-mcp \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-mcp \
    && rm -rf /tmp/mcp-gateway \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
