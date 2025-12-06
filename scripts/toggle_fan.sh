#!/bin/bash

if [ "$1" == "travel" ]; then
    # 1. Load Silent Fan Config (Fan stays OFF until 85°C)
    sudo cp /etc/i8kutils/i8kmon_travel.conf /etc/i8kutils/i8kmon.conf
    sudo systemctl restart i8kmon
    
    # 2. Disable Turbo Boost
    # This caps the CPU at its Base Frequency (e.g., 2.4GHz)
    # It's fast enough for work, but generates 50% less heat.
    echo "1" | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
    
    # 3. Notify
    echo "✈️ Travel Mode ACTIVATED:"
    echo "   - Fan: OFF (Emergency trigger at 85°C)"
    echo "   - CPU: Turbo Disabled (Cool & Efficient)"

else
    # 1. Load Normal Fan Config (Fan keeps laptop cool)
    sudo cp /etc/i8kutils/i8kmon_normal.conf /etc/i8kutils/i8kmon.conf
    sudo systemctl restart i8kmon
    
    # 2. Re-enable Turbo Boost (Max Performance)
    echo "0" | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
    
    # 3. Notify
    echo "🏠 Normal Mode ACTIVATED:"
    echo "   - Fan: Auto (Aggressive cooling)"
    echo "   - CPU: Max Performance (Turbo ON)"
fi
