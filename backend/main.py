"""
DocQuery backend entry point.

Run with:  python -m backend.main
(or:       uvicorn backend.main:app --reload)

Startup NEVER deletes ./document_store or ./chroma_db. It only creates them
if they don't exist yet and re-opens whatever is already there -- this is
the direct fix for the old prototype wiping all uploaded data and
embeddings on every restart.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import config, database
from backend.routes import chat, contact, documents, misc
from backend.utils.errors import AppError, error_body
from backend.utils.file_utils import UploadValidationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("docquery")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for problem in config.validate():
        logger.warning("Configuration problem: %s", problem)
    config.ensure_directories()  # create-if-missing; never deletes existing data
    database.init_db()  # create tables if missing; never drops existing data
    logger.info(
        "DocQuery ready. document_store=%s chroma_db=%s sqlite=%s",
        config.DOCUMENT_STORE_DIR, config.CHROMA_DB_DIR, config.SQLITE_DB_PATH,
    )
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="DocQuery", version="2.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    # --- Structured error handling: every error path returns the same
    # {"success": false, "error": {"code", "message"}} shape. ------------
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(UploadValidationError)
    async def _upload_validation_error_handler(request: Request, exc: UploadValidationError):
        return JSONResponse(status_code=400, content=error_body(exc.code, exc.message))

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "The request body didn't match what was expected."),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=error_body("INTERNAL_ERROR", "Something went wrong on the server.")
        )

    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(contact.router)
    app.include_router(misc.router)

    # Serve the frontend from the same process/port as the API, so there's
    # exactly one thing to start. API routers are registered above this, so
    # /api/... is always matched first; this mount only catches everything else.
    if config.FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT, reload=config.RELOAD)
