from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== OceanScan AI starting up ===")

    try:
        from app.services.model import get_model

        model = get_model()
        logger.info("Model ready: %s", type(model).__name__)
    except Exception as exc:
        logger.error("Model pre-warm failed: %s", exc)

    try:
        from app.services.data_sources import load_hycom

        hycom = load_hycom()
        if hycom is not None:
            logger.info("HYCOM data ready.")
        else:
            logger.warning("HYCOM data unavailable at startup; synthetic currents will be used.")
    except Exception as exc:
        logger.warning("HYCOM pre-fetch error: %s", exc)

    logger.info("=== Startup complete. Listening for requests. ===")
    yield
    logger.info("=== OceanScan AI shutting down. ===")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.VERSION,
        description=(
            "AI-powered ocean garbage hotspot forecasting API. Uses ERA5 wind, "
            "HYCOM ocean currents, and bundled NOAA/MDMAP observation assets."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    from app.api.routes.datasets import list_datasets
    from app.api.routes.predict import (
        get_currents,
        health,
        predict_get,
        predict_post,
        refresh_cache,
    )

    app.add_api_route("/predict", predict_get, methods=["GET"], tags=["prediction"])
    app.add_api_route("/predict", predict_post, methods=["POST"], tags=["prediction"])
    app.add_api_route("/health", health, methods=["GET"], tags=["system"])
    app.add_api_route("/currents/{day}", get_currents, methods=["GET"], tags=["data"])
    app.add_api_route("/predict/refresh", refresh_cache, methods=["POST"], tags=["system"])
    app.add_api_route("/datasets", list_datasets, methods=["GET"], tags=["data"])

    return app


app = create_app()
