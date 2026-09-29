# Fixes and changes — Rollo X1040 copy helper

Complete record of everything changed to get the app working, why each change
was needed, and how it was proven. Written 2026-09-29.

Baseline: commit `571bc8f` ("Add tray helper app and install bundle").

---

## 1. The headline: the app had never started, on any machine

Every symptom reported from the Zorin laptop — no tray icon, no window, a
desktop icon that "did nothing", an empty log — had a single cause.

`x1040/app/main.py` began with:

```python
from app.cups_helper import PRINTER_NAME, current_copies   # line 8
```

Every launcher started it by file path:

```bash
python3 /home/kristina/apps/rollo-copies/app/main.py
```

Launching a script by path puts **that script's own directory** on `sys.path`,
not its parent. So `app` was not importable from inside `app/`, and the process
died instantly:

```
File ".../app/main.py", line 8, in <module>
    from app.cups_helper import PRINTER_NAME, current_copies
ModuleNotFoundError: No module named 'app'
EXIT: 1
```

Reproduced against the **original committed code**, not a refactor of it.

Why it was completely silent:

| Layer | Why nothing was reported |
| --- | --- |
| The crash | Happened at import time — before Qt, before any window |
| The log | `configure_logging()` was on line 100 and was never reached |
| The desktop icon | `Terminal=false` discards stderr, so the traceback vanished |
| The installer | Reported "may need a desktop session for the tray icon" — a wrong guess |
| systemd | Logged only `Failed to start rollo-copies.service` |

The laptop's own files confirmed the install itself had always succeeded:
`Successfully installed PySide6-6.11.2` on Python 3.12.3 (Zorin 18 / Ubuntu
noble). The environment was never the problem.

**Fix** — `app/main.py` now puts its package parent on `sys.path` before
importing anything from `app`:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

The app now starts however it is launched, from any working directory.

---

## 2. Silent failure when the printer name was wrong

`lpoptions` returns success for a queue that does not exist. Demonstrated:

```console
$ lpoptions -p Rollo_X1040_USB -o copies=3     # no such queue on this machine
$ echo $?
0
$ cat ~/.cups/lpoptions
Dest Rollo_X1040_USB copies=3                  # junk entry, printer untouched
```

So `set_copies()` returned `True`, the UI reported success, and nothing
happened at the printer. The design docs said `Rollo_X1040USB` while the code
said `Rollo_X1040_USB`; either could have been wrong with no visible sign.

The laptop's own `lpstat -p` output settled it:

```
printer Rollo_X1040_USB is idle.  enabled since Sun 13 Sep 2026 08:30:18 PM EDT
device for Rollo_X1040_USB: usb://Rollo/X1040?serial=X1210262164
```

**Fix** — the queue name is no longer hardcoded:

1. `ROLLO_PRINTER` environment variable, else
2. `~/.rollo-printer/printer` (written by the **Use this printer** button), else
3. auto-detection: any queue from `lpstat -e` matching `rollo` or `x1040`,
   case-insensitive — so both spellings work

And every write is now checked:

- the queue must appear in `lpstat -e` before any write is attempted
- after writing, the value is **read back** and compared
- if either check fails, `set_copies()` returns `False` and the UI says so

---

## 3. `current_copies()` returned `None` for every real printer

`lpoptions -p <queue>` prints **one space-separated line**, not one option per
line:

```
copies=1 device-uri=socket://… finishings=3 job-cancel-after=10800 number-up=1 …
```

The old parser did `line.split("copies=")[-1]` and `int()` on the result, which
was `"1 device-uri=socket://…"` — a `ValueError` every time, swallowed by a
`continue`, returning `None`.

Effect: the window permanently read "Current copies: unavailable" and the tray
always claimed 1, so a successful change could never be confirmed.

**Fix** — a pattern that extracts the value from the real format, and is not
fooled by similar keys such as `job-copies=`:

```python
COPIES_PATTERN = re.compile(r"(?:^|\s)copies=(\d+)")
```

Verified against a live CUPS queue: returns `1` where the old code returned
`None`.

---

## 4. The auto-reset feature did not exist

`queue_watcher.py` was imported by nothing. The centrepiece of both design
documents — set 3 copies, print, drop back to 1 — was dead code.

And the logic itself was wrong. It read:

```python
while self.running:
    if not check_queue_has_jobs():
        reset_to_default()      # the queue is ALWAYS empty at this moment
        return
    time.sleep(self.poll_interval)
```

The queue is empty at the instant the user picks a copy count, so had it ever
run, it would have reset to 1 before they printed anything.

**Fix** — rewritten as a two-phase watcher on a daemon thread, and wired into
the window:

