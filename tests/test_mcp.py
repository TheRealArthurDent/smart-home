"""Home Assistant's MCP server for Claude Code (#2), project-scoped so it only loads in this repo.

One entry per instance. The tokens, URLs and the root CA come from environment variables on the dev machine, never
from this file; the server version is pinned and updated by Renovate.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTANCES = ("testbench", "raspi")


def servers():
    return json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]


def test_one_server_per_home_assistant_instance():
    assert sorted(servers()) == sorted(f"ha-{instance}" for instance in INSTANCES)


def test_tokens_urls_and_ca_come_from_the_environment():
    for instance in INSTANCES:
        env = servers()[f"ha-{instance}"]["env"]
        prefix = f"HA_{instance.upper()}"
        assert env == {
            "HOMEASSISTANT_URL": f"${{{prefix}_URL}}",
            "HOMEASSISTANT_TOKEN": f"${{{prefix}_TOKEN}}",
            "SSL_CERT_FILE": "${HA_CA_FILE}",
        }


def test_the_server_version_is_pinned():
    for server in servers().values():
        assert server["command"] == "uvx"
        assert re.fullmatch(r"ha-mcp==\d+\.\d+\.\d+", server["args"][0])
    assert len({tuple(server["args"]) for server in servers().values()}) == 1


def test_renovate_updates_the_pinned_version():
    config = json.loads((ROOT / "renovate.json").read_text())
    managers = [m for m in config.get("customManagers", [])
                if any(re.search(pattern.strip("/"), ".mcp.json") for pattern in m.get("managerFilePatterns", []))]
    assert len(managers) == 1
    manager = managers[0]
    assert manager["datasourceTemplate"] == "pypi"
    version = servers()["ha-testbench"]["args"][0].split("==")[1]
    pattern = manager["matchStrings"][0].replace("(?<", "(?P<")
    match = re.search(pattern, (ROOT / ".mcp.json").read_text())
    assert match and match.group("depName") == "ha-mcp" and match.group("currentValue") == version
