"""Shared Pydantic input contract base (protocol-agnostic; no DB / no FastMCP)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


class PageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    limit: int = Field(default=20, ge=1, le=100, description="Maximum records to return, 1-100.")
    offset: int = Field(default=0, ge=0, description="Number of matching records to skip.")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON, description="json or markdown")