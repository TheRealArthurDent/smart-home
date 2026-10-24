"""The smart_home role lists the volumes raspberry's restic-restore brings back on a fresh host (#1).

smart_home_restore_volumes in the role's defaults holds the state that doesn't come from IaC. Every named volume
of docker-compose.yaml is either listed there or left out on purpose, and each listed volume names the services
that mount it: the role takes their container names for the restore helper and leaves out the volumes of
disabled services.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "ansible" / "roles" / "smart_home" / "defaults" / "main.yaml"

# Volumes a fresh host doesn't need back, and why
NOT_RESTORED = {
    # firmware-download fetches the IKEA firmware again
    "ikea-tradfri-firmware-storage",
}


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yaml").read_text())


def restore_volumes():
    return yaml.safe_load(DEFAULTS.read_text())["smart_home_restore_volumes"]


def mounting_services(volume):
    """The services of docker-compose.yaml that mount the named volume."""
    return sorted(
        name
        for name, service in compose()["services"].items()
        if any(str(mount).split(":")[0] == volume for mount in service.get("volumes", []))
    )


def test_every_named_volume_is_restored_or_left_out_on_purpose():
    volumes = set(compose()["volumes"])
    listed = set(restore_volumes())
    assert listed.isdisjoint(NOT_RESTORED)
    assert listed | NOT_RESTORED == volumes


def test_each_volume_names_the_services_that_mount_it():
    for volume, item in restore_volumes().items():
        assert sorted(item["services"]) == mounting_services(volume), volume


def test_each_volume_says_what_it_keeps_from_a_restore():
    """preserve lists the files inside the volume that raspberry's backup excludes (excludes.j2 there)."""
    for volume, item in restore_volumes().items():
        assert isinstance(item["preserve"], list), volume
        assert all(not pattern.startswith("/") for pattern in item["preserve"]), volume
        assert item["note"], volume


def test_iobroker_keeps_its_npm_cache():
    """raspberry's excludes.j2 leaves out smart-home_iobroker-storage/_data/.npm."""
    assert ".npm" in restore_volumes()["iobroker-storage"]["preserve"]
