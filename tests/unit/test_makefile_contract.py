"""The Makefile declares the pipeline; these tests hold it to that declaration.

The monthly release ran for months without a generation pass. Every individual
target worked - ``generate-data`` was correct and runnable - but the release
sequence simply did not name it, so 32,672 English records were never adapted
and CERT-FR CTI never became drafts. Nothing failed, because nothing asserted
what a stage is supposed to contain.

These tests read the Makefile as the contract it is. They are deliberately
textual: the point is to catch a step dropped from a stage, and running the
stage to find out costs a full pipeline pass.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"


def _text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _prerequisites(target: str) -> list[str]:
    """Prerequisites declared for ``target``, in order."""
    match = re.search(rf"^{re.escape(target)}:([^\n=]*)$", _text(), re.MULTILINE)
    assert match is not None, f"target '{target}' is not defined in the Makefile"
    return match.group(1).split()


def _variable(name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\s*:?=\s*(.*)$", _text(), re.MULTILINE)
    assert match is not None, f"variable '{name}' is not defined in the Makefile"
    return match.group(1).strip()


def test_every_declared_source_has_a_scheduler_script_that_exists() -> None:
    """A source in the table with no script would fail only when it next ran."""
    sources = _variable("SOURCES").split()
    assert sources, "SOURCES is empty"

    for source in sources:
        script = _variable(f"CRON_SCRIPT_{source}")
        path = REPO_ROOT / "src" / "data_platform" / "cron_schedulers" / script
        assert path.is_file(), f"{source}: {path} does not exist"


def test_every_declared_source_has_a_label() -> None:
    for source in _variable("SOURCES").split():
        assert _variable(f"CRON_LABEL_{source}"), f"{source} has no CRON_LABEL"


def test_scheduled_ingestion_actually_dispatches_for_every_source() -> None:
    """A scheduled ingestion that succeeds without ingesting is the worst case."""
    for source in _variable("SOURCES").split():
        result = subprocess.run(
            ["make", "--no-print-directory", "-n", f"{source}-cron"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{source}-cron failed: {result.stderr}"
        assert "Nothing to be done" not in result.stdout + result.stderr, (
            f"'{source}-cron' resolves to no recipe - scheduled ingestion for "
            f"{source} would report success without ingesting anything"
        )
        assert _variable(f"CRON_SCRIPT_{source}") in result.stdout, (
            f"'{source}-cron' does not dispatch its scheduler script"
        )


def test_an_unknown_source_fails_loudly() -> None:
    """Pattern rules match anything; a typo must not silently no-op."""
    result = subprocess.run(
        ["make", "--no-print-directory", "definitely-not-a-source-cron"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Unknown ingestion source" in result.stdout + result.stderr


def test_process_runs_generation_between_normalize_and_annotate() -> None:
    """Order is load-bearing, not cosmetic."""
    assert _prerequisites("process") == ["normalize", "generate-data", "annotate"]


def test_every_release_path_runs_the_full_process_stage() -> None:
    """The regression that started this: a release path skipping generation."""
    for target in ("release", "pipeline-push", "dataset-release"):
        assert "process" in _prerequisites(target), (
            f"'{target}' does not run the process stage, so it can publish a "
            f"dataset built without a generation pass"
        )


def test_monthly_release_still_resolves_to_the_release_stage() -> None:
    """Kept as an alias: it is the name the release path is known by."""
    assert _prerequisites("monthly-release") == ["release"]


def test_legacy_scheduler_aliases_still_resolve() -> None:
    """CI, the docs and the defence script call these names."""
    assert _prerequisites("run-scheduler") == ["collect"]
    assert _prerequisites("ingest-all-cron") == ["collect"]
    assert _prerequisites("collect") == ["cron-orchestrate"]


def _tracked_yaml_and_markdown() -> list[Path]:
    """Workflow and doc files that are actually part of the repository."""
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--", ".github/workflows", "docs"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        # Outside a checkout, fall back to the working tree rather than
        # silently checking nothing.
        return [
            path
            for source in (REPO_ROOT / ".github" / "workflows", REPO_ROOT / "docs")
            for path in source.rglob("*")
            if path.suffix in {".yml", ".yaml", ".md"}
        ]

    return [
        REPO_ROOT / name
        for name in listing.split("\0")
        if name.endswith((".yml", ".yaml", ".md")) and (REPO_ROOT / name).is_file()
    ]


def test_targets_referenced_by_ci_and_docs_are_defined() -> None:
    """Renaming a target that CI or the defence script calls breaks them."""
    defined = set(re.findall(r"^([a-zA-Z0-9_-]+):", _text(), re.MULTILINE))

    referenced: set[str] = set()
    for path in _tracked_yaml_and_markdown():
    # Only real invocations: "make x", a CI "run: make x", or an inline `make x`.
        referenced |= set(
            re.findall(
                r"(?:^|`|run:[ \t]*)make ([a-z][a-z0-9-]{2,})\b",
                path.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )

    # Pattern-rule targets are real but never appear as literal definitions.
    sources = _variable("SOURCES").split()
    defined |= {f"{s}-cron" for s in sources}
    defined |= {f"{s}-cron-reserved" for s in sources}

    missing = sorted(referenced - defined)
    assert not missing, f"referenced in CI/docs but not defined in the Makefile: {missing}"


def test_every_release_path_step_runs_without_resyncing() -> None:
    """A bare `uv run` in the release image destroys the environment it runs in."""
    text = _text()
    recipes = re.findall(r"^\t(?:@)?(uv run[^\n]*)", text, re.MULTILINE)

    release_steps = (
        "cli/normalize/messages.py",
        "cli/datasets/generate.py",
        "cli/maintenance/annotation_backfill.py",
        "cli/datasets/build.py",
        "cli/datasets/export.py",
        "publish_latest.py",
    )

    for step in release_steps:
        matching = [r for r in recipes if step in r]
        assert matching, f"no recipe found invoking {step}"
        for recipe in matching:
            if "--dry-run" in recipe:
                continue  # dry-run targets are developer tools, not release steps
            assert "--no-sync" in recipe, (
                f"release step '{step}' runs `uv run` without --no-sync; in the "
                f"release image that re-syncs to the default groups and removes "
                f"the release group the later steps depend on"
            )
