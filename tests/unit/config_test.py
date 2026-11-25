import pytest
from pydantic import ValidationError

from deploy.config import Settings


@pytest.mark.parametrize(
    "api_url, base",
    [
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://localhost:8000/", "http://localhost:8000"),
        ("https://deploy.example.test/team/deploy", "https://deploy.example.test/team/deploy"),
        ("https://deploy.example.test/team/deploy///", "https://deploy.example.test/team/deploy"),
    ],
)
def test_callbacks_use_normalized_api_base(monkeypatch, api_url, base):
    monkeypatch.setenv("API_URL", api_url)
    settings = Settings(secret_key="test-secret", path_for_deploy="/tmp/deploy")

    assert settings.steps_url == f"{base}/steps/"
    assert settings.deployment_finish_url == f"{base}/deployments/finish/"
    assert settings.sync_services_url == f"{base}/services/sync"


@pytest.mark.parametrize(
    "api_url",
    [
        "/deploy",
        "https:///deploy",
        "ftp://deploy.example.test",
        "https://user@deploy.example.test",
        "https://deploy.example.test/prefix?key=value",
        "https://deploy.example.test/prefix#tag",
        "https://deploy.example.test:65536",
        "https://deploy .example.test",
    ],
)
def test_invalid_api_base_is_rejected_at_admission(monkeypatch, api_url):
    monkeypatch.setenv("API_URL", api_url)
    with pytest.raises(ValidationError, match="api_url"):
        Settings(secret_key="test-secret", path_for_deploy="/tmp/deploy")
