"""Home Assistant's MCP server for Claude Code (#2), project-scoped so it only loads in this repo.

ha-mcp runs on the dev machine as one Docker container per Home Assistant instance (tools/ha-mcp/), serving
streamable HTTP on loopback only; .mcp.json points Claude Code at them. URLs, tokens and the root CA come from a
git-ignored env file next to the compose file, never from a tracked file; the image is pinned and updated by Renovate.
"""

import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL_DIR = ROOT / "tools" / "ha-mcp"
INSTANCES = ("testbench", "raspi")
ENV_KEYS = ["HA_TESTBENCH_URL", "HA_TESTBENCH_TOKEN", "HA_RASPI_URL", "HA_RASPI_TOKEN", "HA_CA_FILE"]


def servers():
    return json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]


def services():
    return yaml.safe_load((TOOL_DIR / "docker-compose.yaml").read_text())["services"]


def test_one_server_per_home_assistant_instance():
    assert sorted(servers()) == sorted(f"ha-{instance}" for instance in INSTANCES)
    assert sorted(services()) == sorted(f"ha-mcp-{instance}" for instance in INSTANCES)


def test_claude_code_reaches_each_container_on_loopback():
    for instance in INSTANCES:
        server = servers()[f"ha-{instance}"]
        assert server["type"] == "http"
        match = re.fullmatch(r"http://127\.0\.0\.1:(\d+)/mcp", server["url"])
        assert match, server["url"]
        assert services()[f"ha-mcp-{instance}"]["ports"] == [f"127.0.0.1:{match.group(1)}:8086"]
        assert "env" not in server and "headers" not in server


def test_the_containers_serve_http_with_the_pinned_image():
    images = {service["image"] for service in services().values()}
    assert len(images) == 1
    assert re.fullmatch(r"ghcr\.io/homeassistant-ai/ha-mcp:\d+\.\d+\.\d+", images.pop())
    for service in services().values():
        assert service["command"] == ["ha-mcp-web"]


def test_tokens_urls_and_ca_come_from_the_git_ignored_env_file():
    for instance in INSTANCES:
        service = services()[f"ha-mcp-{instance}"]
        prefix = f"HA_{instance.upper()}"
        env = service["environment"]
        assert env["HOMEASSISTANT_URL"].startswith(f"${{{prefix}_URL:?")
        assert env["HOMEASSISTANT_TOKEN"].startswith(f"${{{prefix}_TOKEN:?")
        ca = env["SSL_CERT_FILE"]
        assert any(volume.startswith("${HA_CA_FILE:?") and volume.endswith(f":{ca}:ro")
                   for volume in service["volumes"])
    entries = [line for line in (TOOL_DIR / ".env.example").read_text().splitlines()
               if line and not line.startswith("#")]
    assert sorted(entries) == sorted(f"{key}=" for key in ENV_KEYS)
    env_file = (TOOL_DIR / ".env").relative_to(ROOT)
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "-q", str(env_file)], cwd=ROOT, check=False)
    assert ignored.returncode == 0


def test_the_containers_are_hardened():
    for name, service in services().items():
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in service["security_opt"], name
        assert service["restart"] == "unless-stopped", name
        # ha-mcp keeps its settings and backups in ~/.ha-mcp
        assert any(volume.endswith(":/home/mcpuser/.ha-mcp") for volume in service["volumes"]), name
