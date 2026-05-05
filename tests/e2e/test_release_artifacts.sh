#!/usr/bin/env bash
#
# Script to download and test GitHub release artifacts inside Docker containers.
# It specifically targets the Linux AMD64 Python 3.9 binary and the RPM package.
#
set -euo pipefail

# Determine version
if [ $# -ge 1 ]; then
    VERSION="$1"
else
    # Extract version from pg_migrator.py
    VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' src/migrator.py 2>/dev/null || grep -oP '(?<=__version__ = ")[^"]+' pg_migrator.py)
fi

# Ensure version has 'v' prefix for GH release
TAG_NAME="v${VERSION#v}"
RAW_VERSION="${VERSION#v}"

echo "=========================================================="
echo " Testing Release Artifacts for version: $TAG_NAME"
echo "=========================================================="

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "Error: 'gh' CLI is not installed. Please install it to download artifacts."
    exit 1
fi

WORK_DIR=$(mktemp -d)
echo "Working directory: $WORK_DIR"

# Artifact names
BIN_FILE="pg_migrator-linux-amd64-python3.9-v${RAW_VERSION}"
RPM_FILE="pg-logical-migrator-python3.9-${RAW_VERSION}-1.x86_64.rpm"

echo "Downloading artifacts from GitHub Release $TAG_NAME..."
# Download Binary
if ! gh release download "$TAG_NAME" -p "$BIN_FILE" --dir "$WORK_DIR" --clobber; then
    echo "Error: Failed to download $BIN_FILE"
    exit 1
fi

# Download RPM
if ! gh release download "$TAG_NAME" -p "$RPM_FILE" --dir "$WORK_DIR" --clobber; then
    echo "Error: Failed to download $RPM_FILE"
    exit 1
fi

cd "$WORK_DIR"

echo "Artifacts downloaded successfully."

# 1. Test Standalone Binary in Ubuntu 22.04
echo "----------------------------------------------------------"
echo " Test 1: Testing Standalone Binary in ubuntu:22.04"
echo "----------------------------------------------------------"
chmod +x "$BIN_FILE"
docker run --rm -v "$(pwd):/artifacts" ubuntu:22.04 bash -c "
    echo 'Running $BIN_FILE...'
    /artifacts/$BIN_FILE --help > /dev/null
    if [ \$? -eq 0 ]; then
        echo 'SUCCESS: Binary executed successfully.'
    else
        echo 'FAILED: Binary execution failed.'
        exit 1
    fi
"

# 2. Test RPM Package in Rocky Linux 8
echo "----------------------------------------------------------"
echo " Test 2: Testing RPM Package in rockylinux:8"
echo "----------------------------------------------------------"
docker run --rm -v "$(pwd):/artifacts" rockylinux:8 bash -c "
    echo 'Installing $RPM_FILE...'
    dnf install -y /artifacts/$RPM_FILE > /dev/null
    echo 'Running pg_migrator...'
    pg_migrator --help > /dev/null
    if [ \$? -eq 0 ]; then
        echo 'SUCCESS: RPM installed and executed successfully.'
    else
        echo 'FAILED: RPM execution failed.'
        exit 1
    fi
"

echo "=========================================================="
echo " All release artifact tests passed successfully!"
echo "=========================================================="

cd - > /dev/null
rm -rf "$WORK_DIR"
