from fastapi import APIRouter

from app.api.routes import datasets, predict

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(predict.router)
api_router.include_router(datasets.router)
