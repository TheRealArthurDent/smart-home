"""Home Assistant runs next to ioBroker until the last automation has moved (#2).

Its UI state (integrations, devices, users, history) lives in a named volume; everything written by hand
(configuration.yaml, the packages with automations, scripts and helpers) comes from this repo and is mounted
read-only, so the UI can't change it behind the repo's back.
"""

import datetime
import re
from pathlib import Path

import jinja2
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
        "./homeassistant/dashboards:/config/dashboards:ro",
        "./homeassistant-virtual:/config/virtual:ro",
        "./homeassistant-real:/config/real:ro",
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


def real_devices():
    return yaml.load((ROOT / "homeassistant-real" / "sonos.yaml").read_text(), Loader=HomeAssistantLoader)


def package(name):
    return yaml.load((CONFIG_DIR / "packages" / f"{name}.yaml").read_text(), Loader=HomeAssistantLoader)


def test_sonos_speakers_are_configured_by_address():
    """SSDP discovery doesn't cross the bridge network, so the speakers are listed, and they send their events to the
    host's address on port 1400, which Compose forwards to the container."""
    sonos = real_devices()["sonos"]["media_player"]
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
    "input_boolean.wake_up_workday": "on",
    "input_boolean.wake_up_weekend": "on",
    "input_datetime.wake_up_time_workday": "07:20:00",
    "input_datetime.wake_up_time_weekend": "10:00:00",
    "input_datetime.night_rest": "22:00:00",
    "input_number.shoe_heating_duration": 8,
    "input_number.shutter_brightness": 30000,
    "input_number.shutter_brightness_max": 35000,
    "input_number.shutter_temperature": 23,
    "input_number.shutter_temperature_max": 26,
}
SHUTTERS = ["office", "kitchen", "bedroom", "garden", "terrace"]


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
    assert {"input_boolean.guests", "input_boolean.evening", "input_boolean.skip_next_wake_up",
            "timer.wake_up_light"} <= ids
    for shutter in SHUTTERS:
        assert {f"input_number.shutter_{shutter}_target", f"input_boolean.shutter_{shutter}_locked"} <= ids


def test_helpers_keep_what_is_set_in_the_app():
    """With initial: Home Assistant would reset a helper to it on every restart, undoing what was set in the app.
    Without it, the helper restores its last state."""
    helpers = package("helpers")
    for domain in ("input_boolean", "input_datetime", "input_number"):
        for object_id, config in helpers[domain].items():
            assert "initial" not in (config or {}), f"{domain}.{object_id}"


def start_value_automation():
    automations = package("helpers")["automation"]
    automation = next(a for a in automations if a["id"] == "helper_start_values")
    return automation


