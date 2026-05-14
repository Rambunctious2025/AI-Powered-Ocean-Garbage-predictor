from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _normalise_spatial_coords(ds: xr.Dataset) -> xr.Dataset:
    rename_map = {}
    for source, target in (
        ("latitude", "lat"),
        ("longitude", "lon"),
        ("Latitude", "lat"),
        ("Longitude", "lon"),
    ):
        if source in ds.coords and target not in ds.coords:
            rename_map[source] = target

    if rename_map:
        ds = ds.rename(rename_map)

    if "lon" in ds.coords:
        lon_values = np.asarray(ds["lon"].values)
        if lon_values.size and np.nanmax(lon_values) > 180:
            ds = ds.assign_coords(lon=(((ds["lon"] + 180) % 360) - 180)).sortby("lon")

    return ds


def _slice_to_region(ds: xr.Dataset) -> xr.Dataset:
    if "lat" not in ds.coords or "lon" not in ds.coords:
        return ds

    lat_values = np.asarray(ds["lat"].values)
    lat_slice = (
        slice(settings.LAT_MAX, settings.LAT_MIN)
        if lat_values.size > 1 and lat_values[0] > lat_values[-1]
        else slice(settings.LAT_MIN, settings.LAT_MAX)
    )
    lon_slice = slice(settings.LON_MIN, settings.LON_MAX)
    return ds.sel(lat=lat_slice, lon=lon_slice)


@lru_cache(maxsize=2)
def _load_era5_cached(path_str: str) -> Optional[xr.Dataset]:
    path = Path(path_str)
    if not path.exists():
        logger.warning(
            "ERA5 NetCDF not found at %s. Download it from the Copernicus Climate Data Store.",
            path,
        )
        return None

    try:
        ds = xr.open_dataset(path, engine="netcdf4")
        ds = _slice_to_region(_normalise_spatial_coords(ds))
        logger.info("ERA5 dataset loaded: %s", dict(ds.dims))
        return ds
    except Exception as exc:
        logger.error("Failed to load ERA5 data: %s", exc)
        return None


def load_era5(
    nc_path: Optional[Path] = None,
    force_refresh: bool = False,
) -> Optional[xr.Dataset]:
    if force_refresh:
        _load_era5_cached.cache_clear()

    path = Path(nc_path or settings.ERA5_NC_PATH)
    return _load_era5_cached(str(path.resolve()))


def load_hycom(force_refresh: bool = False) -> Optional[xr.Dataset]:
    cache = settings.HYCOM_CACHE_PATH

    if cache.exists() and not force_refresh:
        try:
            ds = xr.open_dataset(cache, engine="netcdf4", decode_times=False)
            ds = _slice_to_region(_normalise_spatial_coords(ds))
            logger.info("HYCOM loaded from cache: %s", cache)
            return ds
        except Exception as exc:
            logger.warning("HYCOM cache read failed (%s); attempting remote fetch.", exc)

    logger.info("Fetching HYCOM slice from OPeNDAP; this may take 30-60 seconds.")
    try:
        ds_remote = xr.open_dataset(
            settings.HYCOM_URL,
            engine="netcdf4",
            decode_times=False,
        )

        sel_kwargs: dict[str, int] = {}
        if "time" in ds_remote.dims:
            sel_kwargs["time"] = 0
        if "depth" in ds_remote.dims:
            sel_kwargs["depth"] = 0

        ds_sliced = ds_remote.isel(**sel_kwargs) if sel_kwargs else ds_remote
        ds_sliced = _slice_to_region(_normalise_spatial_coords(ds_sliced))

        t0 = time.perf_counter()
        ds_sliced = ds_sliced.load()
        logger.info("HYCOM slice downloaded in %.1f s", time.perf_counter() - t0)

        ds_sliced.to_netcdf(cache)
        logger.info("HYCOM cache saved to %s", cache)
        return ds_sliced
    except Exception as exc:
        logger.error("HYCOM remote fetch failed: %s", exc)
        if cache.exists():
            logger.warning("Returning stale HYCOM cache after fetch failure.")
            ds = xr.open_dataset(cache, engine="netcdf4", decode_times=False)
            return _slice_to_region(_normalise_spatial_coords(ds))
        logger.error("No HYCOM data available (remote failed, no cache).")
        return None


def clear_data_source_caches() -> None:
    _load_era5_cached.cache_clear()
