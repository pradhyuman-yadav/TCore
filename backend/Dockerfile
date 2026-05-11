FROM python:3.12-slim
WORKDIR /app
RUN pip install uv
COPY pyproject.toml .
RUN uv sync
COPY . .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
