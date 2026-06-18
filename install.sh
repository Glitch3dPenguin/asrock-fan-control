#!/bin/bash

# Install dependencies
apt-get update
apt-get install -y ipmitool python3

# Move script and service file to system locations
cp gpu_fan_control.py /usr/local/bin/gpu_fan_control.py
chmod +x /usr/local/bin/gpu_fan_control.py
cp gpu-fan-control.service /etc/systemd/system/gpu-fan-control.service

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable gpu-fan-control

echo "Installation complete. You can now start the service with: sudo systemctl start gpu-fan-control"
