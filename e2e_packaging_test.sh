#!/bin/bash
set -e

echo "Starting E2E Packaging Validation..."

# Extract version
VERSION=$(grep -oP '(?<=__version__ = ")[^"]+' pg_migrator.py)
echo "Extracted Version: $VERSION"

PYTHON_VERSION="3.11"
PLATFORM="linux-amd64"
BINARY_NAME="pg_migrator-${PLATFORM}-python${PYTHON_VERSION}-v${VERSION}"

# Clean dist
rm -rf dist
mkdir -p dist

echo "1. Building Linux Binary inside almalinux:8..."
docker run --rm -v $(pwd):/workspace -w /workspace almalinux:8 bash -c "
  dnf install -y python3.11 python3.11-pip python3.11-devel gcc &&
  pip3.11 install pyinstaller build &&
  pip3.11 install -r requirements.txt &&
  python3.11 -m PyInstaller --onefile --name pg_migrator --add-data 'src:src' --add-data 'config_migrator.sample.ini:.' --collect-all textual --collect-all rich --collect-all psycopg --collect-all docker --collect-all jinja2 --collect-all yaml pg_migrator.py &&
  python3.11 -m build &&
  chmod 777 dist/* &&
  chown -R $(id -u):$(id -g) dist
"
mv dist/pg_migrator "dist/${BINARY_NAME}"

echo "2. Validating Linux Binary in almalinux:8.10..."
chmod +x "dist/${BINARY_NAME}"
docker run --rm -v $(pwd):/workspace -w /workspace almalinux:8.10 bash -c "
  ./dist/${BINARY_NAME} --help
"
echo "Linux binary execution successful."

echo "3. Packaging DEB and RPM using nfpm..."
# We will run nfpm via docker so we don't need go locally
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
echo "6. Testing Python Wheel installation in python:3.11-slim..."
docker run --rm -v $(pwd):/workspace -w /workspace python:3.11-slim bash -c "
  pip install ./$WHEEL_FILE &&
  pg_migrator --help
"
echo "Wheel installation and execution successful."

echo "All packaging and end-to-end tests completed successfully!"
