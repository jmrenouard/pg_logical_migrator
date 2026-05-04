#!/bin/bash
set -e
set -u
set -o pipefail

trap 'rm -f nfpm.yaml' EXIT

echo "Starting E2E Packaging Validation..."

# Extract version
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pg_migrator.py)
echo "Extracted Version: ${VERSION}"

# Use Rocky Linux 8 for building (GLIBC 2.28 baseline for maximum compatibility)
# Rocky 8 repo is active and stable.

validate_artifact() {
    local container="$1"
    local binary_path="$2"
    local expected_version="$3"

    echo "--- Validating ${binary_path} in ${container} ---"
    
    # Check version
    local version_out
    version_out=$(docker run --rm -v "$(pwd):/workspace" -w /workspace "${container}" "./${binary_path}" --version 2>&1)
    echo "Version output: ${version_out}"
    if [[ ! "${version_out}" =~ "${expected_version}" ]]; then
        echo "ERROR: Version mismatch! Expected ${expected_version}"
        exit 1
    fi

    # Check shared libs (ldd) - skip if ldd not found (UBI)
    echo "Checking shared libraries..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace "${container}" bash -c "command -v ldd >/dev/null && ldd \"./${binary_path}\" || echo 'ldd not available, skipping check'" | grep "not found" && { echo "ERROR: Missing shared libraries!"; exit 1; } || echo "All shared libs found (or ldd skipped)."

    # Check resource access (generate-config)
    echo "Checking resource access (generate-config)..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace "${container}" "./${binary_path}" generate-config --output /tmp/test_config.ini
    echo "Resource check successful."
}

for PYTHON_VERSION in "3.11" "3.12"; do
    echo "Testing with Python ${PYTHON_VERSION}..."
    BINARY_NAME="pg_migrator-linux-python${PYTHON_VERSION}-v${VERSION}"

    echo "1. Building Linux Binary inside rockylinux:8..."
    # Ensure dist is clean and has right permissions before starting
    rm -rf dist build
    mkdir -p dist

    docker run --rm -v "$(pwd):/workspace" -w /workspace rockylinux:8 bash -c "
      dnf install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-pip gcc postgresql-devel &&
      python${PYTHON_VERSION} -m pip install --upgrade pip &&
      python${PYTHON_VERSION} -m pip install pyinstaller build &&
      python${PYTHON_VERSION} -m pip install -r requirements.txt &&
      python${PYTHON_VERSION} -m PyInstaller --onefile --name pg_migrator --add-data 'src:src' --add-data 'config_migrator.sample.ini:.' --collect-all textual --collect-all rich --collect-all psycopg --collect-all docker --collect-all jinja2 --collect-all yaml pg_migrator.py &&
      python${PYTHON_VERSION} -m build &&
      chown -R $(id -u):$(id -g) dist/ build/
    "
    # Ensure binary is executable on host
    chmod +x dist/pg_migrator
    mv dist/pg_migrator "dist/${BINARY_NAME}"

    echo "2. Validating Linux Binary across distributions..."
    validate_artifact "ubuntu:24.04" "dist/${BINARY_NAME}" "${VERSION}"
    validate_artifact "fedora:39" "dist/${BINARY_NAME}" "${VERSION}"
    validate_artifact "redhat/ubi8" "dist/${BINARY_NAME}" "${VERSION}"
    
    echo "Linux binary execution successful."

    echo "3. Packaging DEB and RPM using nfpm..."
    cat <<INTERNAL_EOF > nfpm.yaml
name: "pg-logical-migrator-python${PYTHON_VERSION}"
arch: "amd64"
platform: "linux"
version: "${VERSION}"
section: "utils"
priority: "extra"
maintainer: "Jean-Marie Renouard <jmrenouard@gmail.com>"
description: "PostgreSQL Logical Migration CLI Tool"
vendor: "jmrenouard"
homepage: "https://github.com/jmrenouard/pg_logical_migrator"
license: "MIT"
contents:
  - src: "dist/${BINARY_NAME}"
    dst: "/usr/bin/pg_migrator"
INTERNAL_EOF

    docker run --rm -v "$(pwd):/workspace" -w /workspace goreleaser/nfpm:latest pkg --packager deb --target dist/
    docker run --rm -v "$(pwd):/workspace" -w /workspace goreleaser/nfpm:latest pkg --packager rpm --target dist/
    
    # Fix ownership of generated packages using docker
    docker run --rm -v "$(pwd):/workspace" -w /workspace rockylinux:8 chown -R $(id -u):$(id -g) dist/

    DEB_FILE="$(ls dist/*.deb | sort -V | tail -n 1)"
    RPM_FILE="$(ls dist/*.rpm | sort -V | tail -n 1)"
    echo "Created ${DEB_FILE} and ${RPM_FILE}"

    echo "4.1 Testing DEB installation in debian:11..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace debian:11 bash -c "apt-get update && apt-get install -y \"./${DEB_FILE}\" && pg_migrator --help"
    
    echo "4.2 Testing DEB installation in ubuntu:22.04..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace ubuntu:22.04 bash -c "apt-get update && apt-get install -y \"./${DEB_FILE}\" && pg_migrator --help"
    
    echo "DEB installation and execution successful."

    echo "5. Testing RPM installation in almalinux:9..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace almalinux:9 bash -c "dnf install -y \"./${RPM_FILE}\" && pg_migrator --help"
    
    echo "6. Testing RPM installation in almalinux:8..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace almalinux:8 bash -c "dnf install -y \"./${RPM_FILE}\" && pg_migrator --help"

    echo "7. Testing RPM installation in redhat/ubi9..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace redhat/ubi9 bash -c "dnf install -y \"./${RPM_FILE}\" && pg_migrator --help"

    echo "8. Testing RPM installation in redhat/ubi8..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace redhat/ubi8 bash -c "dnf install -y \"./${RPM_FILE}\" && pg_migrator --help"

    echo "RPM installation and execution successful."
done

echo "All packaging and end-to-end tests completed successfully!"
