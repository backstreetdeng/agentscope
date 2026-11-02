"""Policy MCP input contracts."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from .common import PageInput, ResponseFormat


class PolicySearchInput(PageInput):
    province: str = Field(default="", max_length=50, description="Province name, e.g. 江苏.")
    city: str = Field(default="", max_length=80, description="City name, e.g. 南京市.")
    keyword: str = Field(default="", max_length=200, description="Keyword matched against all policy fields.")
    start_date: date | None = Field(default=None, description="Earliest monitoring/publish date.")
    end_date: date | None = Field(default=None, description="Latest monitoring/publish date.")
    policy_type: str = Field(default="", max_length=80, description="Policy promotion type or audience keyword.")


class PolicyIdInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    record_id: str = Field(min_length=1, max_length=80, description="Policy record ID, e.g. POL-0002-408044.")
    response_format: ResponseFormat = ResponseFormat.JSON


class PolicyChangeInput(PageInput):
    province: str = Field(default="", max_length=50, description="Optional province filter.")
    change_type: str = Field(default="", max_length=80, description="Change type, such as 新增、调整、到期.")
    start_date: date | None = Field(default=None, description="Earliest monitoring date.")
    end_date: date | None = Field(default=None, description="Latest monitoring date.")


class PolicyCompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    regions: list[str] = Field(min_length=2, max_length=10, description="Two to ten province/city names.")
    keyword: str = Field(default="", max_length=200, description="Optional policy keyword.")
    active_on: date | None = Field(default=None, description="Optional date that must fall in the policy validity range.")
    limit_per_region: int = Field(default=10, ge=1, le=30)
    response_format: ResponseFormat = ResponseFormat.JSON


class PolicyExportInput(PolicySearchInput):
    record_ids: list[str] = Field(default_factory=list, max_length=5000, description="Optional explicit policy IDs.")
    limit: int = Field(default=100, ge=1, le=5000)