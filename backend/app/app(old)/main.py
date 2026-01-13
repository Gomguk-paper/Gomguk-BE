from fastapi import FastAPI
from api.routers import router as event_stats_router

app = FastAPI()
app.include_router(event_stats_router)