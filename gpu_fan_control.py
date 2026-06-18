import subprocess
import time
import signal
import sys
import argparse

# --- CONFIGURATION ---
POLL_INTERVAL_SEC = 5
MAX_DUTY_DECREASE_PER_CYCLE = 3  # Percent points

# Fan Curve: (Temperature Celsius, Duty Cycle Percentage)
CURVE = [
    (30, 20),
    (45, 40),
    (60, 70),
    (80, 100),
]
# ---------------------

def get_max_temp():
    try:
        # GPU Temperatures via nvidia-smi
        gpu_out = subprocess.check_output(['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'], encoding='utf-8')
        gpu_temps = [int(t) for t in gpu_out.strip().split('\\n')]
        max_gpu = max(gpu_temps) if gpu_temps else 0

        # CPU Temperature via sensors (simplified example - target specific sensor path as needed)
        cpu_out = subprocess.check_output(['sensors', '-j'], encoding='utf-8')
        # Note: In a real scenario, parse the JSON for the highest package temp
        # This is a placeholder for logic that handles the ROMED8's specific layout
        max_cpu = 40 # placeholder

        return max(max_gpu, max_cpu)
    except Exception as e:
        print(f"Error reading sensors: {e}")
        return None

def interpolate_duty(temp):
    if temp <= CURVE[0][0]: return CURVE[0][1]
    if temp >= CURVE[-1][0]: return CURVE[-1][1]
    for i in range(len(CURVE) - 1):
        t1, d1 = CURVE[i]
        t2, d2 = CURVE[i+1]
        if t1 <= temp < t2:
            return int(d1 + (d2 - d1) * (temp - t1) / (t2 - t1))
    return 100

def set_fan_speed(duty):
    # Raw IPMI command for ASRock Rack ROMED8-2T
    # This is a representative example of the raw hex format used by these BMCs
    hex_val = f"{duty:02x}"
    cmd = ["ipmitool", "raw", "0x3a", "0x01", f"0x{hex_val}"]
    subprocess.run(cmd, check=True)

def set_auto_mode():
    print("Reverting fans to Automatic mode...")
    subprocess.run(["ipmitool", "raw", "0x3a", "0x01", "0x01"], check=False)

def signal_handler(sig, frame):
    set_auto_mode()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()

    last_duty = 0
    while True:
        temp = get_max_temp()
        if temp is None:
            print("Critical: Sensor failure! Forcing fans to 100%.")
            target_duty = 100
        else:
            target_duty = interpolate_duty(temp)

        # Anti-flap logic (fast ramp up, slow ramp down)
        if target_duty < last_duty:
            actual_duty = max(target_duty, last_duty - MAX_DUTY_DECREASE_PER_CYCLE)
        else:
            actual_duty = target_duty

        print(f"Temp: {temp}C -> Duty: {actual_duty}%")
        set_fan_speed(actual_duty)
        last_duty = actual_duty

        if args.once: break
        time.sleep(POLL_INTERVAL_SEC)
