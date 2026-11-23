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
    # Only Sonos' event callbacks; the UI goes through nginx
    assert service["ports"] == ["1400:1400"]


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


def role_tasks():
    return yaml.safe_load((ROOT / "ansible" / "roles" / "smart_home" / "tasks" / "main.yaml").read_text())


def role_defaults():
    return yaml.safe_load((ROOT / "ansible" / "roles" / "smart_home" / "defaults" / "main.yaml").read_text())


def test_http_is_not_configured_in_yaml():
    """Since 2026.x Home Assistant imports http: from YAML once, as a trial an admin must confirm in the UI within
    5 minutes, then reverts and ignores the YAML for good (homeassistant/components/http/config.py)."""
    assert "http" not in configuration()


def test_the_role_seeds_the_http_store_with_the_proxy_settings():
    """Version 1 of the store holds the bare settings; Home Assistant migrates it and fills in the defaults."""
    seed = role_defaults()["smart_home_homeassistant_http_store"]
    assert seed["version"] == 1
    assert seed["key"] == "http"
    assert seed["data"] == {"use_x_forwarded_for": True, "trusted_proxies": [SIZ_SUBNET]}


def test_the_seed_never_overwrites_the_store_and_lands_after_the_restore():
    """Home Assistant owns the file once it ran (UI changes, its own migrations); a restore must find the volume
    empty, so the seed comes after it and before compose up."""
    names = [task.get("name") for task in role_tasks()]
    seed = next(task for task in role_tasks() if task.get("name") == "Ensure Home Assistant starts with the proxy settings")
    assert seed["ansible.builtin.copy"]["force"] is False
    assert names.index("Restore the volumes on a fresh host") < names.index(seed["name"]) < names.index(
        "Start containers")


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


def test_home_assistant_has_its_own_mosquitto_user():
    """Its own user, so ioBroker's can go with ioBroker; infrastructure renders the password into the .env."""
    users = role_defaults()["smart_home_mosquitto_users"]
    assert {"name": "homeassistant", "env": "MOSQUITTO_HOMEASSISTANT_PASSWD"} in users
    assert {"name": "mosquitto", "env": "MOSQUITTO_PASSWD"} in users
    env_example = (ROOT / "setup" / ".env.example").read_text()
    for user in users:
        assert f"\n{user['env']}=" in env_example


def package(name):
    return yaml.load((CONFIG_DIR / "packages" / f"{name}.yaml").read_text(), Loader=HomeAssistantLoader)


def test_sonos_speakers_are_configured_by_address():
    """SSDP discovery doesn't cross the bridge network, so the speakers are listed, and they send their events to the
    host's address on port 1400, which Compose forwards to the container."""
    sonos = package("sonos")["sonos"]["media_player"]
    assert sonos["advertise_addr"] == ("!env_var", "SONOS_ADVERTISE_ADDR")
    assert len(sonos["hosts"]) >= 1
    assert all(re.fullmatch(r"192\.168\.1\.\d{1,3}", host) for host in sonos["hosts"])


def test_the_host_address_reaches_home_assistant_from_a_file_the_role_writes():
    """The address differs per host (raspi, testbench); the role writes it next to the compose file, so a manual
    docker compose up on the Pi gets it too."""
    assert homeassistant()["env_file"] == ["homeassistant.env"]
    assert role_defaults()["smart_home_host_address"] == "{{ ansible_host }}"
    task = next(task for task in role_tasks() if task.get("name") == "Ensure Home Assistant knows the host address")
    copy = task["ansible.builtin.copy"]
    assert copy["dest"] == "{{ smart_home_compose_dir }}/homeassistant.env"
    assert copy["content"] == "SONOS_ADVERTISE_ADDR={{ smart_home_host_address }}\n"


# The values the Node-RED flows read from ioBroker's 0_userdata on 2026-11-23 (#2)
HELPER_START_VALUES = {
    "input_boolean.wecker_werktag": "on",
    "input_boolean.wecker_wochenende": "on",
    "input_datetime.weckzeit_werktag": "07:20:00",
    "input_datetime.weckzeit_wochenende": "10:00:00",
    "input_datetime.nachtruhe": "22:00:00",
    "input_number.dauer_schuhheizung": 8,
    "input_number.rollladen_helligkeit": 30000,
    "input_number.rollladen_helligkeit_max": 35000,
    "input_number.rollladen_temperatur": 23,
    "input_number.rollladen_temperatur_max": 26,
}
SHUTTERS = ["buero", "kueche", "schlafzimmer", "garten", "terrasse"]


