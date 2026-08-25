#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ -f "$ENV_FILE" ]; then
    export DOCKER_CLIENT_TIMEOUT=240
    export COMPOSE_HTTP_TIMEOUT=240

    ionice -c 3 nice -n 10 docker compose --env-file $ENV_FILE config --services | while read service; do
      ionice -c 3 nice -n 10 docker compose --env-file $ENV_FILE pull "$service"
    done
    ionice -c 3 nice -n 10 docker compose --env-file $ENV_FILE up -d
else
    echo "$ENV_FILE does not exist."
fi
