FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install curl for cloudflared download
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

# Make start script executable
RUN chmod +x /app/start.sh

ENV PYTHONPATH=/app
ENV NODE_PORT=8001

EXPOSE 8001

CMD [ "/app/start.sh" ]
