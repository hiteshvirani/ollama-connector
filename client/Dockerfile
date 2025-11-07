FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

ENV PYTHONPATH=/app
ENV NODE_PORT=8001

EXPOSE 8001

CMD [ "sh", "-c", "uvicorn agent:app --host :: --port ${NODE_PORT:-8001}" ]
