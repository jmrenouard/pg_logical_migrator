"""Executable documentation tests for tutorials, CLI parity, Diataxis, and Mermaid."""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from src.cli.helpers import generate_sample_config
from src.cli.pipelines import cmd_init_replication, cmd_post_migration
from src.config import Config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
LEGACY_DOCS_DIR = REPO_ROOT / "DOCS"

REQUIRED_QUADRANTS = (
    "01-tutorials",
    "02-how-to-guides",
    "03-reference",
    "04-explanation",
)

LEGACY_DOC_FILES = (
    "CODEBASE.md",
    "CONCEPTS.md",
    "CONFIGURATION.md",
    "DOCKER.md",
    "LIFECYCLE.md",
    "LIMITATIONS.md",
    "README.md",
    "TESTING.md",
    "TOOLS.md",
    "VALIDATION.md",
    "WORKFLOW.md",
)

FENCE_OPEN_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\n]*)$")
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\n]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")
MERMAID_HEADER_RE = re.compile(
    r"^(?:graph|flowchart|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|"
    r"erDiagram|gantt|pie|gitGraph)\b"
)
CLI_CMD_RE = re.compile(
    r"(?:PYTHONPATH=\.\s+)?(?:python3?\s+|venv/bin/python\s+|\./)?"
    r"(pg_migrator(?:\.py)?|py_migrator\.py)\s+(.*)"
)


def _iter_diataxis_files() -> list[pathlib.Path]:
    """Return index.md plus all Markdown files in the four Diataxis quadrants."""
    files: list[pathlib.Path] = []
    index_file = DOCS_DIR / "index.md"
    if index_file.is_file():
        files.append(index_file)
    for quadrant in REQUIRED_QUADRANTS:
        quadrant_dir = DOCS_DIR / quadrant
        if quadrant_dir.is_dir():
            files.extend(sorted(quadrant_dir.rglob("*.md")))
    return files


def _iter_active_doc_files() -> list[pathlib.Path]:
    """Return non-archival Markdown files deduplicated by resolved path."""
    seen: set[pathlib.Path] = set()
    ordered: list[pathlib.Path] = []
    candidates: list[pathlib.Path] = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "HOWTO.md",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "GEMINI.md",
        REPO_ROOT / "SECURITY.md",
        *[LEGACY_DOCS_DIR / name for name in LEGACY_DOC_FILES],
        *[
            REPO_ROOT / "PROJECT" / name
            for name in (
                "README.md",
                "CONSTITUTION.md",
                "SPECIFICATIONS.md",
                "PROGRESS.md",
                "MILESTONES.md",
                "TASKS.md",
            )
        ],
        *_iter_diataxis_files(),
    ]
    for path in candidates:
        if path.is_file():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                ordered.append(path)
    return ordered


def _iter_all_repo_markdown() -> list[pathlib.Path]:
    """Return all unique Markdown files across the repository."""
    seen: set[pathlib.Path] = set()
    files: list[pathlib.Path] = []
    ignored_dirs = {".git", "venv", ".venv", "node_modules"}
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if any(part in ignored_dirs for part in path.parts):
            continue
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            files.append(path)
    return files


def _load_build_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> argparse.ArgumentParser:
    """Import pg_migrator.build_parser, stubbing readline if absent."""
    if importlib.util.find_spec("readline") is None:
        stub_readline = types.ModuleType("readline")
        monkeypatch.setitem(sys.modules, "readline", stub_readline)
    if "pg_migrator" in sys.modules:
        del sys.modules["pg_migrator"]
    if str(REPO_ROOT) not in sys.path:
        monkeypatch.syspath_prepend(str(REPO_ROOT))
    import pg_migrator

    return pg_migrator.build_parser()


