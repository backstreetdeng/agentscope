"""Rights (权益) MCP input contracts. Shared by MCP server and data-api read models."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import PageInput, ResponseFormat


class Search(PageInput):
    brand: str = Field(default="", max_length=80, description="Brand name, e.g. 蔚来.")
    model: str = Field(default="", max_length=100, description="Model name keyword.")
    keyword: str = Field(default="", max_length=200, description="Keyword matched against all ledger fields.")
    activity_types: list[str] = Field(default_factory=list, max_length=6, description="Standard activity-type labels to match.")
    region: str = Field(default="", max_length=100, description="Region or channel keyword.")
    active_on: date | None = Field(default=None, description="Date that must fall within the activity validity range.")
    activity_match: Literal["any", "all"] = Field(default="any", description="Match any or all selected activity types.")
    power: str = Field(default="", max_length=80, description="Power type keyword.")
    start_date: date | None = Field(default=None, description="Earliest monitor date.")
    end_date: date | None = Field(default=None, description="Latest monitor date.")
    exact_names: bool = Field(default=False, description="Exact-match brand/model/region/power instead of substring.")
    data_version: str = Field(default="", max_length=100, description="Optional data version for optimistic read.")


class Export(Search):
    record_ids: list[str] = Field(default_factory=list, max_length=5000, description="Optional explicit record IDs (MYSQL-<id>).")
    limit: int = Field(default=5000, ge=1, le=5000)


class RightsIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    record_id: str = Field(min_length=1, max_length=80, description="Stable MYSQL-<id> primary key returned by search.")
    response_format: ResponseFormat = ResponseFormat.JSON


class RightsCompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    models: list[str] = Field(min_length=2, max_length=10, description="Two to ten model names.")
    active_on: date | None = Field(default=None, description="Optional effective date.")
    response_format: ResponseFormat = ResponseFormat.JSON


class RightsChangeInput(PageInput):
    brand: str = Field(default="", max_length=80, description="Optional brand filter.")
    change_type: str = Field(default="", max_length=80, description="Change-type keyword, e.g. 现金优惠调整.")