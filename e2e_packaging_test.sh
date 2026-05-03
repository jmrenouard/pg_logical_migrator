#!/bin/bash
set -e

echo "Starting E2E Packaging Validation..."

# Extract version
VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' pg_migrator.py)
echo "Extracted Version: $VERSION"

for PYTHON_VERSION in "3.11" "3.12" "3.13"; do
    echo "Testing with Python ${PYTHON_VERSION}..."
    BINARY_NAME="pg_migrator-${PLATFORM}-python${PYTHON_VERSION}-v${VERSION}"

    # Clean dist
    rm -rf dist
    mkdir -p dist

    echo "1. Building Linux Binary inside almalinux:8..."
    # Note: almalinux:8 doesn't natively have python3.12/3.13 in standard repos easily.
    # To support 3.11, 3.12, 3.13 locally, we will use the official python images for building.
    docker run --rm -v $(pwd):/workspace -w /workspace -e PYINSTALLER_OPTS="${PYINSTALLER_OPTS}" python:${PYTHON_VERSION}-slim bash -c "
      apt-get update && apt-get install -y gcc libpq-dev &&
      pip install pyinstaller build &&
      pip install -r requirements.txt &&
      python -m PyInstaller --onefile --name pg_migrator --add-data 'src:src' --add-data 'config_migrator.sample.ini:.' \$PYINSTALLER_OPTS pg_migrator.py &&
      python -m build &&
      chmod 777 dist/* &&
      chown -R $(id -u):$(id -g) dist
    "
    mv dist/pg_migrator "dist/${BINARY_NAME}"

    echo "2. Validating Linux Binary in ubuntu:22.04..."
    chmod +x "dist/${BINARY_NAME}"
    docker run --rm -v $(pwd):/workspace -w /workspace ubuntu:22.04 bash -c "
      ./dist/${BINARY_NAME} --help
    "
    echo "Linux binary execution successful."

    echo "3. Packaging DEB and RPM using nfpm..."
    cat <<EOF > nfpm.yaml
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
EOF

    docker run --rm -v $(pwd):/workspace -w /workspace goreleaser/nfpm:latest pkg --packager deb --target dist/
    docker run --rm -v $(pwd):/workspace -w /workspace goreleaser/nfpm:latest pkg --packager rpm --target dist/

    DEB_FILE=$(ls dist/*.deb)
    RPM_FILE=$(ls dist/*.rpm)
    echo "Created $DEB_FILE and $RPM_FILE"

    echo "4. Testing DEB installation in ubuntu:22.04..."
    docker run --rm -v $(pwd):/workspace -w /workspace ubuntu:22.04 bash -c "
      apt-get update && apt-get install -y ./$DEB_FILE &&
      pg_migrator --help
    "
    echo "DEB installation and execution successful."

    echo "5. Testing RPM installation in almalinux:9..."
    docker run --rm -v $(pwd):/workspace -w /workspace almalinux:9 bash -c "
      dnf install -y ./$RPM_FILE &&
      pg_migrator --help
    "
    echo "RPM installation and execution successful."

    WHEEL_FILE=$(ls dist/*.whl)
    echo "6. Testing Python Wheel installation in python:${PYTHON_VERSION}-slim..."
    docker run --rm -v $(pwd):/workspace -w /workspace python:${PYTHON_VERSION}-slim bash -c "
      pip install ./$WHEEL_FILE &&
      pg_migrator --help
    "
    echo "Wheel installation and execution successful."
done

echo "All packaging and end-to-end tests completed successfully!"
