FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY ozon_mcp/ ozon_mcp/

RUN pip install --no-cache-dir .

EXPOSE 8000

ENV DATA_DIR=/data
VOLUME /data

CMD ["uvicorn", "ozon_mcp.app:fastapi_app", "--host", "0.0.0.0", "--port", "8000"]