def test_helpers_start_once_with_the_values_from_iobroker():
    """A fresh Home Assistant starts its helpers at their minimum; the start values are set once, on the first start,
    and a flag that survives restarts keeps them from overwriting later changes."""
    automation = start_value_automation()
    assert automation["triggers"] == [{"trigger": "homeassistant", "event": "start"}]
    assert automation["conditions"] == [
        {"condition": "state", "entity_id": "input_boolean.helper_start_values_set", "state": "off"}
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
    flag = values.pop("input_boolean.helper_start_values_set")
    assert flag == "on"
    assert automation["actions"][-1]["target"]["entity_id"] == "input_boolean.helper_start_values_set"
    assert values == HELPER_START_VALUES | {f"input_number.shutter_{s}_target": 100 for s in SHUTTERS}


def test_someone_is_home_while_a_person_is_in_the_home_zone():
    """Arrival counts at once, leaving after five minutes, like the Node-RED flow. Which phone belongs to whom is set in
    the app (Settings > People), so no device names or addresses end up in this repo."""
    presence = package("presence")
    sensor = next(s for t in presence["template"] for s in t.get("binary_sensor", [])
                  if s.get("default_entity_id") == "binary_sensor.someone_home")
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
    start = automation("presence", "evening_starts")
    triggers = {t["id"]: t for t in start["triggers"]}
    assert triggers["winter"] == {"trigger": "sun", "event": "sunset", "offset": "-00:15:00", "id": "winter"}
    assert "next_dusk" in triggers["summer"]["value_template"]
    assert "minutes=19" in triggers["summer"]["value_template"]
    assert start["actions"][-1]["action"] == "input_boolean.turn_on"
    assert start["actions"][-1]["target"]["entity_id"] == "input_boolean.evening"


def test_evening_ends_at_midnight():
    end = automation("presence", "evening_ends")
    assert end["triggers"] == [{"trigger": "time", "at": "00:00:00"}]
    assert end["actions"] == [{"action": "input_boolean.turn_off", "target": {"entity_id": "input_boolean.evening"}}]


DECO_LIGHTS = ["light.wohnzimmer_dekolights", "light.wohnzimmer_weihnachtssterne"]


def targets(actions):
    """Every entity the actions (and their choose/if branches) act on."""
    found = []
    for action in actions:
        entity = action.get("target", {}).get("entity_id")
        found += entity if isinstance(entity, list) else [entity] if entity else []
        for option in action.get("choose", []):
            found += targets(option["sequence"])
        found += targets(action.get("default", [])) + targets(action.get("then", [])) + targets(action.get("else", []))
    return found


def test_deco_lights_follow_evening_and_presence():
    on = automation("lights", "decoration_lights_on")
    assert {(t["entity_id"], t["to"]) for t in on["triggers"]} == {
        ("input_boolean.evening", "on"), ("binary_sensor.someone_home", "on")}
    assert {(c["entity_id"], c["state"]) for c in on["conditions"]} == {
        ("input_boolean.evening", "on"), ("binary_sensor.someone_home", "on")}
    assert targets(on["actions"]) == DECO_LIGHTS
    off = automation("lights", "decoration_lights_off")
    assert {(t["entity_id"], t["to"]) for t in off["triggers"]} == {
        ("input_boolean.evening", "off"), ("binary_sensor.someone_home", "off")}
    assert targets(off["actions"]) == DECO_LIGHTS


def test_buttons_are_matched_by_the_ieee_address_home_assistant_sends():
    """Home Assistant's deCONZ integration puts the device's IEEE address into deconz_event's unique_id, without the
    endpoint and cluster suffix (-01-1000) of the deCONZ REST uniqueid that the Node-RED flows matched."""
    expected = {
        "decoration_lights_button": ("5c:c7:c1:ff:fe:83:4b:a0", DECO_LIGHTS),
        "decoration_lights_switch": ("84:ba:20:ff:fe:d4:12:52", DECO_LIGHTS),
        "home_office_switch": ("94:34:69:ff:fe:3d:c9:a6", ["switch.buro_on_off_homeoffice"]),
        "corner_desk_switch": ("dc:8e:95:ff:fe:2e:1d:3b", ["light.buro_eckschreibtisch"]),
    }
    for automation_id, (unique_id, entities) in expected.items():
        button = automation("lights", automation_id)
        assert button["triggers"] == [
            {"trigger": "event", "event_type": "deconz_event", "event_data": {"unique_id": unique_id}}], automation_id
        assert sorted(set(targets(button["actions"]))) == sorted(entities), automation_id


def test_every_deconz_trigger_uses_a_bare_ieee_address():
    """A suffixed unique_id never matches; the trigger would stay silent without any error."""
    ieee = re.compile(r"([0-9a-f]{2}:){7}[0-9a-f]{2}")
    for file in (CONFIG_DIR / "packages").glob("*.yaml"):
        config = yaml.load(file.read_text(), Loader=HomeAssistantLoader)
        for item in (config or {}).get("automation", []) if isinstance(config, dict) else []:
            for trigger in item.get("triggers", []):
                if trigger.get("event_type") == "deconz_event":
                    assert ieee.fullmatch(trigger["event_data"]["unique_id"]), item["id"]
    example = virtual_devices()["script"]["virtual_button_press"]["fields"]["unique_id"]["example"]
    assert ieee.fullmatch(example)


def test_storeroom_light_follows_the_motion_sensor_with_30_seconds_delay():
    storeroom = automation("lights", "storeroom_light")
    triggers = {t["id"]: t for t in storeroom["triggers"]}
    assert triggers["motion"]["to"] == "on"
    assert triggers["still"]["to"] == "off"
    assert triggers["still"]["for"] == {"seconds": 30}
    # Node-RED also checked hourly, in case an event got lost
    assert triggers["hourly"]["trigger"] == "time_pattern"
    assert set(targets(storeroom["actions"])) == {"switch.abstellkammer_light_storeroom_output_0"}


def test_bedroom_wall_switch_switches_the_wake_up_light_and_stops_its_dimming():
    bedroom = automation("lights", "bedroom_wall_switch")
    assert bedroom["triggers"][0]["entity_id"] == "binary_sensor.schlafzimmer_light_bedroom_eingang_0"
    assert set(targets(bedroom["actions"])) == {"light.schlafzimmer_aufwachlicht", "timer.wake_up_light"}


def test_christmas_stars_in_winter():
    """December and January mornings 7 to 9; November to January from 15:00 while someone is home."""
    morning = automation("lights", "christmas_stars_morning")
    assert sorted(t["at"] for t in morning["triggers"]) == ["07:00:00", "09:00:00"]
    assert "(12, 1)" in str(morning["conditions"])
    afternoon = automation("lights", "christmas_stars_afternoon")
    assert afternoon["triggers"] == [{"trigger": "time", "at": "15:00:00"}]
    assert "(11, 12, 1)" in str(afternoon["conditions"])
    assert "binary_sensor.someone_home" in str(afternoon["conditions"])
    assert targets(morning["actions"]) == targets(afternoon["actions"]) == ["light.wohnzimmer_weihnachtssterne"]


def test_ci_checks_the_configuration_with_the_release_the_stack_runs():
    """check_config of the pinned image catches invalid YAML before it reaches main; the image is read from the
    compose file, so Renovate bumps one place. check_config exits 0 even on errors, so the job reads its output."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "homeassistant.yaml").read_text())
    job = workflow["jobs"]["config"]
    assert job["name"] == "Home Assistant config"
    script = "\n".join(step.get("run", "") for step in job["steps"])
    assert ".services.homeassistant.image" in script
    assert "homeassistant/home-assistant:" not in script
    assert "check_config" in script
    assert "Invalid config" in script


SANDBOX = {"automation sandbox": "automations.yaml", "script sandbox": "scripts.yaml", "scene sandbox": "scenes.yaml"}


def test_prototypes_made_in_the_ui_land_in_a_sandbox_in_the_volume():
    """The UI editors and the MCP server save to automations.yaml, scripts.yaml and scenes.yaml. They live in the
    volume, not in the repo: what works moves into a package, then the file is emptied again."""
    config = configuration()
    for key, file in SANDBOX.items():
        assert config[key] == ("!include", file)


def test_the_role_creates_empty_sandbox_files_without_touching_existing_ones():
    """An !include of a missing file breaks the whole configuration, so the files must exist before the first
    start; force: false keeps what is in them."""
    assert role_defaults()["smart_home_homeassistant_sandbox_files"] == {
        "automations.yaml": "[]", "scripts.yaml": "{}", "scenes.yaml": "[]"}
    names = [task.get("name") for task in role_tasks()]
    task = next(task for task in role_tasks() if task.get("name") == "Ensure Home Assistant has its sandbox files")
    assert task["ansible.builtin.copy"]["force"] is False
    assert task["loop"] == "{{ smart_home_homeassistant_sandbox_files | dict2items }}"
    assert names.index("Restore the volumes on a fresh host") < names.index(task["name"]) < names.index(
        "Start containers")


def test_ci_checks_the_configuration_with_the_sandbox_files():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "homeassistant.yaml").read_text())
    script = "\n".join(step.get("run", "") for step in workflow["jobs"]["config"]["steps"])
    for file in SANDBOX.values():
        assert file in script


def test_the_presence_dashboard_comes_from_the_repo():
    """A YAML dashboard, read-only like the packages. It lists people and their trackers from the states, so no names
    or device ids end up in this repo."""
    dashboard = configuration()["lovelace"]["dashboards"]["dashboard-presence"]
    assert dashboard["mode"] == "yaml"
    assert dashboard["filename"] == "dashboards/presence.yaml"
    text = (CONFIG_DIR / "dashboards" / "presence.yaml").read_text()
    views = yaml.safe_load(text)["views"]
    assert views
    assert "binary_sensor.someone_home" in text and "zone.home" in text
    assert "states.person" in text and "states.device_tracker" in text
    assert "device_tracker." not in text.replace("states.device_tracker", "")
    assert "person." not in text.replace("states.person", "")


VIRTUAL_DIR = ROOT / "homeassistant-virtual"
# Domains of physical devices; testbench has neither the Zigbee stick nor the Shellies of raspi
DEVICE_DOMAINS = ("light", "switch", "binary_sensor", "sensor", "cover", "media_player")
# Actions, not devices; a templated one (light.turn_{{ ... }}) ends in "_"
ACTIONS = {"turn_on", "turn_off", "toggle", "open_cover", "close_cover", "stop_cover", "set_cover_position",
           "media_stop", "media_play", "media_pause", "media_next_track"}


# Entities of integrations that are no devices and are set up in the UI on testbench as on raspi: Workday
# (Germany, Bavaria, with the Catholic holidays, so Assumption Day counts as in Node-RED)
SET_UP_ON_BOTH_HOSTS = {"binary_sensor.workday_sensor"}


def virtual_devices():
    return yaml.safe_load((VIRTUAL_DIR / "devices.yaml").read_text())


def template_entities(config):
    """(domain, entity) of every template entity of a package."""
    return [(domain, entity) for block in config.get("template", []) for domain, entities in block.items()
            if domain in DEVICE_DOMAINS for entity in entities]


def test_every_device_the_packages_use_has_a_virtual_twin_on_testbench():
    """Automations run on testbench against virtual devices with the entity ids of raspi. A new device in a package
    fails here until it has its twin."""
    pattern = re.compile(rf"\b(?:{'|'.join(DEVICE_DOMAINS)})\.[a-z0-9_]+")
    used, own = set(), set()
    for file in (CONFIG_DIR / "packages").glob("*.yaml"):
        used |= {e for e in pattern.findall(file.read_text()) if e.split(".")[1] not in ACTIONS and not e.endswith("_")}
        config = yaml.load(file.read_text(), Loader=HomeAssistantLoader)
        if isinstance(config, dict):
            own |= {entity.get("default_entity_id") for _, entity in template_entities(config)}
    twins = {entity["default_entity_id"] for _, entity in template_entities(virtual_devices())}
    twins |= set(virtual_media_players())
    assert used - own, "the packages use no devices?"
    assert sorted(used - own - twins - SET_UP_ON_BOTH_HOSTS) == []
    assert all(twin.split(".")[0] == domain for domain, entity in template_entities(virtual_devices())
               for twin in [entity["default_entity_id"]])


def test_virtual_devices_keep_their_state_in_helpers():
    """Switching a twin changes a helper, so its state can be read back and survives a restart (no initial:)."""
    config = virtual_devices()
    booleans = config["input_boolean"]
    for domain, entity in template_entities(config):
        helper = f"virtual_{entity['default_entity_id'].split('.')[1]}"
        assert entity["unique_id"] == helper
        if domain == "cover":
            # A shutter's state is its position
            assert f"{helper}_position" in config["input_number"], entity["default_entity_id"]
            assert f"input_number.{helper}_position" in entity["position"]
            assert f"input_number.{helper}_position" in str(entity["set_cover_position"])
            continue
        if domain == "sensor":
            # A measuring sensor's state is a number
            assert helper in config["input_number"], entity["default_entity_id"]
            assert f"input_number.{helper}" in entity["state"]
            continue
        assert helper in booleans, entity["default_entity_id"]
        assert f"input_boolean.{helper}" in entity["state"]
        assert entity["unique_id"] == helper
        if domain in ("light", "switch"):
            assert f"input_boolean.{helper}" in str(entity["turn_on"]) and "turn_on" in str(entity["turn_on"])
            assert f"input_boolean.{helper}" in str(entity["turn_off"]) and "turn_off" in str(entity["turn_off"])
        if domain == "light":
            assert f"input_number.{helper}_brightness" in entity["level"]
            assert f"input_number.{helper}_brightness" in str(entity["set_level"])
    for helpers in (config["input_boolean"], config["input_number"]):
        assert all("initial" not in helper for helper in helpers.values())


def test_virtual_buttons_fire_the_event_of_a_deconz_button():
    """Buttons have no state; the script fires the deconz_event the automations match by unique_id."""
    script = virtual_devices()["script"]["virtual_button_press"]
    assert set(script["fields"]) == {"unique_id", "event"}
    assert script["sequence"][0]["event"] == "deconz_event"
    assert set(script["sequence"][0]["event_data"]) == {"unique_id", "event"}


def virtual_media_players():
    """Entity id -> config of the virtual media players; a universal player's entity id comes from its name."""
    return {"media_player." + re.sub(r"[^a-z0-9]+", "_", player["name"].lower().translate(UMLAUTS)).strip("_"): player
            for player in virtual_devices().get("media_player", [])}


UMLAUTS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def test_virtual_sonos_speakers_stand_in_for_the_real_ones_on_testbench():
    """testbench shares the house's network with the real speakers; its automations must not stop the music. Each
    twin plays while its helper is on; stop and pause turn it off, play on, the next track counts up."""
    players = virtual_media_players()
    assert set(players) == set(SONOS_SPEAKERS)
    booleans, numbers = virtual_devices()["input_boolean"], virtual_devices()["input_number"]
    for entity, player in players.items():
        helper = f"virtual_{entity.split('.')[1]}"
        assert player["platform"] == "universal" and player["unique_id"] == helper
        assert player["children"] == []
        assert helper in booleans and f"{helper}_track" in numbers
        assert f"input_boolean.{helper}" in player["state_template"]
        commands = player["commands"]
        for command, action in (("media_stop", "turn_off"), ("media_pause", "turn_off"), ("media_play", "turn_on")):
            assert commands[command] == {"action": f"input_boolean.{action}",
                                         "target": {"entity_id": f"input_boolean.{helper}"}}, (entity, command)
        assert commands["media_next_track"] == {"action": "input_number.increment",
                                                "target": {"entity_id": f"input_number.{helper}_track"}}


def test_real_devices_load_only_where_there_are_no_twins():
    """The Sonos integration talks to the real speakers, so it loads on raspi only; testbench gets the twins."""
    assert package("real_devices") == ("!include_dir_merge_named", "../real")
    assert "sonos" not in package("sonos")
    names = [task.get("name") for task in role_tasks()]
    assert "Ensure the real devices are present" in names
    copy = next(task for task in role_tasks() if task.get("name") == "Ensure the real devices are present")
    assert copy["when"] == "not smart_home_homeassistant_virtual_devices | bool"
    assert copy["ansible.builtin.copy"]["src"] == "{{ smart_home_repo_dir }}/homeassistant-real/"


def test_virtual_devices_load_only_where_the_role_puts_them():
    """The package includes a directory the role fills on testbench only and keeps empty everywhere else."""
    assert package("virtual_devices") == ("!include_dir_merge_named", "../virtual")
    assert "./homeassistant-virtual:/config/virtual:ro" in homeassistant()["volumes"]
    assert role_defaults()["smart_home_homeassistant_virtual_devices"] is False
    hosts = yaml.safe_load((ROOT / "ansible" / "inventory" / "hosts.yaml").read_text())["all"]["hosts"]
    assert hosts["testbench"]["smart_home_homeassistant_virtual_devices"] is True
    assert "smart_home_homeassistant_virtual_devices" not in hosts["raspi"]
    names = [task.get("name") for task in role_tasks()]
    for name in ("Ensure the directory of the virtual devices exists", "Ensure the virtual devices are present",
                 "Ensure no other virtual devices are present"):
        assert name in names
    copy = next(task for task in role_tasks() if task.get("name") == "Ensure the virtual devices are present")
    assert copy["when"] == "smart_home_homeassistant_virtual_devices | bool"


def test_ci_checks_the_configuration_with_and_without_the_virtual_devices():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "homeassistant.yaml").read_text())
    script = "\n".join(step.get("run", "") for step in workflow["jobs"]["config"]["steps"])
    assert "homeassistant-virtual/." in script
    assert 'cp -r homeassistant-real/. "$config/real"' in script
    assert script.count("check_config") == 1 and "for virtual in" in script


