from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from app.core.config import default_bbox, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_LAT_COLUMNS = (
    "site_waters_edge_left_lat",
    "site_waters_edge_right_lat",
    "site_back_barrier_left_lat",
    "site_back_barrier_right_lat",
)
_LON_COLUMNS = (
    "site_waters_edge_left_lon",
    "site_waters_edge_right_lon",
    "site_back_barrier_left_lon",
    "site_back_barrier_right_lon",
)
_MDMAP_FILES: tuple[tuple[str, Path], ...] = (
    ("shoreline", settings.MDMAP_MAIN_CSV_PATH),
    ("backbarrier", settings.MDMAP_BACKBARRIER_CSV_PATH),
)


def _existing_columns(frame: pd.DataFrame, columns: Iterable[str]) -> list[str]:
    return [column for column in columns if column in frame.columns]


def _series_or_empty(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(index=frame.index, dtype="float64")


def _file_record(path: Path) -> dict:
    return {
        "name": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size,
    }


def _bbox_from_frame(frame: pd.DataFrame) -> Optional[list[float]]:
    if frame.empty:
        return None
    return [
        round(float(frame["lon"].min()), 6),
        round(float(frame["lat"].min()), 6),
        round(float(frame["lon"].max()), 6),
        round(float(frame["lat"].max()), 6),
    ]


def _clean_mdmap_frame(raw: pd.DataFrame, zone: str, source_file: Path) -> pd.DataFrame:
    lat_columns = _existing_columns(raw, _LAT_COLUMNS)
    lon_columns = _existing_columns(raw, _LON_COLUMNS)

    latitudes = raw[lat_columns].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    longitudes = raw[lon_columns].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    total_debris = pd.to_numeric(_series_or_empty(raw, "total_debris_items"), errors="coerce").fillna(0.0)
    site_length = pd.to_numeric(_series_or_empty(raw, "site_length"), errors="coerce")
    transect_width = pd.to_numeric(_series_or_empty(raw, "transect_width"), errors="coerce")
    beach_width = pd.to_numeric(_series_or_empty(raw, "beach_width_at_transect"), errors="coerce")
    survey_width = transect_width.where(transect_width > 0).fillna(beach_width)
    area_sq_m = site_length * survey_width

    items_per_100m = pd.Series(
        np.where(site_length > 0, (total_debris * 100.0) / site_length, np.nan),
        index=raw.index,
    )
    items_per_sq_m = pd.Series(
        np.where(area_sq_m > 0, total_debris / area_sq_m, np.nan),
        index=raw.index,
    )

    cleaned = pd.DataFrame(
        {
            "dataset_id": "mdmap",
            "zone": zone,
            "survey_id": _series_or_empty(raw, "survey_id"),
            "shoreline_site_id": _series_or_empty(raw, "shoreline_site_id"),
            "shoreline_site_name": _series_or_empty(raw, "shoreline_site_name"),
            "survey_protocol": _series_or_empty(raw, "survey_protocol"),
            "survey_date": pd.to_datetime(_series_or_empty(raw, "survey_date"), errors="coerce"),
            "country": _series_or_empty(raw, "country"),
            "state_province_territory": _series_or_empty(raw, "state_province_territory"),
            "region": _series_or_empty(raw, "region"),
            "lat": latitudes,
            "lon": longitudes,
            "total_debris_items": total_debris,
            "items_per_100m": items_per_100m,
            "items_per_sq_m": items_per_sq_m,
            "source_file": source_file.name,
        }
    )

    cleaned = cleaned.dropna(subset=["lat", "lon"]).copy()
    density = (
        cleaned["items_per_100m"]
        .fillna(cleaned["items_per_sq_m"] * 1000.0)
        .fillna(cleaned["total_debris_items"])
        .clip(lower=0.0)
    )
    log_density = np.log1p(density)
    density_range = float(log_density.max() - log_density.min()) if not cleaned.empty else 0.0
    if density_range > 0:
        cleaned["observation_risk"] = (log_density - log_density.min()) / density_range
    else:
        cleaned["observation_risk"] = 0.0

    return cleaned


@lru_cache(maxsize=1)
def load_mdmap_observations() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for zone, path in _MDMAP_FILES:
        if not path.exists():
            logger.info("MDMAP file not found: %s", path)
            continue

        try:
            raw = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            logger.warning("Failed to read MDMAP file %s: %s", path, exc)
            continue

        if raw.empty:
            continue

        frames.append(_clean_mdmap_frame(raw, zone=zone, source_file=path))

    if not frames:
        return pd.DataFrame(
            columns=[
                "dataset_id",
                "zone",
                "survey_id",
                "shoreline_site_id",
                "shoreline_site_name",
                "survey_protocol",
                "survey_date",
                "country",
                "state_province_territory",
                "region",
                "lat",
                "lon",
                "total_debris_items",
                "items_per_100m",
                "items_per_sq_m",
                "source_file",
                "observation_risk",
            ]
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(
        by=["survey_date", "shoreline_site_id", "zone"],
        ascending=[False, True, True],
        na_position="last",
    ).reset_index(drop=True)
    logger.info("Loaded %d MDMAP observations.", len(combined))
    return combined


def load_observation_labels(region_bbox: Optional[list[float]] = None) -> pd.DataFrame:
    observations = load_mdmap_observations()
    if observations.empty:
        return pd.DataFrame(columns=["lat", "lon", "observation_risk", "dataset_id"])

    lon_min, lat_min, lon_max, lat_max = region_bbox or default_bbox()
    filtered = observations[
        (observations["lat"] >= lat_min)
        & (observations["lat"] <= lat_max)
        & (observations["lon"] >= lon_min)
        & (observations["lon"] <= lon_max)
    ].copy()

    return filtered.loc[:, ["lat", "lon", "observation_risk", "dataset_id"]]


@lru_cache(maxsize=1)
def get_dataset_catalog() -> list[dict]:
    mdmap_files = [path for _, path in _MDMAP_FILES if path.exists()]
    mdmap_observations = load_mdmap_observations()
    mdmap_dates = (
        mdmap_observations["survey_date"].dropna()
        if "survey_date" in mdmap_observations
        else pd.Series(dtype="datetime64[ns]")
    )

    return [
        {
            "id": "mdmap",
            "display_name": "NOAA MDMAP shoreline surveys",
            "kind": "tabular",
            "available": bool(mdmap_files),
            "record_count": int(len(mdmap_observations)),
            "start_date": mdmap_dates.min().date().isoformat() if not mdmap_dates.empty else None,
            "end_date": mdmap_dates.max().date().isoformat() if not mdmap_dates.empty else None,
            "bbox": _bbox_from_frame(mdmap_observations),
            "files": [_file_record(path) for path in mdmap_files],
            "notes": (
                "Cleaned from the bundled MDMAP export. This dataset is available "
                "to the backend for cataloging and optional observation-based training."
            ),
        },
        {
            "id": "noaa_21429",
            "display_name": "NOAA 21429 reference document",
            "kind": "document",
            "available": settings.NOAA_21429_PDF_PATH.exists(),
            "record_count": 0,
            "start_date": None,
            "end_date": None,
            "bbox": None,
            "files": [_file_record(settings.NOAA_21429_PDF_PATH)] if settings.NOAA_21429_PDF_PATH.exists() else [],
            "notes": (
                "Bundled as a local project reference PDF. It is available to the "
                "backend as NOAA_21429 source material, but it is not a tabular training dataset."
            ),
        },
    ]


def get_observation_status() -> dict[str, int | bool]:
    catalog = {entry["id"]: entry for entry in get_dataset_catalog()}
    mdmap = catalog.get("mdmap", {})
    noaa = catalog.get("noaa_21429", {})

    return {
        "mdmap_available": bool(mdmap.get("available", False)),
        "noaa_21429_available": bool(noaa.get("available", False)),
        "observation_records": int(mdmap.get("record_count", 0)),
    }


def clear_observation_caches() -> None:
    load_mdmap_observations.cache_clear()
    get_dataset_catalog.cache_clear()
