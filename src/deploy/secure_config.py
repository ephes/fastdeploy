#!/usr/bin/env python
"""
Secure configuration file handling for FastDeploy.
Replaces environment variable passing with temporary secure files.
"""

import atexit
import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Track temp files for cleanup
_temp_files: set[Path] = set()


def cleanup_temp_files():
    """Clean up any remaining temporary configuration files."""
    for temp_file in _temp_files.copy():
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up {temp_file}: {e}")
        finally:
            _temp_files.discard(temp_file)


# Register cleanup on exit
atexit.register(cleanup_temp_files)


class SecureConfig:
    """Handle secure configuration for deployments."""

    def __init__(self, config_dir: Path | None = None):
        """
        Initialize secure config handler.

        Args:
            config_dir: Directory for config files. Defaults to /var/tmp for systemd PrivateTmp compatibility.
        """
        # Use /var/tmp instead of /tmp to avoid systemd PrivateTmp isolation
        self.config_dir = config_dir or Path("/var/tmp")
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def create_deployment_config(
        self,
        deployment_id: str,
        access_token: str,
        deploy_script: str,
        steps_url: str,
        deployment_finish_url: str,
        context: dict[str, Any],
        path_for_deploy: str,
        ssh_auth_sock: str | None = None,
    ) -> Path:
        """
        Create a secure configuration file for deployment.

        Args:
            deployment_id: Unique deployment identifier
            access_token: JWT token for API authentication
            deploy_script: Path to deployment script
            steps_url: URL for posting step updates
            deployment_finish_url: URL for marking deployment complete
            context: Deployment context data
            path_for_deploy: PATH environment for deployment
            ssh_auth_sock: Optional SSH agent socket path

        Returns:
            Path to the created configuration file
        """
        config_data = {
            "deployment_id": deployment_id,
            "access_token": access_token,
            "deploy_script": deploy_script,
            "steps_url": steps_url,
            "deployment_finish_url": deployment_finish_url,
            "context": context,
            "path_for_deploy": path_for_deploy,
        }

        if ssh_auth_sock:
            config_data["ssh_auth_sock"] = ssh_auth_sock

        # Create temp file with secure permissions
        fd, temp_path = tempfile.mkstemp(prefix=f"deploy_{deployment_id}_", suffix=".json", dir=str(self.config_dir))

        try:
            # Set permissions to be secure - owner and group can read
            # The subprocess runs as deploy user who is in the fastdeploy group
            os.fchmod(fd, 0o640)  # rw-r----- (owner read/write, group read)

            # Write configuration
            with os.fdopen(fd, "w") as f:
                json.dump(config_data, f, indent=2)

            temp_file = Path(temp_path)
            _temp_files.add(temp_file)

            logger.info(f"Created secure config: {temp_file} for deployment {deployment_id}")
            return temp_file

        except Exception as e:
            # Clean up on error
            with contextlib.suppress(Exception):
                os.close(fd)
            if Path(temp_path).exists():
                Path(temp_path).unlink()
            raise RuntimeError(f"Failed to create secure config: {e}") from e

    def read_deployment_config(self, config_path: Path) -> dict[str, Any]:
        """
        Read deployment configuration from secure file.

        Args:
            config_path: Path to configuration file

        Returns:
            Configuration dictionary

        Raises:
            PermissionError: If file permissions are not secure
            FileNotFoundError: If config file doesn't exist
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Verify secure permissions
        stat_info = config_path.stat()
        mode = stat_info.st_mode & 0o777

        if mode not in (0o600, 0o640):
            raise PermissionError(
                f"Config file {config_path} has insecure permissions: {oct(mode)} (expected 0o600 or 0o640)"
            )

        # Verify ownership (should be current user or readable via group)
        # Allow files owned by another user if we can read them (via group permissions)
        if stat_info.st_uid != os.getuid() and not os.access(config_path, os.R_OK):
            raise PermissionError(f"Config file {config_path} not readable by current user")

        with open(config_path) as f:
            return json.load(f)

    def cleanup_config(self, config_path: Path) -> bool:
        """
        Securely remove a configuration file.

        Args:
            config_path: Path to configuration file

        Returns:
            True if successfully removed, False otherwise
        """
        try:
            if config_path.exists():
                # Overwrite with random data before deletion for extra security
                original_size = config_path.stat().st_size
                with open(config_path, "r+b") as f:
                    f.write(os.urandom(original_size))
                    f.flush()
                    os.fsync(f.fileno())

                config_path.unlink()
                _temp_files.discard(config_path)
                logger.debug(f"Securely removed config: {config_path}")
                return True
            else:
                # No file to cleanup is considered success
                _temp_files.discard(config_path)
                return True
        except Exception as e:
            logger.error(f"Failed to cleanup config {config_path}: {e}")
            return False


def get_config_from_env() -> dict[str, Any] | None:
    """
    Read configuration from DEPLOY_CONFIG_FILE environment variable.
    This is the ONLY environment variable we'll use for deployments.

    Returns:
        Configuration dictionary or None if not available
    """
    config_file = os.environ.get("DEPLOY_CONFIG_FILE")
    if not config_file:
        return None

    config_path = Path(config_file)
    handler = SecureConfig()

    try:
        return handler.read_deployment_config(config_path)
    except Exception as e:
        logger.error(f"Failed to read config from {config_file}: {e}")
        return None
