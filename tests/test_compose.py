"""docker-compose.yaml passes the secrets to the containers that need them, instead of setup.sh writing them into
config files (#7)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def service(name):
    return yaml.safe_load((ROOT / "docker-compose.yaml").read_text())["services"][name]


def test_telegraf_gets_its_passwords_from_the_env_file():
    """telegraf.conf references $INFLUXDB_WRITE_PASSWORD and $MOSQUITTO_PASSWD; Telegraf resolves them itself."""
    config = (ROOT / "setup" / "telegraf" / "telegraf.conf").read_text()
    referenced = set(re.findall(r'^\s*password = "\$(\w+)"', config, re.MULTILINE))
    assert referenced == {"INFLUXDB_WRITE_PASSWORD", "MOSQUITTO_PASSWD"}
    environment = service("telegraf").get("environment", [])
    assert sorted(environment) == sorted(f"{var}=${{{var}}}" for var in referenced)
