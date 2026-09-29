#!/usr/bin/env bash
#
# Installs the Rollo printer helper.
#
#     bash INSTALL.sh
#
# Can be run straight from the USB drive: it copies itself to local disk and
# continues from there, because USB drives are mounted non-executable.
# Logs always land in the "rollo-logs" folder at the top of the USB drive.

# Started with "sh INSTALL.sh"? dash cannot run this; hand over to bash.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -uo pipefail

BUNDLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_NAME="INSTALL.sh"

echo
echo "#############################################################"
echo "#  Rollo X1040 printer helper - install                     #"
echo "#############################################################"
echo

# shellcheck source=_stage.inc
. "${BUNDLE_DIR}/_stage.inc"

bash "${BUNDLE_DIR}/x1040/install/install.sh"
INSTALL_RC=$?

echo
echo "#############################################################"
echo "#  Collecting a diagnostic report                           #"
echo "#############################################################"
echo
bash "${BUNDLE_DIR}/x1040/install/diagnose.sh" >/dev/null 2>&1 || true

LOGS="${ROLLO_USB_LOG_DIR:-${HOME}/.rollo-printer/logs}"

echo
echo "#############################################################"
if [[ ${INSTALL_RC} -eq 0 ]]; then
  echo "#  INSTALL: OK                                              #"
else
  echo "#  INSTALL: finished with problems (status ${INSTALL_RC})"
  echo "#  The app may still work - try opening it.                 #"
fi
echo "#############################################################"
echo
if [[ -d "${LOGS}" ]]; then
  echo "Logs written to:"
  echo "    ${LOGS}"
  ls -1t "${LOGS}" 2>/dev/null | head -6 | sed 's/^/        /'
  if [[ -z "${ROLLO_USB_LOG_DIR:-}" ]]; then
    echo
    echo "!! These are on the laptop, NOT on the USB drive."
    echo "!! Copy that folder onto the drive before unplugging."
  fi
else
  echo "!! No log directory was created. Something went wrong very early."
fi
echo
echo "Next: open 'Rollo Printer Copies' from the applications menu."
echo "If anything is wrong, run:  bash DIAGNOSE.sh"
echo
echo "IMPORTANT: eject the drive properly before unplugging it,"
echo "otherwise the logs may not be saved."
echo
sync 2>/dev/null || true
exit ${INSTALL_RC}
