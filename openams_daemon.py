import time
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
import sys
import json
import subprocess
import re
import os

VENV_PYTHON = str(Path.home() / ".openams_env" / "bin" / "python")
OPENAMS_CLI = str(Path(__file__).parent / "openams_cli.py")

LOG_PATH = "/var/log/openams_assistant.log"
STATE_PATH = "/var/lib/openams_assistant/state.json"
console = Console()

def log(msg):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"{time.ctime()}: {msg}\n")
    except Exception:
        pass

def load_state():
    if Path(STATE_PATH).exists():
        try:
            with open(STATE_PATH) as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)

def query_uuid():
    result = subprocess.run(
        [VENV_PYTHON, OPENAMS_CLI, "query"],
        capture_output=True, text=True
    )
    uuids = re.findall(r'canbus_uuid=([0-9a-fA-F]+)', result.stdout)
    return uuids

def run_and_log(cmd, **kwargs):
    # Stream output to console and log file
    log(f"Running: {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs)
    for line in process.stdout:
        print(line, end='')
        log(line.rstrip())
    process.wait()
    return process.returncode

def start_klipper():
    run_and_log(["sudo", "systemctl", "enable", "klipper"])
    run_and_log(["sudo", "systemctl", "start", "klipper"])
    log("Klipper enabled and started.")

def print_summary(state):
    table = [
        ("FPS", state.get("fps_uuid", "N/A")),
        ("Mainboard", state.get("mainboard_uuid", "N/A"))
    ]
    console.print("[bold green]OpenAMS Setup Summary")
    for comp, uuid in table:
        console.print(f"[cyan]{comp}: [magenta]{uuid}")
    console.print(f"[bold blue]Log file: {LOG_PATH}")

def uninstall_self():
    """
    Disables and removes the openams-daemon systemd service and deletes the daemon script.
    """
    service_path = "/etc/systemd/system/openams-daemon.service"
    daemon_path = "/usr/local/bin/openams-daemon"
    try:
        console.print("[yellow]Uninstalling openams-daemon systemd service...")
        log("Uninstalling openams-daemon systemd service...")
        # Disable and stop the service
        subprocess.run(["sudo", "systemctl", "disable", "--now", "openams-daemon.service"], check=False)
        # Remove the service file
        subprocess.run(["sudo", "rm", "-f", service_path], check=False)
        # Remove the daemon script
        subprocess.run(["sudo", "rm", "-f", daemon_path], check=False)
        # Reload systemd
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=False)
        console.print("[green]openams-daemon service uninstalled.")
        log("openams-daemon service uninstalled.")
    except Exception as e:
        console.print(f"[red]Failed to uninstall openams-daemon: {e}")
        log(f"Failed to uninstall openams-daemon: {e}")

def main():
    state = load_state()
    console.rule("[bold blue]OpenAMS Daemon: Waiting for Both UUIDs")
    console.print("[cyan]Waiting for both FPS and Mainboard UUIDs to appear on CANBus...")

    timeout = 900  # seconds (15 minutes)
    start_time = time.time()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Scanning CANBus for both UUIDs...", start=True)
        while True:
            uuids = query_uuid()
            if state.get("fps_uuid") in uuids and len(uuids) > 1:
                mainboard_uuid = [u for u in uuids if u != state["fps_uuid"]][0]
                state["mainboard_uuid"] = mainboard_uuid
                save_state(state)
                console.print(f"[green]Mainboard UUID detected: {mainboard_uuid}")
                log(f"Mainboard UUID: {mainboard_uuid}")
                break
            elapsed = time.time() - start_time
            progress.update(task, description=f"[cyan]Scanning CANBus for both UUIDs... ({int(elapsed)}s elapsed)")
            if elapsed > timeout:
                console.print("[red]Timeout: Could not detect both UUIDs on CANBus after 900 seconds.")
                log("Timeout waiting for both UUIDs on CANBus.")
                sys.exit(1)
            time.sleep(2)

    # 14. Setup macros and config
    console.rule("[bold blue]Klipper Configuration")
    console.print("[cyan]Setting up Klipper macros and config...")
    run_and_log([
        VENV_PYTHON, OPENAMS_CLI, "setup_klipper_config"
    ])

    # 15. Re-enable and restart Klipper
    console.rule("[bold blue]Restarting Klipper")
    console.print("[cyan]Re-enabling and restarting Klipper...")
    start_klipper()

    # 16. Print summary and exit
    console.rule("[bold green]OpenAMS Setup Complete")
    print_summary(state)
    log("OpenAMS Assistant completed successfully.")

    # Uninstall self
    uninstall_self()

if __name__ == "__main__":
    main()