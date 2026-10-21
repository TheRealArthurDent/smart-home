# smart-home – the smart home application stack on Raspberry Pi

Docker Compose stack for the smart home itself: ioBroker (with two Redis instances for states and objects),
deCONZ (Zigbee) plus the IKEA firmware downloader, InfluxDB, Telegraf, Grafana (provisioned dashboards and
alerting) and Mosquitto (MQTT). It runs on the same Raspberry Pi (Debian/Raspberry Pi OS trixie, arm64) as the
infrastructure stack from [raspberry](https://github.com/TheRealArthurDent/raspberry).

## State of the repo

- **Deployment is moving from bash to Ansible (#7)**: `ansible/deploy.yaml` with the role `smart_home` copies
  `docker-compose.yaml`, `setup/` and `grafana-provisioning/` to `/etc/docker/smart-home/` (no templated copies),
  keeps the Mosquitto password file in line with `.env` and runs `docker compose up` as project `smart-home`.
  The bash scripts (`deploy.sh` → `setup/setup.sh` → `run.sh`) stay as a fallback until the role has proven itself
  on testbed and raspi; then they get deleted. Don't extend them; put new deployment logic into the role.
- **raspberry provides what this stack depends on**: the external Docker networks `siz` (nginx reverse proxy)
  and `outbound` (internet via Pi-hole), the nginx vhosts (`grafana.<host>`, `iobroker.<host>`, …), the
  certificates, the restic backups, and the secrets file `/etc/docker/smart-home/.env` (raspberry's `secrets`
  role renders it from KeePass). Without raspberry's bootstrap on the host, this stack doesn't start.
- The role reads only `MOSQUITTO_PASSWD` from that `.env`; it has no KeePass access of its own. Telegraf gets its
  passwords as environment variables from Compose, so `telegraf.conf` holds none.

Open plans: #1 (clean-slate restore from the restic backup), #2 (migration from ioBroker and Node-RED to Home
Assistant, with MCP servers as sub-issues), #3 (voice commands, after #2) and #7 (deployment from bash to Ansible).
Check the open issues before changing an affected area, and reference them in commits.

The repo was recreated on 2026-10-21 with a cleaned history. Issues and PRs from before that live in the private
`TheRealArthurDent/smart-home-archive`; old commit messages already point there (`smart-home-archive#123`).
Never push from a clone of the old repo: it would bring back the old history.

## Layout

- `docker-compose.yaml` – the stack; images pinned, updated by Renovate (`renovate.json`)
- `ansible/` – `deploy.yaml`, `inventory/hosts.yaml`, `requirements.yaml` (collections), the role
  `roles/smart_home` (with the `mosquitto_passwd` filter in `filter_plugins/`) and its Molecule scenario
  `molecule/default/`
- `deploy.sh`, `run.sh`, `setup_and_run.sh`, `setup/setup.sh` – bash deployment (fallback, see above)
- `setup/` – config copied to `/etc/docker/smart-home/` (mosquitto, telegraf, iobroker first-start script);
  `setup/.env.example` lists the keys of the secrets file, without values
- `grafana-provisioning/` – Grafana datasources, dashboards (`dashboards/provisioned/*.json`, linted in CI with
  `dashboard-linter`, exclusions in `.lint`) and alerting (rules, contact points, templates)
- `doc/` – notes on the measurement concept
- `tests/` – pytest tests (Claude hook, rulesets, repo hygiene, `--limit` guard, Mosquitto filter, compose)
- `.claude/` – Claude Code settings, the guard hook (`hooks/guard.py`) and skills
- `.github/rulesets/` + `scripts/rulesets.sh` – rulesets for `main`, applied by the user (`rulesets.sh apply`)

## Hosts

| Host | Purpose |
| --- | --- |
| `raspi` (192.168.1.2) | **Production** smart home, `deploy.sh`'s default target. Only the user deploys to it; hand them the commands. |
| `testbed` (192.168.1.7) | Test Pi, reachable only from the home network: propose the commands to the user (`--check --diff`, real run, second run with `changed=0`). |

Always pass `--limit <host>` to `ansible-playbook`; `deploy.yaml` refuses to run without it.

`himbeere` and `erdbeere` in `deploy.sh` are former Pis.

A `PreToolUse` hook (`.claude/hooks/guard.py`, tests in `tests/test_guard_hook.py`) blocks the risky actions for
Claude: `deploy.sh` without `testbed`, `setup_and_run.sh`, ssh/scp/rsync to raspi, pushes to `main`, force pushes,
PR merges, `git add -f`, committing or printing `.env` files, and edits to the hook and settings themselves.
It doesn't cover `ansible-playbook --limit raspi` yet (proposed change pending); don't run it anyway.
Don't work around a block; give the user the command or the proposed change instead.

## Secrets

The stack's passwords (InfluxDB, Grafana, Mosquitto, deCONZ VNC, Redis ports) live in KeePass and reach the Pi as
`/etc/docker/smart-home/.env` through raspberry's `secrets` role. Compose passes them to the containers; the
`smart_home` role derives the Mosquitto password file from `MOSQUITTO_PASSWD` (tasks handling it need
`no_log: true`; Molecule's leak test fails on any `LEAKCANARY` value in the log). Never commit a `.env` file, never read or print one, and
never put secret values into config files in this repo; reference `${VAR}` from the env file instead. A new key
goes into `setup/.env.example` here and into raspberry's `secrets` role and KeePass lookups.

## Commands

Tooling lives in a venv at the repo root:

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pre-commit install
.venv/bin/pytest tests                                  # unit tests (the --limit guard tests need ansible/requirements.yaml installed)
(cd ansible && ../.venv/bin/ansible-galaxy collection install -r requirements.yaml)
(cd ansible && ../.venv/bin/molecule test)             # role test in a trixie container, needs Docker, ~2 min
(cd ansible && ../.venv/bin/ansible-lint --strict)     # must report 0 findings (CI blocks)
.venv/bin/pre-commit run --all-files                    # whitespace, YAML, gitleaks, renovate config, actionlint
```

When writing or changing the Ansible role, follow raspberry's `ansible-role` skill
(`.claude/skills/ansible-role/SKILL.md` there): FQCN, `no_log`, idempotence, a `verify.yaml` check per change.

CI runs on every PR: unit tests (`tests.yaml`), Ansible lint and Molecule (`ansible.yaml`), Grafana dashboard lint, codespell, and reviewdog (misspell,
actionlint, yamllint, markdownlint). Required checks for `main` are in `.github/rulesets/`; a required job must
run on every PR (no `paths` filter), or `tests/test_rulesets.py` fails.

## Conventions

- Commit messages: conventional style (`feat:`, `fix:`, `test:`, `chore:`), referencing issues (`Refs #1`).
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
