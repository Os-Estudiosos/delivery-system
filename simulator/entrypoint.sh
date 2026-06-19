#!/bin/sh
export TARGET_URL=$1
exec k6 run /app/k6-script.js
