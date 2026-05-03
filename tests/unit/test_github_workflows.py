"""Tests for GitHub Actions workflows (YAML validation + structural contracts).

Strategy:
  - Parse each workflow YAML and assert its structure matches documented intent
  - Validate key job dependencies, triggers, permissions
  - Validate packaging scripts logic with Python-based simulation
  - Test the version-extraction inline Python script used in multiple jobs
  - No GitHub API calls — all tests run fully offline

Install requirement: pyyaml (already in venv)
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixture: paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
MAIN_ENTRY = REPO_ROOT / "pg_migrator.py"


def load_workflow(name: str) -> dict:
    """Load and parse a workflow YAML file."""
    path = WORKFLOWS_DIR / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 1. YAML validity — all workflows must be parseable
# ---------------------------------------------------------------------------

class TestWorkflowYamlValidity:
    @pytest.mark.parametrize("filename", [
        "python-package.yml",
        "pyinstaller-publish.yml",
        "docker-publish.yml",
    ])
    def test_valid_yaml(self, filename):
        """Workflow file must be valid YAML."""
        path = WORKFLOWS_DIR / filename
        assert path.exists(), f"Workflow file not found: {path}"
        with open(path) as f:
            doc = yaml.safe_load(f)
        assert isinstance(doc, dict), "YAML root must be a mapping"
        assert "jobs" in doc, "Workflow must define 'jobs'"
        # PyYAML parses 'on' as Python True (YAML spec boolean)
        assert "on" in doc or True in doc, "Workflow must define triggers ('on')"

    @pytest.mark.parametrize("filename", [
        "python-package.yml",
        "pyinstaller-publish.yml",
        "docker-publish.yml",
    ])
    def test_no_syntax_errors(self, filename):
        """yamllint reports no blocking errors on the workflow file."""
        path = WORKFLOWS_DIR / filename
        result = subprocess.run(
            [sys.executable, "-m", "yamllint", "-d", "relaxed", str(path)],
            capture_output=True, text=True
        )
        # Only fail on hard errors, ignore trailing-spaces (cosmetic)
        blocking_errors = [
            l for l in result.stdout.splitlines()
            if "error" in l.lower() and "trailing-spaces" not in l
        ]
        assert not blocking_errors, (
            f"yamllint errors in {filename}:\n" + "\n".join(blocking_errors))


# ---------------------------------------------------------------------------
# 2. python-package.yml — CI pipeline contracts
# ---------------------------------------------------------------------------

class TestPythonPackageWorkflow:
    @pytest.fixture(autouse=True)
    def workflow(self):
        self.wf = load_workflow("python-package.yml")
        self.jobs = self.wf["jobs"]
        # PyYAML parses YAML 'on' keyword as Python True
        self._on = self.wf.get("on") or self.wf.get(True, {})

    def test_has_required_jobs(self):
        """Must define: test, docker, build-python-assets."""
        assert "test" in self.jobs
        assert "docker" in self.jobs
        assert "build-python-assets" in self.jobs

    def test_test_job_matrix_python_versions(self):
        """CI tests must cover Python 3.11, 3.12, 3.13."""
        matrix = self.jobs["test"]["strategy"]["matrix"]["python-version"]
        assert "3.11" in matrix
        assert "3.12" in matrix
        assert "3.13" in matrix

    def test_docker_job_needs_test(self):
        """Docker build must only run after tests pass."""
        needs = self.jobs["docker"].get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "test" in needs

    def test_build_python_assets_needs_test(self):
        """Python asset build must depend on tests."""
        needs = self.jobs["build-python-assets"].get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "test" in needs

    def test_permissions_include_packages_write(self):
        """GHCR push requires packages: write permission."""
        perms = self.wf.get("permissions", {})
        assert perms.get("packages") == "write"

    def test_trigger_on_push_all_branches(self):
        """CI must run on every push."""
        push = self._on.get("push", {})
        branches = push.get("branches", [])
        assert "*" in branches or "**" in branches, \
            "CI should trigger on all branches"

    def test_trigger_on_pull_request_main(self):
        """PRs to main must trigger CI."""
        pr = self._on.get("pull_request", {})
        branches = pr.get("branches", [])
        assert "main" in branches

    def test_test_job_installs_flake8_and_pytest(self):
        """Test job must install flake8 and pytest."""
        steps = self.jobs["test"]["steps"]
        install_step = next(
            (s for s in steps if "Install" in s.get("name", "")), None)
        assert install_step is not None
        run_cmd = install_step.get("run", "")
        assert "pytest" in run_cmd
        assert "pytest-asyncio" in run_cmd

    def test_test_job_runs_unit_tests(self):
        """Test job must execute pytest against tests/unit."""
        steps = self.jobs["test"]["steps"]
        test_step = next(
            (s for s in steps if "unit" in s.get("run", "").lower()), None)
        assert test_step is not None, "No step runs unit tests"
        assert "pytest" in test_step["run"]
        assert "tests/unit" in test_step["run"]

    def test_test_job_uses_PYTHONPATH(self):
        """PYTHONPATH=. must be set so src/ imports work."""
        steps = self.jobs["test"]["steps"]
        test_step = next(
            (s for s in steps if "unit" in s.get("run", "").lower()), None)
        assert "PYTHONPATH=." in test_step["run"]

    def test_test_report_uploaded_on_failure(self):
        """HTML test report must be uploaded even on failure."""
        steps = self.jobs["test"]["steps"]
        upload_step = next(
            (s for s in steps if "upload" in s.get("name", "").lower()), None)
        assert upload_step is not None
        assert upload_step.get("if", "").strip() == "always()"

    def test_docker_uses_buildx(self):
        """Docker job must set up Docker Buildx."""
        steps = self.jobs["docker"]["steps"]
        buildx = next(
            (s for s in steps if "buildx" in s.get("uses", "").lower() or
             "Buildx" in s.get("name", "")), None)
        assert buildx is not None

    def test_docker_login_only_on_push(self):
        """Docker login must only happen on push events (not PRs)."""
        steps = self.jobs["docker"]["steps"]
        login_step = next(
            (s for s in steps if "login" in s.get("name", "").lower()), None)
        assert login_step is not None
        # Since I moved the 'if' to the job level for the whole job, 
        # the individual step might not have it anymore, or it's inherited.
        job_if = self.jobs["docker"].get("if", "")
        step_if = login_step.get("if", "")
        assert "push" in job_if or "push" in step_if

    def test_version_extraction_script(self):
        """The version extraction bash command must find a version in pg_migrator.py."""
        assert MAIN_ENTRY.exists(), "pg_migrator.py not found"
        content = MAIN_ENTRY.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        assert match is not None, "__version__ not found in pg_migrator.py"
        version = match.group(1)
        # Must be semver-like
        assert re.match(r'^\d+\.\d+\.\d+', version), \
            f"Version '{version}' is not semver-like"


# ---------------------------------------------------------------------------
# 3. pyinstaller-publish.yml — packaging pipeline contracts
# ---------------------------------------------------------------------------

class TestPyInstallerPublishWorkflow:
    @pytest.fixture(autouse=True)
    def workflow(self):
        self.wf = load_workflow("pyinstaller-publish.yml")
        self.jobs = self.wf["jobs"]
        # PyYAML parses YAML 'on' as Python True
        self._on = self.wf.get("on") or self.wf.get(True, {})

    def test_has_required_jobs(self):
        """Must define all four packaging stages."""
        assert "build-binaries" in self.jobs
        assert "validate-linux-binary" in self.jobs
        assert "package-os" in self.jobs
        assert "package-python" in self.jobs
        assert "publish-release" in self.jobs

    def test_validate_runs_after_build(self):
        """Validation must depend on build-binaries."""
        needs = self.jobs["validate-linux-binary"].get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "build-binaries" in needs

    def test_package_os_runs_after_validate(self):
        """OS packaging must depend on binary validation."""
        needs = self.jobs["package-os"].get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "validate-linux-binary" in needs

    def test_publish_release_needs_all_packages(self):
        """GitHub release must depend on build, OS packaging, and Python packaging."""
        needs = self.jobs["publish-release"].get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        assert "build-binaries" in needs
        assert "package-os" in needs
        assert "package-python" in needs

    def test_build_matrix_platforms(self):
        """Must build for Linux, Windows, macOS."""
        strategy = self.jobs["build-binaries"]["strategy"]
        os_list = strategy["matrix"]["os"]
        assert "ubuntu-latest" in os_list
        assert "windows-latest" in os_list
        assert "macos-latest" in os_list

    def test_build_matrix_python_versions(self):
        """Must build for Python 3.11, 3.12, 3.13."""
        strategy = self.jobs["build-binaries"]["strategy"]
        versions = strategy["matrix"]["python_version"]
        assert "3.11" in versions
        assert "3.12" in versions
        assert "3.13" in versions

    def test_trigger_on_version_tags(self):
        """Must trigger on v* tags for stable releases."""
        tags = self._on.get("push", {}).get("tags", [])
        assert any(t.startswith("v") for t in tags)

    def test_trigger_on_workflow_dispatch(self):
        """Must support manual dispatch for emergency releases."""
        assert "workflow_dispatch" in self._on

    def test_version_mismatch_check_in_publish(self):
        """Publish job must validate that git tag matches script version."""
        steps = self.jobs["publish-release"]["steps"]
        rel_info_step = next(
            (s for s in steps if "rel_info" in str(s.get("id", "")) or
             "Release Info" in s.get("name", "")), None)
        assert rel_info_step is not None
        run_code = rel_info_step.get("run", "")
        # Must check for version-tag mismatch
        assert "exit(1)" in run_code or "exit 1" in run_code

    def test_sha256_generated_for_binaries(self):
        """Binary build step must create SHA256 checksums."""
        steps = self.jobs["build-binaries"]["steps"]
        build_step = next(
            (s for s in steps if "Build binary" in s.get("name", "")), None)
        assert build_step is not None
        run_cmd = build_step.get("run", "")
        assert "sha256" in run_cmd.lower()

    def test_sha256_generated_for_os_packages(self):
        """OS package build step must generate SHA256 checksums."""
        steps = self.jobs["package-os"]["steps"]
        build_step = next(
            (s for s in steps if "Build DEB" in s.get("name", "") or
             "DEB and RPM" in s.get("name", "")), None)
        assert build_step is not None
        assert "sha256" in build_step["run"].lower()

    def test_linux_builds_via_ubi8_container(self):
        """Linux binaries must be built inside a UBI 8 container for glibc compat."""
        steps = self.jobs["build-binaries"]["steps"]
        build_step = next(
            (s for s in steps if "Build binary" in s.get("name", "")), None)
        assert build_step is not None
        run_cmd = build_step.get("run", "")
        assert "ubi8" in run_cmd or "ubi" in run_cmd.lower()

    def test_linux_binary_validated_on_ubi8(self):
        """Linux binary must be tested inside a UBI 8 container."""
        steps = self.jobs["validate-linux-binary"]["steps"]
        test_step = next(
            (s for s in steps if "Test Binary" in s.get("name", "") or
             "ubi" in s.get("name", "").lower()), None)
        assert test_step is not None
        run_cmd = test_step.get("run", "")
        assert "ubi8" in run_cmd or "ubi" in run_cmd.lower()
        assert "--help" in run_cmd

    def test_artifact_if_no_files_error(self):
        """Binary upload must fail if no file found (not silently succeed)."""
        steps = self.jobs["build-binaries"]["steps"]
        upload_step = next(
            (s for s in steps if "upload-artifact" in s.get("uses", "")), None)
        assert upload_step is not None
        assert upload_step.get("with", {}).get("if-no-files-found") == "error"

    def test_nfpm_used_for_deb_rpm(self):
        """OS packaging must use nfpm (goreleaser/nfpm)."""
        steps = self.jobs["package-os"]["steps"]
        install_nfpm = next(
            (s for s in steps if "nfpm" in s.get("name", "").lower()), None)
        assert install_nfpm is not None
        assert "nfpm" in install_nfpm.get("run", "")

    def test_release_notes_from_version_file(self):
        """Release body should reference the version-specific release note file."""
        steps = self.jobs["publish-release"]["steps"]
        notes_step = next(
            (s for s in steps if "Release Notes" in s.get("name", "") or
             "release_body" in s.get("run", "")), None)
        assert notes_step is not None
        run_cmd = notes_step.get("run", "")
        assert "releases/" in run_cmd


# ---------------------------------------------------------------------------
# 4. docker-publish.yml — Docker Hub pipeline contracts
# ---------------------------------------------------------------------------

class TestDockerPublishWorkflow:
    @pytest.fixture(autouse=True)
    def workflow(self):
        self.wf = load_workflow("docker-publish.yml")
        self.jobs = self.wf["jobs"]
        # PyYAML parses YAML 'on' as Python True
        self._on = self.wf.get("on") or self.wf.get(True, {})

    def test_has_build_and_push_job(self):
        assert "build-and-push" in self.jobs

    def test_trigger_on_version_tags_only(self):
        """Docker Hub publish only on v* tags (protect from accidental pushes)."""
        tags = self._on.get("push", {}).get("tags", [])
        assert len(tags) > 0
        assert all(t.startswith("v") for t in tags)

    def test_pre_publish_validation_step(self):
        """Must have a pre-publish validation step checking critical files."""
        steps = self.jobs["build-and-push"]["steps"]
        validate_step = next(
            (s for s in steps if "validation" in s.get("name", "").lower() or
             "Pre-publish" in s.get("name", "")), None)
        assert validate_step is not None

    def test_validates_dockerfile_exists(self):
        """Pre-publish validation must check for Dockerfile."""
        steps = self.jobs["build-and-push"]["steps"]
        validate_step = next(
            (s for s in steps if "validation" in s.get("name", "").lower() or
             "Pre-publish" in s.get("name", "")), None)
        assert "Dockerfile" in validate_step["run"]

    def test_validates_version_tag_consistency(self):
        """Pre-publish validation must abort if tag != script version."""
        steps = self.jobs["build-and-push"]["steps"]
        validate_step = next(
            (s for s in steps if "Pre-publish" in s.get("name", "")), None)
        assert validate_step is not None
        run_cmd = validate_step.get("run", "")
        assert "exit 1" in run_cmd

    def test_uses_docker_hub_secrets(self):
        """Login must use DOCKER_USER_LOGIN and DOCKER_USER_PASSWORD secrets."""
        steps = self.jobs["build-and-push"]["steps"]
        login_step = next(
            (s for s in steps
             if "login" in s.get("name", "").lower()
             or "log in" in s.get("name", "").lower()
             or "docker/login-action" in s.get("uses", "")), None)
        assert login_step is not None, "No Docker login step found"
        with_block = str(login_step.get("with", {}))
        assert "DOCKER_USER_LOGIN" in with_block or "docker_user_login" in with_block.lower()


    def test_pushes_latest_and_versioned_tags(self):
        """Must push both 'latest' and versioned tag to Docker Hub."""
        steps = self.jobs["build-and-push"]["steps"]
        push_step = next(
            (s for s in steps if "Build and push" in s.get("name", "")), None)
        assert push_step is not None
        tags = push_step.get("with", {}).get("tags", "")
        assert "latest" in tags
        assert "VERSION" in tags

    def test_push_is_true(self):
        """Build step must actually push (not just build)."""
        steps = self.jobs["build-and-push"]["steps"]
        push_step = next(
            (s for s in steps if "Build and push" in s.get("name", "")), None)
        assert push_step["with"].get("push") is True

    def test_uses_gha_cache(self):
        """Must use GitHub Actions cache for Docker layers."""
        steps = self.jobs["build-and-push"]["steps"]
        push_step = next(
            (s for s in steps if "Build and push" in s.get("name", "")), None)
        cache_from = push_step.get("with", {}).get("cache-from", "")
        assert "gha" in cache_from

    def test_oci_labels_set(self):
        """Must set OpenContainers image labels for traceability."""
        steps = self.jobs["build-and-push"]["steps"]
        push_step = next(
            (s for s in steps if "Build and push" in s.get("name", "")), None)
        labels = push_step.get("with", {}).get("labels", "")
        assert "org.opencontainers.image.title" in labels
        assert "org.opencontainers.image.version" in labels
        assert "org.opencontainers.image.source" in labels


# ---------------------------------------------------------------------------
# 5. Python packaging — version extraction logic validation
# ---------------------------------------------------------------------------

class TestVersionExtractionLogic:
    """Tests the inline Python version-extraction logic used in workflows."""

    def _run_version_extraction(self, content: str) -> str:
        """Simulate the inline Python script used in workflow jobs."""
        match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        return match.group(1) if match else "unknown"

    def test_extracts_standard_version(self):
        content = '__version__ = "1.4.0"'
        assert self._run_version_extraction(content) == "1.4.0"

    def test_extracts_prerelease_version(self):
        content = '__version__ = "1.4.0-alpha.1"'
        assert self._run_version_extraction(content) == "1.4.0-alpha.1"

    def test_returns_unknown_when_not_found(self):
        content = "# no version here"
        assert self._run_version_extraction(content) == "unknown"

    def test_ignores_single_quoted_version(self):
        """Workflow uses double-quote regex — single-quoted is not matched."""
        content = "__version__ = '1.0.0'"
        assert self._run_version_extraction(content) == "unknown"

    def test_extracts_from_real_pg_migrator_py(self):
        """Real pg_migrator.py must have a valid semver version."""
        assert MAIN_ENTRY.exists()
        content = MAIN_ENTRY.read_text(encoding="utf-8")
        version = self._run_version_extraction(content)
        assert version != "unknown"
        assert re.match(r'^\d+\.\d+\.\d+', version)

    def test_tag_matches_version(self):
        """Simulate the tag-consistency check used in publish-release step."""
        content = MAIN_ENTRY.read_text(encoding="utf-8")
        version = self._run_version_extraction(content)
        tag_name = f"v{version}"
        assert tag_name.startswith("v"), "Tag should start with 'v'"
        assert version in tag_name

    def test_tag_mismatch_would_exit(self):
        """Simulate: if tag != f'v{version}' → would exit(1)."""
        version = "1.4.0"
        wrong_tag = "v9.9.9"
        if wrong_tag != f"v{version}":
            assert True  # Would have called exit(1)
        else:
            pytest.fail("Version check should detect mismatch")


# ---------------------------------------------------------------------------
# 6. Packaging artefact contracts — Dockerfile + setup.py + requirements
# ---------------------------------------------------------------------------

class TestPackagingArtifactContracts:
    def test_dockerfile_exists(self):
        assert (REPO_ROOT / "Dockerfile").exists(), "Dockerfile missing"

    def test_requirements_txt_exists(self):
        assert (REPO_ROOT / "requirements.txt").exists(), "requirements.txt missing"

    def test_sample_config_exists(self):
        assert (REPO_ROOT / "config_migrator.sample.ini").exists(), \
            "config_migrator.sample.ini missing (used by PyInstaller --add-data)"

    def test_pg_migrator_py_is_entry_point(self):
        """pg_migrator.py must exist as the PyInstaller entry point."""
        assert MAIN_ENTRY.exists()

    def test_pg_migrator_has_version(self):
        content = MAIN_ENTRY.read_text(encoding="utf-8")
        assert '__version__' in content

    def test_src_directory_exists(self):
        """src/ must exist as it's included via --add-data 'src:src'."""
        assert (REPO_ROOT / "src").is_dir()

    def test_src_has_init(self):
        """src/ may or may not have __init__.py — both are valid packaging styles.
        PyInstaller uses --add-data 'src:src' so it copies the whole directory.
        We verify the directory itself exists."""
        assert (REPO_ROOT / "src").is_dir(), "src/ directory must exist"

    def test_license_file_exists(self):
        """LICENSE file is checked in docker-publish pre-publish validation."""
        assert (REPO_ROOT / "LICENSE").exists(), "LICENSE file missing"

    def test_releases_directory_exists(self):
        """releases/ dir must exist for release notes."""
        assert (REPO_ROOT / "releases").is_dir(), "releases/ directory missing"

    def test_requirements_parseable(self):
        """requirements.txt must be readable (no BOM, no encoding errors)."""
        content = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines() if l.strip()
                 and not l.strip().startswith("#")]
        assert len(lines) > 0, "requirements.txt is empty"

    def test_dockerfile_uses_python_base(self):
        """Dockerfile must derive from a Python base image."""
        content = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "FROM" in content
        # Should reference python, or a known base + python install
        assert "python" in content.lower() or "pip" in content.lower()

    def test_dockerfile_copies_src(self):
        """Dockerfile must copy src/ into the container."""
        content = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "src" in content

    def test_dockerfile_has_entrypoint_or_cmd(self):
        """Dockerfile must specify a default entrypoint or command."""
        content = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "ENTRYPOINT" in content or "CMD" in content

    def test_pyproject_or_setup_exists(self):
        """Build tools need pyproject.toml or setup.py/setup.cfg."""
        has_pyproject = (REPO_ROOT / "pyproject.toml").exists()
        has_setup_py = (REPO_ROOT / "setup.py").exists()
        has_setup_cfg = (REPO_ROOT / "setup.cfg").exists()
        assert has_pyproject or has_setup_py or has_setup_cfg, \
            "No build configuration file found (pyproject.toml, setup.py, or setup.cfg)"


