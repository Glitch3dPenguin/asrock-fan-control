#!/usr/bin/env python3
"""
gpu_fan_watchdog.py

Dead-man's switch for gpu-fan-control.service, run periodically via
a systemd timer (every minute by default).

If the main daemon has crashed enough times that systemd gave up
restarting it (unit state "failed", which happens after exceeding the
default restart-rate limit of 5 restarts in 10 seconds), this forces
all fans to a fixed safe duty directly via the BMC, then attempts to
clear the failure and restart the daemon so it resumes normal
temperature-based control on its own.

Deliberately does NOT act if the service is merely "inactive" (i.e.
you stopped it on purpose, e.g. for `fans` manual testing) - only
genuine crash-loop failures trigger the safety net.
"""

import logging
import subprocess
import sys

sys.path.insert(0, "/usr/local/lib/gpu-fan-control")
import bmc_fan

SERVICE = "gpu-fan-control.service"

# Worst-case fallback duty: if we're here, nobody is actively tracking
# CPU/GPU temps at all, so default to loud-but-safe rather than guessing low.
SAFE_DUTY = 100

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gpu_fan_watchdog")


def service_is_failed():
    result = subprocess.run(["systemctl", "is-failed", SERVICE], capture_output=True, text=True)
    return result.stdout.strip() == "failed"


def main():
    if not service_is_failed():
        return  # service is active, or was deliberately stopped - leave it alone

    log.warning("%s is in a failed state - forcing fans to %d%% as a safety net", SERVICE, SAFE_DUTY)
    try:
        bmc_fan.set_manual_mode()
        bmc_fan.set_duty(SAFE_DUTY)
    except bmc_fan.BmcError as e:
        log.error("Could not force safe fan duty: %s", e)

    log.info("Attempting to clear the failure and restart %s", SERVICE)
    subprocess.run(["systemctl", "reset-failed", SERVICE], capture_output=True, text=True)
    restart = subprocess.run(["systemctl", "start", SERVICE], capture_output=True, text=True)
    if restart.returncode == 0:
        log.info("%s restarted successfully, it will resume normal control on its next poll", SERVICE)
    else:
        log.error("Failed to restart %s: %s", SERVICE, restart.stderr)


if __name__ == "__main__":
    main()
