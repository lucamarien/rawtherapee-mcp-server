FROM python:3.12-slim

# Install RawTherapee
RUN apt-get update && \
    apt-get install -y --no-install-recommends rawtherapee && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

ENTRYPOINT ["rawtherapee-mcp-server"]
