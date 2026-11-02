"""Internal client for MCP servers to call data-api（唯一数据访问层）。

安全约束：
- 只读 DATA_API_INTERNAL_URL / DATA_API_INTERNAL_TOKEN，不持有数据库凭据。
- 不在异常消息中输出 URL、Token、SQL 或响应全文。
- GET 请求连接/超时错误最多重试一次；401/403/409 不重试。
"""
from __future__ import annotations

import os
from typing import Any

import httpx


class DataApiError(Exception):
    """结构化 data-api 错误，只暴露错误码和业务文案。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DataApiClient:
    """MCP 服务器 → data-api 的异步内部客户端。"""

    def __init__(self) -> None:
        self.base_url = os.getenv("DATA_API_INTERNAL_URL", "").rstrip("/")
        self.token = os.getenv("DATA_API_INTERNAL_TOKEN", "")
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            if not self.base_url:
                raise DataApiError("DATA_API_CONFIG", "数据服务地址未配置")
            if not self.token:
                raise DataApiError("DATA_API_CONFIG", "数据服务内部凭据未配置")
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(30.0, connect=3.0),
                headers={"Authorization": "Bearer " + self.token},
            )
        return self._client

    async def get(self, resource: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        client = await self._ensure_client()
        for _attempt in (1, 2):
            try:
                response = await client.get(resource, params=params)
            except (httpx.ConnectError, httpx.TimeoutException):
                continue
            if response.status_code in (401, 403):
                raise DataApiError("DATA_API_UNAUTHORIZED", "数据服务鉴权失败")
            if response.status_code in (400, 422):
                raise DataApiError("DATA_API_BAD_REQUEST", "查询参数无效")
            if response.status_code == 404:
                raise DataApiError("DATA_API_NOT_FOUND", "数据资源不存在")
            if response.status_code == 409:
                raise DataApiError("DATA_API_VERSION_CHANGED", "数据版本已变化，请重新查询")
            if response.status_code >= 500:
                raise DataApiError("DATA_API_UNAVAILABLE", "数据服务暂不可用")
            data = response.json()
            if not data.get("success", True):
                raise DataApiError("DATA_API_ERROR", data.get("error", "数据服务返回失败"))
            return data
        raise DataApiError("DATA_API_UNAVAILABLE", "数据服务不可用")

    async def post(self, resource: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        client = await self._ensure_client()
        for _attempt in (1, 2):
            try:
                response = await client.post(resource, json=payload)
            except (httpx.ConnectError, httpx.TimeoutException):
                continue
            if response.status_code in (401, 403):
                raise DataApiError("DATA_API_UNAUTHORIZED", "数据服务鉴权失败")
            if response.status_code in (400, 422):
                raise DataApiError("DATA_API_BAD_REQUEST", "查询参数无效")
            if response.status_code == 404:
                raise DataApiError("DATA_API_NOT_FOUND", "数据资源不存在")
            if response.status_code == 409:
                raise DataApiError("DATA_API_VERSION_CHANGED", "数据版本已变化，请重新查询")
            if response.status_code >= 500:
                raise DataApiError("DATA_API_UNAVAILABLE", "数据服务暂不可用")
            data = response.json()
            if not data.get("success", True):
                raise DataApiError("DATA_API_ERROR", data.get("error", "数据服务返回失败"))
            return data
        raise DataApiError("DATA_API_UNAVAILABLE", "数据服务不可用")

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
