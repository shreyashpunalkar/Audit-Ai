"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.config import get_settings
from app.database import init_db
from app.routers import upload_router, process_router, document_router
from app.utils.error_handler import AppError, app_error_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("Starting AI Checksheet Converter backend...")
    settings.ensure_upload_dir()
    await init_db()
    logger.info("Database tables created/verified.")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="AI Checksheet to JSON Converter",
    description="Upload checksheet documents (Excel, PDF, Images, DOCX) and extract structured JSON using Gemini AI.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Error Handlers ───────────────────────────────────────────────────────────
app.add_exception_handler(AppError, app_error_handler)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(upload_router)
app.include_router(process_router)
app.include_router(document_router)


# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["health"])
async def health():
    if settings.groq_api_key:
        provider = "Groq"
        model = settings.groq_model
    elif settings.gemini_api_key:
        provider = "Google Gemini"
        model = settings.gemini_model
    else:
        provider = "NVIDIA NIM"
        model = settings.nvidia_model

    return {
        "status": "ok",
        "service": settings.app_name,
        "version": "1.0.0",
        "environment": settings.app_env,
        "ai_provider": provider,
        "ai_model": model,
        "ai_configured": settings.ai_configured,
        "mock_ai_enabled": settings.mock_ai,
    }
