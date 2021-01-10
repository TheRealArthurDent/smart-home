#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ "$1" == "local" ]; then
  mkdir -p /etc/docker/smart-home
  cp .env $ENV_FILE
  chmod 600 $ENV_FILE
else
  if [ ! -f "$ENV_FILE" ]; then
    echo "WARNING: Global env file $ENV_FILE does not exist. Installation will not work."
  fi
fi

MOSQUITTO_PATH=/etc/docker/smart-home/mosquitto
mkdir -p $MOSQUITTO_PATH
cp mosquitto.conf $MOSQUITTO_PATH/mosquitto.conf
chmod 600 $MOSQUITTO_PATH/mosquitto.conf

MOSQUITTO_PASSWD_FILE=$MOSQUITTO_PATH/passwd
if [ ! -f "$MOSQUITTO_PASSWD_FILE" ]; then
  read -rsp "Enter mosquitto user's passwd: " PASSWD
  echo
  docker run eclipse-mosquitto:1.6 /bin/sh -c "touch /tmp/passwd && mosquitto_passwd -b /tmp/passwd mosquitto $PASSWD && cat /tmp/passwd && rm /tmp/passwd" > $MOSQUITTO_PASSWD_FILE
fi

mkdir -p /var/lib/smart-home/grafana
chmod -R 777 /var/lib/smart-home/grafana

mkdir -p /opt/mosquitto/data/
mkdir -p /var/log/mosquitto