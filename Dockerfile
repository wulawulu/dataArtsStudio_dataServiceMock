FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime dependencies
RUN pip install --no-cache-dir \
    flask \
    duckdb \
    requests \
    datetime

# Copy application code
COPY . /app

EXPOSE 80

CMD ["python", "backend.py"]
