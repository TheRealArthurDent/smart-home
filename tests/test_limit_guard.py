"""deploy.yaml targets all hosts, so it must refuse to run without a --limit to exactly one host."""

import subprocess
from pathlib import Path

import pytest
import yaml

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
PLAYBOOK = "deploy.yaml"


def run_playbook(*args):
    return subprocess.run(
        ["ansible-playbook", PLAYBOOK, *args],
        cwd=ANSIBLE_DIR,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_main_play_targets_all_hosts():
    plays = yaml.safe_load((ANSIBLE_DIR / PLAYBOOK).read_text())
    assert plays[-1]["hosts"] == "all"


def test_refuses_to_run_without_limit():
    result = run_playbook()
    assert result.returncode != 0
    assert "Run with --limit <host>" in result.stdout
    # The guard fails before any real host is contacted.
    assert "raspi" not in result.stdout
    assert "testbed" not in result.stdout


@pytest.mark.parametrize("limit", ["all", "*", "testbed,raspi", "testbed:raspi"])
def test_refuses_a_limit_that_matches_several_hosts(limit):
    # With any --limit, the localhost guard play matches no host and is skipped, so a limit that selects every
    # host would otherwise run straight against production too.
    result = run_playbook("--limit", limit)
    assert result.returncode != 0
    assert "Run with --limit <one host>" in result.stdout
    plays = yaml.safe_load((ANSIBLE_DIR / PLAYBOOK).read_text())
    assert f"PLAY [{plays[-1]['name']}]" not in result.stdout


def test_limit_selects_only_that_host():
    result = run_playbook("--limit", "testbed", "--list-hosts")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "testbed" in result.stdout
    assert "raspi" not in result.stdout
