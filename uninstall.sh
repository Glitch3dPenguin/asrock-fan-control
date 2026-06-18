#!/usr/bin/env bash
# Removes the GPU/CPU-aware fan control daemon and reverts the BMC to
# its default automatic fan curve. Run with sudo.

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo ./uninstall.sh)" >&2
  exit 1
fi

echo "==> Stopping and disabling services"
systemctl disable --now gpu-fan-watchdog.timer 2>/dev/null || true
systemctl stop gpu-fan-control 2>/dev/null || true
systemctl disable gpu-fan-control 2>/dev/null || true

# Give the daemon's own SIGTERM handler a moment to revert to auto
# mode on its way down (it does this on a clean `systemctl stop`).
sleep 1

echo "==> Forcing BMC back to automatic fan mode (safety net, in case the"
echo "    daemon was already crashed/failed and never reverted on its own)"
if command -v ipmitool >/dev/null 2>&1; then
  ipmitool raw 0x3a 0xd8 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 0x0 \
    && echo "    BMC fan mode reverted to automatic" \
    || echo "    WARNING: could not confirm revert via ipmitool, check fan behavior manually"
else
  echo "    WARNING: ipmitool not found, could not confirm BMC fan mode - check manually"
fi

echo "==> Clearing any failed unit state"
systemctl reset-failed gpu-fan-control 2>/dev/null || true
systemctl reset-failed gpu-fan-watchdog.service 2>/dev/null || true
systemctl reset-failed gpu-fan-watchdog.timer 2>/dev/null || true

echo "==> Removing systemd units"
rm -f /etc/systemd/system/gpu-fan-control.service
rm -f /etc/systemd/system/gpu-fan-watchdog.service
rm -f /etc/systemd/system/gpu-fan-watchdog.timer
systemctl daemon-reload

echo "==> Removing installed scripts"
rm -f /usr/local/bin/gpu_fan_control.py
rm -f /usr/local/bin/fans
rm -f /usr/local/bin/gpu_fan_watchdog.py
rm -rf /usr/local/lib/gpu-fan-control

echo
echo "Uninstall complete. Fans are back under the BMC's default automatic curve."
echo
echo "Note: ipmitool and lm-sensors were left installed, since other things on"
echo "the system may depend on them. To remove them too:"
echo "    sudo apt-get remove ipmitool lm-sensors"