def _extract_fenced_blocks(text: str) -> list[tuple[int, str, str, str]]:
    """Return (start_line, indent, lang, body) for each fenced code block."""
    blocks: list[tuple[int, str, str, str]] = []
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        match = FENCE_OPEN_RE.match(lines[idx])
        if not match:
            idx += 1
            continue
        indent, marker, info = match.groups()
        fence_char = marker[0]
        fence_len = len(marker)
        start_line = idx + 1
        lang = info.strip().split()[0].lower() if info.strip() else ""
        body_lines: list[str] = []
        idx += 1
        close_re = re.compile(rf"^\s*{re.escape(fence_char)}{{{fence_len},}}\s*$")
        while idx < len(lines) and not close_re.match(lines[idx]):
            body_lines.append(lines[idx])
            idx += 1
        blocks.append((start_line, indent, lang, "\n".join(body_lines)))
        idx += 1
    return blocks


def _strip_fenced_and_inline_code(text: str) -> list[tuple[int, str]]:
    """Return 1-based (lineno, line_text) outside fenced code blocks."""
    out: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if in_fence:
            if re.match(rf"^\s*{re.escape(fence_char)}{{{fence_len},}}\s*$", raw):
                in_fence = False
            continue
        match = FENCE_OPEN_RE.match(raw)
        if match:
            marker = match.group(2)
            fence_char = marker[0]
            fence_len = len(marker)
            in_fence = True
            continue
        cleaned = re.sub(r"`[^`]+`", " ", raw)
        out.append((lineno, cleaned))
    return out


