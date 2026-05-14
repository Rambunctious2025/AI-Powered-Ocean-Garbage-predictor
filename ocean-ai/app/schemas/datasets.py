from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DatasetFileInfo(BaseModel):
    name: str
    path: str
    size_bytes: int = Field(ge=0)


class DatasetSummary(BaseModel):
    id: str
    display_name: str
    kind: str
    available: bool
    record_count: int = Field(default=0, ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bbox: Optional[List[float]] = None
    files: List[DatasetFileInfo] = Field(default_factory=list)
    notes: Optional[str] = None


class DatasetCatalogResponse(BaseModel):
    datasets: List[DatasetSummary]
