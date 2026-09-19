from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import require_api_key


def _make_test_app(api_key):
    app = FastAPI()
    app.state.settings = Settings(database_url="postgresql://unused/db", api_key=api_key)

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    def protected():
        return {"ok": True}

    return app


def test_require_api_key_rejects_missing_header():
    client = TestClient(_make_test_app("expected-key"))
    assert client.get("/protected").status_code == 422


def test_require_api_key_rejects_wrong_key():
    client = TestClient(_make_test_app("expected-key"))
    response = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_require_api_key_accepts_correct_key():
    client = TestClient(_make_test_app("expected-key"))
    response = client.get("/protected", headers={"X-API-Key": "expected-key"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
