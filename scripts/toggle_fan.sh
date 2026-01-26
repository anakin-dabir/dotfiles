#!/bin/bash

if [ "$1" == "travel" ]; then
    # 1. Stop the auto-control service (so it doesn't fight you)
    sudo systemctl stop i8kmon
    
    # 2. Force Fan OFF using the command you confirmed works
    sudo i8kctl fan1 0
    
    # 3. Disable Turbo (Keep CPU cool)
    echo "1" | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo > /dev/null
    
    echo "✈️ Travel Mode ACTIVATED: Fan Forced OFF, Turbo Disabled."

else
    # 1. Re-enable Turbo
    echo "0" | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo > /dev/null
    
    # 2. Restart Auto-Control Service (This takes back control of the fan)
    sudo systemctl restart i8kmon
    
    echo "🏠 Normal Mode ACTIVATED: Auto-Fan Service Restarted."
fi
