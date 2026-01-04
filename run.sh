#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ -f "$ENV_FILE" ]; then
    export DOCKER_BUILDKIT=1
    export DOCKER_CLIENT_TIMEOUT=180
    export COMPOSE_HTTP_TIMEOUT=180
    export COMPOSE_DOCKER_CLI_BUILD=1

    docker buildx use custom-builder
    docker compose build

    docker compose pull
    docker compose --env-file $ENV_FILE up -d
else
    echo "$ENV_FILE does not exist."
fi
