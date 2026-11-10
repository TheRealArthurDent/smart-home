"""The role reads MOSQUITTO_PASSWD from the .env file the way Compose does, so Mosquitto's password file and the
containers that get the password from Compose agree.

infrastructure's secrets role writes each value double-quoted with `\\`, `"` and `$` escaped (its compose_env
filter), because Compose interpolates unquoted values. Older files hold the value unquoted.
"""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "ansible" / "roles" / "smart_home" / "filter_plugins" / "compose.py"

HOSTILE = [
    "plain",
    "a$XXX b ${Y} $$ end$",
    "it's \"quoted\"",
    "back\\slash \\n \\$ end\\",
    "hash #comment",
    " lead and trail ",
    "{{ 7 * 7 }}",
    "ümlaut € 🔑",
]


def filters():
    spec = importlib.util.spec_from_file_location("compose_filter", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FilterModule().filters()


def written_by_infrastructure(value):
    """infrastructure's compose_env filter (roles/secrets/filter_plugins/compose_env.py there)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


@pytest.mark.parametrize("value", HOSTILE)
def test_reads_a_quoted_value_back(value):
    assert filters()["compose_env_value"](written_by_infrastructure(value)) == value


def test_reads_an_unquoted_value_of_an_older_file_as_it_is():
    assert filters()["compose_env_value"]("LEAKCANARY-mosquitto") == "LEAKCANARY-mosquitto"


def test_reads_a_single_quoted_value_literally():
    assert filters()["compose_env_value"]("'a\\b$c'") == "a\\b$c"


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker compose CLI")
@pytest.mark.parametrize("value", HOSTILE)
def test_agrees_with_compose(tmp_path, value):
    line = written_by_infrastructure(value)
    (tmp_path / "x.env").write_text(f"MOSQUITTO_PASSWD={line}\n")
    (tmp_path / "compose.yaml").write_text("services:\n  a:\n    image: busybox:1.36\n    env_file: [x.env]\n")
    config = subprocess.run(
        ["docker", "compose", "config", "--format", "json"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    from_compose = json.loads(config.stdout)["services"]["a"]["environment"]["MOSQUITTO_PASSWD"].replace("$$", "$")
    assert filters()["compose_env_value"](line) == from_compose
