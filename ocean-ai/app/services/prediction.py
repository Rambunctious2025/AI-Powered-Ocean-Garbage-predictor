from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from typing import Optional

import numpy as np
from cachetools import TTLCache

from app.core.config import default_bbox, settings
from app.core.logging import get_logger
from app.schemas.prediction import Hotspot, PredictResponse
from app.services.data_sources import load_era5, load_hycom
from app.services.feature_engineering import FEATURE_COLS, build_features
from app.services.model import get_model

logger = get_logger(__name__)

_pred_cache: TTLCache = TTLCache(maxsize=32, ttl=3600)
RISK_THRESHOLD = 0.35


def _bbox_hash(bbox: list[float]) -> str:
    return hashlib.md5(json.dumps(bbox).encode()).hexdigest()[:8]


def _normalise_bbox(bbox: Optional[list[float]]) -> list[float]:
    normalised = [float(value) for value in (bbox or default_bbox())]
    if len(normalised) != 4:
        raise ValueError("bbox must contain [lon_min, lat_min, lon_max, lat_max]")

    lon_min, lat_min, lon_max, lat_max = normalised
    if lon_min >= lon_max or lat_min >= lat_max:
        raise ValueError("bbox min values must be smaller than max values")
    return [lon_min, lat_min, lon_max, lat_max]


def run_prediction(
    forecast_date: Optional[date] = None,
    resolution: float = 0.5,
    bbox: Optional[list[float]] = None,
    forecast_days: int = 1,
    risk_threshold: float = RISK_THRESHOLD,
) -> PredictResponse:
    if forecast_date is None:
        forecast_date = date.today()

    bbox = _normalise_bbox(bbox)
    cache_key = (str(forecast_date), resolution, _bbox_hash(bbox), forecast_days)
    if cache_key in _pred_cache:
        logger.debug("Serving prediction from cache (key=%s)", cache_key)
        return _pred_cache[cache_key]

    t_start = time.perf_counter()
    era5_ds = load_era5()
    hycom_ds = load_hycom()
    df = build_features(era5_ds, hycom_ds, resolution=resolution)

    lon_min, lat_min, lon_max, lat_max = bbox
    df = df[
        (df["lat"] >= lat_min)
        & (df["lat"] <= lat_max)
        & (df["lon"] >= lon_min)
        & (df["lon"] <= lon_max)
    ].reset_index(drop=True)

    if df.empty:
        logger.warning("No grid points remain after bbox filter: %s", bbox)
        return PredictResponse(
            forecast_date=str(forecast_date),
            model_version=settings.MODEL_VERSION,
            hotspots=[],
            grid_resolution_deg=resolution,
            region_bbox=bbox,
            total_cells=0,
        )

    model = get_model()
    raw_risk = model.predict(df[FEATURE_COLS]).astype(float)

    day_phase = forecast_days * 0.05
    lat_arr = df["lat"].to_numpy(dtype=float)
    lon_arr = df["lon"].to_numpy(dtype=float)
    temporal_wave = (
        np.sin(lat_arr * 0.1 + day_phase) * 0.04
        + np.cos(lon_arr * 0.08 + day_phase * 1.3) * 0.03
    )
    df["risk"] = np.clip(raw_risk + temporal_wave, 0.0, 1.0)

    hotspot_df = df[df["risk"] >= risk_threshold].copy()
    hotspot_df = hotspot_df.sort_values("risk", ascending=False).head(500)

    hotspots = [
        Hotspot(
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            risk=round(float(row["risk"]), 4),
            wind_speed=round(float(row["wind_speed"]), 3),
            current_speed=round(float(row["current_speed"]), 3),
            divergence=round(float(row["divergence"]), 6),
        )
        for _, row in hotspot_df.iterrows()
    ]

    elapsed = time.perf_counter() - t_start
    logger.info(
        "Prediction complete: %d hotspots (of %d cells) in %.2f s",
        len(hotspots),
        len(df),
        elapsed,
    )

    response = PredictResponse(
        forecast_date=str(forecast_date),
        model_version=settings.MODEL_VERSION,
        hotspots=hotspots,
        grid_resolution_deg=resolution,
        region_bbox=bbox,
        total_cells=len(df),
    )
    _pred_cache[cache_key] = response
    return response


def build_current_grid(day: int = 0, resolution: float = 1.0) -> list[dict]:
    hycom_ds = load_hycom()
    era5_ds = load_era5()
    df = build_features(era5_ds, hycom_ds, resolution=resolution)

    day_phase = day * 0.08
    grid: list[dict] = []
    for _, row in df.iterrows():
        u = float(row.get("current_u", row.get("wind_u", 0.0))) + np.sin(day_phase) * 0.05
        v = float(row.get("current_v", row.get("wind_v", 0.0))) + np.cos(day_phase) * 0.05
        div = float(row.get("divergence", 0.0))
        grid.append(
            {
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "u": round(u, 4),
                "v": round(v, 4),
                "div": round(div, 6),
            }
        )

    return grid
