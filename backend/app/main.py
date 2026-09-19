from fastapi import FastAPI

from app.config import Settings
from db.session import create_engine_and_session_factory


def create_app(settings=None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="legalacts backend")

    _, session_factory = create_engine_and_session_factory(settings.database_url)
    app.state.settings = settings
    app.state.session_factory = session_factory

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


try:
    app = create_app()
except Exception:
    # If environment variables aren't set (e.g., during testing),
    # app won't be created. This is OK because tests create app explicitly.
    app = None
