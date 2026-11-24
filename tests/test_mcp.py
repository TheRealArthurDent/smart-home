"""Home Assistant's MCP server for Claude Code (#2), project-scoped so it only loads in this repo.

Claude Code starts ha-mcp on demand as a Docker container per Home Assistant instance and talks to it over stdio.
URLs, tokens and the root CA come from environment variables on the dev machine, never from this repo; the token
reaches the container through the environment, not the command line. The image is pinned and updated by Renovate.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTANCES = ("testbench", "raspi")
IMAGE = re.compile(r"ghcr\.io/homeassistant-ai/ha-mcp:\d+\.\d+\.\d+")


def servers():
    return json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]


def option_values(args, option):
    """Values of a docker run option given as `--opt value`."""
    return [args[i + 1] for i, arg in enumerate(args) if arg == option]


def test_one_server_per_home_assistant_instance():
    assert sorted(servers()) == sorted(f"ha-{instance}" for instance in INSTANCES)


def test_claude_code_starts_a_throwaway_container_with_the_pinned_image():
    images = set()
    for server in servers().values():
        assert server["type"] == "stdio"
        assert server["command"] == "docker"
        args = server["args"]
        assert args[:4] == ["run", "--rm", "-i", "--pull=missing"]
        images |= {arg for arg in args if IMAGE.fullmatch(arg)}
        assert IMAGE.fullmatch(args[-1]), "the image comes last, so ha-mcp's default command (stdio) runs"
    assert len(images) == 1


def test_tokens_urls_and_ca_come_from_the_environment():
    for instance in INSTANCES:
        server = servers()[f"ha-{instance}"]
        prefix = f"HA_{instance.upper()}"
        assert server["env"] == {
            "HOMEASSISTANT_URL": f"${{{prefix}_URL}}",
            "HOMEASSISTANT_TOKEN": f"${{{prefix}_TOKEN}}",
        }
        args = server["args"]
        # Passed by name only: the values stay out of the command line (ps, logs)
        assert sorted(option_values(args, "-e")) == sorted(
            ["HOMEASSISTANT_URL", "HOMEASSISTANT_TOKEN", "SSL_CERT_FILE=/etc/ha-mcp/root-ca.pem"])
        assert "${HA_CA_FILE}:/etc/ha-mcp/root-ca.pem:ro" in option_values(args, "-v")
        assert "TOKEN}" not in " ".join(args)


def test_the_containers_are_hardened():
    for name, server in servers().items():
        args = server["args"]
        for flag in ("--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true"):
            assert flag in args, name
        assert "/tmp" in option_values(args, "--tmpfs"), name
        # ha-mcp keeps its settings and backups in ~/.ha-mcp
        assert f"{name.replace('ha-', 'ha-mcp-')}:/home/mcpuser/.ha-mcp" in option_values(args, "-v"), name


def test_renovate_updates_the_pinned_image():
    config = json.loads((ROOT / "renovate.json").read_text())
    managers = [m for m in config.get("customManagers", [])
                if any(re.search(pattern.strip("/"), ".mcp.json") for pattern in m.get("managerFilePatterns", []))]
    assert len(managers) == 1
    manager = managers[0]
    assert manager["datasourceTemplate"] == "docker"
    pattern = manager["matchStrings"][0].replace("(?<", "(?P<")
    matches = list(re.finditer(pattern, (ROOT / ".mcp.json").read_text()))
    assert len(matches) == len(INSTANCES)
    image = servers()["ha-testbench"]["args"][-1]
    for match in matches:
        assert f"{match.group('depName')}:{match.group('currentValue')}" == image
