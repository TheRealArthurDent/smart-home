"""Renovate groups the Ansible dev tools, which are usually released together."""
import json
import re
from pathlib import Path

REPO_DIR = Path(__file__).parents[1]
DEV_TOOLS = ("ansible-lint", "molecule", "molecule-plugins")


def requirement_names():
    for line in (REPO_DIR / "requirements.txt").read_text().splitlines():
        match = re.match(r"([A-Za-z0-9_.-]+)", line.strip())
        if match and not line.lstrip().startswith("#"):
            yield match.group(1)


def group_of(package):
    config = json.loads((REPO_DIR / "renovate.json").read_text())
    groups = [
        rule["groupName"]
        for rule in config.get("packageRules", [])
        if "groupName" in rule and package in rule.get("matchPackageNames", [])
    ]
    return groups[-1] if groups else None


def test_requirements_pin_the_dev_tools():
    assert set(DEV_TOOLS) <= set(requirement_names())


def test_renovate_updates_the_dev_tools_in_one_group():
    groups = {package: group_of(package) for package in DEV_TOOLS}
    assert None not in groups.values(), groups
    assert len(set(groups.values())) == 1, groups
