#!/bin/sh

echo "Initial download of IKEA Tradfri firmware"
sh download-ikea-firmware.sh

crontab crontab

# Start cron
echo "Starting cron..."
crond -f -l 8
