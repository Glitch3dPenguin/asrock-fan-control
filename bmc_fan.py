"""
bmc_fan.py

Shared low-level helpers for talking to the ASRock Rack ROMED8-2T
(ASPEED AST2500) BMC fan controller via ipmitool. Used by:

    gpu_fan_control.py   - the main temperature-driven daemon
    fans                 - manual CLI override for testing
    gpu_fan_watchdog.py  - dead-man's switch if the daemon crash-loops

Keeping the raw IPMI byte sequences in exactly one place means all
three tools stay in sync if you ever need to adjust them.
"""

import subprocess

IPMITOOL = "ipmitool"

# The AST2500 raw fan commands always take 16 byte slots regardless of
# how many physical headers exist. The ROMED8-2T has 7 (FAN1-FAN7);
# the extra slots are ignored by the BMC.
FAN_SLOTS = 16


class BmcError(Exception):
    """Raised when an ipmitool call to the BMC fails."""


def _run(args):
    cmd = [IPMITOOL] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise BmcError(f"ipmitool failed: {' '.join(cmd)}\n{e.stderr}") from e
    except Exception as e:
        raise BmcError(f"ipmitool errored: {' '.join(cmd)} -> {e}") from e


def set_manual_mode():
    """Switch the BMC from its default automatic fan curve to manual control."""
    _run(["raw", "0x3a", "0xd8"] + ["0x1"] * FAN_SLOTS)


def set_auto_mode():
    """Revert the BMC to its default automatic (CPU-temp-only) fan curve."""
    _run(["raw", "0x3a", "0xd8"] + ["0x0"] * FAN_SLOTS)


def set_duty(duty_percent):
    """Set all fan headers to the given duty cycle (0-100). Returns the clamped value applied."""
    duty = max(0, min(100, int(round(duty_percent))))
    _run(["raw", "0x3a", "0xd6"] + [hex(duty)] * FAN_SLOTS)
    return duty


def read_mode_raw():
    """Raw bytes from the BMC describing current fan mode (manual/auto) per header."""
    return _run(["raw", "0x3a", "0xd7"])


def read_duty_raw():
    """Raw bytes from the BMC describing current duty per header."""
    return _run(["raw", "0x3a", "0xda"])
