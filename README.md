# OpenAMS CLI

OpenAMS is an electronics hardware replacement for the AMS, designed to make advanced multi-material 3D printing compatible with Klipper. This repository provides tools for deploying and configuring klipper compatible firmware to your FPS and OpenAMS Mainboards, automating CANBus setup, and integrating with klipper.

---

## How the System Works

OpenAMS setup is divided into two main phases:

### **Printer Integration (Raspberry Pi running Klipper)**
- Run this script `asssistant.py` and follow the instructions before installing your boards, it will ask you to plug the FPS and the Mainboard in sequence.  Once configured, the wizard to guide you through CANBus setup, UUID detection, and final configuration.
- After setup, and a reboot, a systemd daemon (`openams-daemon`) runs on the Raspberry Pi to automatically detect CANBus UUIDs, configure Klipper, and ensure the system is ready to use.

---

## Features

- Automated environment setup (Python virtualenv, dependencies)
- System package installation (build tools, dfu-util, etc.)
- Cloning and updating Katapult and Klipper repositories
- Automatic detection of printer mode (canbus/bridge)
- Automated build and flashing of firmware
- STM32 option bytes configuration (Linux, Windows, WSL)
- USB device handling for WSL/Windows
- **Automated CANBus network configuration**
- **Assistant wizard for guided setup (Raspberry Pi only)**
- **Systemd daemon for automatic UUID detection and Klipper configuration**

---

## Requirements

- Linux (or WSL/Windows with additional steps)
- Python 3.7+
- `sudo` privileges for installing system packages and flashing
- For the assistant: Raspberry Pi running Klipper

---

## Quick Start

1. **Clone this repository** (if you haven't already):
   ```sh
   git clone <repo-url>
   cd openams_cli
   ```

2. **Start the interactive assistant** (on the Raspberry Pi) to guide you through the full hardware and firmware setup:
   ```sh
   python3 assistant.py
   ```
   - The assistant will walk you through firmware flashing, environment setup, CANBus configuration, and UUID detection.
   - All actions are logged to `/var/log/openams_assistant.log`.

3. **Automated UUID detection and Klipper configuration**  
   After the initial setup, the assistant will install and enable a systemd daemon (`openams-daemon`) that, after a reboot:
   - Waits for both FPS and Mainboard CANBus UUIDs to appear.
   - Automatically configures Klipper macros and config files.
   - Restarts Klipper and prints a summary.
   - This daemon runs automatically on reboot and ensures your system is always ready.

---

## Command Reference

This is the bare (non-assisted) script tht can be used to flash the boards manually, setup canbus, and configure klipper, without the assistants help.  The script can also be run on Windows (under WSL) or just plain linux (x86) to flash firmware to the FPS, the OpenAMS Mainboard, and coming soon the OpenAMS 2 Mainboard.

### `python3 openams_cli.py setup`
- Installs all required system and Python dependencies.
- Sets up a Python virtual environment at `~/.openams_env`.
- Should be run first on any system before using other commands.

### `python3 openams_cli.py setup-canbus [--non-interactive]`
- Configures CANBus networking on the system (systemd-networkd, udev rules, etc.).
- `--non-interactive`: Skips user prompts for automated setup (recommended for assistant use).

### `python3 openams_cli.py deploy --board <fps|openams> [--mode <bridge|canbus>]`
- Flashes firmware to the selected board.
- `--board fps`: Programs the Filament Pressure Sensor board.
- `--board openams`: Programs the OpenAMS Mainboard.
- `--mode bridge|canbus`: (FPS only) Selects the firmware mode.

### `python3 openams_cli.py query`
- Queries the CANBus network for Klipper devices and displays their UUIDs.

### `python3 openams_cli.py setup_klipper_config`
- Guides you through configuring Klipper macros and config files using detected UUIDs.

### `python3 openams_cli.py install_assistant`
- Installs and enables the OpenAMS Assistant systemd service on the Raspberry Pi.
- This is typically called automatically by the assistant after setup.

### `python3 assistant.py`
- **(Raspberry Pi only)**  
  Launches the interactive assistant wizard for guided setup of OpenAMS hardware and CANBus integration.
- Installs and enables the `openams-daemon` systemd service for ongoing automation.

---

## File and Directory Structure

- `openams_cli.py` — Main CLI tool for board programming and configuration (Linux x86/Windows x86 or RPi).
- `assistant.py` — Interactive wizard for guided setup (Raspberry Pi only).
- `openams_daemon.py` — Daemon for automatic UUID detection and Klipper configuration (runs as a systemd service).
- `firmwares/` — Prebuilt firmware binaries for OpenAMS Mainboard.
- `LICENSE` — License file (All rights reserved).

---

## Notes

- On first run, a Python virtual environment will be created at `~/.openams_env`.
- System dependencies will be installed via `apt` (requires sudo).
- For WSL/Windows users, the script will attempt to automate USB device attachment using `usbipd-win`.
- All build artifacts and cloned repositories are placed in your home directory (`~/katapult`, `~/klipper`).
- The assistant and daemon scripts are installed to `/usr/local/bin` and managed as systemd services for persistent automation.
- All logs are available at `/var/log/openams_assistant.log`.

---

## Troubleshooting

- If you encounter permission errors, ensure you are in the `dialout` group and have `sudo` access.
- For WSL/Windows, ensure `usbipd-win` and `STM32CubeProgrammer` are installed on Windows.
- If the script cannot find your STM32 device, check your USB cable and that the device is in DFU mode.
- If CANBus is not detected, verify cabling and termination resistors as described in the CANBus setup output.

---

## FAQ

**Q: Can I use the assistant on my desktop PC?**  
A: No, the assistant (`assistant.py`) is intended only for the Raspberry Pi running Klipper. Use `openams_cli.py` on your desktop for board programming.

**Q: What happens if I re-run the assistant?**  
A: The assistant is safe to re-run and will guide you through the setup steps again. It will not overwrite existing configuration files without confirmation.

**Q: How do I update the system after a firmware or config change?**  
A: Re-run the assistant or the relevant CLI commands. The daemon will ensure Klipper is reconfigured and restarted as needed.

---

## License

See [LICENSE](LICENSE) in this repository.  
**All rights reserved.**

---