def test_ci_fails_when_the_check_itself_fails():
    """The default shell has no pipefail, so a failing docker run (e.g. the image can't be pulled) piped into tee
    would leave an empty log and a green job. shell: bash runs with -eo pipefail."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "homeassistant.yaml").read_text())
    for step in workflow["jobs"]["config"]["steps"]:
        if "run" in step:
            assert step.get("shell") == "bash", step["name"]


# Templates are rendered with plain Jinja and stand-ins for Home Assistant's functions, so the decisions the
# automations take (which alarm, how long to hold, when to heat the shoes) are checked case by case.
def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def render(template, **context):
    env = jinja2.Environment()
    env.filters["as_datetime"] = lambda value, default=None: value if value is not None else default
    env.filters["int"] = lambda value, default=0: int(float(value)) if value not in (None, "") else default
    env.filters["float"] = to_float
    return env.from_string(template).render(**context).strip()


def is_state_of(states):
    return lambda entity, state: states.get(entity) == state


def wake_up():
    return automation("wakeup", "wake_up_start")


def test_wake_up_starts_30_minutes_before_the_alarm_time():
    """Weekends and holidays only for now; Node-RED still wakes on workdays until the workday trigger is added."""
    triggers = {t["id"]: t for t in wake_up()["triggers"]}
    assert triggers == {
        day: {"trigger": "time", "at": {"entity_id": f"input_datetime.wake_up_time_{day}", "offset": "-00:30:00"},
              "id": day}
        for day in ("weekend",)}


def test_wake_up_takes_the_alarm_of_workdays_or_of_weekends_and_holidays():
    """Node-RED took the weekend alarm on Saturdays, Sundays and holidays (german-holidays, Bavaria)."""
    condition = wake_up()["conditions"][0]["value_template"]
    for workday in (True, False):
        for day in ("workday", "weekend"):
            for alarm in (True, False):
                states = {"binary_sensor.workday_sensor": "on" if workday else "off",
                          f"input_boolean.wake_up_{day}": "on" if alarm else "off"}
                fires = render(condition, trigger={"id": day}, is_state=is_state_of(states)) == "True"
                assert fires == (alarm and workday == (day == "workday")), (workday, day, alarm)
    # Without the Workday sensor (not set up, or under another entity id) nobody is woken by mistake
    for day in ("workday", "weekend"):
        states = {f"input_boolean.wake_up_{day}": "on"}
        assert render(condition, trigger={"id": day}, is_state=is_state_of(states)) == "False", day


def test_skipping_a_wake_up_resets_the_skip_and_keeps_the_bedroom_shutter_down():
    skip = wake_up()["actions"][0]
    assert skip["if"] == [{"condition": "state", "entity_id": "input_boolean.skip_next_wake_up", "state": "on"}]
    assert targets(skip["then"]) == ["input_boolean.skip_next_wake_up", "input_boolean.shutter_bedroom_locked"]
    assert [a["action"] for a in skip["then"][:2]] == ["input_boolean.turn_off", "input_boolean.turn_on"]
    assert skip["then"][-1] == {"stop": "Wecken einmal ausgesetzt"}


def test_wake_up_only_with_the_shutter_down_and_someone_home():
    checks = wake_up()["actions"][1:3]
    assert checks[0]["condition"] == "numeric_state"
    assert checks[0]["entity_id"] == "cover.schlafzimmer_shutter_bedroom"
    assert checks[0]["attribute"] == "current_position"
    assert checks[0]["below"] == 50
    assert checks[1] == {"condition": "state", "entity_id": "binary_sensor.someone_home", "state": "on"}


def test_the_wake_up_light_dims_up_in_30_minutes_and_holds_until_sunrise():
    """Node-RED dimmed the wake-up light up to 255 in 30 minutes, then held it for the minutes to sunrise less the
    dimming, at least 30."""
    actions = wake_up()["actions"]
    lights = [a for a in actions if a.get("action") == "light.turn_on"]
    assert [a["data"] for a in lights] == [{"brightness": 1}, {"brightness": 255, "transition": 1800}]
    assert all(a["target"]["entity_id"] == "light.schlafzimmer_aufwachlicht" for a in lights)
    timer = next(a for a in actions if a.get("action") == "timer.start")
    assert timer["target"]["entity_id"] == "timer.wake_up_light"
    hold = next(a for a in actions if "variables" in a)["variables"]["hold_minutes"]
    now = datetime.datetime(2026, 11, 25, 6, 50)
    for minutes_to_sunrise, expected in ((120, 90), (45, 30), (-10, 30)):
        rising = now + datetime.timedelta(minutes=minutes_to_sunrise)
        if minutes_to_sunrise < 0:  # sun.sun's next rising is tomorrow's once the sun is up
            rising += datetime.timedelta(days=1)
        result = render(hold, now=lambda: now, state_attr=lambda entity, attribute: rising)
        assert int(result) == expected, minutes_to_sunrise
    assert "hold_minutes" in str(timer["data"]["duration"]) and "30" in str(timer["data"]["duration"])


def test_the_wake_up_ends_with_the_light_off_and_the_shutter_opening_in_two_steps():
    """After the hold, Node-RED switched the light off, opened the bedroom shutter to 40 % (over a manual change)
    and an hour later fully, unless it had been moved by hand meanwhile."""
    end = automation("wakeup", "wake_up_end")
    assert end["triggers"] == [{"trigger": "event", "event_type": "timer.finished",
                                "event_data": {"entity_id": "timer.wake_up_light"}}]
    actions = end["actions"]
    assert actions[0] == {"action": "light.turn_off", "target": {"entity_id": "light.schlafzimmer_aufwachlicht"}}
    text = str(actions)
    for needed in ("input_boolean.shutter_bedroom_locked", "input_number.shutter_bedroom_target",
                   "'position': 40"):
        assert needed in text, needed
    assert actions[-1] == {"action": "timer.start", "target": {"entity_id": "timer.wake_up_shutter"},
                           "data": {"duration": "01:00:00"}}
    # A timer, not a delay, so a restart in that hour doesn't lose it
    assert package("wakeup")["timer"]["wake_up_shutter"]["restore"] is True
    full = automation("wakeup", "wake_up_shutter_open")
    assert full["triggers"] == [{"trigger": "event", "event_type": "timer.finished",
                                 "event_data": {"entity_id": "timer.wake_up_shutter"}}]
    text = str(full)
    for needed in ("input_boolean.shutter_bedroom_locked", "input_number.shutter_bedroom_target",
                   "'position': 100", "current_position"):
        assert needed in text, needed
    assert targets(actions)[1:].count("cover.schlafzimmer_shutter_bedroom") == 1
    assert targets(full["actions"]).count("cover.schlafzimmer_shutter_bedroom") == 1


def test_the_day_switch_and_switching_off_stop_the_wake_up_without_moving_the_shutter():
    stop = automation("wakeup", "wake_up_stop")
    # Only the day/night switch in the corridor; the corner desk switch had that role once
    assert [t["event_data"]["unique_id"] for t in stop["triggers"]] == ["18:7a:3e:ff:fe:f1:68:1f"]
    assert "1002" in str(stop["conditions"])
    assert targets(stop["actions"]) == ["timer.wake_up_light"]
    stopped = automation("wakeup", "wake_up_stopped")
    assert stopped["triggers"] == [{"trigger": "event", "event_type": "timer.cancelled",
                                    "event_data": {"entity_id": "timer.wake_up_light"}}]
    assert targets(stopped["actions"]) == ["light.schlafzimmer_aufwachlicht"]


SHOES = "switch.bad_on_off_schuhheizung"


def shoe_plan(now, hours=8.0, night="22:00:00", wake="10:00:00"):
    """Seconds the shoe heating runs now and the next day, by the branch the automation takes."""
    actions = automation("shoe_heating", "shoe_heating_start")["actions"]
    clock = datetime.datetime(2026, 11, 25, *(int(x) for x in now.split(":")))
    states = {"input_number.shoe_heating_duration": str(hours), "input_datetime.night_rest": night,
              "input_datetime.wake_up_time_weekend": wake}
    functions = {"states": states.get, "now": lambda: clock,
                 "today_at": lambda time: datetime.datetime.combine(clock.date(), datetime.time.fromisoformat(time))}
    values = {name: float(render(template, **functions)) for name, template in actions[0]["variables"].items()}
    choose = actions[1]
    branch = next((option["sequence"] for option in choose["choose"]
                   if render(option["conditions"], **values) == "True"), choose["default"])
    timer = next((a for a in branch if a.get("action") == "timer.start"), None)
    rest = next(a for a in branch if a.get("action") == "input_number.set_value")
    return {"now": int(float(render(timer["data"]["duration"], **values))) if timer else 0,
            "later": int(float(render(str(rest["data"]["value"]), **values))) * 60}


def test_shoe_heating_starts_when_the_plug_is_plugged_in():
    start = automation("shoe_heating", "shoe_heating_start")
    assert start["triggers"] == [{"trigger": "state", "entity_id": SHOES, "from": "unavailable"}]
    assert set(start["actions"][0]["variables"]) == {"heating_seconds", "seconds_until_night_rest"}


def test_shoe_heating_runs_before_night_rest_and_finishes_the_next_day():
    """Node-RED: in one go if it ends before night rest; past night rest, all of it the next day from the weekend
    alarm time; otherwise until night rest if at least 20 minutes are left, the rest the next day. Night rest lasts
    until the weekend alarm time (Mika, 2026-11-25), so plugging in at night heats from that time in the morning."""
    hour = 3600
    assert shoe_plan("10:30") == {"now": 8 * hour, "later": 0}
    assert shoe_plan("14:00") == {"now": 8 * hour, "later": 0}
    assert shoe_plan("18:00") == {"now": 4 * hour, "later": 4 * hour}
    assert shoe_plan("21:30") == {"now": 1800, "later": 8 * hour - 1800}
    assert shoe_plan("21:50") == {"now": 0, "later": 8 * hour}
    assert shoe_plan("23:00") == {"now": 0, "later": 8 * hour}
    assert shoe_plan("01:00") == {"now": 0, "later": 8 * hour}
    assert shoe_plan("08:00") == {"now": 0, "later": 8 * hour}
    assert shoe_plan("08:00", wake="07:30:00") == {"now": 8 * hour, "later": 0}
    assert shoe_plan("10:00", hours=0.5) == {"now": 1800, "later": 0}


def test_shoe_heating_switches_on_for_now_and_keeps_the_rest_for_the_next_day():
    actions = automation("shoe_heating", "shoe_heating_start")["actions"]
    # Every branch says in words when it applies
    assert all(option.get("alias") for option in actions[1]["choose"])
    text = str(actions)
    assert "timer.shoe_heating" in text and "input_number.shoe_heating_rest" in text
    assert set(targets(actions)) == {SHOES, "timer.shoe_heating", "input_number.shoe_heating_rest"}
    later = automation("shoe_heating", "shoe_heating_next_day")
    assert later["triggers"] == [{"trigger": "time", "at": "input_datetime.wake_up_time_weekend"}]
    assert later["conditions"] == [{"condition": "numeric_state", "entity_id": "input_number.shoe_heating_rest",
                                    "above": 0}]
    assert set(targets(later["actions"])) == {SHOES, "timer.shoe_heating", "input_number.shoe_heating_rest"}
    off = automation("shoe_heating", "shoe_heating_off")
    assert off["triggers"] == [{"trigger": "event", "event_type": "timer.finished",
                                "event_data": {"entity_id": "timer.shoe_heating"}}]
    assert targets(off["actions"]) == [SHOES]


def test_shoe_heating_keeps_its_state_across_restarts():
    config = package("shoe_heating")
    assert config["timer"]["shoe_heating"]["restore"] is True
    assert "initial" not in config["input_number"]["shoe_heating_rest"]


def test_the_shoe_heating_twin_can_be_plugged_in_and_out():
    """The real plug is unavailable while unplugged; plugging it in starts the heating."""
    switches = {e["default_entity_id"]: e for e in next(b for b in virtual_devices()["template"] if "switch" in b)["switch"]}
    assert "input_boolean.virtual_bad_on_off_schuhheizung_plugged_in" in switches[SHOES]["availability"]
    assert "virtual_bad_on_off_schuhheizung_plugged_in" in virtual_devices()["input_boolean"]


def defined_entities():
    """Entity ids the packages define (helpers, timers, template entities) or that have a twin on testbench."""
    found = {entity["default_entity_id"] for _, entity in template_entities(virtual_devices())}
    for file in (CONFIG_DIR / "packages").glob("*.yaml"):
        config = yaml.load(file.read_text(), Loader=HomeAssistantLoader)
        if not isinstance(config, dict):
            continue
        for domain in ("input_boolean", "input_datetime", "input_number", "timer"):
            found |= {f"{domain}.{name}" for name in config.get(domain, {})}
        found |= {entity.get("default_entity_id") for _, entity in template_entities(config)}
    return found


def test_the_home_dashboard_controls_wake_up_and_shoe_heating():
    """Replaces the bedroom and settings views of ioBroker's lovelace UI, without its custom cards."""
    dashboard = configuration()["lovelace"]["dashboards"]["dashboard-home"]
    assert dashboard["mode"] == "yaml"
    assert dashboard["filename"] == "dashboards/home.yaml"
    text = (CONFIG_DIR / "dashboards" / "home.yaml").read_text()
    assert yaml.safe_load(text)["views"]
    assert "custom:" not in text
    used = set(re.findall(r"\b(?:input_boolean|input_datetime|input_number|timer|light|switch|cover)\.[a-z0-9_]+",
                          text)) - {"timer.cancel"}
    for needed in ("input_boolean.wake_up_weekend", "input_datetime.wake_up_time_weekend",
                   "input_boolean.skip_next_wake_up", "input_boolean.shutter_bedroom_locked",
                   "input_datetime.night_rest", "timer.wake_up_light", "input_number.shoe_heating_duration",
                   "timer.shoe_heating", "switch.bad_on_off_schuhheizung"):
        assert needed in used, needed
    assert sorted(used - defined_entities()) == []


