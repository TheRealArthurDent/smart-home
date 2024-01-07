#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ -f "$ENV_FILE" ]; then
    docker-compose pull
    docker-compose --env-file $ENV_FILE up -d --build
else
    echo "$ENV_FILE does not exist."
fi
