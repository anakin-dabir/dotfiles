#!/usr/bin/env bash

echo "Finding processes consuming more than 1GB of memory..."
ps aux --sort=-%mem | awk '$6 > 1048576 {print $2, $6, $11}'  # Show processes using >1GB

echo "Killing processes consuming more than 1GB of memory..."
ps aux --sort=-%mem | awk '$6 > 1048576 {print $2}' | xargs -r kill -9

echo "Processes consuming more than 1GB of memory have been killed!"
