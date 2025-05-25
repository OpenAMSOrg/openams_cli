import os
import subprocess
import sys
import time
from pathlib import Path
import shutil
import platform

ENV_DIR = Path.home() / ".openams_env"
VENV_PYTHON = ENV_DIR / "bin" / "python"
VENV_PIP = ENV_DIR / "bin" / "pip"

LICENSE_PATH = Path(__file__).parent / "LICENSE"
LICENSE_ACCEPTED_PATH = Path(".license_accepted")

APT_PACKAGES = [
    "gcc-arm-none-eabi", "make", "dfu-util", "git", "python3-venv"
]

def require_license_agreement():
    # If the acceptance file exists, skip prompt
    if LICENSE_ACCEPTED_PATH.exists():
        return
    if not LICENSE_PATH.exists():
        console.print("[bold red]LICENSE file not found. Exiting.")
        sys.exit(1)
    with LICENSE_PATH.open() as f:
        license_text = f.read()
    # Show a brief notice, not the full license
    console.rule("[bold yellow]License Agreement")
    console.print("[yellow]You must accept the license to use this software.")
    show_full = Confirm.ask("Show full license text?", default=False)
    if show_full:
        console.print(license_text)
    agreed = Confirm.ask("Do you agree to the license terms? [y/n]", default=False)
    if not agreed:
        console.print("[bold red]You must agree to the license terms to use this software. Exiting.")
        sys.exit(1)
    # Write acceptance file
    LICENSE_ACCEPTED_PATH.touch()
    