GERMAN = re.compile(r"rollladen|weck|abend|schuh|helfer|jemand|deko|weihnacht|gaeste|nachtruhe|dauer|sperre|soll|"
                    r"aufwach|schalter|taster|morgens|nachmittag|startwerte|abstellkammer")


def own_ids():
    """Ids the packages give: helpers, timers, automations, template entities, trigger ids."""
    found = []
    for file in (CONFIG_DIR / "packages").glob("*.yaml"):
        config = yaml.load(file.read_text(), Loader=HomeAssistantLoader)
        if not isinstance(config, dict) or file.stem == "virtual_devices":
            continue
        for domain in ("input_boolean", "input_datetime", "input_number", "timer"):
            found += list(config.get(domain, {}))
        found += [entity["unique_id"] for _, entity in template_entities(config)]
        for item in config.get("automation", []):
            found += [item["id"]] + [t["id"] for t in item.get("triggers", []) if "id" in t]
    return found


def test_own_ids_are_english_and_names_german():
    """Mika's rule: Home Assistant shows German, the ids behind it are English. Entity ids of devices come from their
    names in Home Assistant, not from this repo, and stay as they are."""
    ids = own_ids()
    assert ids
    assert [i for i in ids if GERMAN.search(i)] == []


# Shutters, replacing Node-RED's "Shutters" tab: a schedule after the sun, a target position and a lock per shutter,
# manual changes kept, and the terrace door. Heat protection follows later.
COVERS = {"office": "cover.buro_shutter_office", "kitchen": "cover.kuche_shutter_kitchen",
          "bedroom": "cover.schlafzimmer_shutter_bedroom", "garden": "cover.wohnzimmer_shutter_garden",
          "terrace": "cover.wohnzimmer_shutter_terrace"}
