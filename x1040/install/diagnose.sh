#!/usr/bin/env bash
#
# Gathers everything needed to debug the Rollo helper on a machine we cannot
# log into. Safe to run before OR after install.sh, and it changes nothing.
# Run it from the USB stick and the report is written back onto the stick.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

RUN_LABEL="diagnose"
# shellcheck source=_logging.inc
. "${SCRIPT_DIR}/_logging.inc"

section() { echo; echo "===== $1 ====="; }

echo "Rollo X1040 helper - diagnostic report"
echo "Generated: $(date -Iseconds)"

section "Machine"
echo "Hostname : $(hostname 2>/dev/null)"
echo "User     : $(id -un) (uid $(id -u))"
echo "Home     : ${HOME}"
echo "Kernel   : $(uname -srm)"
echo "OS       :"
sed -n 's/^/    /p' /etc/os-release 2>/dev/null | head -12

section "Desktop session"
for v in XDG_SESSION_TYPE XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP DESKTOP_SESSION \
         DISPLAY WAYLAND_DISPLAY XAUTHORITY QT_QPA_PLATFORM GDMSESSION; do
  printf '%-20s = %s\n' "$v" "${!v:-<unset>}"
done
echo "Real Xauthority files (note: ~/.Xauthority usually does NOT exist):"
found_xauth=0
for f in "${HOME}/.Xauthority" /run/user/"$(id -u)"/xauth* /run/user/"$(id -u)"/.mutter-Xwaylandauth*; do
  [[ -e "$f" ]] || continue
  ls -la "$f" 2>/dev/null | sed 's/^/    /'
  found_xauth=1
done
[[ ${found_xauth} -eq 1 ]] || echo "    none found"

section "System tray support (why a tray icon may not appear)"
if command -v gdbus >/dev/null 2>&1; then
  if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
       --method org.freedesktop.DBus.ListNames 2>/dev/null | grep -q StatusNotifierWatcher; then
    echo "StatusNotifierWatcher : PRESENT  -> a Qt tray icon can appear"
  else
    echo "StatusNotifierWatcher : MISSING  -> no tray; the app must use its window"
  fi
else
  echo "gdbus not available; cannot check"
fi
if command -v gnome-extensions >/dev/null 2>&1; then
  echo "GNOME extensions (appindicator is the one that matters):"
  gnome-extensions list --enabled 2>/dev/null | sed 's/^/    /' || echo "    (could not list)"
fi

section "Printing"
echo "-- lpstat -e (queue names) --"
lpstat -e 2>&1 | sed 's/^/    /' || echo "    lpstat failed"
echo "-- Rollo-like queues --"
lpstat -e 2>/dev/null | grep -iE 'rollo|x1040' | sed 's/^/    /' || echo "    NONE FOUND"
echo "-- lpstat -p (state) --"
lpstat -p 2>&1 | sed 's/^/    /' | head -30
echo "-- default destination --"
lpstat -d 2>&1 | sed 's/^/    /'
echo "-- ~/.cups/lpoptions --"
cat "${HOME}/.cups/lpoptions" 2>/dev/null | sed 's/^/    /' || echo "    (file does not exist)"
for q in $(lpstat -e 2>/dev/null | grep -iE 'rollo|x1040'); do
  echo "-- lpoptions -p ${q} --"
  lpoptions -p "${q}" 2>&1 | tr ' ' '\n' | sed 's/^/    /'
done
echo "-- cups service --"
systemctl is-active cups 2>&1 | sed 's/^/    /'
echo "-- USB devices (looking for the printer) --"
lsusb 2>/dev/null | sed 's/^/    /' || echo "    lsusb unavailable"

section "Python and app install"
echo "python3        : $(command -v python3 || echo MISSING) $(python3 -V 2>&1)"
echo "venv python    : ${HOME}/.venvs/rollo-copies/bin/python"
if [[ -x "${HOME}/.venvs/rollo-copies/bin/python" ]]; then
  echo "   version     : $("${HOME}/.venvs/rollo-copies/bin/python" -V 2>&1)"
  if "${HOME}/.venvs/rollo-copies/bin/python" -c 'import PySide6,PySide6.QtCore as c; print(c.__version__)' 2>/dev/null; then
    echo "   PySide6     : importable"
  else
    echo "   PySide6     : NOT IMPORTABLE"
    "${HOME}/.venvs/rollo-copies/bin/python" -c 'import PySide6' 2>&1 | sed 's/^/      /' | tail -5
  fi
else
  echo "   venv python : MISSING (app not installed yet)"
fi
echo "zenity         : $(command -v zenity || echo MISSING)"
echo "Installed files:"
for f in "${HOME}/apps/rollo-copies/start.sh" \
         "${HOME}/apps/rollo-copies/app/main.py" \
         "${HOME}/.local/share/applications/rollo-copies.desktop" \
         "${HOME}/.config/autostart/rollo-copies.desktop" \
         "${HOME}/Desktop/rollo-copies.desktop" \
         "${HOME}/.rollo-printer/printer"; do
  [[ -e "$f" ]] && echo "    present : $f" || echo "    absent  : $f"
done

section "App self-check"
CANDIDATE=""
if [[ -x "${HOME}/.venvs/rollo-copies/bin/python" && -f "${HOME}/apps/rollo-copies/app/main.py" ]]; then
  CANDIDATE="${HOME}/.venvs/rollo-copies/bin/python ${HOME}/apps/rollo-copies/app/main.py"
elif [[ -f "${SOURCE_DIR}/app/main.py" ]]; then
  CANDIDATE="python3 ${SOURCE_DIR}/app/main.py"
fi
if [[ -n "${CANDIDATE}" ]]; then
  echo "Running: ${CANDIDATE} --diagnose"
  ${CANDIDATE} --diagnose 2>&1 | sed 's/^/    /'
  echo "exit code: $?"
else
  echo "No runnable copy of the app found."
fi

section "System journal"
echo "-- user journal, last 40 lines --"
journalctl --user -n 40 --no-pager 2>/dev/null | sed 's/^/    /' || echo "    (user journal unavailable)"
echo "-- anything mentioning rollo / cups / print / gnome-shell --"
journalctl -n 800 --no-pager 2>/dev/null \
  | grep -iE 'rollo|cups|printer|gnome-shell' | tail -40 | sed 's/^/    /' \
  || echo "    (nothing found, or the journal is not readable by this user)"

section "Desktop entries as installed"
for f in "${HOME}/.local/share/applications/rollo-copies.desktop" \
         "${HOME}/.config/autostart/rollo-copies.desktop" \
         "${HOME}/Desktop/rollo-copies.desktop"; do
  echo "-- ${f} --"
  if [[ -f "${f}" ]]; then
    sed 's/^/    /' "${f}"
    echo "    [trusted: $(gio info "${f}" 2>/dev/null | grep -c 'metadata::trusted' || echo 0)]"
  else
    echo "    (absent)"
  fi
done

section "Launcher script as installed"
if [[ -f "${HOME}/apps/rollo-copies/start.sh" ]]; then
  sed 's/^/    /' "${HOME}/apps/rollo-copies/start.sh"
else
  echo "    (absent)"
fi

section "Recent runtime log (last 60 lines)"
tail -60 "${HOME}/.rollo-printer/runtime.log" 2>/dev/null | sed 's/^/    /' || echo "    no runtime log yet"

section "Recent install log (last 40 lines)"
tail -40 "${HOME}/.rollo-printer/install.log" 2>/dev/null | sed 's/^/    /' || echo "    no install log yet"

echo
echo "===== end of report ====="
echo "Report written to the log paths listed below."