1. **wait** for a job to appear (up to 15 minutes)
2. **watch** until the queue has been empty for several consecutive polls —
   so a brief gap between two jobs of one print run does not trigger a reset
3. **reset** to 1 copy

If nothing is ever printed, it resets after the timeout rather than leaving the
printer stuck on 5 copies forever. Callbacks are marshalled onto the GUI thread
through a Qt signal. The module stays Qt-free so it can be tested directly.

Proven behaviour:

```
after 0.5s with an idle queue : 0 resets   (old code would have reset here)
job appears                    : state = printing, 0 resets
job drains                     : state = idle, 1 reset
transitions                    : waiting -> printing -> idle
```

---

## 5. Failures were invisible

`configure_logging()` installed a single `FileHandler`, which captures only
`logging` calls — not tracebacks, not Qt fatal errors, not anything a crashing
interpreter prints.

**Fix**:

- `sys.excepthook` logs every unhandled exception with its full traceback
- the launcher redirects **all** stdout and stderr into `~/.rollo-printer/runtime.log`
- a stderr handler is added **only when stderr is a terminal** — without that
  guard every line was written twice, since the launcher already redirects
  stderr into the same file
- `--diagnose` prints a full environment report and never raises, even when
  PySide6 is missing entirely

---

## 6. The installer forced X11 settings that do not exist

The autostart entry contained:

```
Exec=/bin/bash -lc 'export QT_QPA_PLATFORM=xcb; export DISPLAY=:0; export XAUTHORITY=$HOME/.Xauthority; …'
```

Three problems:

| Setting | Why it breaks |
| --- | --- |
| `XAUTHORITY=$HOME/.Xauthority` | That file does not exist on modern systems. The real one is `/run/user/1000/xauth_*`. Pointing Qt at a missing auth file means it cannot connect to the display |
| `QT_QPA_PLATFORM=xcb` | Forces X11. Zorin 18 runs Wayland |
| `DISPLAY=:0` | Assumes an X server on display 0 |

**Fix** — the installer sets none of them. The launcher lets Qt choose its own
platform plugin, and only if that fails does it retry once under `xcb`.

---

## 7. The desktop icon did nothing

GNOME and Zorin silently refuse to launch a `.desktop` file they do not trust.

**Fix** — the installer marks each entry trusted:

```bash
gio set "${path}" metadata::trusted true
```

The committed `rollo-copies.desktop` had also been edited to hardcode
`/home/kristina`, which would break for any other user. Entries are now
generated per-user at install time.

---

## 8. The systemd service was removed

The laptop's journal showed:

```
systemd: Failed to start rollo-copies.service - Rollo printer copy helper.
```

A GUI tray application started by `systemd --user` races the graphical session
and inherits none of its environment. The unit also hardcoded `DISPLAY=:0`.

**Fix** — `rollo-copies.service` deleted. Autostart is a desktop entry in
`~/.config/autostart/`, which the session starts at the right moment with the
right environment.

---

## 9. The app depended on a system tray that GNOME does not have

GNOME has no built-in system tray. Qt can only show a tray icon when the
AppIndicator extension is providing `org.kde.StatusNotifierWatcher`. The old
`main.py` created **only** a tray icon — so on a desktop without that
extension, the app ran completely invisibly by design.

**Fix** — the window is the application; the tray is a bonus:

- `QSystemTrayIcon.isSystemTrayAvailable()` is checked at startup and logged
- with no tray, the app runs as a normal window and says so in the log
- `--tray-only` (used by autostart) starts hidden **only if** a tray exists;
  otherwise it shows the window rather than vanishing
- the installer tries to install `gnome-shell-extension-appindicator`, and
  treats failure as non-fatal

Confirmed working in the no-tray case:

```
System tray available: False
No system tray on this desktop; running as a normal window
```

---

## 10. Running the installer from the USB drive failed

Reported symptom: "Permission denied", requiring a manual copy to the laptop
and `chmod +x *.sh` before anything would run.

Cause: the drive is FAT32, mounted with `showexec`, which strips the execute
bit from everything except `.exe`, `.com` and `.bat`. Ubuntu's udisks2 also
adds `noexec` to `/media` mounts. Reproduced:

```console
$ ls -l INSTALL.sh
-rw-r--r--  1 azen azen 2162 INSTALL.sh      # no execute bit, for anyone
$ ./INSTALL.sh
/bin/bash: ./INSTALL.sh: Permission denied
```

No permission setting at write time can change this — the filesystem cannot
store the bit.

**Fix** — `INSTALL.sh` and `DIAGNOSE.sh` detect they are on removable media,
copy the whole bundle to `~/.cache/rollo-copies-install`, and re-exec from
there. This is precisely the manual step a person would otherwise perform.

