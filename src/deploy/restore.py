"""Validate the Echoport runner's restore input before a deployment is recorded."""

import re

from .config import settings


def validate_restore_context(service_name: str, env: dict) -> None:
    # Validate supplied archive keys even when action is omitted or says backup.
    action = str(env.get("ECHOPORT_ACTION", "")).strip().lower()
    if action != "restore" and "ECHOPORT_KEY" not in env:
        return
    policy = settings.restore_policies.get(service_name)
    if policy is None:
        raise ValueError("Restores are not configured for this service")
    # Require an explicit bucket: never depend on an unknown runner default.
    if env.get("ECHOPORT_BUCKET") != policy.bucket:
        raise ValueError("ECHOPORT_BUCKET must match this service's restore bucket")
    key = env.get("ECHOPORT_KEY")
    # Deliberately narrow ASCII object-key allowlist. Reject traversal, URL
    # schemes, absolute paths, backslashes, encodings and empty components.
    if (
        not isinstance(key, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)+", key)
        or ".." in key
        or any(part in {"", "."} for part in key.split("/"))
        or not key.startswith(policy.prefix)
        or len(key) <= len(policy.prefix)
    ):
        raise ValueError("ECHOPORT_KEY must be a relative archive key under this service's restore prefix")
