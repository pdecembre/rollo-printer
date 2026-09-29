#!/usr/bin/env bash
#
# Installs the Rollo copy helper for the current desktop user.
#
# Notes for anyone editing this:
#  * Do NOT force DISPLAY / XAUTHORITY / QT_QPA_PLATFORM here. Zorin 18 runs
#    Wayland, $HOME/.Xauthority does not exist on modern systems, and forcing
#    those values stops Qt from starting at all.
#  * The launcher must capture stderr. A crash with Terminal=false is
#    otherwise completely invisible.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
APP_DIR="${HOME}/apps/rollo-copies"
VENV_DIR="${HOME}/.venvs/rollo-copies"
LOG_DIR="${HOME}/.rollo-printer"
LAUNCHER="${APP_DIR}/start.sh"

RUN_LABEL="install"
# shellcheck source=_logging.inc
. "${SCRIPT_DIR}/_logging.inc"

FAILURES=()
note_failure() { FAILURES+=("$1"); echo "!! $1"; }

echo "=========================================================="
echo " Rollo X1040 copy helper - install"
echo " Timestamp : $(date -Iseconds)"
echo " User      : $(id -un)"
echo " Home      : ${HOME}"
echo " Source    : ${SOURCE_DIR}"
echo " Session   : ${XDG_SESSION_TYPE:-unknown} / ${XDG_CURRENT_DESKTOP:-unknown}"
echo "=========================================================="

if [[ "${EUID}" -eq 0 ]]; then
  echo "Do not run this as root. Run it as the desktop user." >&2
  exit 1
fi

if [[ ! -d "${SOURCE_DIR}/app" ]]; then
  echo "Cannot find the app directory at ${SOURCE_DIR}/app" >&2
  exit 1
fi

# ---------------------------------------------------------------- packages
echo
echo "--- Step 1/7: system packages ---"
if command -v sudo >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update || note_failure "apt-get update failed (no network?)"
  # zenity backs the simple fallback launcher; the appindicator extension is
  # what gives GNOME/Zorin a system tray for Qt to put an icon into.
  sudo apt-get install -y python3-venv python3-pip zenity \
    || note_failure "Could not install python3-venv / python3-pip / zenity"
  sudo apt-get install -y gnome-shell-extension-appindicator \
    || echo "   (appindicator extension unavailable - the tray icon may not appear, which is fine)"
else
  note_failure "sudo or apt-get missing; skipping package installation"
fi

# ---------------------------------------------------------- clean old copy
echo
echo "--- Step 2/7: removing any previous install ---"
systemctl --user disable --now rollo-copies.service 2>/dev/null || true

# Stop a previously running copy. Matching the path alone is not enough: it
# would also match a shell or editor whose command line merely mentions it,
# so only genuine python processes are signalled.
stop_running_app() {
  local pid exe
  for pid in $(pgrep -f 'rollo-copies/app/main\.py' 2>/dev/null || true); do
    [[ "${pid}" == "$$" || "${pid}" == "${PPID}" ]] && continue
    exe="$(readlink -f "/proc/${pid}/exe" 2>/dev/null || true)"
    case "${exe}" in
      *python*) kill "${pid}" 2>/dev/null || true ;;
    esac
  done
}
stop_running_app
rm -f "${HOME}/.config/autostart/rollo-copies.desktop" \
      "${HOME}/.config/systemd/user/rollo-copies.service" \
      "${HOME}/.local/share/applications/rollo-copies.desktop" \
      "${HOME}/Desktop/rollo-copies.desktop"
rm -rf "${APP_DIR}" "${VENV_DIR}"
echo "    done"

# ------------------------------------------------------------- copy files
echo
echo "--- Step 3/7: copying the app to ${APP_DIR} ---"
mkdir -p "${APP_DIR}"
cp -a "${SOURCE_DIR}/app" "${APP_DIR}/app"
cp -a "${SOURCE_DIR}/requirements.txt" "${APP_DIR}/requirements.txt"
rm -rf "${APP_DIR}/app/__pycache__"
echo "    copied $(find "${APP_DIR}/app" -name '*.py' | wc -l) python files"

