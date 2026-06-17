"""Tests for scripts/check_docs_only.py (S5U-1233).

`check_docs_only.py` is the SAFETY-GATE classifier that lets the two
rendering-dependent CI jobs (`web / test`, `visual-regression / visual`)
short-circuit their expensive steps to a GREEN result on a docs-only PR. A
fail-OPEN classifier would let a code-bearing PR skip a required check, so the
classifier is conservative (inverted Rule G2: docs-only ⇔ every changed file is
`*.md`) and fail-closed (Rule G1: indeterminate diff → docs_only=false → full
run). It also ALWAYS exits 0 so it can never fail the calling required job.

These tests pin the classifier semantics, the `$GITHUB_OUTPUT` contract, the
fail-closed `main()` behavior on an indeterminate diff, and the workflow
structure (detector step present + heavy steps gated, no rename, no `paths:`).

Red-before per test (form-(b) local-run excerpt, guard logic; mutations never
committed):
- `classify_docs_only` tests: temporarily flipping the function to
  `return bool(changed_files)` (drop the all-`.md` requirement) made the
  failure/mixed/non-md/empty cases go RED ("assert True == False" / "assert
  False == True"); reverted.
- `main()` indeterminate test: temporarily re-raising the SystemExit (removing
  the `except SystemExit` funnel) made the test go RED (SystemExit escaped /
  output never written); reverted.
- workflow-structure tests: temporarily deleting the `if:` line on the heavy
  step / renaming the `test`/`visual` job made the corresponding assertion go
  RED; reverted.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPT_DIR / "check_docs_only.py"
WORKFLOWS = REPO / ".github" / "workflows"

_HEAVY_GATE = "github.event_name != 'pull_request' || steps.docs_only.outputs.docs_only != 'true'"


@pytest.fixture()
def mod(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """Import scripts/check_docs_only.py as a fresh module per test."""
    monkeypatch.syspath_prepend(str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("check_docs_only", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    sys.modules["check_docs_only"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("check_docs_only", None)


# --- git-repo helpers (mirrors test_git_baseline.py) --------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("repo\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial")


def _commit_file(repo: Path, rel: str, contents: str, *, message: str) -> None:
    full = repo / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(contents)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", message)


# --- classify_docs_only -------------------------------------------------------


def test_classify_happy_md_only_is_docs(mod: ModuleType) -> None:
    """Happy-path: a change set of only *.md files is docs-only."""
    assert mod.classify_docs_only(["docs/a.md", "CLAUDE.md", ".claude/rules/x.md"]) is True


def test_classify_failure_code_file_is_not_docs(mod: ModuleType) -> None:
    """Failure input: a code file (.tsx) flips the verdict to NOT docs-only."""
    assert mod.classify_docs_only(["apps/web/src/App.tsx"]) is False


def test_classify_mixed_md_plus_code_is_not_docs(mod: ModuleType) -> None:
    """Adversarial MIXED: a doc smuggled alongside code is NOT docs-only.

    Requires EVERY file to be *.md; the one .tsx forces a full run.
    """
    assert mod.classify_docs_only(["docs/a.md", "apps/web/src/App.tsx"]) is False


@pytest.mark.parametrize(
    "path",
    [
        "apps/web/src/styles/x.css",
        "apps/web/tests/e2e/__snapshots__/page.png",  # visual baseline
        "apps/web/package.json",
        "pnpm-lock.yaml",
        ".github/workflows/web-tests.yml",
        "configs/x.toml",
        "scripts/foo.py",
        "apps/web/src/main.ts",
        "build.mjs",
        "app.js",
        "README",  # no extension
        "notes.markdown",  # NOT in the .md allowlist (conservative)
    ],
)
def test_classify_non_md_siblings_are_not_docs(mod: ModuleType, path: str) -> None:
    """Every HARD-REQUIREMENT non-docs file type forces a full run.

    Each row exercises the SAME branch (the `all(...)` short-circuits False on a
    non-`.md` file) as existing rows — fixture/data extension on an existing
    branch, no new branch coverage. Per .claude/rules/hooks.md parametrize
    carve-out, no per-row red-before needed.
    """
    assert mod.classify_docs_only([path]) is False


def test_classify_empty_change_set_is_not_docs(mod: ModuleType) -> None:
    """An empty change set is NOT docs-only (no licence to skip on zero files)."""
    assert mod.classify_docs_only([]) is False


def test_classify_md_extension_is_case_insensitive(mod: ModuleType) -> None:
    """`.MD` counts as docs (case-insensitive suffix)."""
    assert mod.classify_docs_only(["a.MD", "B.Md"]) is True


def test_is_docs_file_boundaries(mod: ModuleType) -> None:
    """`is_docs_file` matches only the `.md` suffix, case-insensitively."""
    assert mod.is_docs_file("x.md") is True
    assert mod.is_docs_file("x.MD") is True
    assert mod.is_docs_file("x.markdown") is False
    assert mod.is_docs_file("md") is False  # bare 'md', no extension
    assert mod.is_docs_file("a/b/c.md") is True


# --- main(): $GITHUB_OUTPUT contract + real-repo end-to-end -------------------


def test_main_docs_only_writes_true_output(
    mod: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end happy: a real docs-only diff emits docs_only=true and exits 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "docs/guide.md", "doc\n", message="docs change")
    gh_out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.chdir(repo)
    rc = mod.main(["--base", "HEAD~1", "--head", "HEAD"])
    assert rc == 0
    assert "docs_only=true" in gh_out.read_text(encoding="utf-8")


def test_main_code_change_writes_false_output(
    mod: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end failure: a real code diff emits docs_only=false and exits 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "src/app.py", "print(1)\n", message="code change")
    gh_out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.chdir(repo)
    rc = mod.main(["--base", "HEAD~1", "--head", "HEAD"])
    assert rc == 0
    assert "docs_only=false" in gh_out.read_text(encoding="utf-8")


def test_main_unresolvable_base_fails_closed_to_false(
    mod: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indeterminate (Rule G1): an unresolvable base ref must yield docs_only=false
    and exit 0 — NEVER a docs-only green on an unknown diff, and NEVER a crash
    that fails the required job."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    gh_out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.chdir(repo)
    rc = mod.main(["--base", "origin/definitely-not-a-branch", "--head", "HEAD"])
    assert rc == 0
    assert "docs_only=false" in gh_out.read_text(encoding="utf-8")


def test_main_shallow_checkout_fails_closed_to_false(
    mod: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indeterminate (Rule G1 required shallow scenario): a depth-1 clone whose
    base tip is unfetched yields docs_only=false + exit 0 (full run)."""
    upstream = tmp_path / "upstream"
    _init_repo(upstream)
    _commit_file(upstream, "a.txt", "1\n", message="c1")
    _commit_file(upstream, "docs/b.md", "d\n", message="c2")
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth=1", f"file://{upstream}", str(shallow)],
        check=True,
        capture_output=True,
    )
    gh_out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.chdir(shallow)
    rc = mod.main(["--base", "HEAD~1", "--head", "HEAD"])
    assert rc == 0
    assert "docs_only=false" in gh_out.read_text(encoding="utf-8")


