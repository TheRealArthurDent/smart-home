FROM python:3.13-alpine

# RUN apk add wget - wget is already installed

WORKDIR /usr/firmware-download

# Copy files
COPY entrypoint.sh .
COPY download-ikea-firmware.sh .
COPY crontab .

# Run cron on container startup
ENTRYPOINT ["./entrypoint.sh"]
