FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY adaptive_viva_ast ./adaptive_viva_ast
COPY app ./app

RUN useradd --create-home avg && chown -R avg /app
USER avg

EXPOSE 8000
# The worker uses the same image: `rq worker avg --url $REDIS_URL`
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
