#!/bin/sh
# Generic per-rice hook: if a rice ships its own apply.sh, run it last.
# Lets a rice add styling/assets beyond what the shared modules cover.
_hook="$HOME/.config/bspwm/rices/$RICE/apply.sh"
[ -f "$_hook" ] && . "$_hook"
