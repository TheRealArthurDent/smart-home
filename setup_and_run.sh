#!/bin/bash

(
  cd setup || exit
  bash setup.sh
)

bash run.sh
