import os
import sys
import subprocess
import time
import json
from pathlib import Path

# --- Bootstrap: ensure venv and rich, then re-exec in venv if needed ---
VENV_DIR = Path.home() / ".openams_env"
VENV_PYTHON = VENV_DIR / "bin" / "python"

if sys.executable != str(VENV_PYTHON):
    # Not running in venv: ensure venv exists and rich is installed, then re-exec
    if not VENV_DIR.exists():
        subprocess.run(["python3", "-m", "venv", str(VENV_DIR)], check=True)
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "rich"], check=True)
    # Re-exec this script in the venv
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)

# Now safe to import rich
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

# --- Ensure venv site-packages is in sys.path ---
site_packages = None
if VENV_DIR.exists():
    # Find the correct site-packages directory
    lib_dir = VENV_DIR / "lib"
    if lib_dir.exists():
        for sub in lib_dir.iterdir():
            if sub.name.startswith("python"):
                candidate = sub / "site-packages"
                if candidate.exists():
                    site_packages = candidate
                    break
if site_packages and str(site_packages) not in sys.path:
    sys.path.insert(0, str(site_packages))

LOG_PATH = "/var/log/openams_assistant.log"
STATE_PATH = "/var/lib/openams_assistant/state.json"
console = Console()

# Ensure log and state files exist and are writable by the user
def ensure_paths_writable():
    for path in [LOG_PATH, STATE_PATH]:
        parent = Path(path).parent
        if not parent.exists():
            subprocess.run(["sudo", "mkdir", "-p", str(parent)], check=True)
        # Create the file if it doesn't exist
        subprocess.run(["sudo", "touch", path], check=True)
        # Set permissions to rw-rw-rw- (666)
        subprocess.run(["sudo", "chmod", "666", path], check=True)

ensure_paths_writable()

def log(msg):
    try:
        Path(LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(f"{time.ctime()}: {msg}\n")
    except PermissionError:
        if os.geteuid() != 0:
            # Try once with sudo, then give up if it fails
            try:
                console.print(f"[yellow]Permission denied for {LOG_PATH}. Trying with sudo...")
                subprocess.run(["sudo", "mkdir", "-p", str(Path(LOG_PATH).parent)], check=True)
                subprocess.run([
                    "sudo", "bash", "-c",
                    f"echo '{time.ctime()}: {msg}' >> {LOG_PATH}"
                ], check=True)
            except Exception as e:
                console.print(f"[red]Failed to write log with sudo: {e}. Logging disabled for this session.")
                # Disable further logging by replacing log with a no-op
                globals()["log"] = lambda msg: None
        else:
            raise

def save_state(state):
    Path(STATE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)

def load_state():
    if Path(STATE_PATH).exists():
        try:
            with open(STATE_PATH) as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load state file ({e}). Starting with empty state.")
            return {}
    return {}

def run_and_log(cmd, use_venv_python=False, **kwargs):
    if use_venv_python and cmd[0] == "python3":
        cmd = [str(VENV_PYTHON)] + cmd[1:]
    log(f"Running: {' '.join(cmd)}")
    # Inherit stdout/stderr so colors and animations are preserved
    result = subprocess.run(cmd, **kwargs)
    return result

def wait_for_dfu():
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Waiting for STM32 device in DFU mode...", start=False)
        while True:
            result = subprocess.run(["dfu-util", "-l"], capture_output=True, text=True)
            if "Found DFU: [0483:df11]" in result.stdout:
                progress.update(task, description="[green]DFU device detected!")
                break
            time.sleep(1)

def wait_for_can_bridge():
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Waiting for CAN bridge (can0)...", start=False)
        while True:
            result = subprocess.run(["ip", "link", "show", "can0"], capture_output=True, text=True)
            if result.returncode == 0:
                progress.update(task, description="[green]CAN bridge detected!")
                break
            time.sleep(1)

def query_uuid():
    result = subprocess.run(
        [str(VENV_PYTHON), str(Path(__file__).parent / "openams_cli.py"), "query"],
        capture_output=True, text=True
    )
    import re
    uuids = re.findall(r'canbus_uuid=([0-9a-fA-F]+)', result.stdout)
    return uuids

def stop_klipper():
    result = subprocess.run(["systemctl", "is-active", "klipper"], capture_output=True, text=True)
    if result.stdout.strip() == "active":
        console.print("[yellow]Stopping Klipper service...")
        run_and_log(["sudo", "systemctl", "stop", "klipper"])
        log("Klipper stopped.")

def start_klipper():
    run_and_log(["sudo", "systemctl", "enable", "klipper"])
    run_and_log(["sudo", "systemctl", "start", "klipper"])
    log("Klipper enabled and started.")

def print_summary(state):
    table = Table(title="OpenAMS Setup Summary")
    table.add_column("Component", style="cyan")
    table.add_column("UUID", style="magenta")
    table.add_row("FPS", state.get("fps_uuid", "N/A"))
    table.add_row("Mainboard", state.get("mainboard_uuid", "N/A"))
    console.print(table)
    console.print(f"[bold blue]Log file: {LOG_PATH}")

def install_openams_daemon_service():
    import shutil

    script_dir = Path(__file__).parent
    daemon_src = script_dir / "openams_daemon.py"
    daemon_dst = Path("/usr/local/bin/openams-daemon")
    service_dst = Path("/etc/systemd/system/openams-daemon.service")
    venv_python = Path.home() / ".openams_env" / "bin" / "python"

    # Copy the daemon script and make it executable
    shutil.copyfile(daemon_src, daemon_dst)
    os.chmod(daemon_dst, 0o755)

    # Write the systemd service file
    service_contents = f"""[Unit]
Description=OpenAMS CANBus UUID Wait Daemon
After=network.target

[Service]
Type=simple
Environment="PATH={venv_python.parent}:$PATH"
Environment="VIRTUAL_ENV={venv_python.parent.parent}"
ExecStart={venv_python} {daemon_dst}
Restart=on-failure
User={os.environ.get('USER', 'pi')}

[Install]
WantedBy=multi-user.target
"""
    subprocess.run(["sudo", "tee", str(service_dst)], input=service_contents.encode(), check=True)
    subprocess.run(["sudo", "chmod", "644", str(service_dst)], check=True)
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "enable", "--now", "openams-daemon.service"])
    console.print("[bold green]OpenAMS Daemon service installed and started.")

