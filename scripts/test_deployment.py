#!/usr/bin/env python3
"""
Combined FastDeploy deployment test script.
Gets service token and deploys with real-time step monitoring on terminal.
"""

import argparse
import asyncio
import getpass
import json
import subprocess
import sys
import time
from typing import Optional

import httpx


async def login(api_url: str, username: str, password: str) -> str:
    """Login to FastDeploy and get access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/token",
            data={"username": username, "password": password},
        )
        response.raise_for_status()
        data = response.json()
        return data["access_token"]


async def get_services(api_url: str, token: str) -> list:
    """Get list of all services."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{api_url}/services/",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


async def get_service_token(api_url: str, access_token: str, service_name: str) -> str:
    """Get deployment token for a specific service."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/service-token",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "service": service_name,
                "origin": "cli",
                "expiration_in_days": 1
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["service_token"]


async def deploy_service(api_url: str, token: str, dry_run: bool = False) -> dict:
    """Deploy a service using service token."""
    async with httpx.AsyncClient() as client:
        request_body = {"env": {}}
        
        response = await client.post(
            f"{api_url}/deployments/",
            json=request_body,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


# Removed - steps are included in deployment details when using service token


async def get_deployment_status(api_url: str, token: str, deployment_id: int) -> dict:
    """Get deployment status."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{api_url}/deployments/{deployment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


def print_step_status(steps: list, clear_previous: bool = False):
    """Print step status with icons and formatting."""
    if clear_previous:
        # Move cursor up to overwrite previous output
        print(f"\033[{len(steps) + 2}A", end="")
    
    print("\n🚀 Deployment Progress:")
    print("=" * 50)
    
    for step in steps:
        state = step.get("state", "unknown")
        name = step.get("name", "Unknown step")
        message = step.get("message", "")
        
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "success": "✅",
            "failure": "❌",
            "unknown": "❓"
        }.get(state, "❓")
        
        # Format step display
        step_display = f"  {status_icon} {name}"
        if message and len(message.strip()) > 0:
            # Limit message length for readability
            short_message = message[:60] + "..." if len(message) > 60 else message
            step_display += f" - {short_message}"
        
        print(step_display)
    
    print("=" * 50)


async def monitor_deployment_with_steps(api_url: str, service_token: str, deployment_id: int, service_name: str):
    """Monitor deployment with real-time step updates."""
    print(f"\n🎯 Monitoring deployment {deployment_id} for service: {service_name}")
    print("Using service token for monitoring...")
    
    seen_steps = set()
    
    while True:
        try:
            # Get current deployment status (includes steps when using service token)
            deployment = await get_deployment_status(api_url, service_token, deployment_id)
            steps = deployment.get("steps", [])
            
            # Check for new or updated steps
            current_step_ids = {step.get("id") for step in steps if step.get("id")}
            has_updates = current_step_ids != seen_steps
            
            if has_updates or not seen_steps:
                print_step_status(steps, clear_previous=bool(seen_steps))
                seen_steps = current_step_ids
            
            # Check if deployment is finished
            if deployment.get("finished"):
                print(f"\n🎉 Deployment {deployment_id} finished!")
                
                # Check overall status
                failed_steps = [s for s in steps if s.get("state") == "failure"]
                if failed_steps:
                    print("❌ Deployment FAILED")
                    for step in failed_steps:
                        print(f"  💥 Failed: {step.get('name')}")
                        if step.get('message'):
                            print(f"    Error: {step.get('message')}")
                    return False
                else:
                    print("✅ Deployment SUCCEEDED")
                    return True
            
            # Wait before checking again
            await asyncio.sleep(2)
            
        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP Error {e.response.status_code}: {e.response.text}")
            if e.response.status_code == 401:
                print("❌ Authentication failed during monitoring")
                print("Service token may have expired or be invalid")
                return False
            if e.response.status_code == 403:
                print("❌ Service token doesn't have permission for this deployment")
                return False
            raise


def get_password_from_1password(username: str) -> Optional[str]:
    """Get password from 1Password CLI for fastdeploy entry."""
    try:
        # Try to get password from 1Password CLI
        result = subprocess.run([
            "op", "item", "get", "fastdeploy", 
            "--field", "password", 
            "--format", "json"
        ], capture_output=True, text=True, check=True)
        
        # Parse JSON response from op CLI
        data = json.loads(result.stdout)
        return data.get("value", "")
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️  Could not get password from 1Password: {e}", file=sys.stderr)
        return None


async def main():
    parser = argparse.ArgumentParser(description="Test FastDeploy deployment with interactive monitoring")
    parser.add_argument(
        "--api-url",
        default="https://deploy.home.xn--wersdrfer-47a.de",
        help="FastDeploy API URL",
    )
    parser.add_argument(
        "--username",
        default="jochen",
        help="Username for authentication",
    )
    parser.add_argument(
        "--service",
        default="test_dummy",
        help="Service name to deploy",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Don't monitor deployment progress",
    )
    parser.add_argument(
        "--no-1password",
        action="store_true",
        help="Skip 1Password CLI and prompt for password instead",
    )
    
    args = parser.parse_args()
    
    try:
        # Get password securely
        print(f"FastDeploy Deployment Test")
        print(f"API: {args.api_url}")
        print(f"Service: {args.service}")
        if args.dry_run:
            print("Mode: DRY RUN")
        print("-" * 40)
        
        # Get password from 1Password by default, or prompt if requested
        if args.no_1password:
            password = getpass.getpass(f"Password for {args.username}: ")
        else:
            print("🔑 Getting password from 1Password...")
            password = get_password_from_1password(args.username)
            if not password:
                print("❌ Failed to get password from 1Password, falling back to prompt")
                password = getpass.getpass(f"Password for {args.username}: ")
        
        if not password or not password.strip():
            print("❌ Password is required")
            return 1
        
        print(f"\n🔐 Logging in as {args.username}...")
        user_token = await login(args.api_url, args.username, password)
        print("✅ Login successful")
        
        print(f"\n🎫 Getting service token for {args.service}...")
        service_token = await get_service_token(args.api_url, user_token, args.service)
        print("✅ Service token obtained")
        
        print(f"\n🚀 Starting deployment...")
        deployment = await deploy_service(args.api_url, service_token, args.dry_run)
        deployment_id = deployment["id"]
        print(f"✅ Deployment started: ID {deployment_id}")
        
        if not args.no_monitor:
            success = await monitor_deployment_with_steps(
                args.api_url, service_token, deployment_id, args.service
            )
            return 0 if success else 1
        else:
            print(f"\n📝 Deployment ID: {deployment_id}")
            print("Use --no-monitor=false to watch progress")
            return 0
        
    except httpx.HTTPStatusError as e:
        print(f"❌ API Error: {e.response.status_code} - {e.response.text}")
        return 1
    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))