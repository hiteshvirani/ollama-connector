FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

CMD [ "sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}" ]
