from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.api.v1.jobs import router as jobs_router
from app.api.endpoints.export import router as export_router
from app.api.endpoints.summary import router as summary_router
from app.models.recon import ModuleRun, RawObservation, Entity, Evidence


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables for DB models on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# CORS Configuration for React/Vite Frontend
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route Registrations
app.include_router(jobs_router, prefix=f"{settings.API_V1_STR}/jobs", tags=["Jobs"])
app.include_router(export_router, prefix=f"{settings.API_V1_STR}", tags=["Export"])
app.include_router(summary_router, prefix=f"{settings.API_V1_STR}", tags=["LLM Analysis"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": settings.APP_ENV}