Staging also fixes three neighbouring problems:

- **CRLF line endings** are stripped, which otherwise cause `$'\r': command not found`
- **`sh INSTALL.sh`** now hands over to bash instead of failing on syntax
- a long install no longer depends on the drive staying readable throughout

Still true and documented in `START-HERE.txt`: double-clicking and
`./INSTALL.sh` cannot work. The command must begin with `bash`.

---

## 11. Logs now always come back

The original installer copied its log to the USB drive **at the end**, so a
crash or a freeze left nothing. And when run from a local copy, it never saw
the drive at all — which is why the first laptop run produced no logs on the
stick.

**Fix** — `x1040/install/_logging.inc`, sourced as the first real action of
both scripts:

- writes to the USB drive **continuously**, via `tee`, not as a copy at the end
- **always** writes a local copy too, and says loudly if the drive was not writable
- captures stdout, stderr, and a separate timestamped **command trace**
  (`set -x` to its own file), which pins down exactly which command failed
- `sync`s on exit, because FAT32 loses unflushed data when a drive is unplugged
- names files `<run>-<timestamp>-<hostname>.log`, so nothing overwrites anything

Because staging moves execution off the drive, the mount point is captured
*before* staging and passed through `ROLLO_USB_LOG_DIR` — otherwise the logger
would only ever see local disk.

`INSTALL.sh` runs the diagnostic afterwards **unconditionally**, so there is
always a report even when the install fails.

Everything lands in `rollo-logs/` at the top level of the drive.

---

## 12. The taskbar showed "python3" with a generic icon

Qt falls back to the process name unless the application states its identity.

**Fix**, on three fronts because X11 and Wayland resolve icons differently:

| | Before | After |
| --- | --- | --- |
| Taskbar text | `python3` | `Rollo Page Count` |
| WM_CLASS (X11) | `python3` | `rollo-copies` |
| Desktop-file link (Wayland) | none | `setDesktopFileName("rollo-copies")` |
| `.desktop` entry | — | `StartupWMClass=rollo-copies` |
| Icon | generic gear | themed `printer`, with a drawn fallback |

`QApplication` is constructed as `QApplication(["rollo-copies"])`, because
`argv[0]` is what becomes the X11 instance name.

New `app/icon.py` prefers the desktop theme's `printer` icon and falls back to
a printer drawn with QPainter at eight sizes, for desktops whose theme has no
printer icon.

The app was also renamed throughout, from "Rollo Printer Copies" to
**Rollo Page Count**.

---

## 13. Close now leaves the app running

Requested behaviour: a close button that hides the window while the app keeps
working in the background, reachable from the tray.

**Fix**:

- **Close** hides the window; the app and the auto-reset watcher keep running
- **Quit** shuts the app down properly
- the first time it is hidden, a tray notification explains where it went
- if there is **no** tray, Quit is hidden and the hint text changes to say that
  closing will close the app — otherwise it would vanish with no way back

Verified:

```
visible before close : True
visible after close  : False   (hidden, not quit)
watcher still alive  : True
visible after tray   : True    (reopened from the tray)
watcher after quit   : False   (stopped cleanly)
```

---

## 14. The installer could kill unrelated processes

Cleanup used:

```bash
pkill -f 'rollo-copies/app/main.py'
```

`pkill -f` matches the **whole command line**, so any process merely mentioning
that path — a terminal, an editor, a shell script — was killed. This happened
twice during testing, killing the shell running the tests.

**Fix** — only genuine Python processes are signalled, and the script skips
itself and its parent:

```bash
exe="$(readlink -f "/proc/${pid}/exe")"
case "${exe}" in *python*) kill "${pid}" ;; esac
```

Verified with a decoy shell whose command line contained the path: it survived.

---

## 15. Repository hygiene and tests

| Problem | Fix |
| --- | --- |
| Six `.pyc` files committed to git | Untracked; `.gitignore` added |
| No `.gitignore` at all | Added (`__pycache__`, `*.py[cod]`, `*.log`, `.pytest_cache`) |
| `app/runtime.log` committed as a placeholder | Removed |
| Tests could not run — no `conftest.py`, no path setup | `x1040/conftest.py` added |
| Tests used a printer name that no longer matched | Rewritten |
| Two rival installers (`install.sh`, `one-click-fix.sh`) | One installer |
| Orphaned `rollo-copies.service` / `.desktop` | Deleted |

The suite is now **24 tests**, each pinning a bug that actually shipped:

- `tests/test_cups_helper.py` — real single-line `lpoptions` parsing, the
  `job-copies=` trap, detection of both printer-name spellings, override
  precedence, refusal to write to a missing queue, failure when a value does
  not stick, survival when CUPS is not installed
