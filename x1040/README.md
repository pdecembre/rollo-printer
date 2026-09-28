# Rollo X1040 USB printer helper

This project implements a small Linux tray utility for the `Rollo_X1040_USB` printer.

## What it does

- Shows a tray icon in the desktop environment
- Lets the user set the default copy count with a menu item labeled `# of pages to print`
- Allows a custom numeric value entry
- Resets the queue back to 1 after print jobs complete
- Starts automatically at login and survives reboot

## Installed behavior

The app uses the known-good CUPS command:

```bash
lpoptions -p Rollo_X1040_USB -o copies=<N>
```

It then resets the printer back to 1 when the queue is idle.

## Install from the USB drive

Once the USB drive is plugged into the laptop, use the exact mounted path:

```bash
bash /media/kristina/9B99-60E5/rollo-x1040/x1040/install/install.sh
```

If the drive mounts with a different name on a different machine, the pattern is:

```bash
bash /media/<username>/<drive-name>/rollo-x1040/x1040/install/install.sh
```

This script does everything for you:
- installs required packages
- creates the virtual environment
- copies the app into the user's home
- writes the tray service and autostart files
- enables the service to survive reboot

## Run manually

```bash
cd ~/apps/rollo-copies
~/.venvs/rollo-copies/bin/python app/main.py
```

## Notes

This is the implementation intended for the Zorin 18 laptop using the actual printer queue name `Rollo_X1040_USB`.
