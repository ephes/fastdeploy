#!/usr/bin/env python
"""
Tests for secure configuration file handling.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deploy.secure_config import SecureConfig, cleanup_temp_files, get_config_from_env


class TestSecureConfig:
    """Test secure configuration handler."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def secure_config(self, temp_dir):
        """Create a SecureConfig instance with temp directory."""
        return SecureConfig(config_dir=temp_dir)

    def test_init_creates_config_dir(self, temp_dir):
        """Test that initialization creates the config directory."""
        config_dir = temp_dir / "configs"
        assert not config_dir.exists()

        SecureConfig(config_dir=config_dir)

        assert config_dir.exists()
        assert config_dir.is_dir()

    def test_create_deployment_config_creates_secure_file(self, secure_config, temp_dir):
        """Test creating a deployment configuration file with secure permissions."""
        deployment_id = "test-deploy-123"
        access_token = "secret-jwt-token"
        deploy_script = "/path/to/deploy.sh"
        steps_url = "https://api.example.com/steps"
        deployment_finish_url = "https://api.example.com/finish"
        context = {"env": {"KEY": "value"}}
        path_for_deploy = "/usr/bin:/bin"

        config_path = secure_config.create_deployment_config(
            deployment_id=deployment_id,
            access_token=access_token,
            deploy_script=deploy_script,
            steps_url=steps_url,
            deployment_finish_url=deployment_finish_url,
            context=context,
            path_for_deploy=path_for_deploy,
        )

        # Verify file exists
        assert config_path.exists()
        assert config_path.parent == temp_dir

        # Verify secure permissions (0640 for group access)
        stat_info = config_path.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o640, f"Expected 0o640 permissions, got {oct(mode)}"

        # Verify ownership
        assert stat_info.st_uid == os.getuid()

        # Verify content
        with open(config_path) as f:
            config_data = json.load(f)

        assert config_data["deployment_id"] == deployment_id
        assert config_data["access_token"] == access_token
        assert config_data["deploy_script"] == deploy_script
        assert config_data["steps_url"] == steps_url
        assert config_data["deployment_finish_url"] == deployment_finish_url
        assert config_data["context"] == context
        assert config_data["path_for_deploy"] == path_for_deploy
        assert "ssh_auth_sock" not in config_data

    def test_create_deployment_config_with_ssh_auth_sock(self, secure_config):
        """Test creating config with SSH auth socket."""
        ssh_auth_sock = "/tmp/ssh-agent.sock"

        config_path = secure_config.create_deployment_config(
            deployment_id="test-123",
            access_token="token",
            deploy_script="/deploy.sh",
            steps_url="https://api/steps",
            deployment_finish_url="https://api/finish",
            context={},
            path_for_deploy="/bin",
            ssh_auth_sock=ssh_auth_sock,
        )

        with open(config_path) as f:
            config_data = json.load(f)

        assert config_data["ssh_auth_sock"] == ssh_auth_sock

    def test_read_deployment_config_success(self, secure_config, temp_dir):
        """Test reading a valid configuration file."""
        # Create a config file manually with correct permissions
        config_data = {"deployment_id": "test-123", "access_token": "secret-token", "context": {"key": "value"}}

        config_file = temp_dir / "test_config.json"

        # Create with secure permissions
        fd = os.open(str(config_file), os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(config_data, f)

        # Read the config
        read_data = secure_config.read_deployment_config(config_file)

        assert read_data == config_data

    def test_read_deployment_config_insecure_permissions(self, secure_config, temp_dir):
        """Test that reading fails with insecure file permissions."""
        config_file = temp_dir / "insecure_config.json"

        # Create with insecure permissions (world-readable)
        with open(config_file, "w") as f:
            json.dump({"key": "value"}, f)

        # Make it world-readable
        config_file.chmod(0o644)

        with pytest.raises(PermissionError) as exc_info:
            secure_config.read_deployment_config(config_file)

        assert "insecure permissions" in str(exc_info.value)
        assert "0o644" in str(exc_info.value)

    def test_read_deployment_config_unreadable_file(self, secure_config, temp_dir):
        """Test that reading fails if file is not readable by current user."""
        config_file = temp_dir / "unreadable.json"

        # Create with correct permissions
        fd = os.open(str(config_file), os.O_CREAT | os.O_WRONLY, 0o640)
        with os.fdopen(fd, "w") as f:
            json.dump({"key": "value"}, f)

        # Mock the stat and os.access to simulate unreadable file
        with patch.object(Path, "stat") as mock_stat, patch("os.access") as mock_access:
            mock_stat_result = MagicMock()
            mock_stat_result.st_mode = 0o100640  # Regular file with 0640
            mock_stat_result.st_uid = os.getuid() + 1  # Different user
            mock_stat.return_value = mock_stat_result
            mock_access.return_value = False  # Not readable

            with pytest.raises(PermissionError) as exc_info:
                secure_config.read_deployment_config(config_file)

            assert "not readable by current user" in str(exc_info.value)

    def test_read_deployment_config_file_not_found(self, secure_config, temp_dir):
        """Test that reading fails if file doesn't exist."""
        config_file = temp_dir / "nonexistent.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            secure_config.read_deployment_config(config_file)

        assert "Config file not found" in str(exc_info.value)

    def test_cleanup_config_success(self, secure_config, temp_dir):
        """Test successful cleanup of configuration file."""
        # Create a config file
        config_file = temp_dir / "to_cleanup.json"
        with open(config_file, "w") as f:
            json.dump({"sensitive": "data"}, f)

        assert config_file.exists()

        # Clean it up
        result = secure_config.cleanup_config(config_file)

        assert result is True
        assert not config_file.exists()

    def test_cleanup_config_overwrite_before_deletion(self, secure_config, temp_dir):
        """Test that cleanup overwrites file content before deletion."""
        # Create a config file with known content
        config_file = temp_dir / "sensitive.json"
        sensitive_data = {"secret": "password123"}

        with open(config_file, "w") as f:
            json.dump(sensitive_data, f)

        original_size = config_file.stat().st_size

        # Mock unlink to inspect file content before deletion
        original_unlink = Path.unlink
        captured_content = None

        def mock_unlink(self):
            nonlocal captured_content
            with open(self, "rb") as f:
                captured_content = f.read()
            original_unlink(self)

        with patch.object(Path, "unlink", mock_unlink):
            result = secure_config.cleanup_config(config_file)

        assert result is True
        assert not config_file.exists()
        # Verify content was overwritten with random data (not the original JSON)
        assert captured_content is not None
        assert len(captured_content) == original_size
        assert b"password123" not in captured_content
        assert b"secret" not in captured_content

    def test_cleanup_config_nonexistent_file(self, secure_config, temp_dir):
        """Test cleanup of non-existent file returns False."""
        config_file = temp_dir / "nonexistent.json"

        result = secure_config.cleanup_config(config_file)

        # Should handle gracefully
        assert result is True  # No file to cleanup is considered success

    def test_cleanup_temp_files_atexit(self, temp_dir):
        """Test that temporary files are tracked and cleaned up."""
        from deploy.secure_config import _temp_files

        # Create some config files
        secure_config = SecureConfig(config_dir=temp_dir)

        config_paths = []
        for i in range(3):
            path = secure_config.create_deployment_config(
                deployment_id=f"test-{i}",
                access_token="token",
                deploy_script="/script.sh",
                steps_url="https://api/steps",
                deployment_finish_url="https://api/finish",
                context={},
                path_for_deploy="/bin",
            )
            config_paths.append(path)

        # Verify files are tracked
        assert len(_temp_files) >= 3
        for path in config_paths:
            assert path in _temp_files
            assert path.exists()

        # Call cleanup
        cleanup_temp_files()

        # Verify files are removed
        for path in config_paths:
            assert not path.exists()

        assert len([p for p in _temp_files if p in config_paths]) == 0


class TestGetConfigFromEnv:
    """Test reading configuration from environment variable."""

    def test_get_config_from_env_success(self, tmp_path):
        """Test successfully reading config from DEPLOY_CONFIG_FILE env var."""
        config_data = {"deployment_id": "env-test-123", "access_token": "env-token", "context": {"env": "test"}}

        # Create secure config file
        config_file = tmp_path / "env_config.json"
        fd = os.open(str(config_file), os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(config_data, f)

        # Set environment variable
        with patch.dict(os.environ, {"DEPLOY_CONFIG_FILE": str(config_file)}):
            result = get_config_from_env()

        assert result == config_data

    def test_get_config_from_env_no_variable(self):
        """Test when DEPLOY_CONFIG_FILE is not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_config_from_env()

        assert result is None

    def test_get_config_from_env_invalid_file(self):
        """Test when DEPLOY_CONFIG_FILE points to invalid file."""
        with patch.dict(os.environ, {"DEPLOY_CONFIG_FILE": "/nonexistent/file.json"}):
            result = get_config_from_env()

        assert result is None

    def test_get_config_from_env_insecure_permissions(self, tmp_path):
        """Test when config file has insecure permissions."""
        config_file = tmp_path / "insecure.json"
        with open(config_file, "w") as f:
            json.dump({"key": "value"}, f)

        # Make it world-readable
        config_file.chmod(0o644)

        with patch.dict(os.environ, {"DEPLOY_CONFIG_FILE": str(config_file)}):
            result = get_config_from_env()

        assert result is None


class TestIntegration:
    """Integration tests for the complete secure config workflow."""

    def test_full_deployment_config_lifecycle(self, tmp_path):
        """Test complete lifecycle: create, read, use, cleanup."""
        # Setup
        secure_config = SecureConfig(config_dir=tmp_path)
        deployment_id = "integration-test-123"

        # Create config
        config_path = secure_config.create_deployment_config(
            deployment_id=deployment_id,
            access_token="integration-token",
            deploy_script="/usr/local/bin/deploy.sh",
            steps_url="https://api.example.com/steps",
            deployment_finish_url="https://api.example.com/finish",
            context={"environment": "staging", "version": "1.2.3"},
            path_for_deploy="/usr/local/bin:/usr/bin:/bin",
            ssh_auth_sock="/tmp/ssh-agent.sock",
        )

        # Verify creation
        assert config_path.exists()
        assert (config_path.stat().st_mode & 0o777) == 0o640

        # Simulate deployment process reading config
        with patch.dict(os.environ, {"DEPLOY_CONFIG_FILE": str(config_path)}):
            config_data = get_config_from_env()

        assert config_data is not None
        assert config_data["deployment_id"] == deployment_id
        assert config_data["access_token"] == "integration-token"
        assert config_data["context"]["environment"] == "staging"
        assert config_data["ssh_auth_sock"] == "/tmp/ssh-agent.sock"

        # Cleanup
        success = secure_config.cleanup_config(config_path)
        assert success is True
        assert not config_path.exists()

    def test_concurrent_deployments_isolation(self, tmp_path):
        """Test that multiple deployments have isolated configurations."""
        secure_config = SecureConfig(config_dir=tmp_path)

        # Create multiple deployment configs
        configs = {}
        for i in range(5):
            deployment_id = f"concurrent-{i}"
            config_path = secure_config.create_deployment_config(
                deployment_id=deployment_id,
                access_token=f"token-{i}",
                deploy_script=f"/script-{i}.sh",
                steps_url="https://api/steps",
                deployment_finish_url="https://api/finish",
                context={"deployment_num": i},
                path_for_deploy="/bin",
            )
            configs[deployment_id] = config_path

        # Verify each config is isolated and secure
        for deployment_id, config_path in configs.items():
            assert config_path.exists()
            assert (config_path.stat().st_mode & 0o777) == 0o640

            # Read and verify content
            data = secure_config.read_deployment_config(config_path)
            assert data["deployment_id"] == deployment_id
            assert data["access_token"] == f"token-{deployment_id.split('-')[1]}"

            # Verify no cross-contamination
            for other_id, other_path in configs.items():
                if other_id != deployment_id:
                    assert config_path != other_path

        # Cleanup all
        for config_path in configs.values():
            secure_config.cleanup_config(config_path)
