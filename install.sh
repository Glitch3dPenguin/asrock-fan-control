#!/usr/bin/env bash
# Installs the GPU/CPU-aware fan control daemon as a systemd service.
# Run with sudo. Tested for Debian/Ubuntu-family systems.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo ./install.sh)" >&2
  exit 1
fi

echo "==> Installing dependencies (ipmitool, lm-sensors)"
apt-get update -qq
apt-get install -y ipmitool lm-sensors

echo "==> Detecting sensors (loads k10temp etc. - safe to answer YES to defaults)"
yes "" | sensors-detect >/dev/null || true

echo "==> Installing shared BMC helper module"
mkdir -p /usr/local/lib/gpu-fan-control
install -m 0644 bmc_fan.py /usr/local/lib/gpu-fan-control/bmc_fan.py

echo "==> Copying daemon to /usr/local/bin/"
install -m 0755 gpu_fan_control.py /usr/local/bin/gpu_fan_control.py

echo "==> Installing manual override CLI (fans)"
install -m 0755 fans /usr/local/bin/fans

echo "==> Installing watchdog"
install -m 0755 gpu_fan_watchdog.py /usr/local/bin/gpu_fan_watchdog.py

echo "==> Installing systemd units"
install -m 0644 gpu-fan-control.service /etc/systemd/system/gpu-fan-control.service
install -m 0644 gpu-fan-watchdog.service /etc/systemd/system/gpu-fan-watchdog.service
install -m 0644 gpu-fan-watchdog.timer /etc/systemd/system/gpu-fan-watchdog.timer
systemctl daemon-reload

echo
echo "Install complete. Before enabling the service, sanity-check sensor reads with:"
echo "    sudo python3 /usr/local/bin/gpu_fan_control.py --once"
echo
echo "If CPU and GPU temps look correct, enable and start the service with:"
echo "    sudo systemctl enable --now gpu-fan-control"
echo
echo "Then enable the watchdog (separate dead-man's switch, checks every minute):"
echo "    sudo systemctl enable --now gpu-fan-watchdog.timer"
echo
echo "Watch the daemon work with:"
echo "    journalctl -u gpu-fan-control -f"
echo
echo "For manual testing at any time:"
echo "    sudo systemctl stop gpu-fan-control   # so it doesn't fight you"
echo "    fans 100                              # force all fans to 100%"
echo "    fans status                           # check current raw mode/duty"
echo "    fans auto                             # or: sudo systemctl start gpu-fan-control"
