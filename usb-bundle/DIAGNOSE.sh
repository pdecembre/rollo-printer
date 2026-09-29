#!/usr/bin/env bash
#
# Collects a diagnostic report. Changes nothing.
#
#     bash DIAGNOSE.sh
#
# Writes the report to the "rollo-logs" folder at the top of the USB drive.

if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -uo pipefail

BUNDLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_NAME="DIAGNOSE.sh"

echo
echo "#############################################################"
echo "#  Rollo X1040 - collecting diagnostics (changes nothing)   #"
echo "#############################################################"
echo

# shellcheck source=_stage.inc
. "${BUNDLE_DIR}/_stage.inc"

bash "${BUNDLE_DIR}/x1040/install/diagnose.sh"
RC=$?

LOGS="${ROLLO_USB_LOG_DIR:-${HOME}/.rollo-printer/logs}"
echo
if [[ -d "${LOGS}" ]]; then
  echo "Report written to:"
  echo "    ${LOGS}"
  ls -1t "${LOGS}" 2>/dev/null | head -6 | sed 's/^/        /'
  if [[ -z "${ROLLO_USB_LOG_DIR:-}" ]]; then
    echo
    echo "!! These are on the laptop, NOT on the USB drive."
    echo "!! Copy that folder onto the drive before unplugging."
  fi
fi
echo
echo "IMPORTANT: eject the drive properly before unplugging it."
echo
sync 2>/dev/null || true
exit ${RC}
