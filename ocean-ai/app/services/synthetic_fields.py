from __future__ import annotations

import numpy as np


def synthetic_wind_components(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    lat_rad = np.deg2rad(latitudes)
    lon_rad = np.deg2rad(longitudes)

    wind_u = 5.0 * np.sin(lat_rad * 2.0) + 1.2 * np.cos(lon_rad * 1.3)
    wind_v = 4.0 * np.cos(lon_rad * 1.5) + 0.8 * np.sin(lat_rad * 0.7)
    return wind_u, wind_v


def synthetic_current_components(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    cx, cy = 75.0, 5.0
    dx = longitudes - cx
    dy = latitudes - cy
    radius = np.sqrt(dx**2 + dy**2) + 1e-6

    current_u = -dy / radius * np.exp(-radius / 20.0) * 0.8
    current_v = dx / radius * np.exp(-radius / 20.0) * 0.8
    return current_u, current_v


def approximate_divergence_grid(
    u: np.ndarray,
    v: np.ndarray,
    lat_grid: np.ndarray,
    resolution_deg: float,
) -> np.ndarray:
    dy = resolution_deg * 111_000.0
    cos_lat = np.clip(np.cos(np.deg2rad(lat_grid)), 1e-6, None)
    dx = resolution_deg * 111_000.0 * cos_lat

    du_dx = np.gradient(u, axis=1) / dx
    dv_dy = np.gradient(v, axis=0) / dy
    return du_dx + dv_dy


def sample_synthetic_features(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    resolution_deg: float = 0.25,
) -> dict[str, np.ndarray]:
    wind_u, wind_v = synthetic_wind_components(latitudes, longitudes)
    current_u, current_v = synthetic_current_components(latitudes, longitudes)

    eps = max(resolution_deg / 2.0, 0.05)
    wind_u_plus, _ = synthetic_wind_components(latitudes, longitudes + eps)
    wind_u_minus, _ = synthetic_wind_components(latitudes, longitudes - eps)
    _, wind_v_plus = synthetic_wind_components(latitudes + eps, longitudes)
    _, wind_v_minus = synthetic_wind_components(latitudes - eps, longitudes)

    dx = np.clip(2.0 * eps * 111_000.0 * np.cos(np.deg2rad(latitudes)), 1e-6, None)
    dy = 2.0 * eps * 111_000.0
    divergence = (wind_u_plus - wind_u_minus) / dx + (wind_v_plus - wind_v_minus) / dy

    return {
        "wind_u": wind_u,
        "wind_v": wind_v,
        "wind_speed": np.sqrt(wind_u**2 + wind_v**2),
        "current_u": current_u,
        "current_v": current_v,
        "current_speed": np.sqrt(current_u**2 + current_v**2),
        "divergence": divergence,
    }
