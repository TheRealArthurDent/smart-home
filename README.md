# smart-home

Setup for the smart home environment containing mqtt, iobroker and peripherals

[![Spell Check](https://github.com/TheRealArthurDent/smart-home/actions/workflows/spell-check.yaml/badge.svg)](https://github.com/TheRealArthurDent/smart-home/actions/workflows/spell-check.yaml)
[![Grafana Dashboard Lint](https://github.com/TheRealArthurDent/smart-home/actions/workflows/grafana-dashboard-lint.yaml/badge.svg)](https://github.com/TheRealArthurDent/smart-home/actions/workflows/grafana-dashboard-lint.yaml)

Contents:

- [Overview](#overview)
- [Development](#development)
- [Deployment](#deployment)
  - [Control node setup (once)](#control-node-setup-once)
  - [Deploy](#deploy)
- [Disaster recovery](#disaster-recovery)
  - [raspi is gone (new SSD, reinstall)](#raspi-is-gone-new-ssd-reinstall)
  - [One service lost its data](#one-service-lost-its-data)
  - [Check the stack](#check-the-stack)
- [ioBroker cheat sheet](#iobroker-cheat-sheet)

## Overview

`docker-compose.yaml` runs ioBroker (with two Redis instances for states and objects), deCONZ (Zigbee, ConBee stick)
with the IKEA firmware downloader, InfluxDB, Telegraf, Grafana and Mosquitto on `raspi`. The Ansible role
`smart_home` (`ansible/`) copies the compose file, `setup/` and `grafana-provisioning/` to `/etc/docker/smart-home/`
and runs `docker compose up` as project `smart-home`.

The stack depends on [infrastructure](https://github.com/TheRealArthurDent/infrastructure), whose `bootstrap.yaml`
must have run on the host first: it provides Docker, the networks `siz` and `outbound`, nginx with the vhosts
(`https://grafana.raspi`, `https://iobroker.raspi`, `https://deconz.raspi`, ...), the certificate, the restic
backups with the restore helper `restic-restore`, and the secrets file `/etc/docker/smart-home/.env` (rendered from
KeePass; `setup/.env.example` lists its keys). Notes for Claude Code are in `CLAUDE.md`.

| Host | IP | SSH port | User |
| --- | --- | --- | --- |
| `raspi` | 192.168.1.2 | 1357 | `smarthome` (production) |
| `testbed` | 192.168.1.7 | 4242 | `testuser` (no ConBee stick, so deCONZ stays off) |

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pre-commit install
.venv/bin/pytest tests
```

## Deployment

### Control node setup (once)

In the repo root, then in `ansible/`:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ansible
../.venv/bin/ansible-galaxy collection install -r requirements.yaml
```

The playbook uses the SSH key `~/.ssh/id_ed25519` (`inventory/hosts.yaml`) and needs no KeePass: it only reads the
`.env` that infrastructure put on the host.

### Deploy

In `ansible/`. `deploy.yaml` refuses to run without `--limit <one host>`. Dry run first, then the real run; a second
run ends with `changed=0`:

```sh
../.venv/bin/ansible-playbook deploy.yaml --limit raspi --check --diff
../.venv/bin/ansible-playbook deploy.yaml --limit raspi
```

What the role does on every run: it keeps the Mosquitto password file in line with `MOSQUITTO_PASSWD` from the
`.env`, copies the config (and removes files the repo dropped), restores the volumes on a fresh host (see
[raspi is gone](#raspi-is-gone-new-ssd-reinstall)) and runs `docker compose up`. A container stopped by hand stays
stopped and only produces a warning. Services listed in `smart_home_disabled_services` (`inventory/hosts.yaml`) are
left out, e.g. `deconz` on testbed.

## Disaster recovery

Backups: infrastructure's resticprofile backs up `/home`, `/etc` and `/var/lib/docker/volumes` every night at 03:00
to `dungeon` (`/media/backup/restic/raspi`); rsnapshot keeps local copies under `/var/cache/backup/`. Config comes
from this repo and secrets from KeePass, so only the named volumes need a restore:

| Volume | Holds |
| --- | --- |
| `iobroker-storage` | ioBroker with its adapters, instances and scripts |
| `iobroker-states-redis-storage` | ioBroker's states (current values) |
| `iobroker-objects-redis-storage` | ioBroker's objects (configuration of adapters and devices) |
| `deconz-storage` | The Zigbee network (keys, paired devices); without it every device must be paired again |
| `influxdb-storage` | The measurement history |
| `grafana-storage` | Users, preferences and alert state (dashboards and alerting come from `grafana-provisioning/`) |
| `mosquitto-storage` | Retained messages and persistent sessions |

The list is `smart_home_restore_volumes` in `ansible/roles/smart_home/defaults/main.yaml`.

### raspi is gone (new SSD, reinstall)

1. Rebuild the host with infrastructure first: steps 1 to 6 of its
   [Set up a host](https://github.com/TheRealArthurDent/infrastructure/blob/main/ansible/README.md#set-up-a-host-new-install-or-after-a-crash)
   (flash, first boot, bootstrap, certificate and stack, Pi-hole). That also puts `/etc/docker/smart-home/.env` back.
2. Plug in the ConBee stick (deCONZ needs it at start).
3. On the control node, in `ansible/` of this repo. The dry run says which volumes it would restore from which
   snapshot; the real run restores them from the latest restic snapshot before `docker compose up` and writes the
   marker `/var/lib/restic-restore/smart-home.done`. The third run must end with `changed=0`.

   ```sh
   ../.venv/bin/ansible-playbook deploy.yaml --limit raspi --check --diff
   ../.venv/bin/ansible-playbook deploy.yaml --limit raspi
   ../.venv/bin/ansible-playbook deploy.yaml --limit raspi
   ```

4. Check that backups run again: resticprofile waits for the marker of every stack and says so in its log.

   ```sh
   ssh -p 1357 smarthome@192.168.1.2 docker logs resticprofile
   ```

5. [Check the stack](#check-the-stack).

How the restore decides: with the marker present it does nothing. Without the marker it restores only when all
volumes are empty or missing; if any volume holds data (a host that kept its disk) it only writes the marker. So a
second restore of a running host goes through [One service lost its data](#one-service-lost-its-data), not by
deleting the marker.

If the run fails:

- **Exit 10, restic can't reach the repository**: `dungeon` is down or refuses raspi's restic key. The key comes from KeePass
  (`Backup/Resticprofile SSH`); `dungeon` must list its public key in `backup_target_clients`. See step 4 of
  infrastructure's Set up a host. Then run `deploy.yaml` again.
- **Exit 11, no snapshot**: a new host with nothing to restore. Only then:

  ```sh
  ../.venv/bin/ansible-playbook deploy.yaml --limit raspi -e skip_smart_home_restore=true
  ```

- **The latest snapshot is already broken**: pick an older one on the Pi and restore that one (only works as long
  as the marker doesn't exist yet):

  ```sh
  ssh -p 1357 smarthome@192.168.1.2 sudo restic-restore --runner oneoff snapshots
  ../.venv/bin/ansible-playbook deploy.yaml --limit raspi -e smart_home_restore_snapshot=<id>
  ```

### One service lost its data

The host runs, but one volume is broken or was changed by accident (e.g. ioBroker objects, the Zigbee network, the
InfluxDB history). Restore just that volume with infrastructure's helper. On the Pi:

```sh
ssh -p 1357 smarthome@192.168.1.2
```

1. Pick a snapshot (restic snapshots are taken at 03:00; `daily.0` of rsnapshot is last night, no network needed):

   ```sh
   sudo restic-restore snapshots
   sudo restic-restore snapshots --from rsnapshot
   ```

2. Stage the volume (the item name is the volume name from the table above). This prints the staging directory and
   changes nothing else. Without `--snapshot` it takes the latest one:

   ```sh
   sudo restic-restore stage smart-home/iobroker-objects-redis-storage --snapshot <id>
   sudo restic-restore stage smart-home/deconz-storage --from rsnapshot --snapshot daily.1
   ```

3. See what would change, then apply. `apply` stops the volume's containers, puts the staged files in place and
   starts them again:

   ```sh
   sudo restic-restore diff <staging dir>
   sudo restic-restore apply <staging dir>
   ```

4. [Check the stack](#check-the-stack), then remove the staging directories:

   ```sh
   sudo restic-restore clean --all
   ```

ioBroker's data is spread over three volumes (`iobroker-storage` and the two Redis volumes). After a broken ioBroker
restore all three from the same snapshot, so they fit together. `sudo restic-restore --help` lists all commands;
infrastructure's [Restore](https://github.com/TheRealArthurDent/infrastructure/blob/main/ansible/README.md#restore)
section has the details.

### Check the stack

On the Pi, every container should be `Up` (and `healthy` where it has a healthcheck):

```sh
docker ps --filter label=com.docker.compose.project=smart-home --format 'table {{.Names}}\t{{.Status}}'
docker logs --tail 50 iobroker
docker logs --tail 50 deconz
```

Then open `https://iobroker.raspi`, `https://grafana.raspi` (recent values in the dashboards) and
`https://deconz.raspi` (Zigbee devices reachable).

## ioBroker cheat sheet

Upgrade, on raspi:

```sh
docker exec -it -u iobroker iobroker /bin/bash
maintenance --help
maintenance on
# ...
maintenance off
```
