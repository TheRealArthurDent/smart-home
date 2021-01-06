#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ ! -f "$ENV_FILE" ]; then
    echo "$ENV_FILE does not exist."
    exit 1
fi

docker-compose --env-file /etc/docker/smart-home/.env up -d