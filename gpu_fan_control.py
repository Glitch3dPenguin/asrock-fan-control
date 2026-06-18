#!/usr/bin/env python3
"""
gpu_fan_control.py

Ties chassis fan speed to whichever is hotter: CPU or GPU.

Hardware target: ASRock Rack ROMED8-2T (ASPEED AST2500 BMC).
The BMC's default fan curve only looks at CPU temp, so GPU-heavy
loads never spin the chassis fans up. This daemon takes over manual
fan control via IPMI raw commands and drives all 7 fan headers off
of max(CPU temp, hottest GPU temp).

Confirmed-working IPMI raw commands for this board (ASRock Rack
official FAQ "TSDQA-72" + ASRock Rack forum/STH reports for ROMED8-2T):

    Switch to manual mode:  ipmitool raw 0x3a 0xd8 0x1 x16
    Revert to auto mode:    ipmitool raw 0x3a 0xd8 0x0 x16
    Set duty (0-100):       ipmitool raw 0x3a 0xd6 <duty> x16
    Read mode:               ipmitool raw 0x3a 0xd7
    Read duty:                ipmitool raw 0x3a 0xda

Run with --once to do a single read/print cycle without applying
anything (good for sanity-checking sensor reads before enabling the
service). Run with --dry-run to loop normally but skip the ipmitool
calls (prints what it WOULD set).
"""

import argparse
import logging
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, "/usr/local/lib/gpu-fan-control")
import bmc_fan

# ---------------------------------------------------------------------------
# Configuration - tune this to taste
# ---------------------------------------------------------------------------

# (temperature_C, fan_duty_percent) control points, ascending by temp.
# Duty is linearly interpolated between points. Below the first point,
# duty is clamped to the first point's value. Above the last, clamped
# to the last point's value (100).
CURVE = [
    (40, 25),
    (55, 35),
    (65, 50),
    (72, 65),
    (78, 80),
    (85, 100),
]

POLL_INTERVAL_SEC = 5

# Fan duty is allowed to jump up instantly (safety), but is only
# allowed to drop by this many percentage points per poll cycle, to
# stop the fans from "flapping" when temps hover near a curve point.
MAX_DUTY_DECREASE_PER_CYCLE = 3

# If sensor reads fail (e.g. nvidia-smi hangs, sensors misconfigured),
# fall back to this duty rather than guessing low.
FAIL_SAFE_DUTY = 100

# ---------------------------------------------------------------------------

log = logging.getLogger("gpu_fan_control")


def read_gpu_temps():
    """Return list of GPU temps in C, or None on failure."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        temps = [int(line.strip()) for line in out.stdout.splitlines() if line.strip()]
        if not temps:
            return None
        return temps
    except Exception as e:
        log.warning("Failed to read GPU temps via nvidia-smi: %s", e)
        return None


def read_cpu_temp():
    """Return CPU temp in C (Tctl/Tdie from k10temp), or None on failure."""
    try:
        out = subprocess.run(
            ["sensors"], capture_output=True, text=True, timeout=10, check=True,
        )
    except Exception as e:
        log.warning("Failed to run sensors: %s", e)
        return None

    # Prefer Tctl (what the BMC's own default curve is based on),
    # fall back to Tdie, fall back to any "Core ..." reading.
    for label in ("Tctl:", "Tdie:"):
        m = re.search(rf"{re.escape(label)}\s*\+?(-?[\d.]+)", out.stdout)
        if m:
            return float(m.group(1))

    core_temps = [float(t) for t in re.findall(r"Core \d+:\s*\+?(-?[\d.]+)", out.stdout)]
    if core_temps:
        return max(core_temps)

    log.warning("Could not find Tctl/Tdie/Core temps in `sensors` output")
    return None


def duty_for_temp(temp):
    """Linear-interpolate fan duty (0-100) for a given temp using CURVE."""
    points = CURVE
    if temp <= points[0][0]:
        return points[0][1]
    if temp >= points[-1][0]:
        return points[-1][1]
    for (t0, d0), (t1, d1) in zip(points, points[1:]):
        if t0 <= temp <= t1:
            frac = (temp - t0) / (t1 - t0)
            return d0 + frac * (d1 - d0)
    return points[-1][1]


def run_ipmitool(action, *call_args, dry_run=False):
    """Thin dry-run wrapper around a bmc_fan call. `action` is a bmc_fan function."""
    if dry_run:
        log.info("[dry-run] would call bmc_fan.%s%s", action.__name__, call_args)
        return None
    try:
        return action(*call_args)
    except bmc_fan.BmcError as e:
        log.error("%s", e)
        return None


def set_manual_mode(dry_run=False):
    log.info("Switching BMC to manual fan mode")
    run_ipmitool(bmc_fan.set_manual_mode, dry_run=dry_run)


def set_auto_mode(dry_run=False):
    log.info("Reverting BMC to automatic fan mode")
    run_ipmitool(bmc_fan.set_auto_mode, dry_run=dry_run)


def set_duty(duty_percent, dry_run=False):
    duty = max(0, min(100, int(round(duty_percent))))
    if dry_run:
        log.info("[dry-run] would set duty to %d%%", duty)
        return duty
    applied = run_ipmitool(bmc_fan.set_duty, duty_percent, dry_run=False)
    return applied if applied is not None else duty


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                         help="Read sensors and print the computed duty, then exit. No IPMI calls made.")
    parser.add_argument("--dry-run", action="store_true",
                         help="Run the normal loop but skip actual ipmitool calls.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.once:
        gpu_temps = read_gpu_temps()
        cpu_temp = read_cpu_temp()
        hottest = max([t for t in (gpu_temps or []) + ([cpu_temp] if cpu_temp is not None else [])], default=None)
        print(f"CPU temp: {cpu_temp}")
        print(f"GPU temps: {gpu_temps}")
        if hottest is None:
            print("Could not read any sensor - would fail-safe to", FAIL_SAFE_DUTY, "%")
        else:
            print(f"Hottest component: {hottest}C -> target duty: {duty_for_temp(hottest):.0f}%")
        return

    last_duty = None

    def handle_exit(signum, frame):
        log.info("Received signal %s, reverting fans to automatic control before exit", signum)
        set_auto_mode(dry_run=args.dry_run)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    set_manual_mode(dry_run=args.dry_run)

    log.info("Entering monitor loop (poll every %ss)", POLL_INTERVAL_SEC)
    while True:
        gpu_temps = read_gpu_temps()
        cpu_temp = read_cpu_temp()

        all_temps = list(gpu_temps) if gpu_temps else []
        if cpu_temp is not None:
            all_temps.append(cpu_temp)

        if not all_temps:
            log.error("No sensor data available from CPU or GPU - failing safe to %d%%", FAIL_SAFE_DUTY)
            target_duty = FAIL_SAFE_DUTY
        else:
            hottest = max(all_temps)
            target_duty = duty_for_temp(hottest)

        if last_duty is not None and target_duty < last_duty:
            target_duty = max(target_duty, last_duty - MAX_DUTY_DECREASE_PER_CYCLE)

        applied = set_duty(target_duty, dry_run=args.dry_run)
        last_duty = applied

        log.info(
            "CPU=%s GPU=%s -> duty=%d%%",
            f"{cpu_temp:.0f}C" if cpu_temp is not None else "N/A",
            gpu_temps if gpu_temps else "N/A",
            applied,
        )

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
