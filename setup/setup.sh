#!/bin/bash

ENV_FILE=/etc/docker/smart-home/.env
if [ "$1" == "local" ]; then
  mkdir -p /etc/docker/smart-home
  cp .env $ENV_FILE
  chmod 600 $ENV_FILE
else
  if [ ! -f "$ENV_FILE" ]; then
    echo "WARNING: Global env file $ENV_FILE does not exist. Installation will not work."
    exit 1
  fi
fi
set -o allexport; source $ENV_FILE; set +o allexport

MOSQUITTO_PATH=/etc/docker/smart-home/mosquitto
mkdir -p $MOSQUITTO_PATH
cp mosquitto/mosquitto.conf $MOSQUITTO_PATH/mosquitto.conf
chmod 600 $MOSQUITTO_PATH/mosquitto.conf

MOSQUITTO_PASSWD_FILE=$MOSQUITTO_PATH/passwd
if [ ! -f "$MOSQUITTO_PASSWD_FILE" ]; then
  docker run --rm eclipse-mosquitto:1.6 /bin/sh -c "touch /tmp/passwd && mosquitto_passwd -b /tmp/passwd mosquitto '$MOSQUITTO_PASSWD' && cat /tmp/passwd && rm /tmp/passwd" > $MOSQUITTO_PASSWD_FILE
fi

mkdir -p /var/lib/smart-home/grafana
chmod -R 777 /var/lib/smart-home/grafana

mkdir -p /opt/mosquitto/data/
mkdir -p /var/log/mosquitto

TELEGRAF_PATH=/etc/docker/smart-home/telegraf
if [ ! -f "$TELEGRAF_PATH" ]; then
   mkdir -p $TELEGRAF_PATH
   cp telegraf/telegraf.conf $TELEGRAF_PATH/telegraf.conf
   sed -i -e "s/\$INFLUXDB_WRITE_PASSWORD/$INFLUXDB_WRITE_PASSWORD/g" $TELEGRAF_PATH/telegraf.conf
   sed -i -e "s/\$MOSQUITTO_PASSWD/$MOSQUITTO_PASSWD/g" $TELEGRAF_PATH/telegraf.conf
   chmod 600 $TELEGRAF_PATH/telegraf.conf
fi

