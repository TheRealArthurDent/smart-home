# smart-home – the smart home application stack on Raspberry Pi

Docker Compose stack for the smart home itself: ioBroker (with two Redis instances for states and objects),
deCONZ (Zigbee) plus the IKEA firmware downloader, InfluxDB, Telegraf, Grafana (provisioned dashboards and
alerting) and Mosquitto (MQTT). It runs on the same Raspberry Pi (Debian/Raspberry Pi OS trixie, arm64) as the
infrastructure stack from [raspberry](https://github.com/TheRealArthurDent/raspberry).

## State of the repo

- **Deployment is bash**: `deploy.sh <target>` copies the stack to the Pi as a tarball, then runs
  `setup/setup.sh` (config files, Mosquitto password file, Telegraf config with passwords substituted) and
  `run.sh` (`docker compose pull` + `up -d`) there. There is no Ansible here yet.
- **raspberry provides what this stack depends on**: the external Docker networks `siz` (nginx reverse proxy)
  and `outbound` (internet via Pi-hole), the nginx vhosts (`grafana.<host>`, `iobroker.<host>`, …), the
  certificates, the restic backups, and the secrets file `/etc/docker/smart-home/.env` (raspberry's `secrets`
  role renders it from KeePass). Without raspberry's bootstrap on the host, this stack doesn't start.
- raspberry is migrating its own deployment to Ansible (raspberry#238). New deployment logic for this stack belongs
  there too, so don't extend the bash scripts beyond fixes; propose an Ansible change in raspberry instead.

Check the open issues before changing an affected area (e.g. #276, clean-slate restore from the restic backup),
and reference them in commits.

## Layout

- `docker-compose.yaml` – the stack; images pinned, updated by Renovate (`renovate.json`)
- `deploy.sh`, `run.sh`, `setup_and_run.sh`, `setup/setup.sh` – bash deployment
- `setup/` – config copied to `/etc/docker/smart-home/` (mosquitto, telegraf, iobroker first-start script);
  `setup/.env.example` lists the keys of the secrets file, without values
- `grafana-provisioning/` – Grafana datasources, dashboards (`dashboards/provisioned/*.json`, linted in CI with
  `dashboard-linter`, exclusions in `.lint`) and alerting (rules, contact points, templates)
- `doc/` – notes on the measurement concept
- `tests/` – pytest tests (Claude hook, rulesets, repo hygiene)
- `.claude/` – Claude Code settings, the guard hook (`hooks/guard.py`) and skills
- `.github/rulesets/` + `scripts/rulesets.sh` – rulesets for `main`, applied by the user (`rulesets.sh apply`)

## Hosts

| Host | Purpose |
| --- | --- |
| `raspi` (192.168.1.2) | **Production** smart home, `deploy.sh`'s default target. Only the user deploys to it; hand them the commands. |
| `testbed` (192.168.1.7) | Test Pi, reachable only from the home network: propose `./deploy.sh testbed 4242 testuser` to the user. |

`himbeere` and `erdbeere` in `deploy.sh` are former Pis.

A `PreToolUse` hook (`.claude/hooks/guard.py`, tests in `tests/test_guard_hook.py`) blocks the risky actions for
Claude: `deploy.sh` without `testbed`, `setup_and_run.sh`, ssh/scp/rsync to raspi, pushes to `main`, force pushes,
PR merges, `git add -f`, committing or printing `.env` files, and edits to the hook and settings themselves.
Don't work around a block; give the user the command or the proposed change instead.

## Secrets

The stack's passwords (InfluxDB, Grafana, Mosquitto, deCONZ VNC, Redis ports) live in KeePass and reach the Pi as
`/etc/docker/smart-home/.env` through raspberry's `secrets` role. `setup/setup.sh` substitutes some of them into
the Telegraf config and the Mosquitto password file. Never commit a `.env` file, never read or print one, and
never put secret values into config files in this repo; reference `${VAR}` from the env file instead. A new key
goes into `setup/.env.example` here and into raspberry's `secrets` role and KeePass lookups.

## Commands

Tooling lives in a venv at the repo root:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pre-commit install
.venv/bin/pytest tests                                  # unit tests
.venv/bin/pre-commit run --all-files                    # whitespace, YAML, gitleaks, renovate config, actionlint
```

CI runs on every PR: unit tests (`tests.yaml`), Grafana dashboard lint, codespell, and reviewdog (misspell,
actionlint, yamllint, markdownlint). Required checks for `main` are in `.github/rulesets/`; a required job must
run on every PR (no `paths` filter), or `tests/test_rulesets.py` fails.

## Conventions

- Commit messages: conventional style (`feat:`, `fix:`, `test:`, `chore:`), referencing issues (`Refs #276`).
- Never commit or push to `main`. Branch off `main` and open a PR into `main`; the user merges.
- Container images in `docker-compose.yaml` are pinned and updated by Renovate; keep them pinned (deCONZ and
  the firmware downloader by digest).
- Work test-driven, unless something speaks against it (then say why): write the test first and watch it fail
  for the right reason. Dashboards and alerting are checked by the linters in CI, not by pytest.
- YAML files use the `.yaml` extension, not `.yml`, unless a tool requires a fixed name.
- Everything in the repo is written in English (code, comments, docs, commit messages), even when the user
  chats in German.

## Working with the user

- Before changing code, give a short plan summary (what, which files, how tested).
- Answer in the language of the user's message (German or English); the repo itself stays English.
- Before deploying or changing anything on a Pi, read `.claude/skills/working-with-the-stack/SKILL.md`.
- Whenever a task would benefit from a skill you don't have, say so: which skill, what it would be for, and
  whether a ready-made one exists or it would have to be written.