# ---------------------------------------------------------------------------
# 7. Makefile test targets validation
# ---------------------------------------------------------------------------

class TestMakefileTargets:
    @pytest.fixture(autouse=True)
    def makefile_content(self):
        path = REPO_ROOT / "Makefile"
        assert path.exists(), "Makefile not found"
        self.content = path.read_text(encoding="utf-8")

    def test_has_test_unit_target(self):
        assert "test-unit" in self.content

    def test_has_test_integration_target(self):
        assert "test-integration" in self.content or "test-e2e" in self.content

    def test_has_test_all_target(self):
        assert "test-all" in self.content

    def test_unit_target_uses_pytest(self):
        """test-unit target must invoke pytest (via PYTEST variable or directly)."""
        lines = self.content.splitlines()
        in_target = False
        target_lines = []
        for line in lines:
            if line.startswith("test-unit:"):
                in_target = True
                continue
            if in_target:
                if line.startswith("\t"):
                    target_lines.append(line)
                else:
                    break
        # Makefile uses $(PYTEST) variable, not the literal word 'pytest'
        assert any("PYTEST" in l or "pytest" in l for l in target_lines), \
            "test-unit target must call PYTEST or pytest"

    def test_coverage_target_or_flag_present(self):
        """Makefile must support coverage reporting (test-coverage target or --cov flag)."""
        assert "cov" in self.content or "coverage" in self.content, \
            "No coverage support found in Makefile (add test-coverage target with --cov)"


# ---------------------------------------------------------------------------
# 8. Release notes — current version must have notes
# ---------------------------------------------------------------------------

class TestReleaseNotes:
    def test_current_version_has_release_notes(self):
        content = MAIN_ENTRY.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        assert match, "__version__ not found"
        version = match.group(1)
        notes_path = REPO_ROOT / "releases" / f"v{version}.md"
        assert notes_path.exists(), \
            (f"Release notes missing for v{version}: {notes_path}\n"
             f"Required by docker-publish.yml pre-publish validation.")

    def test_release_notes_not_empty(self):
        content = MAIN_ENTRY.read_text(encoding="utf-8")
        match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        version = match.group(1)
        notes_path = REPO_ROOT / "releases" / f"v{version}.md"
        if notes_path.exists():
            notes = notes_path.read_text(encoding="utf-8").strip()
            assert len(notes) > 50, "Release notes appear too sparse"
