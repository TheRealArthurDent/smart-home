# smart-home
Setup for the smart home environment containing mqtt, iobroker and peripherals

[![Spell Check](https://github.com/TheRealArthurDent/smart-home/actions/workflows/spell-check.yaml/badge.svg)](https://github.com/TheRealArthurDent/smart-home/actions/workflows/spell-check.yaml)

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
