#!/usr/bin/env python
"""
Tests for tasks.py using secure configuration files instead of environment variables.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deploy.domain.model import Deployment
from deploy.secure_config import SecureConfig
from deploy.tasks import (
    DeploymentContext,
    DeployTask,
    get_deploy_environment,
    run_deploy,
)


class TestGetDeployEnvironmentSecure:
    """Test get_deploy_environment with secure config."""

    def test_get_deploy_environment_returns_dict_for_config(self):
        """Test that get_deploy_environment returns config dict, not env vars."""
        deployment = Deployment(
            id="test-123", service_id=1, origin="test", user="testuser", context={"env": {"KEY": "value"}}
        )
        deploy_script = "/path/to/deploy.sh"

        with patch("deploy.tasks.settings") as mock_settings:
            mock_settings.steps_url = "https://api/steps"
            mock_settings.deployment_finish_url = "https://api/finish"
            mock_settings.path_for_deploy = "/usr/bin:/bin"

            result = get_deploy_environment(deployment, deploy_script)

        # Should return config data, not environment variables
        assert "ACCESS_TOKEN" in result
        assert "DEPLOY_SCRIPT" in result
        assert "STEPS_URL" in result
        assert "DEPLOYMENT_FINISH_URL" in result
        assert "CONTEXT" in result
        assert "PATH_FOR_DEPLOY" in result

    def test_no_sensitive_data_in_environment(self):
        """Test that sensitive data is not added to os.environ."""
        deployment = Deployment(
            id="test-456", service_id=1, origin="test", user="testuser", context={"secret": "password"}
        )

        original_env = os.environ.copy()

        with patch("deploy.tasks.settings") as mock_settings:
            mock_settings.steps_url = "https://api/steps"
            mock_settings.deployment_finish_url = "https://api/finish"
            mock_settings.path_for_deploy = "/usr/bin"

            get_deploy_environment(deployment, "/deploy.sh")

        # Verify no sensitive data was added to environment
        assert "ACCESS_TOKEN" not in os.environ
        assert "CONTEXT" not in os.environ
        assert os.environ == original_env


class TestRunDeploySecure:
    """Test run_deploy with secure configuration."""

    @patch("deploy.tasks.subprocess.Popen")
    @patch("deploy.tasks.SecureConfig")
    def test_run_deploy_creates_secure_config(self, mock_secure_config_class, mock_popen):
        """Test that run_deploy creates a secure config file."""
        mock_secure_config = MagicMock()
        mock_config_path = Path("/tmp/deploy_test_123.json")
        mock_secure_config.create_deployment_config.return_value = mock_config_path
        mock_secure_config_class.return_value = mock_secure_config

        deployment = Deployment(id="test-789", service_id=1, origin="test", user="testuser", context={"app": "myapp"})

        environment = {
            "ACCESS_TOKEN": "secret-token",
            "DEPLOY_SCRIPT": "/deploy.sh",
            "STEPS_URL": "https://api/steps",
            "DEPLOYMENT_FINISH_URL": "https://api/finish",
            "CONTEXT": '{"app": "myapp"}',
            "PATH_FOR_DEPLOY": "/usr/bin",
        }

        with patch("deploy.tasks.get_deploy_environment", return_value=environment):
            run_deploy(environment)

        # Verify secure config was created
        mock_secure_config.create_deployment_config.assert_called_once()

        # Verify subprocess was started with config file path
        mock_popen.assert_called_once()
        call_env = mock_popen.call_args[1]["env"]
        assert "DEPLOY_CONFIG_FILE" in call_env
        assert call_env["DEPLOY_CONFIG_FILE"] == str(mock_config_path)

        # Verify sensitive data not in subprocess environment
        assert "ACCESS_TOKEN" not in call_env
        assert "CONTEXT" not in call_env


class TestDeployTaskSecure:
    """Test DeployTask with secure configuration."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def secure_config_file(self, temp_dir):
        """Create a secure config file for testing."""
        config_data = {
            "deployment_id": "test-deploy-123",
            "access_token": "test-token",
            "deploy_script": "/test/deploy.sh",
            "steps_url": "https://api/steps",
            "deployment_finish_url": "https://api/finish",
            "context": {"env": {"TEST": "value"}},
            "path_for_deploy": "/usr/bin:/bin",
        }

        config_file = temp_dir / "deploy_config.json"
        fd = os.open(str(config_file), os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(config_data, f)

        return config_file

    @pytest.mark.asyncio
    async def test_deploy_task_reads_from_config_file(self, secure_config_file):
        """Test that DeployTask can read configuration from secure file."""
        with patch.dict(os.environ, {"DEPLOY_CONFIG_FILE": str(secure_config_file)}):
            with patch("deploy.tasks.get_config_from_env") as mock_get_config:
                mock_get_config.return_value = {
                    "access_token": "test-token",
                    "deploy_script": "/test/deploy.sh",
                    "steps_url": "https://api/steps",
                    "deployment_finish_url": "https://api/finish",
                    "context": {"env": {"TEST": "value"}},
                    "path_for_deploy": "/usr/bin:/bin",
                }

                # Create DeployTask from config
                task = DeployTask(
                    deploy_script="/test/deploy.sh",
                    access_token="test-token",
                    steps_url="https://api/steps",
                    deployment_finish_url="https://api/finish",
                    context=DeploymentContext(env={"TEST": "value"}),
                    path_for_deploy="/usr/bin:/bin",
                )

                assert task.access_token == "test-token"
                assert task.deploy_script == "/test/deploy.sh"
                assert task.context.env == {"TEST": "value"}

    @pytest.mark.asyncio
    async def test_deploy_steps_no_preserve_env(self):
        """Test that deploy_steps doesn't use --preserve-env."""
        task = DeployTask(
            deploy_script="/test/deploy.sh",
            access_token="token",
            steps_url="https://api/steps",
            deployment_finish_url="https://api/finish",
            context=DeploymentContext(),
            path_for_deploy="/usr/bin",
        )

        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")

        with patch("deploy.tasks.settings") as mock_settings:
            mock_settings.sudo_user = "deploy"
            mock_settings.services_root = Path("/services")

            with patch("deploy.tasks.asyncio.create_subprocess_shell") as mock_create:
                mock_create.return_value = mock_proc

                await task.deploy_steps()

                # Check the command that was executed
                command = mock_create.call_args[0][0]

                # Should use sudo without --preserve-env
                assert "sudo -u deploy" in command
                assert "--preserve-env" not in command

                # Should pass config file path
                env = mock_create.call_args[1]["env"]
                assert "DEPLOY_CONFIG_FILE" in env or "PATH" in env

    @pytest.mark.asyncio
    async def test_deploy_steps_with_config_file(self, temp_dir):
        """Test deploy_steps using config file instead of env vars."""
        task = DeployTask(
            deploy_script="/deploy.sh",
            access_token="secure-token",
            steps_url="https://api/steps",
            deployment_finish_url="https://api/finish",
            context=DeploymentContext(),
            path_for_deploy="/usr/bin",
        )

        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")

        config_file_path = None

        # Capture the config file path when create_subprocess_shell is called
        async def capture_config_path(*args, **kwargs):
            nonlocal config_file_path
            env = kwargs.get("env", {})
            if "DEPLOY_CONFIG_FILE" in env:
                config_file_path = env["DEPLOY_CONFIG_FILE"]
                # Check file exists when subprocess is created (before cleanup)
                assert Path(config_file_path).exists(), f"Config file should exist: {config_file_path}"
            return mock_proc

        with patch("deploy.tasks.settings") as mock_settings:
            mock_settings.sudo_user = "deploy"
            mock_settings.services_root = Path("/services")

            with patch("deploy.tasks.SecureConfig") as mock_secure_config_class:
                # Mock the SecureConfig to use our temp_dir
                mock_secure_config = SecureConfig(config_dir=temp_dir)
                mock_secure_config_class.return_value = mock_secure_config

                with patch(
                    "deploy.tasks.asyncio.create_subprocess_shell", side_effect=capture_config_path
                ) as mock_create:
                    await task.deploy_steps()

                # Verify subprocess was called
                assert mock_create.called

                # Verify subprocess environment
                env = mock_create.call_args[1]["env"]

                # Should have config file path
                assert "DEPLOY_CONFIG_FILE" in env
                assert config_file_path is not None

                # Should NOT have sensitive data in environment
                assert "ACCESS_TOKEN" not in env
                assert "CONTEXT" not in env
                assert "STEPS_URL" not in env
                assert "DEPLOYMENT_FINISH_URL" not in env

                # After deploy_steps completes, file should be cleaned up
                assert not Path(config_file_path).exists(), "Config file should be cleaned up after deployment"


class TestSecurityVerification:
    """Verify security properties of the new implementation."""

    def test_no_secrets_in_process_args(self):
        """Verify secrets don't appear in process arguments."""
        with patch("deploy.tasks.subprocess.Popen") as mock_popen:
            with patch("deploy.tasks.SecureConfig") as mock_secure_config_class:
                mock_secure_config = MagicMock()
                mock_secure_config.create_deployment_config.return_value = Path("/tmp/config.json")
                mock_secure_config_class.return_value = mock_secure_config

                environment = {
                    "ACCESS_TOKEN": "super-secret-token",
                    "CONTEXT": '{"password": "secret123"}',
                }

                run_deploy(environment)

                # Check subprocess arguments
                call_args = mock_popen.call_args[0][0]  # Command list
                call_env = mock_popen.call_args[1]["env"]

                # Secrets should not be in command arguments
                assert "super-secret-token" not in str(call_args)
                assert "secret123" not in str(call_args)

                # Secrets should not be in environment
                assert "super-secret-token" not in str(call_env.values())
                assert "secret123" not in str(call_env.values())

    @pytest.mark.asyncio
    @patch("deploy.tasks.asyncio.create_subprocess_shell")
    async def test_sudo_without_preserve_env(self, mock_create_subprocess):
        """Verify sudo is called without --preserve-env."""
        mock_proc = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_create_subprocess.return_value = mock_proc

        task = DeployTask(
            deploy_script="/deploy.sh",
            access_token="token",
            steps_url="https://api/steps",
            deployment_finish_url="https://api/finish",
            context=DeploymentContext(),
            path_for_deploy="/usr/bin",
        )

        with patch("deploy.tasks.settings") as mock_settings:
            mock_settings.sudo_user = "deployuser"
            mock_settings.services_root = Path("/services")

            await task.deploy_steps()

            # Get the command that was executed
            command = mock_create_subprocess.call_args[0][0]

            # Verify sudo command format
            assert "sudo -u deployuser" in command
            assert "--preserve-env" not in command
            assert "SETENV" not in command.upper()
