#!/bin/sh
echo "Downloading..."

SCRIPT_NAME=ikea-ota-download.py

wget -nv -O $SCRIPT_NAME https://raw.githubusercontent.com/dresden-elektronik/deconz-rest-plugin/stable/ikea-ota-download.py

python3 $SCRIPT_NAME

echo "Download finished"
