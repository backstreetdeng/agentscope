# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_TRANSPORT=streamable-http

WORKDIR /app/mcp
COPY deploy/requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --index-url "${PIP_INDEX_URL}" --timeout 120 --retries 5 \
    -r /tmp/requirements.txt

COPY market_data ./market_data
COPY scripts ./scripts
COPY deploy/sql ./deploy/sql

CMD ["python", "-m", "market_data.policy_server"]
