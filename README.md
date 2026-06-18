# ASRock Rack ROMED8-2T GPU/CPU Fan Control

A Python ecosystem for monitoring CPU and GPU temperatures and adjusting chassis fan speeds via IPMI raw commands on the ASRock Rack ROMED8-2T (ASPEED AST2500 BMC).

## 📌 Overview
The **ASRock Rack ROMED8-2T** typically controls fans based on CPU temperature alone. In systems with multiple GPUs, this leads to overheating during GPU-heavy workloads because the BMC doesn't "see" the GPU temps.

This toolset takes over manual fan control and drives all 7 fan headers based on the **highest** detected temperature among the CPU and all installed GPUs.

### Key Features
- **Dynamic Scaling**: Uses a linear interpolation curve to map temperatures to fan duty cycles.
- **Anti-Flap Logic**: Fans ramp up instantly for safety, but only drop by 3% every 5 seconds to prevent rapid oscillation.
- **Fail-Safe**: If `nvidia-smi` or `lm-sensors` fails to return data, the system defaults to **100% fan speed**.
- **Automatic Cleanup**: Reverts the BMC to factory "Automatic" mode upon service stop or system shutdown via SIGTERM handlers.
- **Dead-Man's Switch**: A separate watchdog timer ensures that if the main daemon crash-loops (systemd state `failed`), fans are forced to 100% and the service is restarted.

## 🚀 Installation

### Prerequisites
- Root/Sudo access.
- Debian/Ubuntu family distribution.
- NVIDIA drivers installed (for `nvidia-smi`).

### Deployment
1. Clone this repository:
   ```bash
   git clone https://github.com/Glitch3dPenguin/asrock-fan-control.git
   cd asrock-fan-control
   ```

2. Run the installation script:
   ```bash
   chmod +x install.sh
   sudo ./install.sh
   ```

3. **Sanity Check**: Verify sensors are read correctly before enabling the service:
   ```bash
   sudo python3 /usr/local/bin/gpu_fan_control.py --once
   ```

4. **Enable & Start Primary Control**:
   ```bash
   sudo systemctl enable --now gpu-fan-control
   ```

5. **Enable the Watchdog**:
   The watchdog is a separate safety net and must be enabled independently:
   ```bash
   sudo systemctl enable --now gpu-fan-watchdog.timer
   ```

6. **Monitor Logs**:
   ```bash
   journalctl -u gpu-fan-control -f
   ```

## 🛠 Manual Testing & Overrides

The installation includes a `fans` CLI tool for manual control and testing. 

**Important:** If the daemon is running, it polls every 5 seconds and will overwrite any manual changes. Stop the daemon first for changes to stick.

### Recommended Testing Workflow:
```bash
sudo systemctl stop gpu-fan-control   # Disable automated control
fans 100                              # Force all fans to max; verify physical response
fans status                           # Peek at raw BMC mode/duty bytes
fans auto                             # Revert to BMC default automatic curve
sudo systemctl start gpu-fan-control  # Resume temperature-based control
```

### ⚠️ Critical Warnings
*   **The "Forgetfulness" Risk**: `fans auto` or stopping the service does NOT automatically revert the fans over time. If you stop the service for testing and forget to restart it (or set it back to auto), the fans will remain at their last set value indefinitely.
*   **Watchdog Scope**: The watchdog only fires on **genuine failed states** (e.g., if the daemon crashes 5+ times within 10 seconds). It deliberately ignores `inactive` states. If you manually stop the service to test, the watchdog will not intervene; this is intentional so it doesn't fight your manual overrides.

## ⚙️ Configuration
You can edit `gpu_fan_control.py` to adjust the fan behavior:
- **`CURVE`**: A list of `(temp, duty)` tuples.
- **`POLL_INTERVAL_SEC`**: How often to check sensors (default: 5s).
- **`MAX_DUTY_DECREASE_PER_CYCLE`**: Max percentage points fans can drop per poll.

## Hardware Target
- **Motherboard**: ASRock Rack ROMED8-2T
- **BMC**: ASPEED AST2500
