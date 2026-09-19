from db.models import Comment, Document
from db.session import create_engine_and_session_factory


def _seed_document(database_url, **overrides):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    defaults = dict(
        external_id=1, section="npa", url="https://example.test/1",
        title_ru="Title", status="active",
        first_seen_at="2026-09-01T00:00:00+00:00",
        last_checked_at="2026-09-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    document = Document(**defaults)
    session.add(document)
    session.commit()
    document_id = document.id
    session.close()
    return document_id


def test_list_documents_filters_by_section(database_url, api_client):
    _seed_document(database_url, external_id=1, section="npa", url="https://example.test/1")
    _seed_document(database_url, external_id=2, section="arv", url="https://example.test/2")

    response = api_client.get("/documents", params={"section": "arv"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["section"] == "arv"


def test_get_document_returns_404_for_missing_id(api_client):
    response = api_client.get("/documents/999999")
    assert response.status_code == 404


def test_get_document_includes_comments(database_url, api_client):
    document_id = _seed_document(database_url, external_id=3, section="npa", url="https://example.test/3")
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    session.add(Comment(
        document_id=document_id, external_comment_id=10, body="text",
        first_seen_at="2026-09-01T00:00:00+00:00",
    ))
    session.commit()
    session.close()

    response = api_client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["body"] == "text"


def test_documents_endpoint_requires_api_key(database_url):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(database_url=database_url, api_key="expected-key"))
    client = TestClient(app)

    assert client.get("/documents").status_code in (401, 422)