# ------------------------------------------------------------------ venv
echo
echo "--- Step 4/7: python environment ---"
HAVE_QT=0
if python3 -m venv "${VENV_DIR}"; then
  "${VENV_DIR}/bin/pip" install --upgrade pip || echo "    (pip self-upgrade skipped)"
  if "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"; then
    if "${VENV_DIR}/bin/python" -c 'import PySide6' 2>/dev/null; then
      HAVE_QT=1
      echo "    PySide6 installed and importable"
    else
      note_failure "PySide6 installed but cannot be imported"
    fi
  else
    note_failure "pip could not install PySide6 (check the network connection)"
  fi
else
  note_failure "Could not create the virtual environment"
fi

# -------------------------------------------------------------- launcher
echo
echo "--- Step 5/7: launcher ---"
cat > "${LAUNCHER}" <<'LAUNCHEOF'
#!/usr/bin/env bash
# Launches the Rollo copy helper and records everything it prints.
set -uo pipefail

LOG_DIR="${HOME}/.rollo-printer"
mkdir -p "${LOG_DIR}"
exec >> "${LOG_DIR}/runtime.log" 2>&1

echo "=== launch $(date -Iseconds) : session=${XDG_SESSION_TYPE:-?} desktop=${XDG_CURRENT_DESKTOP:-?} ==="

# Make the session's environment visible to anything started via D-Bus.
if command -v dbus-update-activation-environment >/dev/null 2>&1; then
  dbus-update-activation-environment --systemd DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP >/dev/null 2>&1 || true
fi

if [[ -z "${WAYLAND_DISPLAY:-}" && -z "${DISPLAY:-}" ]]; then
  echo "No desktop session detected; not starting." >&2
  exit 1
fi

PY="${HOME}/.venvs/rollo-copies/bin/python"
APP="${HOME}/apps/rollo-copies/app/main.py"

if [[ ! -x "${PY}" ]]; then
  echo "Python environment missing at ${PY}. Re-run install.sh." >&2
  command -v zenity >/dev/null 2>&1 && \
    zenity --error --text="Rollo helper is not installed correctly.\nRe-run install.sh." 2>/dev/null
  exit 1
fi

# Let Qt pick its own platform plugin first. Only if that fails do we retry
# under XWayland -- forcing xcb up front is what broke earlier installs.
"${PY}" "${APP}" "$@"
rc=$?
if [[ ${rc} -ne 0 ]]; then
  echo "Launch failed (exit ${rc}); retrying with QT_QPA_PLATFORM=xcb" >&2
  QT_QPA_PLATFORM=xcb "${PY}" "${APP}" "$@"
  rc=$?
  echo "Retry exit code: ${rc}" >&2
fi
exit ${rc}
LAUNCHEOF
chmod +x "${LAUNCHER}"
echo "    ${LAUNCHER}"

# A no-Python fallback, so there is always something that works.
SIMPLE="${APP_DIR}/rollo-copies-simple.sh"
cat > "${SIMPLE}" <<'SIMPLEEOF'
#!/usr/bin/env bash
# Zero-dependency fallback: ask for a number with zenity, set it with lpoptions.
set -uo pipefail
QUEUE="$(lpstat -e 2>/dev/null | grep -iE 'rollo|x1040' | head -1)"
if [[ -z "${QUEUE}" ]]; then
  zenity --error --text="No Rollo printer queue found.\n\nQueues available:\n$(lpstat -e 2>/dev/null | tr '\n' ' ')"
  exit 1
fi
CURRENT="$(lpoptions -p "${QUEUE}" 2>/dev/null | grep -oP '(?<=^|\s)copies=\K[0-9]+' || echo 1)"
N="$(zenity --scale --title="Rollo: pages to print" \
      --text="Printer: ${QUEUE}\nCurrent: ${CURRENT} copies\n\nNumber of copies:" \
      --min-value=1 --max-value=50 --value="${CURRENT}" --step=1)" || exit 0
