#!/bin/bash

mkdir -p /etc/docker/smart-home
cp .env /etc/docker/smart-home/.env
chmod 600 /etc/docker/smart-home/.env

MOSQUITTO_PATH=/etc/docker/smart-home/mosquitto
mkdir -p $MOSQUITTO_PATH
cp mosquitto.conf $MOSQUITTO_PATH/mosquitto.conf
chmod 600 $MOSQUITTO_PATH/mosquitto.conf

MOSQUITTO_PASSWD_FILE=$MOSQUITTO_PATH/passwd
if [ ! -f "$MOSQUITTO_PASSWD_FILE" ]; then
  read -rsp "Enter passwd: " PASSWD
  echo
  docker run eclipse-mosquitto:1.6 /bin/sh -c "touch /tmp/passwd && mosquitto_passwd -b /tmp/passwd mosquitto $PASSWD && cat /tmp/passwd && rm /tmp/passwd" > $MOSQUITTO_PASSWD_FILE
fi

mkdir -p /var/lib/smart-home/grafana
chmod -R 777 /var/lib/smart-home/grafana

mkdir -p /opt/mosquitto/data/
mkdir -p /var/log/mosquitto