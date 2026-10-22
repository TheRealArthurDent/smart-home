# smart-home
Setup for the smart home environment containing mqtt, iobroker and peripherals

[![Spell Check](https://github.com/TheRealArthurDent/smart-home/actions/workflows/spell-check.yaml/badge.svg)](https://github.com/TheRealArthurDent/smart-home/actions/workflows/spell-check.yaml)
[![Grafana Dashboard Lint](https://github.com/TheRealArthurDent/smart-home/actions/workflows/grafana-dashboard-lint.yaml/badge.svg)](https://github.com/TheRealArthurDent/smart-home/actions/workflows/grafana-dashboard-lint.yaml)

### Development

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pre-commit install
.venv/bin/pytest tests
```

### Deployment

[raspberry](https://github.com/TheRealArthurDent/raspberry)'s `bootstrap.yaml` must have run on the Pi first
(networks, nginx, secrets). Then, from `ansible/`:

```sh
../.venv/bin/ansible-galaxy collection install -r requirements.yaml
../.venv/bin/ansible-playbook deploy.yaml --limit testbed --check --diff
../.venv/bin/ansible-playbook deploy.yaml --limit testbed
```

Secrets come from KeePass: [raspberry](https://github.com/TheRealArthurDent/raspberry)'s `secrets` role renders
`/etc/docker/smart-home/.env` on the Pi. `setup/.env.example` lists its keys. Notes for Claude Code are in
`CLAUDE.md`.

### iobroker cheat sheet
## upgrade
from raspi:
docker exec -it -u iobroker iobroker /bin/bash

maintenance --help
maintenance on
...
maintenance off
