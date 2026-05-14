from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class PredictRequest(BaseModel):
    bbox: Optional[List[float]] = Field(default=None, min_length=4, max_length=4)
    date: Optional[date] = None
    resolution: float = Field(default=0.5, ge=0.1, le=2.0)
    forecast_days: int = Field(default=1, ge=1, le=14)

    @model_validator(mode="after")
    def validate_bbox(self) -> "PredictRequest":
        if self.bbox is None:
            return self

        lon_min, lat_min, lon_max, lat_max = self.bbox
        if lon_min >= lon_max or lat_min >= lat_max:
            raise ValueError(
                "bbox must be [lon_min, lat_min, lon_max, lat_max] with min values smaller than max values"
            )
        return self


class Hotspot(BaseModel):
    lat: float
    lon: float
    risk: float = Field(..., ge=0.0, le=1.0)
    wind_speed: Optional[float] = None
    current_speed: Optional[float] = None
    divergence: Optional[float] = None


class PredictResponse(BaseModel):
    forecast_date: str
    model_version: str
    hotspots: List[Hotspot]
    grid_resolution_deg: float
    region_bbox: List[float]
    total_cells: int


class HealthResponse(BaseModel):
    status: str
    version: str
    model_loaded: bool
    era5_available: bool
    hycom_cache_available: bool
    mdmap_available: bool = False
    noaa_21429_available: bool = False
    observation_records: int = 0


class CurrentsResponse(BaseModel):
    day: int
    grid: List[dict]
