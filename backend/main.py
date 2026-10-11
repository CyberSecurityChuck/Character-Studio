import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api_engines import API_ENGINES
from backend.api_settings import router as api_settings_router
from backend.backup import BackupRunner, clean_partial
from backend.backups_api import router as backups_router
from backend.batches import router as batches_router
from backend.configuration import Settings, load_settings
from backend.jobs import JobRunner, reconcile_on_startup
from backend.keystore import key_info
from backend.library import backfill_photo_hashes, clean_deleted_files
from backend.library import router as library_router
from backend.models import StudioPreferences
from backend.persistence import SCHEMA_REVISION, open_database
from backend.providers import PROVIDERS
from backend.quality_api import router as quality_router
from backend.results import router as results_router
from backend.scenes import router as scenes_router
from backend.schemas import PreferencesResponse, PreferencesUpdate


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = open_database(settings)
        app.state.settings = settings
        clean_deleted_files(app.state.engine, settings)
        backfill_photo_hashes(app.state.engine, settings)
        # Runs left over from a previous process are never resumed (DECISIONS.md D010).
        # Reconciling also re-checks every approval against the current inputs.
        reconcile_on_startup(app.state.engine)
        clean_partial(settings)
        app.state.backups = BackupRunner(app.state.engine, settings)
        app.state.runner = JobRunner(app.state.engine, settings)
        app.state.runner.start()
        app.state.session_token = secrets.token_urlsafe(32)
        try:
            yield
        finally:
            app.state.runner.stop()
            app.state.engine.dispose()

    app = FastAPI(
        title="Character Studio",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.exception_handler(OSError)
    async def storage_error(request: Request, exc: OSError):
        return JSONResponse(
            {
                "detail": "Local storage is unavailable. Check disk space and folder permissions, "
                "then reload to check saved state before retrying."
            },
            status_code=503,
        )

    @app.exception_handler(OperationalError)
    async def database_error(request: Request, exc: OperationalError):
        return JSONResponse(
            {"detail": "The local database is busy or unavailable. Reload and try again."},
            status_code=503,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return JSONResponse(
            {
                "detail": "This item is still referenced by other saved work. "
                "Reload the library or archive it instead."
            },
            status_code=409,
        )

    @app.middleware("http")
    async def protect_local_session(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in settings.allowed_origins:
            return JSONResponse({"detail": "This origin is not allowed."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site access is not allowed."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            token = request.headers.get("x-studio-token", "")
            if not secrets.compare_digest(token, request.app.state.session_token):
                return JSONResponse(
                    {"detail": "Session expired. Reload the studio before saving."}, status_code=403
                )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        return response

    @app.get("/api/health")
    def health():
        with app.state.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        return {"application": "character-studio", "status": "ok", "schema_revision": revision}

    @app.get("/api/bootstrap")
    def bootstrap():
        with Session(app.state.engine) as session:
            preferences = PreferencesResponse.model_validate(session.get(StudioPreferences, 1))
        return {
            "preferences": preferences,
            "session_token": app.state.session_token,
            "phase": 6,
            "max_upload_bytes": settings.max_upload_bytes,
            "schema_revision": SCHEMA_REVISION,
            "data_directory": str(settings.data_dir),
            # True once an API key is saved; every paid run still needs confirmation.
            "paid_operations_enabled": any(
                key_info(settings, engine)["saved"] for engine in API_ENGINES
            ),
            "providers": PROVIDERS,
        }

    @app.put("/api/preferences", response_model=PreferencesResponse)
    def save_preferences(body: PreferencesUpdate):
        with Session(app.state.engine) as session, session.begin():
            result = session.execute(
                update(StudioPreferences)
                .where(StudioPreferences.id == 1, StudioPreferences.revision == body.revision)
                .values(studio_name=body.studio_name, revision=body.revision + 1)
            )
            if result.rowcount != 1:
                raise HTTPException(409, "Saved preferences changed. Reload before saving again.")
        return PreferencesResponse(studio_name=body.studio_name, revision=body.revision + 1)

    app.include_router(library_router)
    app.include_router(scenes_router)
    app.include_router(results_router)
    app.include_router(backups_router)
    app.include_router(batches_router)
    app.include_router(api_settings_router)
    app.include_router(quality_router)

    @app.get("/api/{unmatched:path}", include_in_schema=False)
    def missing_api(unmatched: str):
        raise HTTPException(404, "This feature is not implemented yet.")

    if settings.frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
    else:

        @app.get("/")
        def frontend_missing():
            return JSONResponse(
                {"detail": "Build with npm --prefix frontend run build, then restart."},
                status_code=503,
            )

    return app
