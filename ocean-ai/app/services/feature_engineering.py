from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

from app.core.config import settings
from app.core.logging import get_logger
from app.services.synthetic_fields import (
    approximate_divergence_grid,
    synthetic_current_components,
    synthetic_wind_components,
)

logger = get_logger(__name__)

FEATURE_COLS = [
    "lat",
    "lon",
    "wind_speed",
    "divergence",
    "current_speed",
]


def _build_lat_lon_grid(resolution: float) -> tuple[np.ndarray, np.ndarray]:
    lats = np.arange(settings.LAT_MIN, settings.LAT_MAX + resolution, resolution)
    lons = np.arange(settings.LON_MIN, settings.LON_MAX + resolution, resolution)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    return lat_grid, lon_grid


def _interp_to_grid(
    ds: xr.Dataset,
    lat_grid: np.ndarray,
    lon_grid: np.ndarray,
    lat_name: str = "lat",
    lon_name: str = "lon",
) -> xr.Dataset:
    flat_lats = xr.DataArray(lat_grid.ravel(), dims="points")
    flat_lons = xr.DataArray(lon_grid.ravel(), dims="points")
    return ds.interp({lat_name: flat_lats, lon_name: flat_lons}, method="linear")


def build_features(
    era5_ds: Optional[xr.Dataset],
    hycom_ds: Optional[xr.Dataset],
    resolution: float = 0.5,
) -> pd.DataFrame:
    lat_grid, lon_grid = _build_lat_lon_grid(resolution)
    n_points = lat_grid.size

    df = pd.DataFrame({"lat": lat_grid.ravel(), "lon": lon_grid.ravel()})

    if era5_ds is not None:
        try:
            lat_name = next((c for c in ("lat", "latitude") if c in era5_ds.coords), "latitude")
            lon_name = next((c for c in ("lon", "longitude") if c in era5_ds.coords), "longitude")
            time_dim = next((d for d in ("time", "valid_time") if d in era5_ds.dims), None)
            ds_t = era5_ds.isel({time_dim: 0}) if time_dim else era5_ds

            interp = _interp_to_grid(ds_t, lat_grid, lon_grid, lat_name, lon_name)
            wind_u = np.array(interp["u10"]).reshape(lat_grid.shape)
            wind_v = np.array(interp["v10"]).reshape(lat_grid.shape)
            wind_u = np.nan_to_num(wind_u, nan=0.0)
            wind_v = np.nan_to_num(wind_v, nan=0.0)

            df["wind_u"] = wind_u.ravel()
            df["wind_v"] = wind_v.ravel()
            df["wind_speed"] = np.sqrt(wind_u**2 + wind_v**2).ravel()
            df["divergence"] = approximate_divergence_grid(
                wind_u,
                wind_v,
                lat_grid,
                resolution,
            ).ravel()
            logger.debug("ERA5 features computed for %d points.", n_points)
        except Exception as exc:
            logger.warning("ERA5 feature extraction failed (%s); using zeros.", exc)
            df["wind_u"] = 0.0
            df["wind_v"] = 0.0
            df["wind_speed"] = 0.0
            df["divergence"] = 0.0
    else:
        logger.info("No ERA5 data; generating synthetic wind field.")
        wind_u, wind_v = synthetic_wind_components(lat_grid, lon_grid)
        df["wind_u"] = wind_u.ravel()
        df["wind_v"] = wind_v.ravel()
        df["wind_speed"] = np.sqrt(wind_u**2 + wind_v**2).ravel()
        df["divergence"] = approximate_divergence_grid(
            wind_u,
            wind_v,
            lat_grid,
            resolution,
        ).ravel()

    if hycom_ds is not None:
        try:
            lat_name = "lat" if "lat" in hycom_ds.coords else "Latitude"
            lon_name = "lon" if "lon" in hycom_ds.coords else "Longitude"
            u_var = next((name for name in ("water_u", "u", "u_curr") if name in hycom_ds), None)
            v_var = next((name for name in ("water_v", "v", "v_curr") if name in hycom_ds), None)

            if not u_var or not v_var:
                raise ValueError(f"Expected velocity vars not found in HYCOM: {list(hycom_ds.data_vars)}")

            interp = _interp_to_grid(hycom_ds, lat_grid, lon_grid, lat_name, lon_name)
            curr_u = np.nan_to_num(np.array(interp[u_var]).reshape(lat_grid.shape))
            curr_v = np.nan_to_num(np.array(interp[v_var]).reshape(lat_grid.shape))
            df["current_u"] = curr_u.ravel()
            df["current_v"] = curr_v.ravel()
            df["current_speed"] = np.sqrt(curr_u**2 + curr_v**2).ravel()
            logger.debug("HYCOM features computed for %d points.", n_points)
        except Exception as exc:
            logger.warning("HYCOM feature extraction failed (%s); using zeros.", exc)
            df["current_u"] = 0.0
            df["current_v"] = 0.0
            df["current_speed"] = 0.0
    else:
        logger.info("No HYCOM data; generating synthetic current field.")
        current_u, current_v = synthetic_current_components(lat_grid, lon_grid)
        df["current_u"] = current_u.ravel()
        df["current_v"] = current_v.ravel()
        df["current_speed"] = np.sqrt(current_u**2 + current_v**2).ravel()

    return df
