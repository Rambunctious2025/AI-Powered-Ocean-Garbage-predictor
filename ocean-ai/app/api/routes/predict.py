from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.prediction import (
    CurrentsResponse,
    HealthResponse,
    PredictRequest,
    PredictResponse,
)
from app.services.data_sources import clear_data_source_caches
from app.services.model import get_model, reset_model_cache
from app.services.observations import clear_observation_caches, get_observation_status
from app.services.prediction import _pred_cache, build_current_grid, run_prediction

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    try:
        model = get_model()
        model_loaded = model is not None
    except Exception:
        model_loaded = False

    observation_status = get_observation_status()
    return HealthResponse(
        status="ok" if model_loaded else "degraded",
        version=settings.VERSION,
        model_loaded=model_loaded,
        era5_available=settings.ERA5_NC_PATH.exists(),
        hycom_cache_available=settings.HYCOM_CACHE_PATH.exists(),
        mdmap_available=bool(observation_status["mdmap_available"]),
        noaa_21429_available=bool(observation_status["noaa_21429_available"]),
        observation_records=int(observation_status["observation_records"]),
    )


@router.get("/predict", response_model=PredictResponse, tags=["prediction"])
async def predict_get(
    date: Optional[date] = Query(default=None, description="Forecast date (YYYY-MM-DD)"),
    resolution: float = Query(default=0.5, ge=0.1, le=2.0, description="Grid resolution in degrees"),
    lat_min: float = Query(default=settings.LAT_MIN, description="South boundary (latitude)"),
    lat_max: float = Query(default=settings.LAT_MAX, description="North boundary (latitude)"),
    lon_min: float = Query(default=settings.LON_MIN, description="West boundary (longitude)"),
    lon_max: float = Query(default=settings.LON_MAX, description="East boundary (longitude)"),
    forecast_days: int = Query(default=1, ge=1, le=14, description="Days ahead to forecast"),
) -> PredictResponse:
    bbox = [lon_min, lat_min, lon_max, lat_max]
    try:
        return run_prediction(
            forecast_date=date,
            resolution=resolution,
            bbox=bbox,
            forecast_days=forecast_days,
        )
    except Exception as exc:
        logger.exception("Prediction failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Prediction error: {exc}")


@router.post("/predict", response_model=PredictResponse, tags=["prediction"])
async def predict_post(body: PredictRequest) -> PredictResponse:
    try:
        return run_prediction(
            forecast_date=body.date,
            resolution=body.resolution,
            bbox=body.bbox,
            forecast_days=body.forecast_days,
        )
    except Exception as exc:
        logger.exception("Prediction failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Prediction error: {exc}")


@router.get("/currents/{day}", response_model=CurrentsResponse, tags=["data"])
async def get_currents(
    day: int = Path(..., ge=0, le=13, description="Forecast day index 0-13"),
    resolution: float = Query(default=1.0, ge=0.5, le=2.0),
) -> CurrentsResponse:
    try:
        grid = build_current_grid(day=day, resolution=resolution)
        return CurrentsResponse(day=day, grid=grid)
    except Exception as exc:
        logger.exception("Current grid failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/predict/refresh", tags=["system"])
async def refresh_cache() -> dict:
    _pred_cache.clear()
    clear_observation_caches()
    clear_data_source_caches()
    reset_model_cache()
    logger.info("Prediction cache cleared via /predict/refresh")
    return {
        "status": "cache cleared",
        "message": "Prediction, model, and dataset caches were reset.",
    }
