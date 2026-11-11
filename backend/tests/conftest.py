import os
from pathlib import Path
os.environ["DATABASE_URL"] = "sqlite:///./test-classflow.db"
os.environ["ADMIN_EMAIL"] = "admin@classflow.example.com"
os.environ["SECRET_KEY"] = "test-only-key"
from fastapi.testclient import TestClient
import pytest
from app.main import app, Base, engine, UPLOADS
@pytest.fixture
def client():
    app.state.auth_attempts.clear()
    existing_uploads={p.name for p in UPLOADS.iterdir() if p.is_file()}
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
    engine.dispose()
    for path in UPLOADS.iterdir():
        if path.is_file() and path.name not in existing_uploads:
            path.unlink()
    Path("test-classflow.db").unlink(missing_ok=True)

