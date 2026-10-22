"""Containers stopped by hand stay stopped, and containers the role doesn't manage get a warning.

The role reads the project's containers before `compose up` (tasks/container_states.yaml). An existing but
exited container was stopped by hand: `restart: unless-stopped` restarts every other exit. The role leaves those
services out of `compose up` and out of the restart handlers, and warns about them. A container of the project
whose service isn't in the compose file anymore, or is disabled for the host, also gets a warning.

These tests feed container_states.yaml the output docker_host_info would return, so they need no Docker.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROLES_DIR = Path(__file__).resolve().parents[1] / "ansible" / "roles"
SERVICES = ["influxdb", "telegraf", "grafana", "mosquitto", "deconz"]


def container(service, state, name=None):
    """A container as docker_host_info lists it with verbose_output."""
    return {
        "Names": [f"/{name or service}"],
        "State": state,
        "Labels": {"com.docker.compose.project": "smart-home", "com.docker.compose.service": service},
    }


def run(tmp_path, containers, disabled=()):
    play = [
        {
            "name": "Container states",
            "hosts": "localhost",
            "gather_facts": False,
            "vars": {
                "smart_home_services": SERVICES,
                "smart_home_disabled_services": list(disabled),
                "smart_home_host_info": {"containers": containers},
            },
            "tasks": [
                {
                    "name": "Evaluate the container states",
                    "ansible.builtin.include_role": {"name": "smart_home", "tasks_from": "container_states"},
                },
                {
                    "name": "Report",
                    "ansible.builtin.copy": {
                        "content": "{{ {'up': smart_home_up_services} | to_json }}",
                        "dest": str(tmp_path / "facts.json"),
                        "mode": "0600",
                    },
                },
            ],
        }
    ]
    playbook = tmp_path / "play.yaml"
    playbook.write_text(yaml.safe_dump(play, sort_keys=False))
    result = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
        env={**os.environ, "ANSIBLE_ROLES_PATH": str(ROLES_DIR), "ANSIBLE_NOCOLOR": "1", "ANSIBLE_PYTHON_INTERPRETER": "auto_silent"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    facts = json.loads((tmp_path / "facts.json").read_text())
    warnings = [line for line in (result.stdout + result.stderr).splitlines() if "[WARNING]" in line]
    return facts["up"], warnings


def test_first_deployment_brings_up_every_service(tmp_path):
    up, warnings = run(tmp_path, [])
    assert up == SERVICES
    assert not warnings


def test_running_containers_stay_managed(tmp_path):
    up, warnings = run(tmp_path, [container(s, "running") for s in SERVICES])
    assert up == SERVICES
    assert not warnings


def test_a_stopped_container_is_left_alone_with_a_warning(tmp_path):
    containers = [container(s, "running") for s in SERVICES if s != "mosquitto"]
    containers.append(container("mosquitto", "exited", name="mqtt"))
    up, warnings = run(tmp_path, containers)
    assert "mosquitto" not in up
    assert up == [s for s in SERVICES if s != "mosquitto"]
    assert len(warnings) == 1
    assert "stopped" in warnings[0] and "mqtt" in warnings[0]


def test_every_stopped_container_is_named(tmp_path):
    containers = [container(s, "exited" if s in ("telegraf", "grafana") else "running") for s in SERVICES]
    up, warnings = run(tmp_path, containers)
    assert up == ["influxdb", "mosquitto", "deconz"]
    assert len(warnings) == 1
    assert "telegraf" in warnings[0] and "grafana" in warnings[0]


@pytest.mark.parametrize("state", ["created", "restarting"])
def test_a_container_that_is_not_stopped_by_hand_stays_managed(tmp_path, state):
    # "created": Compose couldn't start it, so it should try again. "restarting": Docker is on it.
    up, warnings = run(tmp_path, [container("grafana", state)])
    assert "grafana" in up
    assert not warnings


def test_all_containers_stopped_brings_up_nothing(tmp_path):
    # An empty services list would make Compose bring up every service.
    up, warnings = run(tmp_path, [container(s, "exited") for s in SERVICES])
    assert up == []
    assert len(warnings) == 1


def test_a_container_of_a_removed_service_gets_a_warning(tmp_path):
    containers = [container(s, "running") for s in SERVICES] + [container("node-red", "running")]
    up, warnings = run(tmp_path, containers)
    assert up == SERVICES
    assert len(warnings) == 1
    assert "node-red" in warnings[0] and "not managed" in warnings[0]


def test_a_container_of_a_disabled_service_gets_a_warning(tmp_path):
    up, warnings = run(tmp_path, [container("deconz", "running")], disabled=["deconz"])
    assert "deconz" not in up
    assert len(warnings) == 1
    assert "deconz" in warnings[0] and "not managed" in warnings[0]


def test_a_disabled_service_without_a_container_gets_no_warning(tmp_path):
    up, warnings = run(tmp_path, [], disabled=["deconz"])
    assert "deconz" not in up
    assert not warnings


def role_file(*parts):
    return yaml.safe_load(ROLES_DIR.joinpath("smart_home", *parts).read_text())


def compose_up():
    return next(
        task
        for block in role_file("tasks", "main.yaml")
        for task in block.get("block", [])
        if task.get("name") == "Ensure the stack is up"
    )


def test_compose_up_brings_up_only_the_managed_services():
    task = compose_up()
    module = task["community.docker.docker_compose_v2"]
    assert module["services"] == "{{ smart_home_up_services }}"
    # Without --no-deps, Compose would start a stopped influxdb as telegraf's dependency.
    assert module["dependencies"] is False
    assert "smart_home_up_services | length > 0" in task["when"]


def test_restart_handlers_skip_services_left_alone():
    for handler in role_file("handlers", "main.yaml"):
        (service,) = handler["community.docker.docker_compose_v2"]["services"]
        assert f"'{service}' in smart_home_up_services | default([])" in handler["when"], handler["name"]
