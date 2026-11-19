#!/bin/sh
# Disable spurious wakeup sources that cause self-wake / resume loops.
# Keeps PWRB (power button) and lid as valid wake triggers.
for src in XHCI TXHC RP07 RP08 PEG0 PEG1 PXSX AWAC; do
    if grep -qw "^$src.*enabled" /proc/acpi/wakeup; then
        echo "$src" > /proc/acpi/wakeup
    fi
done
