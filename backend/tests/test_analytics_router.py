import datetime

from db.models import Comment, LegalAct
from db.session import create_engine_and_session_factory

UTC = datetime.timezone.utc


def _seed(database_url, acts, comments=()):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for act in acts:
        session.add(LegalAct(**act))
    session.commit()
    for comment in comments:
        session.add(Comment(**comment))
    session.commit()
    session.close()


def test_analytics_summary_counts_by_section_and_status(database_url, api_client):
    _seed(database_url, [
        dict(external_id=1, section="npa", url="u1", status="active",
             first_seen_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 1, tzinfo=UTC)),
        dict(external_id=2, section="npa", url="u2", status="archived",
             first_seen_at=datetime.datetime(2026, 9, 2, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 2, tzinfo=UTC)),
        dict(external_id=3, section="arv", url="u3", status="active",
             first_seen_at=datetime.datetime(2026, 9, 3, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 3, tzinfo=UTC)),
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
             first_seen_at=datetime.datetime(2026, 9, 1, 10, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 1, 10, tzinfo=UTC)),
        dict(external_id=2, section="npa", url="u2",
             first_seen_at=datetime.datetime(2026, 9, 1, 18, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 1, 18, tzinfo=UTC)),
        dict(external_id=3, section="npa", url="u3",
             first_seen_at=datetime.datetime(2026, 9, 2, 9, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 2, 9, tzinfo=UTC)),
    ])

    response = api_client.get("/analytics/timeseries", params={"interval": "day"})

    assert response.status_code == 200
    body = response.json()
    counts = {point["bucket"][:10]: point["count"] for point in body}
    assert counts == {"2026-09-01": 2, "2026-09-02": 1}


def test_analytics_timeseries_rejects_invalid_interval(api_client):
    response = api_client.get("/analytics/timeseries", params={"interval": "month"})
    assert response.status_code == 400
