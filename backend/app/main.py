





import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi

from backend.app.core.config import settings
from backend.app.core.database import Base, engine, check_db_connection

# ── Register ALL models before create_all() ──────────────────────────────────
from backend.app.models.user import User                                        
from backend.app.models.quiz import Quiz, Question, QuestionOption, QuizEnrollment  
from backend.app.models.attempt import QuizAttempt, AttemptAnswer               
from backend.app.models.notification import Notification                        

# ── Routers ───────────────────────────────────────────────────────────────────
from backend.app.routers import auth, dashboard, quiz, analytics
from backend.app.routers import settings as settings_router
from backend.app.routers import notifications, leaderboard, admin

# ── Ensure static directories exist on startup ───────────────────────────────
_STATIC_DIR  = os.path.join(os.getcwd(), "static")
_AVATARS_DIR = os.path.join(_STATIC_DIR, "avatars")
os.makedirs(_AVATARS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]"
    )
    try:
        check_db_connection()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified. Startup complete.")
    except Exception as exc:
        logger.critical(f"Startup failed: {exc}")
        raise
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Curio — Cloud Quiz Platform API",
    # Always expose docs; DEBUG flag controls it via settings but keep it on for now
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "X-Request-ID"],
)


# ── Request logger ────────────────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(f"Unhandled middleware error: {exc}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected server error occurred. Please try again."},
        )
    logger.debug(f"{request.method} {request.url.path} → {response.status_code}")
    return response


# ── API routers — MUST come before StaticFiles mounts ────────────────────────
app.include_router(auth.router,             prefix="/api/auth",          tags=["Auth"])
app.include_router(dashboard.router,        prefix="/api/dashboard",     tags=["Dashboard"])
app.include_router(quiz.router,             prefix="/api/quizzes",       tags=["Quizzes"])
app.include_router(analytics.router,        prefix="/api/analytics",     tags=["Analytics"])
app.include_router(settings_router.router,  prefix="/api/settings",      tags=["Settings"])
app.include_router(notifications.router,    prefix="/api/notifications", tags=["Notifications"])
app.include_router(leaderboard.router,      prefix="/api/leaderboard",   tags=["Leaderboard"])
app.include_router(admin.router,            prefix="/api/admin",         tags=["Admin"])

# ── Static files (avatars uploaded by users) ─────────────────────────────────
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health", include_in_schema=False)
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred. Please try again."},
    )


# ── Custom OpenAPI schema with Bearer auth ────────────────────────────────────
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token (obtained from /api/auth/login)",
        }
    }
    # Apply BearerAuth to every operation
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi

