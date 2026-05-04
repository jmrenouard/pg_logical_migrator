# Design Document: Robust Packaging Tests and Anomaly Detection

**Date:** 2026-05-04
**Topic:** Improving `e2e_packaging_test.sh` for `pg_logical_migrator`

## 1. Problem Statement
The current packaging tests are basic: they only run `--help` to verify the binary starts. They also have issues with file ownership and permissions when running inside Docker, leading to `chmod: Operation not permitted` errors. To ensure "top-notch" packaging, we need deeper verification and more robust environment handling.

## 2. Goals
- **Robustness**: Fix ownership/permission issues by using consistent UID/GID handling.
- **Anomaly Detection**: Detect missing dependencies, incorrect versions, and missing bundled resources.
- **Portability**: Ensure the binary works across a wide range of Linux distributions.

## 3. Proposed Design

### 3.1. Unified Validation Function
A new Bash function `validate_artifact` will be introduced to perform standardized checks:
1.  **Existence Check**: Verify the file was actually created.
2.  **Version Check**: Run `./pg_migrator --version` and grep for the expected version string.
3.  **Dependency Check**: Run `ldd` and check for "not found" entries.
4.  **Resource Check**: Run `./pg_migrator generate-config --output /tmp/test.ini` to verify that the binary can access its bundled internal data (like the sample config).

### 3.2. Permission Management
- Every Docker execution that creates files in the workspace volume will be followed by a `chown` command to return ownership to the host user (`$(id -u):$(id -g)`).
- Use `--user $(id -u):$(id -g)` for containers that don't need root privileges (like `nfpm`).

### 3.3. Extended Distribution Testing
Continue testing on:
- **Debian-based**: Ubuntu 24.04, Ubuntu 22.04, Debian 11.
- **RHEL-based**: AlmaLinux 8, AlmaLinux 9, Fedora 39, UBI 8, UBI 9.

### 3.4. Package Metadata Verification
For DEB and RPM packages:
- Verify that the binary is installed in `/usr/bin/pg_migrator`.
- Verify the package version and name.

## 4. Implementation Plan
1.  **Phase 1**: Modify `e2e_packaging_test.sh` to add the `validate_artifact` function and improve permission handling.
2.  **Phase 2**: Add `chown` after `nfpm` package generation.
3.  **Phase 3**: Run the full test suite and verify it passes.

## 5. Success Criteria
- The `chmod` error is resolved.
- The script fails if the version is wrong.
- The script fails if a library is missing.
- The script fails if the bundled config sample is missing.
- All DEB/RPM installations are verified on multiple distros.
