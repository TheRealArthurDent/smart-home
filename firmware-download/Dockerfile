FROM python:3.12-alpine

RUN apk add --no-cache wget=1.24.5-r0

WORKDIR /usr/firmware-download

# Copy files
COPY entrypoint.sh .
COPY download-ikea-firmware.sh .
COPY crontab .

# Run cron on container startup
ENTRYPOINT ["./entrypoint.sh"]
