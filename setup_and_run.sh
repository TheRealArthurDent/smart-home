#!/bin/bash

(
  cd setup || exit
  cp .env /etc/docker/smart-home/
  bash setup.sh
)

bash run.sh