def assistant():
    state = load_state()
    console.rule("[bold blue]OpenAMS Assistant")
    log("Starting OpenAMS Assistant")
    console.print("[bold blue]Welcome to the OpenAMS Assistant!")
    console.print("[bold green]This wizard will guide you through the complete setup process.")
    console.print(f"[bold yellow]All actions are logged to {LOG_PATH}\n")

    # 1. Setup environment
    console.rule("[bold blue]Step 1/10: Python Environment Setup")
    console.print("[cyan]Setting up Python environment...")
    run_and_log([str(VENV_PYTHON), str(Path(__file__).parent / "openams_cli.py"), "setup", "--allow-missing-programmer"])

    # 2. Shutdown Klipper
    console.rule("[bold blue]Step 2/10: Stopping Klipper")
    stop_klipper()

    # 3. Instruct user for BOOT jumper
    console.rule("[bold blue]Step 3/10: Prepare FPS Board")
    console.print("[bold magenta]🛠️  Please place the BOOT jumper on the FPS board, connect it to the RPI, and press [bold]Enter[/bold] to continue.")
    input()

    # 4. Wait for DFU device
    console.rule("[bold blue]Step 4/10: Detect FPS Board in DFU Mode")
    wait_for_dfu()
    log("FPS board detected in DFU mode.")

    # 5. Flash FPS firmware
    console.rule("[bold blue]Step 5/10: Flash FPS Firmware")
    console.print("[cyan]Flashing FPS firmware...")
    run_and_log([
        str(VENV_PYTHON), str(Path(__file__).parent / "openams_cli.py"), "deploy", "--board", "fps", "--mode", "bridge", "--allow-missing-programmer"
    ])

    # 6. Instruct user to remove jumper and replug
    console.rule("[bold blue]Step 6/10: Reconnect FPS Board")
    console.print("[bold magenta]🔌 Remove the BOOT jumper, unplug, and replug the FPS board, then press [bold]Enter[/bold].")
    input()

    # 7. Wait for bridge device
    console.rule("[bold blue]Step 7/10: Detect CAN Bridge")
    wait_for_can_bridge()
    log("FPS bridge detected.")

    # 8. Setup CANBus
    console.rule("[bold blue]Step 8/10: CANBus Setup")
    console.print("[cyan]Setting up CANBus...")
    run_and_log([str(VENV_PYTHON), str(Path(__file__).parent / "openams_cli.py"), "setup-canbus", "--non-interactive"])

    # 9. Query CANBus for FPS UUID
    console.rule("[bold blue]Step 9/10: Query FPS UUID")
    console.print("[cyan]Querying CANBus for FPS UUID...")
    uuids = query_uuid()
    if not uuids or len(uuids) != 1:
        console.print("[red]Could not detect FPS UUID. Aborting.")
        log("FPS UUID not found.")
        print_summary(state)
        sys.exit(1)
    state["fps_uuid"] = uuids[0]
    save_state(state)
    console.print(f"[green]FPS UUID recorded: {uuids[0]}")
    log(f"FPS UUID: {uuids[0]}")

    # 10. Prompt for mainboard in DFU mode
    console.rule("[bold blue]Step 10/10: Prepare Mainboard")
    console.print("[bold magenta]🛠️  Plug in the mainboard in DFU mode and press [bold]Enter[/bold].")
    input()

    # 11. Flash mainboard
    console.rule("[bold blue]Flashing Mainboard Firmware")
    console.print("[cyan]Flashing mainboard firmware...")
    run_and_log([str(VENV_PYTHON), str(Path(__file__).parent / "openams_cli.py"), "deploy", "--board", "openams"])

    install_openams_daemon_service()

    # 12. Final hardware instructions
    console.rule("[bold blue]Hardware Installation")
    console.print("[bold green]Install FPS and mainboard, make all connections, then restart the printer. Press [bold]Enter[/bold] when ready.")
    input()


if __name__ == "__main__":
    assistant()