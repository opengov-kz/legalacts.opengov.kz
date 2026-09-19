from app.config import Settings


def test_settings_reads_database_url_and_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("API_KEY", "secret123")

    settings = Settings()

    assert settings.database_url == "postgresql://u:p@h/db"
    assert settings.api_key == "secret123"