TERRACE_DOOR = "binary_sensor.wohnzimmer_openclose_terrace"


def shutter_move():
    return package("shutters")["script"]["shutter_move"]


def shutter_decision(shutter, position, current, target, locked=False, override=False, door_open=False):
    """What shutter_move does: its wanted position and decision, rendered like Home Assistant would."""
    script = shutter_move()
    # Home Assistant passes a field only when the call sets it; its default only fills the UI
    variables = {"shutter": shutter, "position": position}
    if override:
        variables["override"] = True
    states = {f"input_number.shutter_{shutter}_target": str(target),
              f"input_boolean.shutter_{shutter}_locked": "on" if locked else "off",
              TERRACE_DOOR: "on" if door_open else "off"}
    context = dict(variables, states=lambda entity: states.get(entity, "unknown"), is_state=is_state_of(states),
                   state_attr=lambda entity, attribute: current if attribute == "current_position" else None)
    for name in ("cover", "target_helper", "wanted", "decision"):
        context[name] = render(script["variables"][name], **context)
        if name == "wanted":
            context[name] = int(context[name])
    return context["wanted"], context["decision"]


def test_half_open_differs_per_shutter():
    """Node-RED's half-open positions; open is 100 and closed 0, as with the Shellies."""
    half = {"office": 40, "kitchen": 40, "bedroom": 40, "garden": 25, "terrace": 40}
    for shutter, position in half.items():
        assert shutter_decision(shutter, "half_open", current=100, target=100)[0] == position
        assert shutter_decision(shutter, "open", current=0, target=0)[0] == 100
        assert shutter_decision(shutter, "closed", current=100, target=100)[0] == 0
        assert shutter_decision(shutter, 55, current=100, target=100)[0] == 55
    assert {name for name in shutter_move()["fields"]["shutter"]["selector"]["select"]["options"]} == set(COVERS)
    assert render(shutter_move()["variables"]["cover"], shutter="garden") == COVERS["garden"]


