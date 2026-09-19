from fastapi.testclient import TestClient


def test_health_endpoint_works_without_api_key(database_url):
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(database_url=database_url, api_key="unused"))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
