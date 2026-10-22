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


def test_restart_handlers_skip_a_compose_project_check_mode_has_not_written():
    """In --check, a first Ansible run doesn't create the compose dir, and Compose fails on a missing project_src.
    The handlers need the same guard as the "Ensure the stack is up" task (the container part can't run in Molecule)."""
    role = ROOT / "ansible" / "roles" / "smart_home"
    guard = "not (ansible_check_mode and smart_home_compose_file is changed)"
    tasks = yaml.safe_load((role / "tasks" / "main.yaml").read_text())
    compose_up = next(
        task for block in tasks for task in block.get("block", []) if task.get("name") == "Ensure the stack is up"
    )
    assert compose_up["when"] == guard
    for handler in yaml.safe_load((role / "handlers" / "main.yaml").read_text()):
        assert guard in handler["when"], handler["name"]


def test_mosquitto_keeps_its_data_in_a_named_volume():
    """Only the config comes from the host. The data lives in a volume, which restic backs up (/opt it doesn't), and
    the log goes to stderr (no log_dest in mosquitto.conf), so there's no host user or directory to manage."""
    mounts = service("mosquitto")["volumes"]
    assert mounts == ["/etc/docker/smart-home/mosquitto:/mosquitto/config:ro", "mosquitto-storage:/mosquitto/data"]
    compose = yaml.safe_load((ROOT / "docker-compose.yaml").read_text())
    assert "mosquitto-storage" in compose["volumes"]
    assert "log_dest" not in (ROOT / "setup" / "mosquitto" / "mosquitto.conf").read_text()


def test_grafana_provisioning_needs_no_secret_files():
    """Telegram is gone (#7): nothing reads files from /etc/secrets, so Grafana doesn't mount it either."""
    provisioning = ROOT / "grafana-provisioning"
    readers = [p.name for p in provisioning.rglob("*.yaml") if "$__file{" in p.read_text()]
    assert readers == []
    assert not any("/etc/secrets" in mount for mount in service("grafana")["volumes"])


def test_compose_up_fails_on_containers_that_dont_come_up():
    """Without wait, `compose up` reports changed while a container crash-loops (Grafana on testbed)."""
    tasks = yaml.safe_load((ROOT / "ansible" / "roles" / "smart_home" / "tasks" / "main.yaml").read_text())
    compose_up = next(
        task for block in tasks for task in block.get("block", []) if task.get("name") == "Ensure the stack is up"
    )
    assert compose_up["community.docker.docker_compose_v2"]["wait"] is True