- `tests/test_queue_watcher.py` — no reset before a job appears, exactly one
  reset after the drain, surviving a gap between two jobs, cancellation, the
  timeout path

---

## 16. File inventory

**Added**

| File | Purpose |
| --- | --- |
| `x1040/app/icon.py` | Application icon and identity constants |
| `x1040/install/diagnose.sh` | Standalone diagnostic; changes nothing |
| `x1040/install/_logging.inc` | Shared log capture for both scripts |
| `x1040/conftest.py` | Makes `import app.*` work under pytest |
| `x1040/tests/test_queue_watcher.py` | Auto-reset tests |
| `usb-bundle/INSTALL.sh` | Self-staging installer wrapper |
| `usb-bundle/DIAGNOSE.sh` | Self-staging diagnostic wrapper |
| `usb-bundle/_stage.inc` | Copy-to-local-disk logic |
| `usb-bundle/START-HERE.txt` | Instructions for the person installing |
| `usb-bundle/make-usb.sh` | Builds the USB bundle reproducibly |
| `.gitignore` | — |
| `docs/fixes-and-changes.md` | This document |

**Removed**

| File | Why |
| --- | --- |
| `x1040/install/rollo-copies.service` | systemd approach abandoned (§8) |
| `x1040/install/rollo-copies.desktop` | Hardcoded `/home/kristina`; now generated |
| `x1040/install/one-click-fix.sh` | Superseded by the single installer |
| `x1040/app/runtime.log` | Committed placeholder |
| `x1040/app/__pycache__/*.pyc` | Should never have been tracked |

**Substantially rewritten**: `app/main.py`, `app/cups_helper.py`,
`app/queue_watcher.py`, `app/tray.py`, `install/install.sh`,
`tests/test_cups_helper.py`, `x1040/README.md`.

---

## 17. Rebuilding the USB drive

The drive is built from the repository by one command, not assembled by hand:

```bash
bash usb-bundle/make-usb.sh /run/media/$USER/9B99-60E5
```

It replaces the payload and leaves `rollo-logs/` alone. Always eject the drive
properly afterwards — FAT32 loses unflushed writes.

---

## 18. What is proven, and what is not

**Proven by execution:**

- the import crash, reproduced against the original committed code
- `lpoptions` exiting 0 for a nonexistent queue
- `current_copies()` returning `None`, and the fix returning the real value,
  both against a live CUPS queue
- the watcher's full `waiting → printing → idle` cycle with exactly one reset
- the app launching, the window rendering, close-to-tray and reopen
- installation end-to-end from the USB drive, including automatic staging
- logs and traces landing in `rollo-logs/` on the drive
- the `pkill` fix sparing an unrelated process
- 24 unit tests

**Not yet verified — needs the physical printer:**

- that a print job actually produces the requested number of copies
- that the queue-draining detection matches this printer's real timing
- that the taskbar icon and name resolve correctly under Zorin's GNOME shell
- whether a system tray is present on that machine

The last two are answered by running `bash DIAGNOSE.sh` on the laptop; the
report includes tray availability and the installed desktop entries.

---

## 19. Testing with the physical printer

Suggested order, so a failure points at one thing:

1. **Confirm detection.** Open the app. It should name `Rollo_X1040_USB` and
   show the current copy count as a number, not "unavailable".

2. **Confirm the write works.** Click **3**. The "Current copies" line should
   change to 3. Cross-check in a terminal:

   ```bash
   lpoptions -p Rollo_X1040_USB | tr ' ' '\n' | grep copies
   ```

   If the app says it failed, it genuinely failed — it verifies by reading the
   value back rather than trusting the exit code.

3. **Print one label.** Three should come out. This is the step that has never
   been tested and the one most likely to reveal something new.

4. **Watch the reset.** The window shows `Auto-reset: printing` while the job
   runs, then `Auto-reset: idle`, and the count returns to 1 on its own.

5. **Test the background behaviour.** Press **Close**, then reopen from the
   tray icon and check the count is still correct.

If step 3 prints only one copy, the CUPS default is being overridden by the
printing application rather than ignored by the printer. The fallback is to set
it server-side, which applies to every job regardless of what the client sends:

```bash
sudo lpadmin -p Rollo_X1040_USB -o copies-default=3
```

Worth trying by hand before changing any code — if that works where
`lpoptions` does not, the app should be switched to it.

**Whatever happens, run `bash DIAGNOSE.sh` afterwards** and bring the drive
back. The report and trace in `rollo-logs/` contain what is needed to diagnose
it without guessing.
