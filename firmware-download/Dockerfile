FROM python:3.14-alpine

# RUN apk add wget - wget is already installed

USER nobody

WORKDIR /usr/firmware-download

# Copy files
COPY entrypoint.sh .
COPY download-ikea-firmware.sh .
COPY crontab .

# Run cron on container startup
ENTRYPOINT ["./entrypoint.sh"]
