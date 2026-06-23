FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY prompts/ prompts/

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "-c", "import uvicorn; uvicorn.run('rinha.main:app', host='0.0.0.0', port=8765)"]
