from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "OceanScan AI"
    VERSION: str = "1.1.0"
    MODEL_VERSION: str = "xgb-1.1"
    DEBUG: bool = False

    LAT_MIN: float = -30.0
    LAT_MAX: float = 35.0
    LON_MIN: float = 40.0
    LON_MAX: float = 110.0

    DATA_DIR: Path = BASE_DIR / "data"
    MODELS_DIR: Path = BASE_DIR / "models"
    OBSERVATIONS_DIR: Path = DATA_DIR / "observations"
    OBSERVATIONS_RAW_DIR: Path = OBSERVATIONS_DIR / "raw"

    ERA5_NC_PATH: Path = DATA_DIR / "era5_wind.nc"
    HYCOM_URL: str = "https://tds.hycom.org/thredds/dodsC/GLBy0.08/expt_93.0"
    HYCOM_CACHE_PATH: Path = DATA_DIR / "hycom_cache.nc"

    MDMAP_DIR: Path = OBSERVATIONS_RAW_DIR / "mdmap"
    MDMAP_MAIN_CSV_PATH: Path = MDMAP_DIR / "MDMAP_Export_20260401.csv"
    MDMAP_BACKBARRIER_CSV_PATH: Path = MDMAP_DIR / "MDMAP_Export_20260401_backbarrier.csv"
    MDMAP_ZIP_PATH: Path = MDMAP_DIR / "MDMAP_Export_20260401.zip"

    NOAA_21429_DIR: Path = OBSERVATIONS_RAW_DIR / "noaa_21429"
    NOAA_21429_PDF_PATH: Path = NOAA_21429_DIR / "noaa_21429_DS1.pdf"

    MODEL_PATH: Path = MODELS_DIR / "xgb_garbage_risk.json"
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    GRID_RESOLUTION: float = 0.5

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str] | str:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return stripped
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value


settings = Settings()

settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.MODELS_DIR.mkdir(parents=True, exist_ok=True)
settings.OBSERVATIONS_RAW_DIR.mkdir(parents=True, exist_ok=True)
settings.MDMAP_DIR.mkdir(parents=True, exist_ok=True)
settings.NOAA_21429_DIR.mkdir(parents=True, exist_ok=True)


def default_bbox() -> list[float]:
    return [settings.LON_MIN, settings.LAT_MIN, settings.LON_MAX, settings.LAT_MAX]
