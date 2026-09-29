# Rollo X1040 USB printer helper

A small Linux desktop utility that sets the default copy count for the Rollo
label printer, then puts it back to 1 once printing has finished.

It exists because the GUI print dialog ignores the copy count for this queue,
while the CUPS queue default is honoured:

```bash
lpoptions -p <queue> -o copies=3
```

## What was fixed

A complete record of every bug found and fixed, with the evidence for each, is
in [`docs/fixes-and-changes.md`](../docs/fixes-and-changes.md). Read that first
if something behaves unexpectedly — most surprising behaviour is documented
there along with why it was changed.

## Install on the Zorin laptop

Plug in the USB drive and run, in a terminal:

```bash
bash /media/$USER/<drive-name>/rollo-x1040/x1040/install/install.sh
```

The installer prints a clear `RESULT: OK` or a numbered list of problems at
the end, and writes a copy of its log back onto the USB drive.

Then open **Rollo Printer Copies** from the applications menu, or use the
desktop icon.

## If something does not work

Run the diagnostic. It changes nothing, works even if the install failed, and
writes a full report back onto the USB drive so it can be read on another
machine:

```bash
bash /media/$USER/<drive-name>/rollo-x1040/x1040/install/diagnose.sh
```

Useful one-liners:

```bash
~/apps/rollo-copies/start.sh          # launch, logging to ~/.rollo-printer/runtime.log
~/.venvs/rollo-copies/bin/python ~/apps/rollo-copies/app/main.py --diagnose
~/.venvs/rollo-copies/bin/python ~/apps/rollo-copies/app/main.py --status
~/.venvs/rollo-copies/bin/python ~/apps/rollo-copies/app/main.py --set 3
tail -40 ~/.rollo-printer/runtime.log
```

There is also a no-Python fallback, **Rollo Copies (simple)** in the
applications menu, which just asks for a number using zenity. It works even if
the Python environment is broken.

## Which printer does it use?

The queue name is **auto-detected** -- any queue whose name contains `rollo` or
`x1040`. Detection order:

1. the `ROLLO_PRINTER` environment variable
2. `~/.rollo-printer/printer` (written when you press **Use this printer**)
3. auto-detection from `lpstat -e`

If no Rollo queue is found the window says so and lists every queue CUPS can
see, so the right one can be picked from the dropdown. This matters because
`lpoptions` exits 0 for a queue that does not exist -- a wrong name would
otherwise look like success and silently do nothing.

## Auto-reset behaviour

When you set a count above 1 with **Automatically reset to 1** ticked, a
background watcher:

1. waits for a print job to appear (up to 15 minutes),
2. waits for the queue to drain and stay drained,
3. sets the copy count back to 1.

It deliberately does *not* reset the moment the queue looks empty -- the queue
is always empty at the instant you pick a copy count.

## The system tray

GNOME (and therefore Zorin) has no built-in system tray. Qt can only show a
tray icon when the AppIndicator extension is providing
`org.kde.StatusNotifierWatcher`. The installer tries to install it, but the app
never depends on it: when there is no tray, it simply runs as a normal window.

## Running the tests

```bash
cd x1040
python3 -m pytest tests/ -q
```

## Layout

```text
x1040/
├── app/
│   ├── main.py           entry point, window, logging, diagnostics
│   ├── tray.py           optional tray icon
│   ├── cups_helper.py    all CUPS calls, printer detection, verification
│   └── queue_watcher.py  two-phase auto-reset watcher
├── install/
│   ├── install.sh        the only installer
│   └── diagnose.sh       standalone diagnostic report
└── tests/
```
