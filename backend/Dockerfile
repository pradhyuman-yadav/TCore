FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install uv
COPY pyproject.toml .
RUN uv sync
COPY . .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
