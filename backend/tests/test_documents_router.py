import datetime

from db.models import Comment, LegalAct
from db.session import create_engine_and_session_factory

UTC = datetime.timezone.utc
T1 = datetime.datetime(2026, 9, 1, tzinfo=UTC)


def _seed_legal_act(database_url, **overrides):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    defaults = dict(
        external_id=1, section="npa", url="https://example.test/1",
        title_ru="Title", status="active",
        first_seen_at=T1, last_checked_at=T1,
    )
    defaults.update(overrides)
    legal_act = LegalAct(**defaults)
    session.add(legal_act)
    session.commit()
    legal_act_id = legal_act.id
    session.close()
    return legal_act_id


def test_list_documents_filters_by_section(database_url, api_client):
    _seed_legal_act(database_url, external_id=1, section="npa", url="https://example.test/1")
    _seed_legal_act(database_url, external_id=2, section="arv", url="https://example.test/2")

    response = api_client.get("/documents", params={"section": "arv"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["section"] == "arv"


def test_get_document_returns_404_for_missing_id(api_client):
    response = api_client.get("/documents/999999")
    assert response.status_code == 404


def test_get_document_includes_comments(database_url, api_client):
    legal_act_id = _seed_legal_act(database_url, external_id=3, section="npa", url="https://example.test/3")
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    session.add(Comment(
        legal_act_id=legal_act_id, external_comment_id=10, comment_channel=6, body="text",
        first_seen_at=T1,
    ))
    session.commit()
    session.close()

    response = api_client.get(f"/documents/{legal_act_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["body"] == "text"


def test_get_document_resolves_government_body_and_doc_type_names(database_url, api_client):
    legal_act_id = _seed_legal_act(database_url, external_id=4, section="npa", url="https://example.test/4")
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    from db.models import ActType, GovernmentBody
    legal_act = session.get(LegalAct, legal_act_id)
    government_body = GovernmentBody(name="Министерство юстиции")
    act_type = ActType(name="Закон")
    session.add_all([government_body, act_type])
    session.flush()
    legal_act.government_body_id = government_body.id
    legal_act.act_type_id = act_type.id
    session.commit()
    session.close()

    response = api_client.get(f"/documents/{legal_act_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["government_body"] == "Министерство юстиции"
    assert body["doc_type"] == "Закон"


def test_documents_endpoint_requires_api_key(database_url):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(database_url=database_url, api_key="expected-key"))
    client = TestClient(app)

    assert client.get("/documents").status_code in (401, 422)