# Step 1: Minimal environment setup to bootstrap required packages
if not ENV_DIR.exists():
    print("[BOOTSTRAP] Installing minimal required packages...")
    subprocess.run(["sudo", "apt", "update"])
    subprocess.run(["sudo", "apt", "install", "-y"] + APT_PACKAGES)
    
    print("[BOOTSTRAP] Creating virtual environment at ~/.openams_env...")
    subprocess.run(["python3", "-m", "venv", str(ENV_DIR)], check=True)
    subprocess.run([str(VENV_PIP), "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(VENV_PIP), "install", "click", "rich"], check=True)

# Step 2: Ensure environment is in sys.path
activate_site = str(ENV_DIR / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
if activate_site not in sys.path:
    sys.path.insert(0, activate_site)

# Step 3: Now safely import packages that require the environment
import click
from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()

REQUIRED_PACKAGES = [
    "click", "rich"
]



KATAPULT_REPO = "https://github.com/Arksine/katapult"
KLIPPER_REPO = "https://github.com/Klipper3d/klipper"

@click.group()
@click.option(
    "--allow-missing-programmer", is_flag=True, default=False,
    help="Allow running even if STM32_Programmer_CLI is not available (skip option byte programming)."
)
@click.pass_context
def cli(ctx, allow_missing_programmer):
    require_license_agreement()
    ctx.ensure_object(dict)
    ctx.obj["allow_missing_programmer"] = allow_missing_programmer

def ensure_stm32_programmer_cli(allow_missing=False):
    """
    Ensure STM32_Programmer_CLI is installed and available in PATH.
    If allow_missing is True, skip error if not found.
    """
    from shutil import which
    arch = platform.machine()
    if arch.startswith("arm") or arch.startswith("aarch64"):
        console.print("[yellow]STM32_Programmer_CLI is not available for ARM (Raspberry Pi). Skipping installation.")
        console.print("[yellow]You can use dfu-util for firmware flashing, but option byte programming is not supported on ARM.")
        if allow_missing:
            return False
        else:
            sys.exit(1)

    stm32_cli = which("STM32_Programmer_CLI")
    if stm32_cli:
        console.print(f"[green]STM32_Programmer_CLI found at {stm32_cli}")
        return True

    # Instead of attempting installation, just ask the user
    console.print("[yellow]STM32_Programmer_CLI not found in PATH.")
    if allow_missing:
        console.print("[yellow]Continuing without STM32_Programmer_CLI (option byte programming will be skipped).")
        return False
    else:
        proceed = Confirm.ask(
            "[yellow]STM32_Programmer_CLI is required for option byte programming but was not found. "
            "Do you want to continue without it? (Option byte programming will be skipped)",
            default=True
        )
        if proceed:
            console.print("[yellow]Continuing without STM32_Programmer_CLI. Option byte programming will be skipped.")
            return False
        else:
            console.print("[red]STM32_Programmer_CLI is required for option byte programming. Exiting.")
            sys.exit(1)

@cli.command()
@click.option(
    "--allow-missing-programmer", is_flag=True, default=False,
    help="Allow running even if STM32_Programmer_CLI is not available (skip option byte programming)."
)
@click.pass_context
def setup(ctx, allow_missing_programmer):
    ctx.ensure_object(dict)
    ctx.obj["allow_missing_programmer"] = allow_missing_programmer
    console.rule("[bold green]Environment Setup")

    # Create virtual environment
    if not ENV_DIR.exists():
        console.print(f"[bold yellow]Creating virtual environment at {ENV_DIR}")
        subprocess.run(["python3", "-m", "venv", str(ENV_DIR)])
    else:
        console.print(f"[green]Virtual environment already exists at {ENV_DIR}")

    # Install Python packages
    pip = ENV_DIR / "bin" / "pip"
    console.print("[bold cyan]Installing Python packages in virtual environment...")
    subprocess.run([str(pip), "install", "--upgrade", "pip"])
    subprocess.run([str(pip), "install"] + REQUIRED_PACKAGES)

    # Ensure STM32_Programmer_CLI is installed
    ensure_stm32_programmer_cli(allow_missing=allow_missing_programmer)

    console.print("[bold green]Setup complete. Run the script with the [bold]deploy[/bold] command to continue.")

@cli.command()
@click.option(
    "--non-interactive", is_flag=True, default=False,
    help="Run setup-canbus without user prompts (auto-continue)."
)
def setup_canbus(non_interactive):
    """Set up CANBus network on this system (systemd-networkd, udev, config, reboot)."""
    console.rule("[bold blue]CANBus Network Setup")

    # Prompt user to plug in CANBus bridge device
    if not non_interactive:
        proceed = Confirm.ask("[bold yellow]Please plug in your USB-to-CANBus bridge device now. Continue?", default=True)
        if not proceed:
            console.print("[red]CANBus bridge device not detected. Exiting setup.")
            sys.exit(1)
    else:
        console.print("[yellow]Non-interactive mode: Skipping USB-to-CANBus bridge prompt.")

    # --- Check for legacy can0 setup ---
    legacy_iface_file = Path("/etc/network/interfaces.d/can0")
    interfaces_file = Path("/etc/network/interfaces")
    can0_exists = subprocess.run(["ip", "link", "show", "can0"], capture_output=True, text=True)
    legacy_config_found = False

    if can0_exists.returncode == 0:
        # can0 interface exists, check for legacy config files
        if legacy_iface_file.exists():
            legacy_config_found = True
            console.print("[yellow]Legacy CANBus config detected at /etc/network/interfaces.d/can0.")
        elif interfaces_file.exists():
            with interfaces_file.open() as f:
                if "can0" in f.read():
                    legacy_config_found = True
                    console.print("[yellow]Legacy CANBus config detected in /etc/network/interfaces.")

    if legacy_config_found:
        console.print("[yellow]Removing legacy CANBus setup before proceeding...")
        # Bring down can0 interface
        subprocess.run(["sudo", "ip", "link", "set", "can0", "down"])
        # Remove legacy config files
        if legacy_iface_file.exists():
            subprocess.run(["sudo", "rm", "-f", str(legacy_iface_file)])
            console.print("[green]Removed /etc/network/interfaces.d/can0")
        if interfaces_file.exists():
            # Remove can0 lines from /etc/network/interfaces with sudo (elevated permissions)
            # Read lines first
            lines = []
            with interfaces_file.open() as f:
                lines = f.readlines()
            # Write filtered lines to a temp file
            import tempfile
            with tempfile.NamedTemporaryFile("w", delete=False) as tmpf:
                for line in lines:
                    if "can0" not in line:
                        tmpf.write(line)
                tmp_path = tmpf.name
            # Move temp file to interfaces_file with sudo
            subprocess.run(["sudo", "mv", tmp_path, str(interfaces_file)], check=True)
            console.print("[green]Removed can0 entries from /etc/network/interfaces")
        # Restart networking
        subprocess.run(["sudo", "systemctl", "restart", "networking"])
        console.print("[green]Legacy CANBus setup removed. Proceeding with new setup...")

    # 1. Enable and start systemd-networkd
    console.print("[cyan]Enabling and starting systemd-networkd...")
    subprocess.run(["sudo", "systemctl", "enable", "systemd-networkd"])
    result = subprocess.run(["sudo", "systemctl", "start", "systemd-networkd"], capture_output=True, text=True)
    if "masked" in result.stderr:
        console.print("[yellow]systemd-networkd is masked, unmasking and starting...")
        subprocess.run(["sudo", "systemctl", "unmask", "systemd-networkd"])
        subprocess.run(["sudo", "systemctl", "start", "systemd-networkd"])
    # Check status
    status = subprocess.run(["systemctl"], capture_output=True, text=True)
    if "systemd-networkd" in status.stdout:
        console.print("[green]systemd-networkd service status:")
        console.print(status.stdout.split("systemd-networkd")[1].splitlines()[0])
    # 2. Disable wait-online
    console.print("[cyan]Disabling systemd-networkd-wait-online.service...")
    subprocess.run(["sudo", "systemctl", "disable", "systemd-networkd-wait-online.service"])
    # 3. Set CAN txqueuelen
    console.print("[cyan]Setting CAN txqueuelen udev rule...")
    subprocess.run(["bash", "-c", "echo -e 'SUBSYSTEM==\"net\", ACTION==\"change|add\", KERNEL==\"can*\"  ATTR{tx_queue_len}=\"128\"' | sudo tee /etc/udev/rules.d/10-can.rules > /dev/null"])
    # Show rule
    rule = subprocess.run(["cat", "/etc/udev/rules.d/10-can.rules"], capture_output=True, text=True)
    console.print("[green]udev rule set:")
    console.print(rule.stdout)
    # 4. Create systemd-networkd CAN config
    console.print("[cyan]Creating systemd-networkd CAN config...")
    subprocess.run(["bash", "-c", "echo -e '[Match]\\nName=can*\\n\\n[CAN]\\nBitRate=1M\\nRestartSec=0.1s\\n\\n[Link]\\nRequiredForOnline=no' | sudo tee /etc/systemd/network/25-can.network > /dev/null"])
    # Show config
    netconf = subprocess.run(["cat", "/etc/systemd/network/25-can.network"], capture_output=True, text=True)
    console.print("[green]CAN network config:")
    console.print(netconf.stdout)

    # 5. Verify CAN network interface is up
    console.print("[cyan]Verifying CAN network interface is up...")
    can_status = subprocess.run(["ip", "link", "show", "can0"], capture_output=True, text=True)
    if can_status.returncode == 0 and "state UP" in can_status.stdout:
        console.print("[bold green]can0 interface is UP and ready.")
    elif can_status.returncode == 0:
        console.print("[yellow]can0 interface found but not UP. Attempting to bring it up...")
        subprocess.run(["sudo", "ip", "link", "set", "can0", "up"])
        # Re-check status
        can_status = subprocess.run(["ip", "link", "show", "can0"], capture_output=True, text=True)
        if "state UP" in can_status.stdout:
            console.print("[bold green]can0 interface is now UP and ready.")
        else:
            console.print("[red]Failed to bring up can0 interface. Please check your hardware and configuration.")
    else:
        console.print("[red]can0 interface not found. Please check your CAN hardware and configuration.")

    # 6. Print cabling/termination advice
    console.print("\n[bold blue]CANBus Cabling & Termination Advice")
    console.print("- Ensure exactly two 120Ω termination resistors: one at each end of the CANBus line.")
    console.print("- Check crimps and strain relief on all connectors.")
    console.print("- Use flexible, stranded wire (22-26AWG recommended).\n")
    console.print("For more info, see: https://canbus.esoterical.online/Getting_Started.html#120r-termination-resistors and https://canbus.esoterical.online/Getting_Started.html#cabling")

@cli.command()
@click.option(
    "--board",
    type=click.Choice(["fps", "openams"], case_sensitive=False),
    help="Board to configure: 'fps' or 'openams'."
)
@click.option(
    "--mode",
    type=click.Choice(["bridge", "canbus"], case_sensitive=False),
    help="FPS board mode: 'bridge' or 'canbus'. Only used if --board=fps."
)
@click.option(
    "--allow-missing-programmer", is_flag=True, default=False,
    help="Allow running even if STM32_Programmer_CLI is not available (skip option byte programming)."
)
def deploy(board, mode, allow_missing_programmer):
    """Deploy Katapult and Klipper to the STM32G0B1 device."""
    script_dir = Path.cwd()
    console.rule("[bold blue]Starting Deployment")
    os.environ["PATH"] = f"{ENV_DIR}/bin:" + os.environ["PATH"]

    # Ensure the current working directory is up to date if it's a git repo
    if (script_dir / '.git').exists():
        console.print('[bold cyan]Updating current directory from git...')
        subprocess.run(['git', 'pull'], cwd=script_dir)

    # Board selection menu with visible options
    if not board:
        console.print("\nSelect the board to configure:")
        console.print("1. Filament Pressure Sensor board (FPS)")
        console.print("2. OpenAMS Mainboard")
        console.print("3. OpenAMS 2 Mainboard (coming soon)")
        board_choice = Prompt.ask(
            "Enter your choice [1/2]",
            choices=["1", "2"],
            default="1",
            show_choices=False
        )
        if board_choice == "1":
            board = "fps"
        elif board_choice == "2":
            board = "openams"
        else:
            console.print("[red]Invalid selection. Exiting.")
            sys.exit(1)

    # Helper to ensure device is attached to WSL if needed (shared for FPS and OpenAMS)
    def ensure_device_attached():
        if sys.platform == "win32" or os.environ.get("WSL_DISTRO_NAME"):
            console.print("[yellow]Detected Windows/WSL environment. Checking for usbipd-win...")
            usbipd_path = "/mnt/c/Windows/System32/usbipd.exe"
            if not Path(usbipd_path).exists():
                import shutil
                usbipd_path = shutil.which("usbipd.exe") or usbipd_path
            if not usbipd_path or not Path(usbipd_path).exists():
                console.print("[red]usbipd.exe not found. Downloading usbipd-win installer...")
                import urllib.request
                import shutil
                installer_url = "https://github.com/dorssel/usbipd-win/releases/download/v5.0.0/usbipd-win_5.0.0_x64.msi"
                installer_path = "/tmp/usbipd-win_5.0.0_x64.msi"
                with urllib.request.urlopen(installer_url) as response, open(installer_path, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                console.print(f"[yellow]Downloaded installer to {installer_path}. Launching installer...")
                win_installer_path = installer_path.replace("/mnt/c", "C:").replace("/", "\\") if installer_path.startswith("/mnt/c") else f"C:\\tmp\\usbipd-win_5.0.0_x64.msi"
                if not installer_path.startswith("/mnt/c"):
                    import subprocess as sp
                    sp.run(["mkdir", "-p", "/mnt/c/tmp"])
                    sp.run(["cp", installer_path, "/mnt/c/tmp/usbipd-win_5.0.0_x64.msi"])
                ps_cmd = ["powershell.exe", "Start-Process", win_installer_path, "-Wait"]
                console.print("[yellow]Starting usbipd-win installer in Windows. Please complete the installation in the Windows UI if prompted.")
                subprocess.run(ps_cmd)
                console.print("[green]usbipd-win installer finished. Continuing...")
            console.print("[yellow]Detected Windows/WSL environment. Attempting to automate usbipd attach...")
            try:
                result = subprocess.run([usbipd_path, "list"], capture_output=True, text=True)
                console.print("[yellow]usbipd list output:")
                console.print(result.stdout)
                stm32_line = next((line for line in result.stdout.splitlines() if "DFU in FS Mode" in line or "STM32" in line), None)
                if stm32_line:
                    busid = stm32_line.split()[0]
                    console.print(f"[yellow]Attempting to bind STM32 device with busid {busid}...")
                    bind_result = subprocess.run([usbipd_path, "bind", "--busid", busid], capture_output=True, text=True)
                    if 'Access denied' in bind_result.stderr:
                        console.print("\n[bold red]usbipd: Access denied; this operation requires administrator privileges.[/bold red]")
                        console.print("[yellow]To resolve this, follow these steps:")
                        console.print("1. Open a Windows Command Prompt or PowerShell as Administrator.")
                        console.print(f"2. Run the following commands, replacing <BUS-ID> with {busid} and <YourDistro> with your WSL distribution name (e.g., Ubuntu):\n")
                        console.print(f"   usbipd list")
                        console.print(f"   usbipd bind --busid={busid}")
                        console.print(f"   usbipd attach --wsl <YourDistro> --busid={busid}\n")
                        console.print("3. Return here and press Enter to continue after the device is attached.")
                        Prompt.ask("Press Enter when ready.")
                    if bind_result.returncode == 0:
                        console.print("[green]usbipd bind successful.")
                    else:
                        console.print(f"[red]usbipd bind failed: {bind_result.stderr}")
                        Prompt.ask("Please manually bind the device using usbipd, then press Enter to continue.")
                    distro = os.environ.get("WSL_DISTRO_NAME")
                    if not distro:
                        try:
                            with open("/etc/os-release") as f:
                                for line in f:
                                    if line.startswith("PRETTY_NAME="):
                                        distro = line.strip().split('=')[1].replace('"','').replace(' ', '-')
                                        break
                        except Exception:
                            distro = "Ubuntu"
                    console.print(f"[yellow]Attempting to attach STM32 device to WSL distro {distro} with busid {busid}...")
                    attach_result = subprocess.run([usbipd_path, "attach", "--wsl", distro, f"--busid={busid}"], capture_output=True, text=True)
                    if attach_result.returncode == 0:
                        console.print("[green]usbipd attach successful.")
                    else:
                        console.print(f"[red]usbipd attach failed: {attach_result.stderr}")
                        Prompt.ask("Please manually attach the device using usbipd, then press Enter to continue.")
                else:
                    console.print("[red]STM32 device not found in usbipd list. Please attach manually and press Enter to continue.")
                    Prompt.ask("Press Enter when ready.")
            except Exception as e:
                console.print(f"[red]Automatic usbipd attach failed: {e}\nPlease run the following in a Windows terminal as Administrator:")
                console.print("  usbipd list\n  usbipd bind --busid=<BUS-ID>\n  usbipd attach --wsl <YourDistro> --busid=<BUS-ID>")
                Prompt.ask("Press Enter when your device is attached to WSL and visible via 'lsusb' in this shell")

    # FPS logic
    if board == "fps":
        katapult_path = Path.home() / "katapult"
        if not katapult_path.exists():
            console.print("[cyan]Cloning Katapult...")
            subprocess.run(["git", "clone", KATAPULT_REPO, str(katapult_path)])
        else:
            console.print("[cyan]Updating Katapult...")
            subprocess.run(["git", "-C", str(katapult_path), "pull"])

        os.chdir(katapult_path)

        # Use mode from CLI if provided, otherwise prompt
        if not mode:
            mode = Prompt.ask("Configure FPS board for", choices=["bridge", "canbus"], default="bridge")
        else:
            mode = mode.lower()

        # Clean up old config files and run make clean before building
        for proj_path in [katapult_path, Path.home() / "klipper"]:
            for fname in [".config", ".config.old"]:
                f = proj_path / fname
                if f.exists():
                    f.unlink()
            # Run make clean if Makefile exists
            if (proj_path / "Makefile").exists():
                subprocess.run(["make", "clean"], cwd=proj_path)

        # Katapult config selection
        katapult_config_file = f".config-katapult-{mode}"
        console.print(f"[yellow]Using Katapult configuration: {katapult_config_file}")
        if not (script_dir / katapult_config_file).exists():
            console.print(f"[red]Katapult configuration file {katapult_config_file} not found in {script_dir}.")
            sys.exit(1)
        subprocess.run(["cp", str(script_dir / katapult_config_file), ".config"])

        console.print("[cyan]Building Katapult...")
        subprocess.run(["make"])

        bin_path = katapult_path / "out" / "katapult.bin"
        if not bin_path.exists():
            console.print("[bold red]Build failed. katapult.bin not found.")
            sys.exit(1)

        console.print("[bold magenta]Please plug in your STM32 device (DFU mode)...")
        
        # Set STM32 option bytes before flashing (on both Windows/WSL and Linux)
        set_option_bytes = False
        st_prog_paths = []
        if sys.platform == "win32" or os.environ.get("WSL_DISTRO_NAME"):
            # Windows/WSL: try both possible Windows paths for STM32_Programmer_CLI.exe
            st_prog_paths = [
                "/mnt/c/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe",
                "/mnt/c/Program\ Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"
            ]
            found_prog = None
            for path in st_prog_paths:
                if Path(path).exists():
                    found_prog = path
                    break
            if found_prog:
                set_option_bytes = True
                console.print(f"[yellow]Setting STM32 option bytes (nBOOT_SEL=0) using {found_prog} ...")
                win_path = found_prog.replace("/mnt/c/", "C:/").replace("/", "\\")
                ps_cmd = ["powershell.exe", "-Command", f"& '{win_path}' -c port=USB1 -ob nBOOT_SEL=0"]
                result = subprocess.run(ps_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
                if result.returncode == 0:
                    console.print("[green]Option bytes set successfully.")
                else:
                    console.print(f"[red]Failed to set option bytes: {result.stderr}")
                    sys.exit(1)
            else:
                if not allow_missing_programmer:
                    console.print("[red]STM32_Programmer_CLI.exe not found in standard locations. Please check your STM32CubeProgrammer installation.")
                    sys.exit(1)
                else:
                    console.print("[yellow]STM32_Programmer_CLI.exe not found, but --allow-missing-programmer is set. Skipping option byte programming.")
        else:
            # Linux: try to find STM32_Programmer_CLI in PATH
            from shutil import which
            st_prog_paths = ["/home/jrlomas/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI"]
            found_prog = None
            for path in st_prog_paths:
                if Path(path).exists():
                    found_prog = path
                    break
            st_prog = found_prog or which("STM32_Programmer_CLI")
            if st_prog:
                set_option_bytes = True
                console.print(f"[yellow]Setting STM32 option bytes (nBOOT_SEL=0) using {st_prog} ...")
                result = subprocess.run([st_prog, "-c", "port=USB1", "-ob", "nBOOT_SEL=0"], capture_output=True, text=True)
                if result.returncode == 0:
                    console.print("[green]Option bytes set successfully.")
                else:
                    console.print(f"[red]Failed to set option bytes: {result.stderr}")
                    sys.exit(1)
            else:
                if not allow_missing_programmer:
                    console.print("[red]STM32_Programmer_CLI not found in PATH. Please install STM32CubeProgrammer and ensure STM32_Programmer_CLI is available.")
                    sys.exit(1)
                else:
                    console.print("[yellow]STM32_Programmer_CLI not found, but --allow-missing-programmer is set. Skipping option byte programming.")

        ensure_device_attached()

        # Wait for STM32 device in DFU mode
        while True:
            result = subprocess.run(["sudo", "dfu-util", "-l"], capture_output=True, text=True)
            if "Found DFU: [0483:df11]" in result.stdout:
                break
            time.sleep(1)

        # Optionally, print the found DFU devices for user clarity
        console.print("[green]Device detected. DFU devices found:")
        console.print(result.stdout)
        console.print("[green]Flashing Katapult with mass erase...")
        subprocess.run(["sudo", "dfu-util", "-a", "0", "-s", "0x08000000:force:mass-erase", "-D", str(bin_path)])

        klipper_path = Path.home() / "klipper"
        if not klipper_path.exists():
            console.print("[cyan]Cloning Klipper...")
            subprocess.run(["git", "clone", KLIPPER_REPO, str(klipper_path)])
        else:
            console.print("[cyan]Updating Klipper...")
            subprocess.run(["git", "-C", str(klipper_path), "pull"])

        os.chdir(klipper_path)

        # Klipper config selection
        klipper_config_file = f".config-klipper-{mode}"
        console.print(f"[yellow]Using Klipper configuration: {klipper_config_file}")
        if not (script_dir / klipper_config_file).exists():
            console.print(f"[red]Klipper configuration file {klipper_config_file} not found in {script_dir}.")
            sys.exit(1)
        subprocess.run(["cp", str(script_dir / klipper_config_file), ".config"])
        console.print("[cyan]Building Klipper...")
        subprocess.run(["make"])

        klipper_bin = klipper_path / "out" / "klipper.bin"
        if not klipper_bin.exists():
            console.print("[bold red]Klipper build failed. klipper.bin not found.")
            sys.exit(1)

        console.print("[bold magenta]Flashing Klipper to offset 8KiB (0x08002000)...")
        subprocess.run(["sudo", "dfu-util", "-a", "0", "-s", "0x08002000", "-D", str(klipper_bin)])

        console.print("[bold green]Deployment complete. Verify operation on your FPS board.")
        return

    # OpenAMS Mainboard logic
    if board == "openams":
        import re
        fw_dir = script_dir / "firmwares" / "openams"
        def find_latest_bin(prefix):
            bins = list(fw_dir.glob(f"{prefix}_*.bin"))
            def version_tuple(f):
                m = re.search(rf'{prefix}_(\d+)\.(\d+)\.(\d+)\.bin', f.name)
                return tuple(map(int, m.groups())) if m else (0, 0, 0)
            bins = [f for f in bins if version_tuple(f) != (0, 0, 0)]
            if not bins:
                return None
            return max(bins, key=version_tuple)
        kancan_bin = find_latest_bin("kancan")
        oams_bin = find_latest_bin("oams")
        if not kancan_bin or not oams_bin:
            console.print(f"[red]Could not find both kancan_*.bin and oams_*.bin in {fw_dir}")
            sys.exit(1)
        console.print(f"[yellow]Flashing {kancan_bin.name} to 0x08000000 and {oams_bin.name} to 0x08002000")

        ensure_device_attached()

        # Wait for STM32 device in DFU mode
        while True:
            result = subprocess.run(["sudo", "dfu-util", "-l"], capture_output=True, text=True)
            if "Found DFU: [0483:df11]" in result.stdout:
                break
            time.sleep(1)
        console.print("[green]Device detected. DFU devices found:")
        console.print(result.stdout)
        console.print("[green]Flashing OpenAMS Mainboard firmware...")
        subprocess.run(["sudo", "dfu-util", "-a", "0", "-s", "0x08000000:force:mass-erase", "-D", str(kancan_bin)])
        subprocess.run(["sudo", "dfu-util", "-a", "0", "-s", "0x08002000", "-D", str(oams_bin)])
        console.print("[bold green]Deployment complete. Verify operation on your OpenAMS Mainboard.")
        return

@cli.command()
def query():
    """Query the CANBus network for Klipper devices and display UUIDs."""
    console.rule("[bold blue]Querying CANBus Network")

    # Ensure 'can' pip package is installed in the venv
    pip = ENV_DIR / "bin" / "pip"
    result = subprocess.run([str(pip), "show", "python-can"], capture_output=True, text=True)
    if result.returncode != 0:
        console.print("[yellow]python-can package not found. Installing...")
        subprocess.run([str(pip), "install", "python-can"])

    # Run the canbus_query script
    canbus_query_script = Path.home() / "klipper" / "scripts" / "canbus_query.py"
    if not canbus_query_script.exists():
        console.print(f"[red]canbus_query.py script not found at {canbus_query_script}")
        sys.exit(1)

    console.print(f"[cyan]Running: {canbus_query_script} can0")
    result = subprocess.run([str(VENV_PYTHON), str(canbus_query_script), "can0"], capture_output=True, text=True)
    if result.returncode == 0:
        console.print("[green]CANBus query result:")
        console.print(result.stdout)
        import re
        uuids = re.findall(r'canbus_uuid=([0-9a-fA-F]+)', result.stdout)
        if uuids:
            console.print(f"[bold green]Found {len(uuids)} UUID(s):")
            for i, uuid in enumerate(uuids, 1):
                console.print(f"  [cyan]{i}: {uuid}[/cyan]")
        else:
            console.print("[yellow]No UUIDs found in CANBus query output.")
    else:
        console.print(f"[red]CANBus query failed:\n{result.stderr}")

@cli.command()
def setup_klipper_config():
    """Set up Klipper configuration (oams.cfg and macros) using CANBus UUIDs."""
    import re
    import requests
    from rich.prompt import IntPrompt

    # Ask user to enter the UUIDs found (from query)
    console.print("[bold blue]Klipper Configuration Setup")
    uuids_input = Prompt.ask("Enter the CANBus UUIDs found (comma separated, in order: FPS, Mainboard)")
    uuids = [u.strip() for u in uuids_input.split(",") if u.strip()]
    if len(uuids) < 2:
        console.print("[red]At least two UUIDs are required (one FPS and one Mainboard).")
        return

    # Let user select which UUID is FPS and which is Mainboard
    console.print("\nSelect the UUID for each device:")
    for idx, uuid in enumerate(uuids, 1):
        console.print(f"  {idx}: {uuid}")

    fps_idx = IntPrompt.ask("Enter the number for the FPS board UUID", choices=[str(i) for i in range(1, len(uuids)+1)])
    mainboard_idx = IntPrompt.ask("Enter the number for the Mainboard UUID", choices=[str(i) for i in range(1, len(uuids)+1) if str(i) != str(fps_idx)])

    selected = [
        (uuids[fps_idx-1], "fps"),
        (uuids[mainboard_idx-1], "mainboard")
    ]

    # Download oams_sample.cfg and oams_macros.cfg if not present
    klipper_openams_repo = "https://raw.githubusercontent.com/OpenAMSOrg/klipper_openams/master/"
    sample_cfg_path = Path("/tmp/oams_sample.cfg")
    macros_cfg_path = Path("/tmp/oams_macros.cfg")
    for url, path in [
        (klipper_openams_repo + "oams_sample.cfg", sample_cfg_path),
        (klipper_openams_repo + "oams_macros.cfg", macros_cfg_path)
    ]:
        if not path.exists():
            r = requests.get(url)
            if r.status_code == 200:
                path.write_text(r.text)
            else:
                console.print(f"[red]Failed to download {url}")
                return

    # Prepare output config directory
    config_dir = Path.home() / "printer_data" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    oams_cfg_path = config_dir / "oams.cfg"
    oams_macros_path = config_dir / "oams_macros.cfg"

    # Check if oams.cfg already exists
    if oams_cfg_path.exists():
        overwrite = Confirm.ask("[yellow]oams.cfg already exists. Overwrite?", default=False)
        if not overwrite:
            console.print("[yellow]Not overwriting existing oams.cfg.")
            return

    # Fill in oams_sample.cfg with selected UUIDs and IDs
    sample_cfg = sample_cfg_path.read_text()
    fps_uuid = selected[0][0]  # UUID for FPS
    mainboard_uuid = selected[1][0]  # UUID for Mainboard

    # Replace the UUID placeholders in the sample config
    sample_cfg = sample_cfg.replace("canbus_uuid: <your_unique_FPS_UUID>", f"canbus_uuid: {fps_uuid}")
    sample_cfg = sample_cfg.replace("canbus_uuid: <your_unique_OAMS_MCU1_UUID>", f"canbus_uuid: {mainboard_uuid}")

    # Write the filled config
    oams_cfg_path.write_text(sample_cfg)
    console.print(f"[green]Wrote new oams.cfg to {oams_cfg_path}")

    # Copy macros file
    shutil.copy(macros_cfg_path, oams_macros_path)
    console.print(f"[green]Copied oams_macros.cfg to {oams_macros_path}")

    # Check printer.cfg for include
    printer_cfg_path = config_dir / "printer.cfg"
    if not printer_cfg_path.exists():
        console.print(f"[yellow]printer.cfg not found at {printer_cfg_path}. Please add the include manually.")
        return

    printer_cfg = printer_cfg_path.read_text()
    include_line = "[include oams.cfg]"
    if include_line in printer_cfg:
        console.print("[green]printer.cfg already includes oams.cfg.")
    else:
        add_include = Confirm.ask("[yellow]printer.cfg does not include oams.cfg. Add it now?", default=True)
        if add_include:
            # Add include at the end
            with printer_cfg_path.open("a") as f:
                f.write(f"\n{include_line}\n")
            console.print("[green]Added oams.cfg include to printer.cfg.")
        else:
            console.print("[yellow]Did not modify printer.cfg. Please add the include manually if needed.")

    # ...after querying and saving FPS UUID...
    install_openams_assistant_service()
    console.print("[bold cyan]System will now continue setup using the OpenAMS Assistant service.")

def install_openams_assistant_service():
    """
    Installs and enables the openams-assistant systemd service.
    Assumes openams-assistant.systemd and assistant.py are in the same directory as this script.
    """
    import shutil

    script_dir = Path(__file__).parent
    service_src = script_dir / "openams-assistant.systemd"
    service_dst = Path("/etc/systemd/system/openams-assistant.service")
    assistant_src = script_dir / "assistant.py"
    assistant_dst = Path("/usr/local/bin/openams-assistant")

    # Copy the systemd service file
    shutil.copyfile(service_src, service_dst)
    os.chmod(service_dst, 0o644)

    # Copy the assistant script and make it executable
    shutil.copyfile(assistant_src, assistant_dst)
    os.chmod(assistant_dst, 0o755)

    # Reload systemd, enable and start the service
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", "--now", "openams-assistant.service"])

    console.print("[bold green]OpenAMS Assistant service installed and started.")

@cli.command()
def install_assistant():
    """Install and enable the OpenAMS Assistant systemd service."""
    install_openams_assistant_service()

if __name__ == "__main__":
    cli()