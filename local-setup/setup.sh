#!/bin/bash

mkdir -p /etc/docker/smart-home
cp .env /etc/docker/smart-home/.env
chmod 600 /etc/docker/smart-home/.env

mkdir -p /etc/mosquitto
cp mosquitto.conf /etc/mosquitto/mosquitto.conf
chmod 600 /etc/mosquitto/mosquitto.conf

mkdir -p /var/lib/smart-home/grafana
chmod -R 777 /var/lib/smart-home/grafana

mkdir -p /opt/mosquitto/data/
mkdir -p /var/log/mosquitto

# TODO setup mosquitto passwd file -