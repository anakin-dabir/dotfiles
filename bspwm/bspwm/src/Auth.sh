#!/usr/bin/env bash

APP_NAME="enteauth"
APP_CLASS="Io.ente.auth"

# Check if Warp is running
if pgrep -f "$APP_NAME" > /dev/null; then
    # Warp is running, close it
    pkill -f "$APP_NAME"
else
    # Warp is not running, start it
    setsid "$APP_NAME" > /dev/null 2>&1 &
fi