lpoptions -p "${QUEUE}" -o "copies=${N}"
VERIFY="$(lpoptions -p "${QUEUE}" 2>/dev/null | grep -oP '(?<=^|\s)copies=\K[0-9]+' || echo '?')"
if [[ "${VERIFY}" == "${N}" ]]; then
  zenity --info --text="${QUEUE} is now set to ${N} copies.\n\nPrint now, then run this again and set it back to 1."
else
  zenity --error --text="Could not set the copy count (read back: ${VERIFY})."
fi
SIMPLEEOF
chmod +x "${SIMPLE}"
echo "    ${SIMPLE}"

# ---------------------------------------------------------- desktop entries
echo
echo "--- Step 6/7: desktop entries ---"
mkdir -p "${HOME}/.local/share/applications" "${HOME}/.config/autostart" "${HOME}/Desktop"

write_entry() {
  local path="$1" exec_line="$2" name="$3"
  cat > "${path}" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=${name}
Comment=Set the number of pages to print for the Rollo X1040 USB printer
Exec=${exec_line}
Path=${APP_DIR}
Icon=printer
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=rollo-copies
EOF
  chmod +x "${path}"
  # GNOME/Zorin refuses to launch a desktop file it does not trust, silently.
  gio set "${path}" metadata::trusted true 2>/dev/null || true
}

# The basename "rollo-copies" must match what the app reports as its desktop
# file name, or the taskbar shows "python3" with a generic icon instead.
write_entry "${HOME}/.local/share/applications/rollo-copies.desktop" "${LAUNCHER}" "Rollo Page Count"
write_entry "${HOME}/Desktop/rollo-copies.desktop"                   "${LAUNCHER}" "Rollo Page Count"
write_entry "${HOME}/.config/autostart/rollo-copies.desktop"         "${LAUNCHER} --tray-only" "Rollo Page Count"
write_entry "${HOME}/.local/share/applications/rollo-copies-simple.desktop" "${SIMPLE}" "Rollo Page Count (simple)"

update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
echo "    menu entry, desktop icon, autostart entry and simple fallback written"

# ------------------------------------------------------------- verification
echo
echo "--- Step 7/7: verification ---"
DIAG_OUTPUT=""
if [[ ${HAVE_QT} -eq 1 ]]; then
  if DIAG_OUTPUT="$("${VENV_DIR}/bin/python" "${APP_DIR}/app/main.py" --diagnose 2>&1)"; then
    echo "${DIAG_OUTPUT}"
  else
    note_failure "The app could not run --diagnose"
    echo "${DIAG_OUTPUT}"
  fi
else
  note_failure "Skipping verification because PySide6 is unavailable"
fi

QUEUE="$(lpstat -e 2>/dev/null | grep -iE 'rollo|x1040' | head -1 || true)"
if [[ -z "${QUEUE}" ]]; then
  note_failure "No Rollo print queue found. Add the printer, then open the app and pick it from the list."
  echo "    Queues CUPS can see: $(lpstat -e 2>/dev/null | tr '\n' ' ')"
else
  echo "    Rollo queue detected: ${QUEUE}"
fi

if [[ -n "${USB_LOG_DIR}" && -n "${DIAG_OUTPUT}" ]]; then
  printf '%s\n' "${DIAG_OUTPUT}" > "${USB_LOG_DIR}/${LOG_NAME}-diagnostics.txt" 2>/dev/null || true
fi

echo
echo "=========================================================="
if [[ ${#FAILURES[@]} -eq 0 ]]; then
  echo " RESULT: OK - installation complete"
else
  echo " RESULT: finished with ${#FAILURES[@]} problem(s):"
  for f in "${FAILURES[@]}"; do echo "   - ${f}"; done
fi
echo "=========================================================="
echo " Open it from:  Activities -> 'Rollo Page Count'"
echo " Or run:        ${LAUNCHER}"
echo " Runtime log:   ${LOG_DIR}/runtime.log"
echo " Install log:   ${LOG_FILE}"
echo "=========================================================="

[[ ${#FAILURES[@]} -eq 0 ]] || exit 1
