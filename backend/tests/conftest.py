from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "health_agent_test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_path}",
        model_api_key="",
        cors_origins=["*"],
    )
    app = create_app(settings)

    with TestClient(app) as test_client:
        yield test_client
