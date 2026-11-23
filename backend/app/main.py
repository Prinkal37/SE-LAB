"""Adaptive Viva Generator - backend API.

Run:  uvicorn app.main:app --reload        (from the backend/ folder)
Docs: http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import db as dbmod
from .config import get_settings
from .errors import install_error_handlers
from .queue import queue_health
from .routers import assignments, auth, courses, questions, submissions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    dbmod.init_db()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description="REST API for the Adaptive Viva Generator (SRS v1.0). "
                    "Auth: log in via /auth/login; the JWT is set as an httpOnly cookie.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,  # frontend sends the cookie with credentials: "include"
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for r in (auth.router, courses.router, assignments.router, submissions.router, questions.router):
        app.include_router(r, prefix=s.api_prefix)

    @app.get("/health", tags=["health"])
    def health():
        try:
            with dbmod.engine.connect() as c:
                c.execute(text("SELECT 1"))
            database = "ok"
        except Exception:
            database = "error"
        return {"status": "ok" if database == "ok" else "degraded", "database": database,
                "queue": queue_health(), "llm": s.llm_model or "template"}

    return app


app = create_app()