def test_a_shutter_moved_by_hand_stays_unless_overridden():
    """Node-RED's "Determine action": locked never moves; already there only stores the target; moved since the
    last automatic move (more than the Shellies' 2 % off the target) only moves with override."""
    assert shutter_decision("kitchen", "half_open", current=100, target=100, locked=True, override=True)[1] == "locked"
    assert shutter_decision("kitchen", "half_open", current=40, target=100)[1] == "there"
    assert shutter_decision("kitchen", "half_open", current=100, target=100)[1] == "move"
    assert shutter_decision("kitchen", "half_open", current=99, target=100)[1] == "move"
    assert shutter_decision("kitchen", "half_open", current=70, target=100)[1] == "moved_by_hand"
    assert shutter_decision("kitchen", "half_open", current=70, target=100, override=True)[1] == "move"
    assert shutter_decision("kitchen", "half_open", current=None, target=100, override=True)[1] == "unavailable"


def test_the_terrace_shutter_does_not_close_while_the_door_is_open():
    """Node-RED's "Terrace light on": with the door open, closing only stores the target for when it closes."""
    assert shutter_decision("terrace", "half_open", current=100, target=100, door_open=True)[1] == "door_open"
    assert shutter_decision("terrace", "open", current=40, target=40, door_open=True)[1] == "move"
    assert shutter_decision("garden", "half_open", current=100, target=100, door_open=True)[1] == "move"


def test_shutter_move_acts_on_its_decision():
    script = shutter_move()
    branches = {option["conditions"]: option["sequence"] for option in script["sequence"][0]["choose"]}
    move = branches["{{ decision == 'move' }}"]
    assert move[0] == {"action": "cover.set_cover_position", "target": {"entity_id": "{{ cover }}"},
                       "data": {"position": "{{ wanted }}"}}
    store = {"action": "input_number.set_value", "target": {"entity_id": "{{ target_helper }}"},
             "data": {"value": "{{ wanted }}"}}
    # The terrace door opens the shutter without changing the target it returns to
    assert move[1] == {"if": "{{ not keep_target | default(false) }}", "then": [store]}
    assert branches["{{ decision == 'there' }}"] == move[1:]
    assert branches["{{ decision == 'door_open' }}"] == [store]
    assert script["mode"] == "parallel"
    assert script["fields"]["override"]["default"] is False
    assert script["fields"]["keep_target"]["default"] is False


def shutter_calls(actions, items=None):
    """(shutter, position, override) of each shutter_move call, through repeat for_each, if and choose."""
    calls = []
    for action in actions:
        if action.get("action") == "script.shutter_move":
            data = action["data"]
            shutters = items if data["shutter"] == "{{ repeat.item }}" else [data["shutter"]]
            calls += [(s, data["position"], data.get("override", False)) for s in shutters]
        if "repeat" in action:
            calls += shutter_calls(action["repeat"]["sequence"], action["repeat"]["for_each"])
        for branch in ("then", "else", "sequence"):
            calls += shutter_calls(action.get(branch, []), items)
        for option in action.get("choose", []):
            calls += shutter_calls(option["sequence"], items)
    return calls


def sun_trigger(trigger):
    return (trigger["trigger"], trigger.get("entity_id"), trigger.get("attribute"),
            trigger.get("above"), trigger.get("below"))


def test_shutters_half_open_shortly_before_nautical_dusk():
    """Node-RED: 30 minutes before nautical dusk (sun 12° below the horizon); the sun sinks about 4° in that time."""
    dusk = automation("shutters", "shutters_dusk")
    assert [sun_trigger(t) for t in dusk["triggers"]] == [("numeric_state", "sun.sun", "elevation", None, -8)]
    assert shutter_calls(dusk["actions"]) == [(s, "half_open", True) for s in ("office", "garden", "terrace")]


def test_the_kitchen_shutter_half_opens_at_midnight():
    midnight = automation("shutters", "shutters_midnight")
    assert midnight["triggers"] == [{"trigger": "time", "at": "00:00:00"}]
    assert shutter_calls(midnight["actions"]) == [("kitchen", "half_open", True)]


def test_shutters_open_in_the_morning_but_not_on_guests_or_sleepers():
    """At 7:00 and at civil dawn (6° below the horizon); the office only without guests, the bedroom only when
    nobody is home."""
    morning = automation("shutters", "shutters_morning")
    triggers = {t["id"]: t for t in morning["triggers"]}
    assert triggers["seven"] == {"trigger": "time", "at": "07:00:00", "id": "seven"}
    assert sun_trigger(triggers["dawn"]) == ("numeric_state", "sun.sun", "elevation", -6, None)
    # The eastern shutters (kitchen, garden, bedroom) stay half open while heat protection is needed
    assert sorted(shutter_calls(morning["actions"])) == sorted(
        [(s, "{{ eastern }}", True) for s in ("kitchen", "garden", "bedroom")]
        + [(s, "open", True) for s in ("terrace", "office")])
    eastern = next(a for a in morning["actions"] if "variables" in a)["variables"]["eastern"]
    for heat, forecast, expected in (("on", "on", "half_open"), ("on", "off", "half_open"), ("off", "on", "40"),
                                     ("off", "off", "open"), ("unavailable", "unavailable", "open")):
        states = {HEAT: heat, HOT_DAY: forecast}
        assert render(eastern, is_state=is_state_of(states)) == expected, (heat, forecast)
    office = next(a for a in morning["actions"] if "office" in str(a.get("then")))
    assert office["if"] == [{"condition": "state", "entity_id": "input_boolean.guests", "state": "off"}]
    bedroom = next(a for a in morning["actions"] if "bedroom" in str(a.get("then")))
    assert bedroom["if"] == [{"condition": "state", "entity_id": "binary_sensor.someone_home", "state": "off"}]


