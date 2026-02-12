from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings
import app.models


app = FastAPI(
    root_path="/api",
    title="Gomguk API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
