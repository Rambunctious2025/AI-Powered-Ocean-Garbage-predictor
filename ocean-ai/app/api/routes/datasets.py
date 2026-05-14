from __future__ import annotations

from fastapi import APIRouter

from app.schemas.datasets import DatasetCatalogResponse, DatasetSummary
from app.services.observations import get_dataset_catalog

router = APIRouter()


@router.get("/datasets", response_model=DatasetCatalogResponse, tags=["data"])
async def list_datasets() -> DatasetCatalogResponse:
    datasets = [DatasetSummary.model_validate(entry) for entry in get_dataset_catalog()]
    return DatasetCatalogResponse(datasets=datasets)
