# Robust Packaging Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `e2e_packaging_test.sh` to fix permission issues and add deep anomaly detection (version, ldd, bundled resources).

**Architecture:** Use a centralized Bash function `validate_artifact` for consistent checks across multiple distributions. Implement strict ownership management after every Docker build step.

**Tech Stack:** Bash, Docker, PyInstaller, NFPM.

---

### Task 1: Refactor `e2e_packaging_test.sh` with `validate_artifact`

**Files:**
- Modify: `e2e_packaging_test.sh`

- [ ] **Step 1: Add `validate_artifact` function and improve Step 1 & 2**

```bash
<<<<
    echo "1. Building Linux Binary inside rockylinux:8..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace rockylinux:8 bash -c "
      dnf install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-pip gcc postgresql-devel &&
      python${PYTHON_VERSION} -m pip install --upgrade pip &&
      python${PYTHON_VERSION} -m pip install pyinstaller build &&
      python${PYTHON_VERSION} -m pip install -r requirements.txt &&
      python${PYTHON_VERSION} -m PyInstaller --onefile --name pg_migrator --add-data 'src:src' --add-data 'config_migrator.sample.ini:.' --collect-all textual --collect-all rich --collect-all psycopg --collect-all docker --collect-all jinja2 --collect-all yaml pg_migrator.py &&
      python${PYTHON_VERSION} -m build &&
      chmod 755 dist/* &&
      chown -R $(id -u):$(id -g) dist/
    "
    mv dist/pg_migrator "dist/${BINARY_NAME}"

    echo "2.1 Validating Linux Binary in ubuntu:24.04..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace ubuntu:24.04 bash -c "./dist/${BINARY_NAME} --help"
    
    echo "2.2 Validating Linux Binary in fedora:39..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace fedora:39 bash -c "./dist/${BINARY_NAME} --help"
    
    echo "2.3 Validating Linux Binary in redhat/ubi8..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace redhat/ubi8 bash -c "./dist/${BINARY_NAME} --help"
====
validate_artifact() {
    local container=$1
    local binary_path=$2
    local expected_version=$3

    echo "--- Validating $binary_path in $container ---"
    
    # Check version
    local version_out=$(docker run --rm -v "$(pwd):/workspace" -w /workspace "$container" "./$binary_path" --version 2>&1)
    echo "Version output: $version_out"
    if [[ ! "$version_out" =~ "$expected_version" ]]; then
        echo "ERROR: Version mismatch! Expected $expected_version"
        exit 1
    fi

    # Check shared libs (ldd) - skip if ldd not found (UBI)
    echo "Checking shared libraries..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace "$container" bash -c "command -v ldd >/dev/null && ldd ./$binary_path || echo 'ldd not available, skipping check'" | grep "not found" && { echo "ERROR: Missing shared libraries!"; exit 1; } || echo "All shared libs found (or ldd skipped)."

    # Check resource access (generate-config)
    echo "Checking resource access (generate-config)..."
    docker run --rm -v "$(pwd):/workspace" -w /workspace "$container" "./$binary_path" generate-config --output /tmp/test_config.ini
    echo "Resource check successful."
}

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
    validate_artifact "ubuntu:24.04" "dist/${BINARY_NAME}" "$VERSION"
    validate_artifact "fedora:39" "dist/${BINARY_NAME}" "$VERSION"
    validate_artifact "redhat/ubi8" "dist/${BINARY_NAME}" "$VERSION"
>>>>
```

- [ ] **Step 2: Update NFPM and installation tests**

```bash
<<<<
    docker run --rm -v "$(pwd):/workspace" -w /workspace goreleaser/nfpm:latest pkg --packager deb --target dist/
    docker run --rm -v "$(pwd):/workspace" -w /workspace goreleaser/nfpm:latest pkg --packager rpm --target dist/

    DEB_FILE=$(ls dist/*.deb | head -n 1)
    RPM_FILE=$(ls dist/*.rpm | head -n 1)
====
    docker run --rm -v "$(pwd):/workspace" -w /workspace goreleaser/nfpm:latest pkg --packager deb --target dist/
    docker run --rm -v "$(pwd):/workspace" -w /workspace goreleaser/nfpm:latest pkg --packager rpm --target dist/
    
    # Fix ownership of generated packages using docker
    docker run --rm -v "$(pwd):/workspace" -w /workspace rockylinux:8 chown -R $(id -u):$(id -g) dist/

    DEB_FILE=$(ls dist/*.deb | sort -V | tail -n 1)
    RPM_FILE=$(ls dist/*.rpm | sort -V | tail -n 1)
>>>>
```

- [ ] **Step 3: Run the tests**

Run: `./e2e_packaging_test.sh`
Expected: Completion with "All packaging and end-to-end tests completed successfully!"

- [ ] **Step 4: Commit**

```bash
git add e2e_packaging_test.sh
git commit -m "test: improve packaging tests with anomaly detection and better permissions"
```