def helper_ids(helpers):
    return {
        f"{domain}.{object_id}"
        for domain, entities in helpers.items()
        if domain in {"input_boolean", "input_datetime", "input_number", "timer"}
        for object_id in entities
    }


def test_helpers_replace_the_states_of_iobroker_and_node_red():
    ids = helper_ids(package("helpers"))
    assert set(HELPER_START_VALUES) <= ids
    assert {"input_boolean.gaeste", "input_boolean.abend", "input_boolean.wecken_aussetzen",
            "timer.aufwachlicht"} <= ids
    for shutter in SHUTTERS:
        assert {f"input_number.rollladen_{shutter}_soll", f"input_boolean.rollladen_{shutter}_sperre"} <= ids


def test_helpers_keep_what_is_set_in_the_app():
    """With initial: Home Assistant would reset a helper to it on every restart, undoing what was set in the app.
    Without it, the helper restores its last state."""
    helpers = package("helpers")
    for domain in ("input_boolean", "input_datetime", "input_number"):
        for object_id, config in helpers[domain].items():
            assert "initial" not in (config or {}), f"{domain}.{object_id}"


def start_value_automation():
    automations = package("helpers")["automation"]
    automation = next(a for a in automations if a["id"] == "helfer_startwerte")
    return automation


def test_helpers_start_once_with_the_values_from_iobroker():
    """A fresh Home Assistant starts its helpers at their minimum; the start values are set once, on the first start,
    and a flag that survives restarts keeps them from overwriting later changes."""
    automation = start_value_automation()
    assert automation["triggers"] == [{"trigger": "homeassistant", "event": "start"}]
    assert automation["conditions"] == [
        {"condition": "state", "entity_id": "input_boolean.helfer_startwerte_gesetzt", "state": "off"}
    ]
    values = {}
    for action in automation["actions"]:
        domain, service = action["action"].split(".")
        entity = action["target"]["entity_id"]
        if service == "set_value":
            values[entity] = action["data"]["value"]
        elif service == "set_datetime":
            values[entity] = action["data"]["time"]
        elif service == "turn_on":
            values[entity] = "on"
    flag = values.pop("input_boolean.helfer_startwerte_gesetzt")
    assert flag == "on"
    assert automation["actions"][-1]["target"]["entity_id"] == "input_boolean.helfer_startwerte_gesetzt"
    assert values == HELPER_START_VALUES | {f"input_number.rollladen_{s}_soll": 100 for s in SHUTTERS}


def test_someone_is_home_while_a_person_is_in_the_home_zone():
    """Arrival counts at once, leaving after five minutes, like the Node-RED flow. Which phone belongs to whom is set in
    the app (Settings > People), so no device names or addresses end up in this repo."""
    presence = package("presence")
    sensor = next(s for t in presence["template"] for s in t.get("binary_sensor", [])
                  if s.get("default_entity_id") == "binary_sensor.jemand_zuhause")
    assert "zone.home" in sensor["state"]
    assert sensor["delay_off"] == {"minutes": 5}
    assert sensor["device_class"] == "presence"
    text = (CONFIG_DIR / "packages" / "presence.yaml").read_text()
    assert "device_tracker." not in text
    assert not re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", text)


def automation(package_name, automation_id):
    return next(a for a in package(package_name)["automation"] if a["id"] == automation_id)


def test_evening_starts_before_sunset_in_winter_and_before_dusk_in_summer():
    """Node-RED's evening: 15 minutes before sunset in winter (standard time), 19 minutes before civil dusk in summer
    (daylight saving time)."""
    start = automation("presence", "abend_beginnt")
    triggers = {t["id"]: t for t in start["triggers"]}
    assert triggers["winter"] == {"trigger": "sun", "event": "sunset", "offset": "-00:15:00", "id": "winter"}
    assert "next_dusk" in triggers["summer"]["value_template"]
    assert "minutes=19" in triggers["summer"]["value_template"]
    assert start["actions"][-1]["action"] == "input_boolean.turn_on"
    assert start["actions"][-1]["target"]["entity_id"] == "input_boolean.abend"


def test_evening_ends_at_midnight():
    end = automation("presence", "abend_endet")
    assert end["triggers"] == [{"trigger": "time", "at": "00:00:00"}]
    assert end["actions"] == [{"action": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.abend"}}]
