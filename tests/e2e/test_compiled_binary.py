import pytest
import os
import subprocess
import platform


def test_binary_glibc_backward_compatibility():
    """
    E2E Test to validate that the compiled binary works on an older Linux system (e.g. RedHat/AlmaLinux 8).
    This validates the glibc backward compatibility fix.
    """
    if platform.system() != "Linux":
        pytest.skip("GLIBC compatibility test is only relevant on Linux.")

    # Locate the binary built by PyInstaller
    dist_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "dist"))

    # Check if the directory exists and has a binary
    if not os.path.exists(dist_dir):
        pytest.skip(
            "dist directory not found. Please compile the binary first.")

    binaries = [f for f in os.listdir(dist_dir) if f.startswith("pg_migrator")]
    if not binaries:
        pytest.skip(
            "Compiled binary not found in dist/. Please run pyinstaller first.")

    bin_path = os.path.join(dist_dir, binaries[0])

    # To test compatibility, we use docker with almalinux:8.10
    # Make sure docker is installed and running
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker is not available to run the compatibility test.")

    print(f"Testing binary {bin_path} inside almalinux:8.10 container...")

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{dist_dir}:/workspace",
        "-w", "/workspace",
        "almalinux:8.10",
        f"./{binaries[0]}", "--help"
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)

    # If the glibc is incompatible, it will fail with an error like "version
    # `GLIBC_2.38' not found"
    assert res.returncode == 0, f"Binary failed to execute in AlmaLinux 8.10! Error:\n{
        res.stderr}\nOutput:\n{
        res.stdout}"
    assert "usage" in res.stdout or "positional arguments:" in res.stdout, "Help output was not found."
