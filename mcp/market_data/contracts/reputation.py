"""Reputation MCP input contracts."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .common import PageInput, ResponseFormat


class Direction(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class SourceName(str, Enum):
    AUTOHOME = "autohome"
    DONGCHEDI = "dongchedi"


class SourceReviewInput(PageInput):
    model: str = Field(default="", max_length=100, description="Exact source model/input name; no fuzzy competitor-text attribution.")
    source: SourceName | None = None
    keyword: str = Field(default="", max_length=200, description="Filter original review text.")
    published_from: date | None = None
    published_to: date | None = None


class ReputationModelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    response_format: ResponseFormat = ResponseFormat.JSON


class ReputationSearchInput(PageInput):
    model: str = Field(default="", max_length=100)
    direction: Direction | None = None
    primary_label: str = Field(default="", max_length=100)
    secondary_label: str = Field(default="", max_length=100)
    tertiary_label: str = Field(default="", max_length=100)
    source: str = Field(default="", max_length=80)
    keyword: str = Field(default="", max_length=200)


class EvidenceInput(PageInput):
    model: str = Field(min_length=1, max_length=100)
    direction: Direction
    tertiary_label: str = Field(min_length=1, max_length=100)


class ReputationCompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    models: list[str] = Field(min_length=2, max_length=10)
    top_n: int = Field(default=5, ge=1, le=10)
    response_format: ResponseFormat = ResponseFormat.JSON