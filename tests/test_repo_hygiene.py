""".env files are never committed, and the git hooks catch secrets and commits to main before they leave the machine."""

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def test_env_example_holds_no_values():
    """setup/.env.example documents the keys; the values come from KeePass via raspberry's secrets role."""
    lines = (ROOT / "setup" / ".env.example").read_text().splitlines()
    entries = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
    assert entries, "setup/.env.example lists no keys"
    assert [line for line in entries if not re.fullmatch(r"[A-Z0-9_]+=", line)] == []


def test_no_env_file_is_tracked():
    tracked = git("ls-files").stdout.splitlines()
    env_files = [f for f in tracked if Path(f).name == ".env" or f.endswith(".env")]
    assert env_files == []


def test_env_files_are_ignored():
    for path in ("setup/.env", ".env"):
        assert git("check-ignore", "--no-index", "-q", path).returncode == 0, f"{path} is not git-ignored"


def pre_commit_hook_ids():
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}


def test_pre_commit_scans_for_secrets():
    hooks = pre_commit_hook_ids()
    assert "gitleaks" in hooks
    assert "detect-private-key" in hooks


def test_pre_commit_refuses_commits_on_main():
    hook = pre_commit_hook_ids().get("no-commit-to-branch")
    assert hook is not None
    assert hook.get("args") == ["--branch", "main"]


def test_pre_commit_is_installed_with_the_tooling():
    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    assert any(line.startswith("pre-commit==") for line in requirements)


def test_workflows_use_no_repository_secrets():
    """Workflows get by with GITHUB_TOKEN and hold no other secrets, so forks and Renovate PRs can run them."""
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    offenders = [
        f"{workflow.name}: {secret}"
        for workflow in workflows
        for secret in re.findall(r"secrets\.(\w+)", workflow.read_text())
        if secret != "GITHUB_TOKEN"
    ]
    assert offenders == []
