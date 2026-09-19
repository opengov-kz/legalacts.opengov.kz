from db.models import Comment, Document
from db.session import create_engine_and_session_factory


def _seed(database_url, documents, comments=()):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for doc in documents:
        session.add(Document(**doc))
    session.commit()
    for comment in comments:
        session.add(Comment(**comment))
    session.commit()
    session.close()


def test_analytics_summary_counts_by_section_and_status(database_url, api_client):
    _seed(database_url, [
        dict(external_id=1, section="npa", url="u1", status="active",
             first_seen_at="2026-09-01T00:00:00+00:00", last_checked_at="2026-09-01T00:00:00+00:00"),
        dict(external_id=2, section="npa", url="u2", status="archived",
             first_seen_at="2026-09-02T00:00:00+00:00", last_checked_at="2026-09-02T00:00:00+00:00"),
        dict(external_id=3, section="arv", url="u3", status="active",
             first_seen_at="2026-09-03T00:00:00+00:00", last_checked_at="2026-09-03T00:00:00+00:00"),
    ])

    response = api_client.get("/analytics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 3
    section_counts = {row["section"]: row["count"] for row in body["documents_by_section"]}
    assert section_counts == {"npa": 2, "arv": 1}


def test_analytics_timeseries_buckets_by_day(database_url, api_client):
    _seed(database_url, [
        dict(external_id=1, section="npa", url="u1",
             first_seen_at="2026-09-01T10:00:00+00:00", last_checked_at="2026-09-01T10:00:00+00:00"),
        dict(external_id=2, section="npa", url="u2",
             first_seen_at="2026-09-01T18:00:00+00:00", last_checked_at="2026-09-01T18:00:00+00:00"),
        dict(external_id=3, section="npa", url="u3",
             first_seen_at="2026-09-02T09:00:00+00:00", last_checked_at="2026-09-02T09:00:00+00:00"),
    ])

    response = api_client.get("/analytics/timeseries", params={"interval": "day"})

    assert response.status_code == 200
    body = response.json()
    counts = {point["bucket"][:10]: point["count"] for point in body}
    assert counts == {"2026-09-01": 2, "2026-09-02": 1}


def test_analytics_timeseries_rejects_invalid_interval(api_client):
    response = api_client.get("/analytics/timeseries", params={"interval": "month"})
    assert response.status_code == 400
