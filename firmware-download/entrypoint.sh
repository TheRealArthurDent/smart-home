#!/bin/sh

echo "Initial download of IKEA Tradfri firmware"
sh download-ikea-firmware.sh

# Start cron
echo "Starting supercronic..."
exec supercronic crontab
