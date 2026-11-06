import pytest
from pydantic import ValidationError

from deploy.config import Settings


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), 0, -1, 86401])
def test_websocket_timeout_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            secret_key="fixture-key",
            path_for_deploy="/tmp/fixture",
            websocket_auth_timeout_seconds=value,
        )


@pytest.mark.parametrize(
    ("field", "maximum", "minimum"),
    [
        ("access_token_expire_minutes", 525600, 1),
        ("deployment_access_token_expire_minutes", 525600, 1),
        ("default_expire_minutes", 525600, 1),
        ("deployment_orphan_reconcile_delay_seconds", 31536000, 0),
        ("service_token_max_expire_days", 3650, 1),
        ("service_token_retention_days", 3650, 1),
    ],
)
def test_lifecycle_duration_bounds(field, maximum, minimum):
    base = {"_env_file": None, "secret_key": "fixture-key", "path_for_deploy": "/tmp/fixture"}
    for value in (float("inf"), float("nan"), -1, minimum - 1, maximum + 1, 10**30):
        with pytest.raises(ValidationError):
            Settings(**base, **{field: value})
    for value in (minimum, maximum):
        assert getattr(Settings(**base, **{field: value}), field) == value


def test_finite_websocket_timeout_boundaries():
    for value in (0.001, 86400):
        assert (
            Settings(
                _env_file=None,
                secret_key="fixture-key",
                path_for_deploy="/tmp/fixture",
                websocket_auth_timeout_seconds=value,
            ).websocket_auth_timeout_seconds
            == value
        )
