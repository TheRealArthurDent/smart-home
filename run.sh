#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ -f "$ENV_FILE" ]; then
    docker-compose --env-file $ENV_FILE up -d
else
    echo "$ENV_FILE does not exist."
fi