"""Home Assistant runs next to ioBroker until the last automation has moved (#2).

Its UI state (integrations, devices, users, history) lives in a named volume; everything written by hand
(configuration.yaml, the packages with automations, scripts and helpers) comes from this repo and is mounted
read-only, so the UI can't change it behind the repo's back.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "homeassistant"
# infrastructure creates the network siz with this subnet; nginx reaches Home Assistant from it
SIZ_SUBNET = "172.30.2.0/24"
OUTBOUND_PIHOLE = "172.30.1.153"


class HomeAssistantLoader(yaml.SafeLoader):
    """Reads Home Assistant's YAML tags (!include_dir_named, !secret, ...) as tagged strings."""


HomeAssistantLoader.add_multi_constructor("!", lambda loader, tag, node: ("!" + tag, loader.construct_scalar(node)))


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yaml").read_text())


def homeassistant():
    return compose()["services"]["homeassistant"]


def configuration():
    return yaml.load((CONFIG_DIR / "configuration.yaml").read_text(), Loader=HomeAssistantLoader)


def test_image_is_pinned_to_a_release_from_docker_hub():
    """Renovate bumps the exact release; a moving tag (stable, latest) would update it unreviewed. Docker Hub, not
    ghcr.io: only Docker Hub gives Renovate a release timestamp, so the shared preset's minimumReleaseAge holds the
    update back and its patch auto-merge applies."""
    assert re.fullmatch(r"homeassistant/home-assistant:\d{4}\.\d{1,2}\.\d+", homeassistant()["image"])


def test_runs_in_the_networks_of_the_stack_not_the_host():
    """nginx reaches it through siz, deCONZ and Mosquitto through smart-home, the LAN devices and the internet
    through outbound, with the outbound Pi-hole as its DNS server."""
    service = homeassistant()
    assert "network_mode" not in service
    assert "privileged" not in service
    assert sorted(service["networks"]) == ["outbound", "siz", "smart-home"]
    assert service["dns"] == [OUTBOUND_PIHOLE]
    assert "ports" not in service


def test_ui_state_lives_in_a_volume_and_the_repo_config_is_read_only():
    service = homeassistant()
    assert service["volumes"] == [
        "homeassistant-config:/config",
        "./homeassistant/configuration.yaml:/config/configuration.yaml:ro",
        "./homeassistant/packages:/config/packages:ro",
    ]
    assert "homeassistant-config" in compose()["volumes"]


def test_has_a_healthcheck_and_a_memory_limit():
    service = homeassistant()
    assert "http://localhost:8123/" in " ".join(service["healthcheck"]["test"])
    assert service["mem_limit"]


def test_trusts_forwarded_addresses_only_from_the_proxy_network():
    http = configuration()["http"]
    assert http["use_x_forwarded_for"] is True
    assert http["trusted_proxies"] == [SIZ_SUBNET]


def test_automations_scripts_and_helpers_come_from_the_packages():
    config = configuration()
    assert config["homeassistant"]["packages"] == ("!include_dir_named", "packages")
    # The UI editors would write automations.yaml and friends, which the read-only mount doesn't have
    for key in ("automation", "script", "scene"):
        assert key not in config
    assert (CONFIG_DIR / "packages").is_dir()


def test_configuration_holds_no_private_data():
    """Location and coordinates are set during onboarding and live in the volume, not in this public repo."""
    core = configuration()["homeassistant"]
    for key in ("latitude", "longitude", "elevation"):
        assert key not in core
