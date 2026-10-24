---
name: working-with-the-stack
description: Use when a task in this repo changes or rolls out the smart-home Docker stack (docker-compose.yaml, setup/, ansible/, Grafana provisioning, Mosquitto, Telegraf, ioBroker, deCONZ, InfluxDB), deploys to testbed or raspi, or when deciding what can be checked from a cloud container and what the user has to run themselves.
---

# Working with the smart-home stack

## Overview

This stack runs the real smart home (Zigbee, MQTT, ioBroker automations, history in InfluxDB) on a Pi that only
machines in the home network can reach. It sits on top of raspberry's infrastructure stack: the networks `siz`
and `outbound`, the nginx vhosts, certificates, backups and `/etc/docker/smart-home/.env` all come from there.
Know before you start what you can verify yourself, what only CI can, and what only the user can run.

## Who can run what

First find out where you run: a cloud container (claude.ai/code) or a local session on the user's machine.

| Check | Cloud container | Local session | CI |
|---|---|---|---|
| pytest (`tests/`), pre-commit | yes | yes | pytest yes |
| `dashboard-linter lint --strict` on a dashboard | only if the binary can be downloaded | yes | yes |
| Molecule (`ansible/molecule/default`) | rarely: needs a Docker daemon, and the image build needs deb.debian.org, which the proxy may refuse | yes | yes |
| `ansible-lint --strict` | if `ansible/requirements.yaml` installs (Galaxy may be blocked; `pip install ansible==<version>` ships the collections) | yes | yes |
| `docker compose config` | only with a dummy env file (copy `setup/.env.example`, fill dummy values) | same | no |
| Deploy to testbed | **no**: the 192.168.1.x LAN is only reachable from the home network | **only after asking**, every time | no |
| Deploy to raspi | no | **no**: hand the user the commands | no |

In a cloud container, don't probe the LAN to find this out again. `.claude/hooks/guard.py` blocks
`ansible-playbook` against raspi or without `--limit`, and ssh to raspi; when it blocks something, hand the user the command
instead of looking for another way to run it.

## Order of work

1. **Plan first.** Give the user a short plan summary (what, which files, how tested) and check the related
   open issue. Answer in the user's language.
2. **Branch off `main`, PR into `main`**, never push to `main`. Commit style `fix:`/`feat:` + `Refs #<n>`.
3. **Test first** where pytest can express it, then let CI run and drive it green.
4. **Hand the user the rollout**, testbed before raspi, and say what to look for:

```sh
cd ansible
../.venv/bin/ansible-playbook deploy.yaml --limit testbed --check --diff
../.venv/bin/ansible-playbook deploy.yaml --limit testbed      # then once more: must report changed=0
ssh -p 4242 testuser@192.168.1.7 'docker ps --format "{{.Names}}\t{{.Status}}"'   # all containers up/healthy
../.venv/bin/ansible-playbook deploy.yaml --limit raspi --check --diff   # raspi, only after the user says so
```

## Things that look wrong but aren't (and traps)

- **raspberry first.** The role stops when `/etc/docker/smart-home/.env` or the external networks `siz` and
  `outbound` are missing. On a fresh Pi, the user runs raspberry's `bootstrap.yaml` before `deploy.yaml`.
- **A new secret needs three places**: the key in `setup/.env.example`, the line in raspberry's
  `ansible/roles/secrets/tasks/main.yaml` (with `no_log: true`), and its KeePass lookup in raspberry's
  `bootstrap.yaml`. Reference it here as `${VAR}`; never write a value into the repo.
- **A new web UI needs raspberry**: nginx vhost, Pi-hole CNAME and certificate SAN are all in raspberry. The
  container joins the `siz` network here.
- **The Mosquitto password file** is kept by the role while its entry matches `MOSQUITTO_PASSWD` (the
  `mosquitto_passwd` filter re-checks the hash), and rewritten only when the password changed. It belongs to
  uid 1883 (Mosquitto inside the container); the host has no such user, which check mode warns about.
- **Telegraf reads its passwords from the environment** (`$INFLUXDB_WRITE_PASSWORD`, `$MOSQUITTO_PASSWD` in
  `telegraf.conf`, passed by Compose); the file holds no secrets.
- **testbed has no ConBee stick**: `compose up` fails on the missing `/dev/ttyACM0`, so the inventory leaves
  deconz out there (`smart_home_disabled_services`). An unknown name in that list fails the run.
- **A container stopped by hand stays stopped**: the role leaves an exited container out of `compose up` and its
  restart handler and prints a `[WARNING]`. To bring it back, `docker start <name>`, then deploy again. Containers
  of the project the role doesn't manage (service gone from the compose file, or disabled) also get a warning and
  are left alone.
- **Memory limits are discarded on the Pi** ("kernel does not support memory limit capabilities"): Raspberry Pi
  OS boots without the memory cgroup unless `cmdline.txt` enables it, so `mem_limit` in the compose file has no effect.
- **Grafana doesn't rescan dashboards** (`updateIntervalSeconds: 0`, it caused I/O spikes). Changed dashboard
  JSON takes effect after `docker restart grafana`. `allowUiUpdates: false`: edits in the UI are lost, the JSON
  in `grafana-provisioning/dashboards/provisioned/` is the source of truth.
- **Removing an alert rule** from the YAML doesn't delete it in Grafana; use a `deleteRules` entry
  (template in `grafana-provisioning/alerting/00_delete-rules.yaml`).
- **Dashboard lint exclusions** are in `grafana-provisioning/dashboards/provisioned/.lint`; add an entry with a
  reason instead of weakening the CI step.
- **Dashboard links point to `grafana.raspi`**; on testbed they lead to production.
- **Container names are fixed** (`container_name:`), and the role sets the Compose project name `smart-home` (the
  name the bash deployment's folder gave it). Any other name would start a second project whose names collide.
- **Images are pinned** and Renovate updates them; deCONZ and the firmware downloader are pinned by digest.
  Redis uses the `arm64v8/` image, so it won't run on an amd64 CI runner.

## Reporting back

End with: what changed (files, PR link), what you ran and its result, what CI showed on the head commit, and the
rollout commands the user still has to run, testbed before raspi.