HEAT = "binary_sensor.heat_protection"
HOT_DAY = "binary_sensor.hot_clear_day_forecast"


def hot_day_forecast():
    return next(block for block in package("shutters")["template"] if "triggers" in block)


def hot_day(entries, now):
    """The forecast sensor's state for 3-hourly forecast entries of (hour from now's midnight, °C, cloud %)."""
    midnight = now.replace(hour=0, minute=0)
    forecast = [{"datetime": midnight + datetime.timedelta(hours=h), "temperature": t, "cloud_coverage": c}
                for h, t, c in entries]
    env = jinja2.Environment()
    env.filters["as_datetime"] = lambda value, default=None: value
    env.filters["as_local"] = lambda value: value
    sensor = hot_day_forecast()["binary_sensor"][0]
    context = {"forecast": {"weather.garten_openweathermap": {"forecast": forecast}}, "now": lambda: now}
    return env.from_string(sensor["state"]).render(**context).strip() == "True"


def test_a_hot_clear_day_comes_from_the_free_3_hourly_forecast():
    """Node-RED took ioBroker's daily values of OpenWeatherMap: today's maximum above 24 °C and clouds below 30 %.
    The free forecast mode gives 3-hourly values; today's are taken, as ioBroker did."""
    block = hot_day_forecast()
    action = block["actions"][0]
    assert action["action"] == "weather.get_forecasts"
    assert action["target"] == {"entity_id": "weather.garten_openweathermap"}
    assert action["data"] == {"type": "hourly"}
    assert action["response_variable"] == "forecast"
    assert block["binary_sensor"][0]["default_entity_id"] == HOT_DAY
    now = datetime.datetime(2026, 7, 1, 6, 0)
    assert hot_day([(9, 20, 10), (12, 25, 20), (15, 26, 30)], now)
    assert not hot_day([(9, 20, 10), (12, 24, 20), (15, 23, 30)], now)
    assert not hot_day([(9, 20, 40), (12, 25, 40), (15, 26, 30)], now)
    # Tomorrow's heat doesn't count
    assert not hot_day([(12, 22, 10), (36, 30, 10)], now)
    assert not hot_day([], now)
LIVING_ROOM_LUX = "sensor.wohnzimmer_lichtsensor_wohnzimmer"
LIVING_ROOM_TEMPERATURE = "sensor.wohnzimmer_wohnzimmer_2"


def heat_needed(lux, temperature):
    """The heat protection sensor's state with ioBroker's thresholds (30000/35000 lx, 23/26 °C)."""
    sensor = next(e for _, e in template_entities(package("shutters")) if e["default_entity_id"] == HEAT)
    states = {LIVING_ROOM_LUX: lux, LIVING_ROOM_TEMPERATURE: temperature,
              "input_number.shutter_brightness": "30000.0", "input_number.shutter_brightness_max": "35000.0",
              "input_number.shutter_temperature": "23.0", "input_number.shutter_temperature_max": "26.0"}
    return render(sensor["state"], states=lambda entity: states.get(entity, "unknown")) == "True"


def test_heat_protection_follows_the_living_room_like_node_red():
    """Node-RED's "Close shutters based on sensor data": very bright, or very warm, or bright and warm."""
    assert heat_needed("36000", "20")
    assert heat_needed("1000", "27")
    assert heat_needed("31000", "24")
    assert not heat_needed("31000", "22")
    assert not heat_needed("29000", "24")
    assert not heat_needed("1000", "20")


def test_heat_protection_without_a_sensor_uses_the_other():
    """The temperature sensor's battery may be empty: its rules drop out, brightness alone still counts."""
    assert heat_needed("36000", "unavailable")
    assert not heat_needed("31000", "unavailable")
    assert heat_needed("unavailable", "27")
    assert not heat_needed("unavailable", "unavailable")


def test_heat_protection_half_opens_the_eastern_shutters_in_the_morning():
    """Node-RED checked every 5 minutes from 8 to 13; here from 8, and whenever it turns on until 13. Moved by hand
    stays: no override."""
    heat = automation("shutters", "shutters_heat_protection")
    assert {(t["trigger"], t.get("entity_id"), t.get("to"), t.get("at")) for t in heat["triggers"]} == {
        ("state", HEAT, "on", None), ("time", None, None, "08:00:00")}
    assert heat["conditions"] == [
        {"condition": "time", "after": "08:00:00", "before": "13:00:00"},
        {"condition": "state", "entity_id": HEAT, "state": "on"}]
    assert shutter_calls(heat["actions"]) == [(s, "half_open", False) for s in ("garden", "kitchen", "bedroom")]


def test_eastern_shutters_open_before_solar_noon():
    noon = automation("shutters", "shutters_noon")
    template = noon["triggers"][0]["value_template"]
    assert "next_noon" in template and "minutes=10" in template
    assert shutter_calls(noon["actions"]) == [(s, "open", True) for s in ("bedroom", "garden", "kitchen")]


def test_the_office_shutter_opens_at_golden_hour():
    """Unless moved by hand: no override."""
    afternoon = automation("shutters", "shutters_office_afternoon")
    assert [sun_trigger(t) for t in afternoon["triggers"]] == [("numeric_state", "sun.sun", "elevation", None, 6)]
    assert shutter_calls(afternoon["actions"]) == [("office", "open", False)]


def test_the_bedroom_shutter_closes_at_nautical_dusk_and_at_ten_unless_mostly_closed():
    night = automation("shutters", "shutters_bedroom_night")
    triggers = {t["id"]: t for t in night["triggers"]}
    assert sun_trigger(triggers["nautical_dusk"]) == ("numeric_state", "sun.sun", "elevation", None, -12)
    assert triggers["ten"] == {"trigger": "time", "at": "22:00:00", "id": "ten"}
    assert night["conditions"] == [{"condition": "numeric_state", "entity_id": COVERS["bedroom"],
                                    "attribute": "current_position", "above": 70}]
    assert shutter_calls(night["actions"]) == [("bedroom", "closed", True)]


def test_the_terrace_door_opens_its_shutter_and_closing_it_returns_the_shutter():
    opened = automation("shutters", "shutters_terrace_door_opened")
    assert opened["triggers"] == [{"trigger": "state", "entity_id": TERRACE_DOOR, "to": "on"}]
    assert shutter_calls(opened["actions"]) == [("terrace", "open", True)]
    assert opened["actions"][0]["data"]["keep_target"] is True
    closed = automation("shutters", "shutters_terrace_door_closed")
    assert closed["triggers"] == [{"trigger": "state", "entity_id": TERRACE_DOOR, "from": "on", "to": "off"}]
    position = closed["actions"][0]["data"]["position"]
    assert "input_number.shutter_terrace_target" in position
    assert shutter_calls(closed["actions"]) == [("terrace", position, True)]
    assert closed["actions"][0]["data"]["keep_target"] is True


def test_the_home_dashboard_moves_and_locks_every_shutter():
    text = (CONFIG_DIR / "dashboards" / "home.yaml").read_text()
    for shutter, cover in COVERS.items():
        assert cover in text and f"input_boolean.shutter_{shutter}_locked" in text, shutter
    assert "input_boolean.guests" in text


def test_every_shutter_has_a_twin_on_testbench():
    twins = {e["default_entity_id"] for _, e in template_entities(virtual_devices())}
    assert set(COVERS.values()) | {TERRACE_DOOR} <= twins


