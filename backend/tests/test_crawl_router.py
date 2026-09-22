import datetime

from db.models import CrawlQueueEntry
from db.session import create_engine_and_session_factory

UTC = datetime.timezone.utc


def _seed(database_url, entries):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for entry in entries:
        session.add(CrawlQueueEntry(**entry))
    session.commit()
    session.close()


def test_crawl_status_reports_counts_by_page_type_and_status(database_url, api_client):
    _seed(database_url, [
        dict(url="u1", page_type="document", status="done",
             discovered_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
             processed_at=datetime.datetime(2026, 9, 1, 1, tzinfo=UTC)),
        dict(url="u2", page_type="document", status="pending",
             discovered_at=datetime.datetime(2026, 9, 1, tzinfo=UTC)),
        dict(url="u3", page_type="list", status="error", last_error="timeout",
             discovered_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
             processed_at=datetime.datetime(2026, 9, 1, 2, tzinfo=UTC)),
    ])

    response = api_client.get("/crawl/status")

    assert response.status_code == 200
    body = response.json()
    counts = {(row["page_type"], row["status"]): row["count"] for row in body["counts"]}
    assert counts == {
        ("document", "done"): 1,
        ("document", "pending"): 1,
        ("list", "error"): 1,
    }
    assert body["last_processed_at"] == "2026-09-01T02:00:00+00:00"
    assert len(body["recent_errors"]) == 1
    assert body["recent_errors"][0]["last_error"] == "timeout"


def test_crawl_status_requires_api_key(database_url):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(database_url=database_url, api_key="expected-key"))
    client = TestClient(app)

    assert client.get("/crawl/status").status_code in (401, 422)
