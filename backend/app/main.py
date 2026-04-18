
# import logging
# import sys
# import os
# from contextlib import asynccontextmanager

# from fastapi import FastAPI, Request
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# from fastapi.staticfiles import StaticFiles

# from backend.app.core.config import settings
# from backend.app.core.database import Base, engine, check_db_connection

# #  Register all models so SQLAlchemy creates tables 
# from backend.app.models.user import User                                
# from backend.app.models.quiz import Quiz, Question, QuestionOption      
# from backend.app.models.attempt import QuizAttempt, AttemptAnswer       
# from backend.app.models.notification import Notification                

# #  Routers  #
# from backend.app.routers import auth, dashboard, quiz, analytics
# from backend.app.routers import settings as settings_router
# from backend.app.routers import notifications
# from backend.app.routers import leaderboard          

# #  Create static/avatars directory before StaticFiles is mounted 
# # Must exist before the app starts — StaticFiles will crash if dir is missing.
# _STATIC_DIR  = os.path.join(os.getcwd(), "static")
# _AVATARS_DIR = os.path.join(_STATIC_DIR, "avatars")
# os.makedirs(_AVATARS_DIR, exist_ok=True)

# #  Logging 
# logging.basicConfig(
#     level=logging.DEBUG if settings.DEBUG else logging.INFO,
#     format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
#     stream=sys.stdout,
# )
# logger = logging.getLogger(__name__)


# #  Lifespan  #
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
#     check_db_connection()
#     Base.metadata.create_all(bind=engine)
#     logger.info("Startup complete.")
#     yield
#     logger.info("Shutting down.")


# #  App  #
# app = FastAPI(
#     title=settings.APP_NAME,
#     version=settings.APP_VERSION,
#     docs_url="/docs"  if settings.DEBUG else None,
#     redoc_url="/redoc" if settings.DEBUG else None,
#     lifespan=lifespan,
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.FRONTEND_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     response = await call_next(request)
#     return response


# #  API Routers (ALL registered before any static mounts)  
# app.include_router(auth.router)
# app.include_router(dashboard.router)
# app.include_router(quiz.router)
# app.include_router(analytics.router)
# app.include_router(settings_router.router)
# app.include_router(notifications.router)
# app.include_router(leaderboard.router)      

# #  Static files: uploaded avatars (/static/avatars/<uuid>.jpg)  
# # Must come AFTER all API routers and BEFORE the catch-all frontend mount.
# app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# #  Frontend catch-all (MUST be last)  
# _frontend_dir = os.path.join(os.getcwd(), "frontend")
# if os.path.isdir(_frontend_dir):
#     app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
#     logger.info(f"Serving frontend from {os.path.abspath(_frontend_dir)}")


# #  Health 
# @app.get("/health", include_in_schema=False)
# def health():
#     return {"status": "ok", "app": settings.APP_NAME, "env": settings.ENVIRONMENT}


# #  Global error handler 
# @app.exception_handler(Exception)
# async def generic_exception_handler(request: Request, exc: Exception):
#     logger.exception(f"Unhandled error on {request.url.path}: {exc}")
#     return JSONResponse(
#         status_code=500,
#         content={"detail": "An unexpected server error occurred."},
#     )
















import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.core.database import Base, engine, check_db_connection

# Register all models
from backend.app.models.user import User                                # noqa
from backend.app.models.quiz import Quiz, Question, QuestionOption, QuizEnrollment  # noqa
from backend.app.models.attempt import QuizAttempt, AttemptAnswer       # noqa
from backend.app.models.notification import Notification                # noqa

# Routers
from backend.app.routers import auth, dashboard, quiz, analytics
from backend.app.routers import settings as settings_router
from backend.app.routers import notifications, leaderboard
from backend.app.routers import admin                                   # ← NEW

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
    logger.info(f"Starting {settings.APP_NAME} [{settings.ENVIRONMENT}]")
    check_db_connection()
    Base.metadata.create_all(bind=engine)
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs"  if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    return response


# ── API routers (before any static mounts) ───────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(quiz.router)
app.include_router(analytics.router)
app.include_router(settings_router.router)
app.include_router(notifications.router)
app.include_router(leaderboard.router)
app.include_router(admin.router)                                        # ← NEW

# ── Static files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "app": settings.APP_NAME}


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})
