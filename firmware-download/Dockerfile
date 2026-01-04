FROM python:3.14-alpine

# Latest releases available at https://github.com/aptible/supercronic/releases
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.41/supercronic-linux-arm64 \
    SUPERCRONIC_SHA1SUM=44e10e33e8d98b1d1522f6719f15fb9469786ff0 \
    SUPERCRONIC=supercronic-linux-arm64

RUN wget -q "$SUPERCRONIC_URL" \
 && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
 && chmod +x "$SUPERCRONIC" \
 && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
 && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic \
 && addgroup -S downloader && adduser -S downloader -G downloader \
 && mkdir /home/downloader/otau \
 && chown downloader:downloader /home/downloader/otau

VOLUME /home/downloader/otau

WORKDIR /home/downloader

# Copy files
COPY --chown=downloader:downloader --chmod=544 entrypoint.sh .
COPY --chown=downloader:downloader --chmod=544 download-ikea-firmware.sh .
COPY --chown=downloader:downloader --chmod=444 crontab .

#RUN crontab crontab

USER downloader

# Run cron on container startup
ENTRYPOINT ["./entrypoint.sh"]
