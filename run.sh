#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ -f "$ENV_FILE" ]; then
    export DOCKER_CLIENT_TIMEOUT=180
    export COMPOSE_HTTP_TIMEOUT=180

    docker compose pull
    docker compose --env-file $ENV_FILE up -d
else
    echo "$ENV_FILE does not exist."
fi
