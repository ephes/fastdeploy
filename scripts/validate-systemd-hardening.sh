#!/usr/bin/env bash
# Validate systemd service hardening configuration
# This script checks systemd service files for security best practices

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Service files to check
SERVICE_FILES=(
    "ansible/deploy.service"
    "ansible/deploy-hardened.service"
    "ansible/templates/deploy.macmini.service.j2"
    "ansible/templates/fastdeploy-hardened.service.j2"
)

echo -e "${BLUE}FastDeploy Systemd Security Validation${NC}"
echo "========================================"
echo ""

# Function to check if a security directive exists in service file
check_directive() {
    local file=$1
    local directive=$2
    local required=$3

    if grep -q "^${directive}=" "$file" 2>/dev/null; then
        value=$(grep "^${directive}=" "$file" | cut -d= -f2-)
        if [ "$required" == "yes" ]; then
            echo -e "${GREEN}✓${NC} ${directive}=${value}"
        else
            echo -e "${YELLOW}○${NC} ${directive}=${value}"
        fi
        return 0
    else
        if [ "$required" == "yes" ]; then
            echo -e "${RED}✗${NC} ${directive} - MISSING (Required)"
            return 1
        else
            echo -e "${YELLOW}○${NC} ${directive} - Not set (Optional)"
            return 0
        fi
    fi
}

# Function to calculate security score
calculate_score() {
    local file=$1
    local score=0
    local max_score=0

    # Required directives (1 point each)
    local required_directives=(
        "User"
        "PrivateTmp"
        "NoNewPrivileges"
        "ProtectKernelTunables"
        "ProtectKernelModules"
        "ProtectControlGroups"
    )

    # Optional but recommended (0.5 points each)
    local optional_directives=(
        "ProtectSystem"
        "ProtectHome"
        "RestrictAddressFamilies"
        "RestrictRealtime"
        "RestrictSUIDSGID"
        "MemoryMax"
        "LimitNOFILE"
        "SystemCallFilter"
        "PrivateDevices"
        "MemoryDenyWriteExecute"
    )

    for directive in "${required_directives[@]}"; do
        max_score=$((max_score + 2))
        if grep -q "^${directive}=" "$file" 2>/dev/null; then
            score=$((score + 2))
        fi
    done

    for directive in "${optional_directives[@]}"; do
        max_score=$((max_score + 1))
        if grep -q "^${directive}=" "$file" 2>/dev/null; then
            score=$((score + 1))
        fi
    done

    echo "$score/$max_score"
}

# Main validation loop
total_files=0
valid_files=0

for service_file in "${SERVICE_FILES[@]}"; do
    if [ ! -f "$service_file" ]; then
        echo -e "${YELLOW}Skipping${NC} $service_file (not found)"
        echo ""
        continue
    fi

    total_files=$((total_files + 1))
    echo -e "${BLUE}Checking:${NC} $service_file"
    echo "----------------------------------------"

    # Check for [Service] section
    if ! grep -q "^\[Service\]" "$service_file"; then
        echo -e "${RED}✗${NC} No [Service] section found"
        echo ""
        continue
    fi

    # Required security directives
    echo -e "${GREEN}Required Security Directives:${NC}"
    errors=0
    check_directive "$service_file" "User" "yes" || errors=$((errors + 1))
    check_directive "$service_file" "PrivateTmp" "yes" || errors=$((errors + 1))
    check_directive "$service_file" "NoNewPrivileges" "yes" || errors=$((errors + 1))
    check_directive "$service_file" "ProtectKernelTunables" "yes" || errors=$((errors + 1))
    check_directive "$service_file" "ProtectKernelModules" "yes" || errors=$((errors + 1))

    echo ""
    echo -e "${YELLOW}Recommended Security Directives:${NC}"
    check_directive "$service_file" "ProtectSystem" "no"
    check_directive "$service_file" "ProtectHome" "no"
    check_directive "$service_file" "RestrictAddressFamilies" "no"
    check_directive "$service_file" "MemoryMax" "no"
    check_directive "$service_file" "SystemCallFilter" "no"

    # Calculate and display score
    score=$(calculate_score "$service_file")
    echo ""
    echo -e "${BLUE}Security Score:${NC} $score"

    # Determine security level
    score_value=${score%/*}
    if [ "$score_value" -ge 15 ]; then
        echo -e "${GREEN}Security Level: HIGH${NC}"
        valid_files=$((valid_files + 1))
    elif [ "$score_value" -ge 10 ]; then
        echo -e "${YELLOW}Security Level: MEDIUM${NC}"
        valid_files=$((valid_files + 1))
    else
        echo -e "${RED}Security Level: LOW${NC}"
    fi

    if [ "$errors" -gt 0 ]; then
        echo -e "${RED}⚠ Missing $errors required directives${NC}"
    fi

    echo ""
done

# Summary
echo "========================================"
echo -e "${BLUE}Summary:${NC}"
echo "Files checked: $total_files"
echo "Files with adequate security: $valid_files"

if [ "$valid_files" -eq "$total_files" ] && [ "$total_files" -gt 0 ]; then
    echo -e "${GREEN}✓ All service files have adequate security hardening${NC}"
    exit 0
elif [ "$valid_files" -gt 0 ]; then
    echo -e "${YELLOW}⚠ Some service files need security improvements${NC}"
    exit 1
else
    echo -e "${RED}✗ No service files have adequate security hardening${NC}"
    exit 1
fi