def test_main_diff_subprocess_failure_fails_closed_to_false(
    mod: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indeterminate (Rule G1): if get_changed_files raises SystemExit (both git
    diff tiers failed), main() funnels to docs_only=false + exit 0."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    gh_out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.chdir(repo)

    def _boom(*_a: object, **_k: object) -> list[str]:
        raise SystemExit("ERROR: git diff failed for both ...")

    monkeypatch.setattr(mod, "get_changed_files", _boom)
    rc = mod.main(["--base", "HEAD", "--head", "HEAD"])
    assert rc == 0
    assert "docs_only=false" in gh_out.read_text(encoding="utf-8")


# --- workflow structure: detector wired + heavy steps gated, no rename --------


def _load_workflow(name: str) -> dict[str, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _job(workflow: dict[str, Any], job_id: str) -> dict[str, Any]:
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs[job_id]
    assert isinstance(job, dict)
    return job


@pytest.mark.parametrize(
    ("workflow_name", "job_id", "heavy_step_names"),
    [
        ("web-tests.yml", "test", ["Test", "Lint", "Typecheck", "Install dependencies"]),
        (
            "visual-regression.yml",
            "visual",
            ["Build", "Install Playwright browsers", "Run e2e and visual regression tests"],
        ),
    ],
)
def test_workflow_detector_present_and_heavy_steps_gated(
    workflow_name: str, job_id: str, heavy_step_names: list[str]
) -> None:
    """Each rendering job carries the docs-only detector step and gates its heavy
    steps on the detector output. This is a structural pin: dropping the gate or
    the detector should fail here.

    Carve-out: fixture/data extension across two workflow files on the SAME
    branch (the assertion shape is identical per row) — no per-row red-before.
    """
    wf = _load_workflow(workflow_name)
    job = _job(wf, job_id)
    steps = job["steps"]
    assert isinstance(steps, list)

    # Detector step present, PR-only, with the expected id.
    detector = [s for s in steps if isinstance(s, dict) and s.get("id") == "docs_only"]
    assert len(detector) == 1, f"{workflow_name}:{job_id} missing single docs_only detector step"
    assert detector[0].get("if") == "github.event_name == 'pull_request'"
    assert "check_docs_only.py" in str(detector[0].get("run", ""))

    # Each named heavy step is gated on the detector output.
    by_name = {s.get("name"): s for s in steps if isinstance(s, dict)}
    for heavy in heavy_step_names:
        assert heavy in by_name, f"{workflow_name}:{job_id} missing step {heavy!r}"
        assert by_name[heavy].get("if") == _HEAVY_GATE, (
            f"{workflow_name}:{job_id} step {heavy!r} not gated on docs_only output"
        )


@pytest.mark.parametrize("workflow_name", ["web-tests.yml", "visual-regression.yml"])
def test_workflow_has_no_path_filters(workflow_name: str) -> None:
    """No `paths:`/`paths-ignore:` trigger filters — those would leave the
    required context PENDING and permanently block merge (HARD REQUIREMENT #1).

    Carve-out: fixture/data extension on the same branch — no per-row red-before.
    """
    raw = (WORKFLOWS / workflow_name).read_text(encoding="utf-8")
    wf = yaml.safe_load(raw)
    assert isinstance(wf, dict)
    # The `on:` key parses to boolean True under YAML 1.1; handle both.
    on_block = wf.get("on", wf.get(True))
    text = yaml.safe_dump(on_block)
    assert "paths:" not in text and "paths-ignore:" not in text


def test_required_context_jobs_not_renamed() -> None:
    """The job IDs (web-tests.yml:test, visual-regression.yml:visual) and the
    absence of a `name:` override are the required-context-name invariant. A
    rename changes the branch-protection context string → merge blocked
    (HARD REQUIREMENT #5).

    Red-before: N/A — characterization test pins an existing invariant; the
    diff adds steps but must not rename these jobs. Reviewer cross-checks diff.
    """
    web = _load_workflow("web-tests.yml")
    assert "test" in web["jobs"]
    assert "name" not in _job(web, "test"), "web 'test' job must not add a name: (context drift)"

    vis = _load_workflow("visual-regression.yml")
    assert "visual" in vis["jobs"]
    assert "name" not in _job(vis, "visual"), "visual job must not add a name: (context drift)"