# Device status, replacing Grafana's "Device status" dashboard: unreachable devices, battery levels and the
# Shellies' warnings. The counts find devices by integration, so a new device counts without an edit here.
DEVICE_STATES = {
    # entity: (integration, device, state, device_class)
    "light.wohnzimmer_dekolights": ("deconz", "dekolights", "unavailable", None),
    "sensor.wohnzimmer_wohnzimmer_2": ("deconz", "climate", "unavailable", "temperature"),
    "sensor.wohnzimmer_wohnzimmer": ("deconz", "climate", "unavailable", "humidity"),
    "sensor.wohnzimmer_wohnzimmer_battery": ("deconz", "climate", "unavailable", "battery"),
    "sensor.buro_button_battery": ("deconz", "button", "16", "battery"),
    "sensor.flur_switch_battery": ("deconz", "switch", "34", "battery"),
    "switch.bad_on_off_schuhheizung": ("deconz", "shoes", "unavailable", None),
    "cover.buro_shutter_office": ("shelly", "shutter", "open", "shutter"),
    "binary_sensor.buro_shutter_office_uberhitzung": ("shelly", "shutter", "on", "problem"),
    "binary_sensor.buro_shutter_office_uberlast": ("shelly", "shutter", "off", "problem"),
    "media_player.bad_bad": ("sonos", "sonos", "unavailable", None),
    "sensor.phone_battery_level": ("mobile_app", "phone", "5", "battery"),
    "binary_sensor.fritz_box_7490_verbindung": ("fritz", "fritz", "unavailable", "connectivity"),
}


def render_device_template(template):
    env = jinja2.Environment()
    env.filters["device_id"] = lambda entity: DEVICE_STATES[entity][1]
    env.filters["states"] = lambda entity: DEVICE_STATES[entity][2]
    env.filters["float"] = lambda value, default=0.0: float(value) if value.replace(".", "").isdigit() else default
    env.tests["is_state"] = lambda entity, state: DEVICE_STATES[entity][2] == state
    env.tests["is_state_attr"] = (
        lambda entity, name, value: name == "device_class" and DEVICE_STATES[entity][3] == value)
    env.tests["match"] = lambda value, pattern: re.match(pattern, value) is not None
    env.tests["none"] = lambda value: value is None

    def integration_entities(integration):
        return [e for e, (i, *_) in DEVICE_STATES.items() if i == integration]

    return env.from_string(template).render(integration_entities=integration_entities).strip()


def device_sensors():
    return {e["default_entity_id"]: e for _, e in template_entities(package("devices"))}


def test_unreachable_devices_count_devices_not_entities():
    """Three unavailable entities of one device count once; the unplugged shoe heating is no fault, the FRITZ!Box no
    house device."""
    assert render_device_template(device_sensors()["sensor.unreachable_devices"]["state"]) == "3"


def test_battery_sensors_count_the_house_devices_only():
    """deCONZ's batteries; a phone's battery is no device of the house."""
    sensors = device_sensors()
    assert render_device_template(sensors["sensor.low_batteries"]["state"]) == "1"
    assert float(render_device_template(sensors["sensor.lowest_battery"]["state"])) == 16
    assert sensors["sensor.lowest_battery"]["device_class"] == "battery"


def test_shelly_warnings_count_their_problem_sensors_that_are_on():
    assert render_device_template(device_sensors()["sensor.device_warnings"]["state"]) == "1"


def device_dashboard():
    return yaml.safe_load((CONFIG_DIR / "dashboards" / "devices.yaml").read_text())


def dashboard_cards(dashboard):
    return [card for view in dashboard["views"] for section in view.get("sections", [])
            for card in section["cards"]]


def test_the_devices_dashboard_is_a_built_in_sections_view():
    dashboard = configuration()["lovelace"]["dashboards"]["dashboard-devices"]
    assert dashboard["mode"] == "yaml"
    assert dashboard["filename"] == "dashboards/devices.yaml"
    text = (CONFIG_DIR / "dashboards" / "devices.yaml").read_text()
    assert "custom:" not in text
    assert [view["type"] for view in device_dashboard()["views"]] == ["sections"]
    for sensor in device_sensors():
        assert sensor in text, sensor


def test_device_tiles_show_only_while_something_is_wrong():
    """Unreachable devices and low batteries show up as tiles of their own; the rest of the time those sections only
    say that all is well."""
    reachability, low = [], []
    for card in dashboard_cards(device_dashboard()):
        for condition in card.get("visibility", []):
            if card["type"] == "tile" and condition.get("state") == "unavailable":
                assert condition["entity"] == card["entity"]
                reachability.append(card["entity"])
            if card["type"] == "tile" and condition.get("below") == 20:
                assert condition["entity"] == card["entity"]
                low.append(card["entity"])
    assert len(reachability) == len(set(reachability)) > 40
    assert "switch.bad_on_off_schuhheizung" not in reachability
    assert len(low) == len(set(low)) > 15
    assert all(entity.endswith("_battery") for entity in low)


def test_the_devices_dashboard_holds_no_personal_devices():
    """Phones and their trackers carry their owners' names."""
    text = "".join((CONFIG_DIR / folder / "devices.yaml").read_text() for folder in ("dashboards", "packages"))
    assert "device_tracker." not in text and "mobile_app" not in text


# Sonos, replacing Node-RED's "Stop Sonos": the living room Amp's power outlet follows presence, and a button skips.
SONOS_SPEAKERS = ["media_player.wohnzimmer_wohnzimmer", "media_player.buro_buro", "media_player.bad_bad"]
SONOS_OUTLET = "switch.wohnzimmer_on_off_sonos"


def test_arriving_powers_the_sonos_amp():
    on = automation("sonos", "sonos_power_on")
    assert [(t["entity_id"], t["to"]) for t in on["triggers"]] == [("binary_sensor.someone_home", "on")]
    assert on["actions"] == [{"action": "switch.turn_on", "target": {"entity_id": SONOS_OUTLET}}]


def test_sonos_stop_and_power_off_15_minutes_after_everyone_left():
    """Also after a restart while nobody is home, since a trigger's for: doesn't survive one. The speakers stop before
    the amp loses its power."""
    off = automation("sonos", "sonos_off_when_away")
    away = next(t for t in off["triggers"] if t["trigger"] == "state")
    assert (away["entity_id"], away["to"], away["for"]) == ("binary_sensor.someone_home", "off", {"minutes": 15})
    assert {"trigger": "homeassistant", "event": "start"} in off["triggers"]
    assert off["conditions"] == [{"condition": "state", "entity_id": "binary_sensor.someone_home", "state": "off"}]
    stop, power = off["actions"]
    assert stop == {"action": "media_player.media_stop", "continue_on_error": True,
                    "target": {"entity_id": SONOS_SPEAKERS}}
    assert power == {"action": "switch.turn_off", "target": {"entity_id": SONOS_OUTLET}}


def test_the_skip_button_plays_the_next_track_in_the_living_room():
    skip = automation("sonos", "sonos_skip_track")
    assert [t["event_type"] for t in skip["triggers"]] == ["deconz_event"]
    assert skip["triggers"][0]["event_data"] == {"unique_id": "84:ba:20:ff:fe:ca:e8:ba", "event": 1002}
    assert skip["actions"] == [{"action": "media_player.media_next_track",
                                "target": {"entity_id": "media_player.wohnzimmer_wohnzimmer"}}]
