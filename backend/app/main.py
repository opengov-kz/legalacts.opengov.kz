from fastapi import FastAPI

from app.config import Settings
from app.routers import analytics, crawl, documents
from db.session import create_engine_and_session_factory


def create_app(settings=None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="legalacts backend")

    _, session_factory = create_engine_and_session_factory(settings.database_url)
    app.state.settings = settings
    app.state.session_factory = session_factory

    app.include_router(documents.router)
    app.include_router(analytics.router)
    app.include_router(crawl.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
