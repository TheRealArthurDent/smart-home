#!/bin/bash

ARTIFACT=smart-home

echo "Deploying $ARTIFACT to raspberry pi..."

TARGET_FOLDER=dev/$ARTIFACT

ssh pi@raspi -p 1357 'mkdir -p ~/dev/smart-home/setup'
scp -P 1357 ../docker-compose.yaml pi@raspi:~/$TARGET_FOLDER
scp -P 1357 ../run.sh pi@raspi:~/$TARGET_FOLDER
# TODO remove the string "--env-file $ENV_FILE " from this file, because raspi's version of docker-compose doesn't know that yet
ssh pi@raspi -p 1357 "cd ~/dev/smart-home && pwd && sed -i -e 's/--env-file \$ENV_FILE //g' run.sh"

scp -P 1357 -r ../setup/mosquitto/ pi@raspi:~/$TARGET_FOLDER/setup
scp -P 1357 -r ../setup/telegraf/ pi@raspi:~/$TARGET_FOLDER/setup
scp -P 1357 ../setup/setup.sh pi@raspi:~/$TARGET_FOLDER/setup

ssh pi@raspi -p 1357 'cd ~/dev/smart-home/setup && pwd && sudo bash setup.sh && cd .. && sudo bash run.sh'
