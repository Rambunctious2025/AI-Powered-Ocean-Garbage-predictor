from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split

from app.core.config import default_bbox, settings
from app.core.logging import get_logger
from app.services.observations import load_observation_labels
from app.services.synthetic_fields import (
    approximate_divergence_grid,
    sample_synthetic_features,
    synthetic_current_components,
    synthetic_wind_components,
)

logger = get_logger(__name__)

FEATURE_COLS = ["lat", "lon", "wind_speed", "divergence", "current_speed"]

_model_cache: Optional[xgb.XGBRegressor] = None


def _generate_synthetic_labels(df: pd.DataFrame, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)

    gyres = [
        (10.0, 75.0, 15.0),
        (-25.0, 80.0, 20.0),
        (0.0, 60.0, 12.0),
    ]

    gyre_proximity = np.zeros(len(df))
    for glat, glon, radius_deg in gyres:
        dist = np.sqrt((df["lat"] - glat) ** 2 + (df["lon"] - glon) ** 2)
        gyre_proximity += np.exp(-(dist**2) / (2 * radius_deg**2))

    gyre_proximity = np.clip(gyre_proximity, 0.0, 1.0)
    convergence = np.clip(-df["divergence"] * 5e4, 0.0, 1.0)
    current_norm = np.clip(df["current_speed"] / 1.5, 0.0, 1.0)

    risk = (0.45 * gyre_proximity) + (0.30 * convergence) + (0.25 * current_norm)
    risk = np.clip(risk + rng.normal(0.0, 0.04, size=len(df)), 0.0, 1.0)
    return risk.astype(np.float32)


def _build_synthetic_training_frame(
    resolution: float = 0.25,
    seed: int = 0,
) -> pd.DataFrame:
    lats = np.arange(settings.LAT_MIN, settings.LAT_MAX + resolution, resolution)
    lons = np.arange(settings.LON_MIN, settings.LON_MAX + resolution, resolution)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    rng = np.random.default_rng(seed)
    wind_u, wind_v = synthetic_wind_components(lat_grid, lon_grid)
    current_u, current_v = synthetic_current_components(lat_grid, lon_grid)

    wind_u = wind_u + rng.normal(0.0, 0.8, size=wind_u.shape)
    wind_v = wind_v + rng.normal(0.0, 0.8, size=wind_v.shape)
    current_u = current_u + rng.normal(0.0, 0.05, size=current_u.shape)
    current_v = current_v + rng.normal(0.0, 0.05, size=current_v.shape)

    divergence = approximate_divergence_grid(
        wind_u,
        wind_v,
        lat_grid=lat_grid,
        resolution_deg=resolution,
    )

    return pd.DataFrame(
        {
            "lat": lat_grid.ravel(),
            "lon": lon_grid.ravel(),
            "wind_speed": np.sqrt(wind_u**2 + wind_v**2).ravel(),
            "divergence": divergence.ravel(),
            "current_speed": np.sqrt(current_u**2 + current_v**2).ravel(),
        }
    )


def _build_observation_training_rows() -> tuple[pd.DataFrame, np.ndarray]:
    observations = load_observation_labels(region_bbox=default_bbox())
    if observations.empty:
        logger.info("No bundled observation rows fall inside the configured Indian Ocean region.")
        return pd.DataFrame(columns=FEATURE_COLS), np.array([], dtype=np.float32)

    sampled = sample_synthetic_features(
        observations["lat"].to_numpy(dtype=float),
        observations["lon"].to_numpy(dtype=float),
    )

    observed_df = pd.DataFrame(
        {
            "lat": observations["lat"].to_numpy(dtype=float),
            "lon": observations["lon"].to_numpy(dtype=float),
            "wind_speed": sampled["wind_speed"],
            "divergence": sampled["divergence"],
            "current_speed": sampled["current_speed"],
        }
    )
    observed_y = observations["observation_risk"].to_numpy(dtype=np.float32)

    logger.info("Prepared %d observation-backed training rows.", len(observed_df))
    return observed_df, observed_y


def train_model(save_path: Optional[Path] = None) -> xgb.XGBRegressor:
    save_path = save_path or settings.MODEL_PATH
    logger.info("Training XGBoost model ...")

    df = _build_synthetic_training_frame()
    y = _generate_synthetic_labels(df)
    sample_weight = np.ones(len(df), dtype=np.float32)

    observed_df, observed_y = _build_observation_training_rows()
    if not observed_df.empty:
        df = pd.concat([df, observed_df], ignore_index=True)
        y = np.concatenate([y, observed_y])
        sample_weight = np.concatenate(
            [sample_weight, np.full(len(observed_df), 2.5, dtype=np.float32)]
        )

    X_train, X_test, y_train, y_test, w_train, _w_test = train_test_split(
        df[FEATURE_COLS],
        y,
        sample_weight,
        test_size=0.15,
        random_state=42,
    )

    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        tree_method="hist",
        eval_metric="rmse",
        random_state=42,
        verbosity=0,
    )

    model.fit(
        X_train,
        y_train,
        sample_weight=w_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    rmse = float(np.sqrt(np.mean((model.predict(X_test) - y_test) ** 2)))
    logger.info("Model trained. Test RMSE = %.4f", rmse)

    save_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(save_path))
    logger.info("Model saved to %s", save_path)
    model.__dict__.setdefault("_estimator_type", "regressor")
    return model


def load_model(model_path: Optional[Path] = None) -> xgb.XGBRegressor:
    model_path = model_path or settings.MODEL_PATH
    model = xgb.XGBRegressor()
    model.__dict__.setdefault("_estimator_type", "regressor")
    model.load_model(str(model_path))
    logger.info("Model loaded from %s", model_path)
    return model


def get_model() -> xgb.XGBRegressor:
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    if settings.MODEL_PATH.exists():
        _model_cache = load_model()
    else:
        logger.warning(
            "No saved model found at %s; training from synthetic data.",
            settings.MODEL_PATH,
        )
        _model_cache = train_model()

    return _model_cache


def reset_model_cache() -> None:
    global _model_cache
    _model_cache = None
