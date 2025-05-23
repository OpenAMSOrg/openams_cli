# openams_cli

A command-line tool to automate the deployment of Katapult and Klipper firmware to STM32G0B1-based 3D printer controller boards.

## Features
- Automated environment setup (Python virtualenv, dependencies)
- System package installation (build tools, dfu-util, etc.)
- Cloning and updating Katapult and Klipper repositories
- Automatic detection of printer mode (canbus/bridge)
- Automated build and flashing of firmware
- STM32 option bytes configuration (Linux, Windows, WSL)
- USB device handling for WSL/Windows

## Requirements
- Linux (or WSL/Windows with additional steps)
- Python 3.7+
- `sudo` privileges for installing system packages and flashing

## Quick Start

1. **Clone this repository** (if you haven't already):
   ```zsh
   git clone <repo-url>
   cd openams_cli
   ```

2. **Run the setup command** to install dependencies:
   ```zsh
   python3 openams_cli.py setup
   ```

3. **Deploy firmware** to your STM32 device:
   ```zsh
   python3 openams_cli.py deploy
   ```
   - The script will detect your printer mode (canbus/bridge) from `~/printer_data/config/printer.cfg` or prompt you.
   - It will build and flash Katapult and Klipper automatically.
   - Follow on-screen instructions for plugging in your device and handling USB permissions.

## Notes
- On first run, a Python virtual environment will be created at `~/.openams_env`.
- System dependencies will be installed via `apt` (requires sudo).
- For WSL/Windows users, the script will attempt to automate USB device attachment using `usbipd-win`.
- All build artifacts and cloned repositories are placed in your home directory (`~/katapult`, `~/klipper`).

## Troubleshooting
- If you encounter permission errors, ensure you are in the `dialout` group and have `sudo` access.
- For WSL/Windows, ensure `usbipd-win` and `STM32CubeProgrammer` are installed on Windows.
- If the script cannot find your STM32 device, check your USB cable and that the device is in DFU mode.

## License
MIT
