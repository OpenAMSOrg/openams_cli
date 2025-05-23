import os
import subprocess
import sys
import time
from pathlib import Path

ENV_DIR = Path.home() / ".openams_env"
VENV_PYTHON = ENV_DIR / "bin" / "python"
VENV_PIP = ENV_DIR / "bin" / "pip"

# Step 1: Minimal environment setup to bootstrap required packages
if not ENV_DIR.exists():
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

APT_PACKAGES = [
    "gcc-arm-none-eabi", "make", "dfu-util", "git", "python3-venv"
]

KATAPULT_REPO = "https://github.com/Arksine/katapult"
KLIPPER_REPO = "https://github.com/Klipper3d/klipper"

@click.group()
def cli():
    pass

@cli.command()
def setup():
    """Set up local Python environment and install dependencies."""
    console.rule("[bold green]Environment Setup")

    # Install system packages
    console.print("[bold cyan]Installing system dependencies (requires sudo)...")
    subprocess.run(["sudo", "apt", "update"])
    subprocess.run(["sudo", "apt", "install", "-y"] + APT_PACKAGES)

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

    console.print("[bold green]Setup complete. Run the script with the [bold]deploy[/bold] command to continue.")

@cli.command()
def deploy():
    """Deploy Katapult and Klipper to the STM32G0B1 device."""
    console.rule("[bold blue]Starting Deployment")
    os.environ["PATH"] = f"{ENV_DIR}/bin:" + os.environ["PATH"]

    katapult_path = Path.home() / "katapult"
    if not katapult_path.exists():
        console.print("[cyan]Cloning Katapult...")
        subprocess.run(["git", "clone", KATAPULT_REPO, str(katapult_path)])
    else:
        console.print("[cyan]Updating Katapult...")
        subprocess.run(["git", "-C", str(katapult_path), "pull"])

    os.chdir(katapult_path)

    # Determine mode based on printer.cfg
    printer_cfg_path = Path.home() / "printer_data" / "config" / "printer.cfg"
    if printer_cfg_path.exists():
        with printer_cfg_path.open() as f:
            contents = f.read()
        if "canbus_serial" in contents:
            mode = "canbus"
            console.print("[green]Detected canbus mode from printer.cfg")
        else:
            mode = "bridge"
            console.print("[green]Detected bridge mode from printer.cfg")
    else:
        mode = Prompt.ask("printer.cfg not found. Configure FPS board for", choices=["bridge", "canbus"], default="bridge")

    # Katapult config selection
    katapult_config_file = f".config-katapult-{mode}"
    console.print(f"[yellow]Using Katapult configuration: {katapult_config_file}")
    subprocess.run(["cp", str(katapult_config_file), ".config"])

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
            console.print("[red]STM32_Programmer_CLI.exe not found in standard locations. Please check your STM32CubeProgrammer installation.")
            sys.exit(1)
    else:
        # Linux: try to find STM32_Programmer_CLI in PATH
        from shutil import which
        st_prog = which("STM32_Programmer_CLI")
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
            console.print("[red]STM32_Programmer_CLI not found in PATH. Please install STM32CubeProgrammer and ensure STM32_Programmer_CLI is available.")
            sys.exit(1)

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
            # Use the correct installer filename for v5.0.0 (usbipd-win_5.0.0_x64.msi)
            installer_url = "https://github.com/dorssel/usbipd-win/releases/download/v5.0.0/usbipd-win_5.0.0_x64.msi"
            installer_path = "/tmp/usbipd-win_5.0.0_x64.msi"
            with urllib.request.urlopen(installer_url) as response, open(installer_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            console.print(f"[yellow]Downloaded installer to {installer_path}. Launching installer...")
            # Launch installer via Windows
            win_installer_path = installer_path.replace("/mnt/c", "C:").replace("/", "\\") if installer_path.startswith("/mnt/c") else f"C:\\tmp\\usbipd-win_5.0.0_x64.msi"
            # Move to /mnt/c/tmp if needed
            if not installer_path.startswith("/mnt/c"):
                import subprocess as sp
                sp.run(["mkdir", "-p", "/mnt/c/tmp"])
                sp.run(["cp", installer_path, "/mnt/c/tmp/usbipd-win_5.0.0_x64.msi"])
            # Start installer using powershell
            ps_cmd = ["powershell.exe", "Start-Process", win_installer_path, "-Wait"]
            console.print("[yellow]Starting usbipd-win installer in Windows. Please complete the installation in the Windows UI if prompted.")
            subprocess.run(ps_cmd)
            console.print("[green]usbipd-win installer finished. Continuing...")
        console.print("[yellow]Detected Windows/WSL environment. Attempting to automate usbipd attach...")
        # Try to call usbipd.exe from WSL if available
        try:
            # List USB devices
            result = subprocess.run([usbipd_path, "list"], capture_output=True, text=True)
            console.print("[yellow]usbipd list output:")
            console.print(result.stdout)
            # Try to find STM32 device in the list
            stm32_line = next((line for line in result.stdout.splitlines() if "DFU in FS Mode" in line or "STM32" in line), None)
            if stm32_line:
                # Extract busid (format: BUSID  VID:PID  DEVICE)
                busid = stm32_line.split()[0]
                console.print(f"[yellow]Attempting to bind STM32 device with busid {busid}...")
                bind_result = subprocess.run([usbipd_path, "bind", "--busid", busid], capture_output=True, text=True)
                if bind_result.returncode == 0:
                    console.print("[green]usbipd bind successful.")
                else:
                    console.print(f"[red]usbipd bind failed: {bind_result.stderr}")
                    Prompt.ask("Please manually bind the device using usbipd, then press Enter to continue.")
                # Attach to WSL
                distro = os.environ.get("WSL_DISTRO_NAME")
                if not distro:
                    # Try to get from /etc/os-release if not set
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
    subprocess.run(["cp", str(klipper_config_file), ".config"])
    console.print("[cyan]Building Klipper...")
    subprocess.run(["make"])

    klipper_bin = klipper_path / "out" / "klipper.bin"
    if not klipper_bin.exists():
        console.print("[bold red]Klipper build failed. klipper.bin not found.")
        sys.exit(1)

    console.print("[bold magenta]Flashing Klipper to offset 8KiB (0x08002000)...")
    subprocess.run(["sudo", "dfu-util", "-a", "0", "-s", "0x08002000", "-D", str(klipper_bin)])

    console.print("[bold green]Deployment complete. Verify operation on your FPS board.")

if __name__ == "__main__":
    cli()