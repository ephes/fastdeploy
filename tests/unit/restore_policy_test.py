"""Parsing and validation of the restore policy and issuer settings."""

import pytest
from pydantic import ValidationError

from deploy.config import RestorePolicy, Settings


def test_restore_policies_parse_from_environment(monkeypatch):
    monkeypatch.setenv(
        "RESTORE_POLICIES", '{"echoport-backup":{"bucket":"backups","prefixes":["archive/","work_app/"]}}'
    )
    monkeypatch.setenv("SERVICE_TOKEN_ADMIN_USERS", '["operator"]')
    parsed = Settings()
    assert parsed.restore_policies["echoport-backup"].prefixes == ["archive/", "work_app/"]
    assert parsed.service_token_admin_users == ["operator"]


@pytest.mark.parametrize(
    "policy",
    [
        {"bucket": "backups", "prefixes": []},
        {"bucket": "backups", "prefixes": ["archive"]},
        {"bucket": "backups", "prefixes": ["/archive/"]},
        {"bucket": "backups", "prefixes": ["../archive/"]},
        {"bucket": "Backups", "prefixes": ["archive/"]},
        {"bucket": "backups", "prefix": "archive/"},
    ],
)
def test_invalid_restore_policy_is_rejected(policy):
    with pytest.raises(ValidationError):
        RestorePolicy(**policy)