class TestExecutableTutorialWorkflows:
    """Validate tutorial config generation, dry-run pipelines, and CLI execution."""

    def test_tutorial_generate_config_and_config_parsing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Exercise Tutorial 1 config generation and Config suffix resolution."""
        ini_path = tmp_path / "tutorial_migrator.ini"
        generate_sample_config(str(ini_path))
        assert ini_path.is_file()

        cfg = Config(str(ini_path))
        assert cfg.get_databases() == ["source_db"]
        assert cfg.get_target_schemas() == ["public"]

        rep = cfg.get_replication()
        assert rep["publication_name"] == "migrator_pub_source_db_public"
        assert rep["subscription_name"] == "migrator_sub_source_db_public"
        assert rep["slot_name"] == "migrator_slot_source_db_public"

        cfg.update_section("replication", {"target_schema": "sales, billing"})
        cfg.save()
        reloaded = Config(str(ini_path))
        assert reloaded.get_target_schemas() == ["sales", "billing"]
        assert "_multi_" in reloaded.get_replication()["publication_name"]

    def test_tutorial_dry_run_pipelines_execute(
        self, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Execute init-replication and post-migration in dry-run mode."""
        ini_path = tmp_path / "tut_dry.ini"
        results_dir = tmp_path / "results"
        generate_sample_config(str(ini_path))

        args = types.SimpleNamespace(
            config=str(ini_path),
            results_dir=str(results_dir),
            loglevel="INFO",
            sync_delay=3600,
            dry_run=True,
            verbose=False,
            use_stats=False,
            drop_dest=False,
            wait=False,
        )
        fake_clients = (MagicMock(), MagicMock())
        with patch("src.cli.pipelines.build_clients", return_value=fake_clients):
            rc_init = cmd_init_replication(args)
            rc_post = cmd_post_migration(args)

        assert rc_init == 0
        assert rc_post == 0
        output = capsys.readouterr().out
        assert "DRY-RUN (no changes)" in output
        assert "Wait 3600s for initial sync" in output
        assert "Terminate Replication & Schema Post-Data" in output
        assert "Row Parity Check" in output
        assert "No changes were made." in output
        assert (results_dir / "pg_migrator.log").is_file()

    def test_subprocess_cli_tutorial_commands(self, tmp_path: pathlib.Path) -> None:
        """Execute real pg_migrator.py subprocess commands documented in Tutorial 1."""
        if importlib.util.find_spec("readline") is None:
            pytest.skip("pg_migrator.py imports POSIX readline (covered in Linux CI).")

        ini_path = tmp_path / "cli_tut.ini"
        results_dir = tmp_path / "cli_results"

        ver = subprocess.run(
            [sys.executable, "pg_migrator.py", "--version"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert ver.returncode == 0
        assert "1.4.1" in ver.stdout

        hlp = subprocess.run(
            [sys.executable, "pg_migrator.py", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert hlp.returncode == 0
        assert "init-replication" in hlp.stdout
        assert "post-migration" in hlp.stdout

        gen_cmd = [
            sys.executable,
            "pg_migrator.py",
            "generate-config",
            "--output",
            str(ini_path),
        ]
        gen = subprocess.run(
            gen_cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert gen.returncode == 0
        assert ini_path.is_file()

        for subcmd in ("init-replication", "post-migration"):
            res = subprocess.run(
                [
                    sys.executable,
                    "pg_migrator.py",
                    subcmd,
                    "-c",
                    str(ini_path),
                    "--results-dir",
                    str(results_dir),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            assert res.returncode == 0, res.stderr
            assert "No changes were made." in res.stdout

        bad = subprocess.run(
            [sys.executable, "pg_migrator.py", "-c", str(ini_path), "init-replication"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert bad.returncode == 2


class TestCliDocumentationParity:
    """Validate that documented CLI flags and subcommands match build_parser()."""

    def test_all_documented_bash_cli_examples_parse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parse every non-placeholder bash CLI invocation with build_parser()."""
        parser = _load_build_parser(monkeypatch)
        failures: list[str] = []

        for md_file in _iter_active_doc_files():
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            text = md_file.read_text(encoding="utf-8")
            for start_line, _, lang, body in _extract_fenced_blocks(text):
                if lang not in {"bash", "sh", "shell"}:
                    continue
                for offset, raw_line in enumerate(body.splitlines(), start=1):
                    line = raw_line.strip()
                    if not line or line.startswith("#") or line.startswith("scp "):
                        continue
                    if "<" in line or "..." in line:
                        continue
                    match = CLI_CMD_RE.search(line)
                    if not match:
                        continue
                    prog, rest = match.groups()
                    if prog == "py_migrator.py":
                        failures.append(f"{rel}:{start_line + offset}: typo '{prog}'")
                        continue
                    tokens = shlex.split(rest.split("#", 1)[0].strip())
                    cmd_tokens: list[str] = []
                    for tok in tokens:
                        if tok in {"|", "&&", ";", ">"}:
                            break
                        cmd_tokens.append(tok)
                    if not cmd_tokens:
                        continue
                    try:
                        parser.parse_args(cmd_tokens)
                    except SystemExit as exc:
                        if exc.code != 0:
                            msg = f"{rel}:{start_line + offset}: '{line}' -> {exc.code}"
                            failures.append(msg)

        assert not failures, "\n".join(failures)

    def test_reference_documents_all_27_subcommands_and_sync_delay_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify all 27 subcommands and --sync-delay=3600 appear in reference docs."""
        parser = _load_build_parser(monkeypatch)
        subparser_action = next(
            act
            for act in parser._actions
            if isinstance(act, argparse._SubParsersAction)
        )
        subcommands = sorted(subparser_action.choices.keys())
        assert len(subcommands) == 27

        ref_path = DOCS_DIR / "03-reference" / "cli-commands-and-configuration.md"
        ref_text = ref_path.read_text(encoding="utf-8")
        tools_text = (LEGACY_DOCS_DIR / "TOOLS.md").read_text(encoding="utf-8")
        missing = [cmd for cmd in subcommands if f"`{cmd}`" not in ref_text]
        assert not missing, f"Missing subcommands in Reference: {missing}"
        assert "`3600`" in ref_text
        assert "`3600`" in tools_text

    def test_no_phantom_cli_commands_or_flags_in_active_docs(self) -> None:
        """Reject previously removed phantom CLI commands/flags in active docs."""
        banned_patterns = (
            re.compile(r"\bapply-params\b"),
            re.compile(r"\bpg_migrator(?:\.py)?\s+progress\b"),
            re.compile(r"--db\s+target_db"),
            re.compile(r"--no-wait\b"),
        )
        hits: list[str] = []
        for md_file in _iter_active_doc_files():
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            text = md_file.read_text(encoding="utf-8")
            for pattern in banned_patterns:
                if pattern.search(text):
                    hits.append(f"{rel}: matched banned pattern '{pattern.pattern}'")
        assert not hits, "\n".join(hits)


class TestDiataxisSteAndLinks:
    """Validate Diataxis quadrant boundaries, STE constraints, and links."""

    def test_diataxis_structure_and_quadrant_boundaries(self) -> None:
        """Verify docs/index.md, 4 quadrants, and quadrant genre separation rules."""
        assert (DOCS_DIR / "index.md").is_file()
        for quadrant in REQUIRED_QUADRANTS:
            q_dir = DOCS_DIR / quadrant
            assert q_dir.is_dir(), f"Missing quadrant {quadrant}"
            assert (q_dir / "index.md").is_file(), f"Missing {quadrant}/index.md"
            non_index = [p for p in q_dir.rglob("*.md") if p.name.lower() != "index.md"]
            assert non_index, f"Expected non-index docs inside {quadrant}"

        for md_file in _iter_diataxis_files():
            if md_file.name.lower() == "index.md":
                continue
            rel = md_file.relative_to(DOCS_DIR)
            quadrant = rel.parts[0]
            lines = _strip_fenced_and_inline_code(md_file.read_text(encoding="utf-8"))
            body = "\n".join(line for _, line in lines)
            headings = [
                m.group(1)
                for _, line in lines
                if (m := HEADING_RE.match(line)) is not None
            ]

            if quadrant == "02-how-to-guides":
                val_re = re.compile(r"\b(?:validat|verif)\w*\b", re.I)
                rb_re = re.compile(r"\b(?:rollback|revert|backout)\b", re.I)
                assert val_re.search(body), md_file
                assert rb_re.search(body), md_file
                theory_re = re.compile(
                    r"\b(?:why|architecture|theory|explanation)\b", re.I
                )
                assert not any(theory_re.search(h) for h in headings), md_file
            elif quadrant == "03-reference":
                assert "|" in body or re.search(r"^\s*[-*]\s+", body, re.M), md_file
                tut_re = re.compile(r"\b(?:in this tutorial|let's|step 1)\b", re.I)
                assert not tut_re.search(body), md_file
            elif quadrant == "04-explanation":
                proc_re = re.compile(r"\b(?:step\s+\d+|rollback|prerequisites)\b", re.I)
                assert not any(proc_re.search(h) for h in headings), md_file

    def test_how_to_guides_asd_ste100_constraints(self) -> None:
        """Enforce key ASD-STE100 Issue 9 constraints on docs/02-how-to-guides/*.md."""
        howto_dir = DOCS_DIR / "02-how-to-guides"
        for md_file in sorted(howto_dir.rglob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            for lineno, line in _strip_fenced_and_inline_code(text):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                assert ";" not in stripped, f"Semicolon in {md_file}:{lineno}"
                assert not re.search(
                    r"\b(?:should|would|may|might|shall)\b", stripped, re.I
                ), f"Weak modal in {md_file}:{lineno}: {stripped}"
                assert not re.search(
                    r"\b[A-Za-z]+(?:n't|'re|'ve|'ll|'d)\b", stripped, re.I
                ), f"Contraction in {md_file}:{lineno}: {stripped}"
                clean_line = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", stripped)
                clean_line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean_line)
                for sentence in re.split(r"(?<=[.!?])\s+", clean_line):
                    words = [w for w in re.split(r"\s+", sentence.strip()) if w]
                    if words:
                        assert len(words) <= 20, (
                            f"STE > 20 words ({len(words)}) in {md_file}:{lineno}"
                        )

    def test_all_markdown_relative_links_resolve_and_no_local_paths(self) -> None:
        """Verify relative links resolve and no local /home paths remain."""
        broken: list[str] = []
        forbidden: list[str] = []
        ext_schemes = ("http://", "https://", "mailto:", "#")
        for md_file in _iter_all_repo_markdown():
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            text = md_file.read_text(encoding="utf-8", errors="replace")
            if "/home/jmren" in text or "file:///" in text:
                forbidden.append(rel)
            for lineno, line in _strip_fenced_and_inline_code(text):
                for match in LINK_RE.finditer(line):
                    raw_dest = match.group(1).strip()
                    target = raw_dest.split("#", 1)[0].split("?", 1)[0].strip()
                    if not target or target.startswith(ext_schemes):
                        continue
                    resolved = (md_file.parent / target).resolve()
                    if not resolved.exists():
                        broken.append(f"{rel}:{lineno}: {target}")
        assert not forbidden, f"Forbidden hardcoded local URIs: {forbidden}"
        assert not broken, "\n".join(broken)


class TestMermaidAndLanguageHygiene:
    """Validate Mermaid syntax, no ASCII flowcharts, and English-only docs."""

    def test_zero_ascii_flowcharts_and_valid_column0_mermaid(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Ban untagged ASCII trees and enforce valid column-0 Mermaid blocks."""
        errors: list[str] = []
        mermaid_blocks: list[tuple[str, str]] = []

        for md_file in _iter_all_repo_markdown():
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            text = md_file.read_text(encoding="utf-8", errors="replace")
            for start_line, indent, lang, body in _extract_fenced_blocks(text):
                if lang == "mermaid":
                    if indent:
                        errors.append(f"{rel}:{start_line}: indented mermaid fence")
                    first_non_comment = next(
                        (
                            ln.strip()
                            for ln in body.splitlines()
                            if ln.strip() and not ln.strip().startswith("%%")
                        ),
                        "",
                    )
                    if not MERMAID_HEADER_RE.match(first_non_comment):
                        msg = (
                            f"{rel}:{start_line}: bad header '{first_non_comment}'"
                        )
                        errors.append(msg)
                    mermaid_blocks.append((f"{rel}:{start_line}", body))
                    continue

                if not lang:
                    if re.search(r"[┌┐└┘├┤┬┴┼─│═║╔╗╚╝]|-->|<--", body):
                        errors.append(f"{rel}:{start_line}: untagged ASCII diagram")
                elif lang == "text" and re.search(r"-->|<--|\+---+\+", body):
                    errors.append(f"{rel}:{start_line}: ASCII arrow in text block")

        assert mermaid_blocks, "Expected Mermaid diagrams in documentation"
        assert not errors, "\n".join(errors)

        mmdc_bin = shutil.which("mmdc")
        if mmdc_bin is not None:
            out_svg = tmp_path / "rendered.svg"
            for loc, code in mermaid_blocks:
                res = subprocess.run(
                    [mmdc_bin, "-i", "-", "-o", str(out_svg)],
                    input=code,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert res.returncode == 0, f"mmdc failed on {loc}: {res.stderr}"

    def test_english_only_documentation_isolation(self) -> None:
        """Ensure documentation remains 100% English without French headers."""
        fr_markers = re.compile(
            r"\b(?:tutoriel|guides-pratiques|avertissement|étapes|prérequis|vérification)\b",
            re.I,
        )
        hits: list[str] = []
        for md_file in _iter_all_repo_markdown():
            rel = md_file.relative_to(REPO_ROOT).as_posix()
            text = md_file.read_text(encoding="utf-8", errors="replace")
            for lineno, line in _strip_fenced_and_inline_code(text):
                if fr_markers.search(line):
                    hits.append(f"{rel}:{lineno}: {line.strip()}")
        assert not hits, "\n".join(hits)
