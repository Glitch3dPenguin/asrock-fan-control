# ASRock Rack ROMED8-2T GPU/CPU Fan Control

A Python daemon that monitors CPU and GPU temperatures and adjusts chassis fan speeds via IPMI raw commands. 

## 📌 Overview
The **ASRock Rack ROMED8-2T** (ASPEED AST2500 BMC) typically controls fans based on CPU temperature alone. In systems with multiple GPUs, this leads to overheating during GPU-heavy workloads because the BMC doesn't "see" the GPU temps.

This tool takes over manual fan control and drives all 7 fan headers based on the **highest** detected temperature among the CPU and all installed GPUs.

### Key Features
- **Dynamic Scaling**: Uses a linear interpolation curve to map temperatures to fan duty cycles.
- **Anti-Flap Logic**: Fans can ramp up instantly for safety, but only drop by 3% every 5 seconds to prevent rapid oscillation ("flapping").
- **Fail-Safe**: If `nvidia-smi` or `lm-sensors` fails to return data, the system defaults to **100% fan speed**.
- **Automatic Cleanup**: Reverts the BMC to factory "Automatic" mode upon service stop or system shutdown via SIGTERM handlers.
- **Systemd Integration**: Runs as a background daemon with `Restart=always` for maximum reliability.

## 🚀 Installation

### Prerequisites
- Root/Sudo access.
- Debian/Ubuntu family distribution.
- NVIDIA drivers installed (for `nvidia-smi`).

### Deployment
1. Clone this repository to your server:
   ```bash
   git clone https://github.com/Glitch3dPenguin/asrock-fan-control.git
   cd asrock-fan-control
   ```

2. Run the installation script:
   ```bash
   chmod +x install.sh
   sudo ./install.sh
   ```

3. **Sanity Check**: Before enabling the service, verify that sensors are being read correctly:
   ```bash
   sudo python3 /usr/local/bin/gpu_fan_control.py --once
   ```

4. **Enable & Start**:
   ```bash
   sudo systemctl enable --now gpu-fan-control
   ```

5. **Monitor Logs**:
   ```bash
   journalctl -u gpu-fan-control -f
   ```

## 🛠 Configuration

You can edit `gpu_fan_control.py` to adjust the fan curve or polling intervals:

- **`CURVE`**: A list of `(temp, duty)` tuples.
- **`POLL_INTERVAL_SEC`**: How often to check sensors (default: 5s).
- **`MAX_DUTY_DECREASE_PER_CYCLE`**: Maximum percentage points the fans can drop per poll.

## ⚠️ Warning
When this daemon is active, you "own" the cooling logic. If the service is stopped or crashed, the fans will remain at their last set value until `set_auto_mode` is triggered or the system reboots.

## Hardware Target
- **Motherboard**: ASRock Rack ROMED8-2T
- **BMC**: ASPEED AST2500
