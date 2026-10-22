"""Hosts without some hardware (testbed has no ConBee stick for deCONZ) leave services out of `compose up` (#7)."""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_DIR = ROOT / "ansible"


def run_role(tmp_path, disabled):
    playbook = tmp_path / "play.yaml"
    playbook.write_text(
        yaml.safe_dump(
            [{"name": "Role", "hosts": "localhost", "connection": "local", "gather_facts": False,
              "roles": ["smart_home"]}]
        )
    )
    return subprocess.run(
        [
            "ansible-playbook", "-i", "localhost,", str(playbook),
            "-e", yaml.safe_dump({"smart_home_disabled_services": disabled,
                                  "smart_home_env_file": str(tmp_path / "missing.env")}, default_flow_style=True),
        ],
        cwd=ANSIBLE_DIR,
        env={"ANSIBLE_ROLES_PATH": str(ANSIBLE_DIR / "roles"), "PATH": subprocess.os.environ["PATH"]},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_testbed_leaves_out_deconz():
    hosts = yaml.safe_load((ANSIBLE_DIR / "inventory" / "hosts.yaml").read_text())["all"]["hosts"]
    assert hosts["testbed"]["smart_home_disabled_services"] == ["deconz"]
    assert "smart_home_disabled_services" not in hosts["raspi"]


def test_refuses_an_unknown_service(tmp_path):
    """A typo must not silently start everything, the production deCONZ included."""
    result = run_role(tmp_path, ["deconzz"])
    assert result.returncode != 0
    assert "Unknown services in smart_home_disabled_services: deconzz" in result.stdout


def test_accepts_services_of_the_compose_file(tmp_path):
    # Passes the check and stops at the next one, the missing secrets file.
    result = run_role(tmp_path, ["deconz", "firmware-download"])
    assert "Unknown services" not in result.stdout
    assert "missing.env is missing" in result.stdout
