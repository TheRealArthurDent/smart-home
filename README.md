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

`deploy.sh` is the old bash deployment, kept as a fallback until the playbook has proven itself (#7).

Secrets come from KeePass: [raspberry](https://github.com/TheRealArthurDent/raspberry)'s `secrets` role renders
`/etc/docker/smart-home/.env` on the Pi. `setup/.env.example` lists its keys. Notes for Claude Code are in
`CLAUDE.md`.

### local setup

1. Change to folder local-setup
2. Execute 'sudo bash setup.sh'
3. Return to root folder
4. Execute 'sudo bash run.sh'
5. Be happy

### iobroker cheat sheet
## upgrade
from raspi:
docker exec -it -u iobroker iobroker /bin/bash

maintenance --help
maintenance on
...
maintenance off
