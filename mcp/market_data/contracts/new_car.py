"""New-car MCP input contracts."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from .common import PageInput, ResponseFormat


class NewCarSearchInput(PageInput):
    brand: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=100)
    enterprise: str = Field(default="", max_length=100)
    energy_type: str = Field(default="", max_length=50)
    vehicle_type: str = Field(default="", max_length=50)
    launch_start: date | None = None
    launch_end: date | None = None


class PlannedCarSearchInput(PageInput):
    brand: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=100)
    market_status: str = Field(default="", max_length=50)
    energy_type: str = Field(default="", max_length=50)
    launch_year: int | None = Field(default=None, ge=2000, le=2100)
    launch_quarter: str = Field(default="", max_length=20)


class ModelInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model: str = Field(min_length=1, max_length=100)
    brand: str = Field(default="", max_length=100)
    energy_type: str = Field(default="", max_length=100)
    response_format: ResponseFormat = ResponseFormat.JSON


class ModelDetailInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    model_style_id: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=100)
    response_format: ResponseFormat = ResponseFormat.JSON


class LaunchCalendarInput(PageInput):
    start_date: date
    end_date: date
    energy_type: str = Field(default="", max_length=50)
    brand: str = Field(default="", max_length=80)


class CompareModelsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    models: list[str] = Field(min_length=2, max_length=10)
    response_format: ResponseFormat = ResponseFormat.JSON