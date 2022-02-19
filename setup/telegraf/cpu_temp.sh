#!/bin/bash

sensors | grep temp1 | sed -e 's/temp1:[ ]*[+]//g' | sed 's/ C//g'