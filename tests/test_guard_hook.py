"""The Claude Code PreToolUse hook (.claude/hooks/guard.py) blocks risky tool calls and lets everyday work through."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "guard.py"
SETTINGS = HOOK.parent.parent / "settings.json"


def run_hook(tool_name, tool_input):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, "-I", str(HOOK)], input=json.dumps(event), capture_output=True, text=True, check=False
    )


BLOCKED_COMMANDS = [
    # Production (raspi): deploy.sh defaults to it
    "ssh -p 1357 smarthome@192.168.1.2",
    "ssh smarthome@raspi -p 1357 'docker ps'",
    "scp install.tar smarthome@raspi:dev/smart-home",
    "rsync -a setup/ smarthome@192.168.1.2:dev/smart-home/setup/",
    "cd ansible && ansible-playbook deploy.yaml --limit raspi",
    "ansible-playbook deploy.yaml -l raspi --check",
    "ansible-playbook deploy.yaml --limit=all",
    "ansible-playbook deploy.yaml --limit 'testbed,raspi'",
    "cd ansible && ../.venv/bin/ansible-playbook deploy.yaml",
    "ansible raspi -m ping",
    # main branch
    "git push origin main",
    "git push origin HEAD:main",
    "git push --force origin feat/x",
    "git push -f origin claude/x",
    "git push --mirror",
    # Secrets
    "git add -f setup/.env",
    "git add setup/.env",
    "git add -Af setup/",
    "git commit -m wip setup/.env",
    "cat setup/.env",
    "grep PASSWORD setup/.env",
    "sudo cat /etc/docker/smart-home/.env",
    # The guardrails themselves
    "sed -i s/x/y/ .claude/settings.json",
    "rm .claude/hooks/guard.py",
    "echo '{}' > .claude/settings.local.json",
]

ALLOWED_COMMANDS = [
    "cd ansible && ansible-playbook deploy.yaml --limit testbed --check --diff",
    "cd ansible && ../.venv/bin/molecule test",
    "cd ansible && ../.venv/bin/ansible-lint --strict",
    "pytest tests/test_limit_guard.py",
    "ssh -p 4242 testuser@192.168.1.7",
    "cat deploy.sh",
    "grep -n raspi deploy.sh docker-compose.yaml",
    "git diff main -- deploy.sh setup/setup.sh",
    "git commit -m 'fix: raspi grafana links'",
    "git add setup/.env.example",
    "cat setup/.env.example",
    "git push -u origin claude/project-thread-v1246k",
    "git push --force-with-lease origin claude/x",
    "rm -f /tmp/x && git push origin claude/x",
    "git add -A && git commit -q -F msg.txt && git push -u origin claude/project-thread-v1246k",
    ".venv/bin/pytest tests",
    "docker compose config --quiet",
    "cat .claude/settings.json",
    "git diff main -- .claude/hooks/guard.py",
]


def assert_blocked(result):
    # Exit code 2 alone isn't proof: Python also exits 2 when the script is missing.
    assert result.returncode == 2, result.stderr
    assert "Blocked by" in result.stderr


@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
def test_blocks_risky_command(command):
    assert_blocked(run_hook("Bash", {"command": command}))


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
def test_allows_everyday_command(command):
    result = run_hook("Bash", {"command": command})
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "/repo/.claude/settings.json",
        "/repo/.claude/settings.local.json",
        "/repo/.claude/hooks/guard.py",
        "/repo/setup/.env",
        "/home/mika/Passwords.kdbx",
    ],
)
@pytest.mark.parametrize("tool", ["Edit", "Write"])
def test_blocks_editing_guardrails_and_secret_files(tool, path):
    assert_blocked(run_hook(tool, {"file_path": path}))


@pytest.mark.parametrize(
    "path", ["/repo/.claude/skills/working-with-the-stack/SKILL.md", "/repo/CLAUDE.md", "/repo/setup/.env.example"]
)
def test_allows_editing_other_files(path):
    assert run_hook("Edit", {"file_path": path}).returncode == 0


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("mcp__github__push_files", {"branch": "main"}),
        ("mcp__github__create_or_update_file", {"branch": "main"}),
        ("mcp__github__delete_file", {"branch": "refs/heads/main"}),
        ("mcp__github__merge_pull_request", {"pullNumber": 1}),
        ("mcp__github__enable_pr_auto_merge", {"pullNumber": 1}),
    ],
)
def test_blocks_github_writes_to_main_and_merges(tool, tool_input):
    assert_blocked(run_hook(tool, tool_input))


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("mcp__github__push_files", {"branch": "claude/x"}),
        ("mcp__github__create_pull_request", {"base": "main"}),
    ],
)
def test_allows_github_feature_branch_work(tool, tool_input):
    assert run_hook(tool, tool_input).returncode == 0


def test_settings_route_all_guarded_tools_through_the_hook():
    settings = json.loads(SETTINGS.read_text())
    matchers = [entry["matcher"] for entry in settings["hooks"]["PreToolUse"]]
    for tool in ["Bash", "Edit", "Write", "mcp__github__push_files", "mcp__github__merge_pull_request"]:
        assert any(re.fullmatch(m, tool) for m in matchers), tool


def test_settings_deny_reading_secrets():
    deny = json.loads(SETTINGS.read_text())["permissions"]["deny"]
    for rule in ["Read(**/.env)", "Read(**/*.kdbx)"]:
        assert rule in deny
