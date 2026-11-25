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


@pytest.mark.parametrize(
    "api_url",
    [
        "https://user:hunter2@deploy.example.test",
        "https://deploy.example.test/?token=hunter2",
        # A "/" in the password ends the netloc early, so "hunter2" is parsed as the port.
        "https://admin:hunter2/x@deploy.example.test",
        "https://deploy.example.test:hunter2",
        "https://deploy.example.test:99999",
        # Fullwidth delimiters pass the ASCII pre-check and fail urlsplit's NFKC netloc check.
        "https://admin:hunter2\uff03@deploy.example.test",
        "https://admin:hunter2\uff1f@deploy.example.test",
    ],
)
def test_rejected_api_base_is_not_echoed(monkeypatch, api_url):
    monkeypatch.setenv("API_URL", api_url)
    with pytest.raises(ValidationError) as error:
        Settings(secret_key="test-secret", path_for_deploy="/tmp/deploy")
    assert "hunter2" not in str(error.value)
