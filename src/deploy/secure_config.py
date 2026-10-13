#!/usr/bin/env python
"""
Secure configuration file handling for FastDeploy.
Replaces environment variable passing with temporary secure files.
"""

import atexit
import json
import logging
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Retain descriptors so an unlinked inode cannot be reused as an owned config.
_temp_files: dict[Path, int] = {}
_cleanup_lock = threading.RLock()


def _forget_config(path: Path) -> None:
    with _cleanup_lock:
        fd = _temp_files.pop(path, None)
        if fd is not None:
            os.close(fd)


def _open_config(path: Path, flags: int) -> int:
    # NONBLOCK avoids hanging on substituted FIFOs before fstat rejects them.
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError(f"Config file {path} is not a regular file")
        mode = stat.S_IMODE(info.st_mode)
        if mode not in (0o600, 0o640):
            raise PermissionError(
                f"Config file {path} has insecure permissions: {oct(mode)} (expected 0o600 or 0o640)"
            )
        # Successful open is the kernel's owner/group/ACL access check.
        return fd
    except BaseException:
        os.close(fd)
        raise


def cleanup_temp_files():
    """Clean up only files created by this process, including at exit."""
    for temp_file in _temp_files.copy():
        with _cleanup_lock:
            try:
                SecureConfig.cleanup_config(temp_file)
            except Exception as e:
                logger.warning(f"Failed to clean up {temp_file}: {e}")
            finally:
                _forget_config(temp_file)


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

        temp_file = Path(temp_path)
        _temp_files[temp_file] = fd
        try:
            # Set permissions to be secure - owner and group can read
            # The subprocess runs as deploy user who is in the fastdeploy group
            os.fchmod(fd, 0o640)  # rw-r----- (owner read/write, group read)

            # Write configuration
            with os.fdopen(os.dup(fd), "w") as f:
                json.dump(config_data, f, indent=2)

            logger.info(f"Created secure config: {temp_file} for deployment {deployment_id}")
            return temp_file

        except Exception as e:
            # Clean up on error
            self.cleanup_config(Path(temp_path))
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
        try:
            fd = _open_config(config_path, os.O_RDONLY)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Config file not found: {config_path}") from e
        with os.fdopen(fd) as f:
            return json.load(f)

    @staticmethod
    def cleanup_config(config_path: Path) -> bool:
        """
        Securely remove a configuration file.

        Args:
            config_path: Path to configuration file

        Returns:
            True if successfully removed, False otherwise
        """
        with _cleanup_lock:
            return _cleanup_config(config_path)


def _cleanup_config(config_path: Path) -> bool:
    try:
        try:
            config_path.lstat()
        except FileNotFoundError:
            _forget_config(config_path)
            return True

        owned_fd = _temp_files.get(config_path)
        if owned_fd is None:
            raise PermissionError(f"Config file {config_path} was not created by this process")

        fd = _open_config(config_path, os.O_RDWR)
        with os.fdopen(fd, "r+b") as f:
            info = os.fstat(f.fileno())
            owned = os.fstat(owned_fd)
            if (info.st_dev, info.st_ino) != (owned.st_dev, owned.st_ino) or info.st_nlink != 1:
                raise PermissionError(f"Config file {config_path} was replaced or hard-linked")
            # Overwrite the validated descriptor, never reopen the pathname.
            f.write(os.urandom(info.st_size))
            f.flush()
            os.fsync(f.fileno())
            current = config_path.lstat()
            if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                raise PermissionError(f"Config file {config_path} was replaced during cleanup")
            config_path.unlink()

        _forget_config(config_path)
        logger.debug(f"Securely removed config: {config_path}")
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
