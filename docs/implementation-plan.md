# Implementation plan for the Zorin 18 tray utility

## Goal

Create a small Python application that:
- sits in the system tray
- lets the user choose the default copy count for the printer queue
- applies the correct CUPS setting for `Rollo_X1040USB`
- resets the copy count back to 1 after printing finishes
- starts automatically on login and survives reboot

## Problem to solve

The printer queue is ignoring the GUI copy-selection value at the application level, but the following command works:

```bash
lpoptions -p Rollo_X1040USB -o copies=3
```

The app should wrap that working command in a simple desktop interface and automatic service lifecycle.

## Proposed solution

### A. Python tray app
Create a desktop app with a tray icon and a simple menu.

Example menu items:
- # of pages to print: 1
- # of pages to print: 2
- # of pages to print: 3
- # of pages to print: 4
- # of pages to print: 5
- # of pages to print: 10
- Enter custom number...
- Reset to 1

The app will execute:

```bash
lpoptions -p Rollo_X1040USB -o copies=<N>
```

for the selected copy count.

### B. Queue watcher
Add a background thread or polling loop to check if a print job is active.

Pseudo-logic:

```python
while True:
    if printer_has_active_jobs('Rollo_X1040USB'):
        sleep(5)
        continue
    set_copies(1)
    break
```

This ensures the queue is only reset after printing is done.

### C. Systemd user service
Create a service file:

```ini
[Unit]
Description=Rollo printer copy helper
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/<user>/rollo-copies/rollo_copies_app.py
Restart=on-failure

[Install]
WantedBy=default.target
```

Enable it with:

```bash
systemctl --user daemon-reload
systemctl --user enable --now rollo-copies.service
loginctl enable-linger "$USER"
```

### D. Desktop autostart fallback
Create a launcher in:

```bash
~/.config/autostart/rollo-copies.desktop
```

This helps the app appear after login even if the user service is delayed or the desktop environment is not fully initialized.

## Project structure

```text
rollo-printer/
├── docs/
│   ├── solution-overview.md
│   └── implementation-plan.md
├── app/
│   ├── main.py
│   ├── tray.py
│   ├── cups_helper.py
│   ├── queue_watcher.py
│   └── config.py
├── install/
│   ├── install.sh
│   ├── rollo-copies.service
│   └── rollo-copies.desktop
├── requirements.txt
└── README.md
```

## Files to implement

### 1) `app/cups_helper.py`
Responsible for all CUPS commands.

Functions:
- `set_copies(count: int) -> None`
- `reset_to_default() -> None`
- `get_active_job_count() -> int`

Implementation sketch:

```python
import subprocess

PRINTER = "Rollo_X1040USB"


def run_cups_command(args):
    subprocess.run(["lpoptions", "-p", PRINTER, *args], check=True)


def set_copies(count: int):
    run_cups_command(["-o", f"copies={count}"])


def reset_to_default():
    set_copies(1)
```

### 2) `app/queue_watcher.py`
Responsible for waiting until printing finishes.

Use:

```bash
lpstat -o Rollo_X1040USB
```

or parse job output from `lpstat -p` if needed.

The watcher should wait until the queue is empty before resetting to 1.

### 3) `app/tray.py`
Use Qt tray API.

Responsibilities:
- build menu
- react to user selection
- provide a custom numeric entry action labeled `# of pages to print`
- display current copy count
- keep app running in tray mode

### 4) `app/main.py`
Entry point.

Responsibilities:
- initialize tray app
- launch queue watcher
- handle app start and shutdown

## Install flow for the user

1. Copy app files into a permanent user directory such as:

```bash
~/apps/rollo-copies
```

2. Install dependencies:

```bash
python3 -m venv ~/.venvs/rollo-copies
source ~/.venvs/rollo-copies/bin/activate
pip install PySide6
```

3. Install service and autostart files.
4. Reload `systemd --user`.
5. Enable the service.
6. Reboot and verify the tray icon appears.

## Testing checklist

### Functional checks
- [ ] setting a value via tray menu calls `lpoptions` with the target copy count
- [ ] `lpoptions -p Rollo_X1040USB -o copies=3` succeeds
- [ ] a normal print job uses 3 copies
- [ ] when the queue becomes empty, the app resets to 1
- [ ] the tray menu still works after a reboot

### Persistence checks
- [ ] app starts automatically after login
- [ ] app survives logout and reboot
- [ ] it continues to display in system tray without user action

## Risks and mitigations

### Risk: user service not enabled
Mitigation: add an autostart `.desktop` launcher as fallback.

### Risk: queue watcher resets too early
Mitigation: only reset when `lpstat` shows no active jobs for the printer.

### Risk: app icon is hidden
Mitigation: use the system tray and keep the app running as a background process.

### Risk: GUI library not present on Zorin
Mitigation: use PySide6, which is available through pip and works on Ubuntu-based systems.

## Final expected user experience

After installation:
- user sees a small tray icon
- user selects copy count from the menu
- user prints normally
- app automatically restores the queue to 1 copy when done
- no further manual support is required

This satisfies the requirement to “never have to do anything” after installation beyond using the tray menu when needed.

---

## Example install commands

```bash
mkdir -p ~/apps/rollo-copies
cd ~/apps/rollo-copies
python3 -m venv ~/.venvs/rollo-copies
source ~/.venvs/rollo-copies/bin/activate
pip install PySide6
```

Then configure the service and autostart entries and enable them with systemd.

## Recommendation

Proceed with a small user-level tray app using PySide6 and a `systemd --user` service. This is the most reliable implementation for Zorin 18 and matches the CUPS behavior already verified in the environment.
