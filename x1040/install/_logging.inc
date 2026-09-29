# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Shared log capture. Sourced as the first real action of install.sh and
# diagnose.sh.
#
# Requirements this satisfies:
#   * writes to the USB drive CONTINUOUSLY, not as a copy at the end, so a
#     crash, a freeze or a yanked cable still leaves a readable log
#   * always also writes locally, in case the drive is read-only
#   * captures stdout AND stderr AND a full command trace
#   * calls sync() on exit, because FAT32 loses unflushed data on unplug
#
# Caller must set RUN_LABEL and SCRIPT_DIR before sourcing.
# ---------------------------------------------------------------------------

STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo unknown)"
HOSTTAG="$(hostname -s 2>/dev/null || echo host)"
LOG_NAME="${RUN_LABEL}-${STAMP}-${HOSTTAG}"

LOCAL_LOG_DIR="${HOME}/.rollo-printer/logs"
mkdir -p "${LOCAL_LOG_DIR}" 2>/dev/null || true

LOG_TARGETS=()
if [[ -d "${LOCAL_LOG_DIR}" ]]; then
  LOG_TARGETS+=("${LOCAL_LOG_DIR}/${LOG_NAME}.log")
fi

# Put logs at the top level of whichever removable drive we were launched
# from: easy for a person to find, easy to read back on another machine.
USB_LOG_DIR=""

_rollo_try_log_dir() {
  [[ -n "${1:-}" ]] || return 1
  mkdir -p "$1" 2>/dev/null || return 1
  : > "$1/.writetest" 2>/dev/null || return 1
  rm -f "$1/.writetest" 2>/dev/null || true
  USB_LOG_DIR="$1"
  return 0
}

# The wrapper stages the installer onto local disk before running it (USB
# drives are mounted noexec/showexec), so it passes the drive's log directory
# through the environment. Without that, df below would just see local disk.
if ! _rollo_try_log_dir "${ROLLO_USB_LOG_DIR:-}"; then
  MOUNT_POINT="$(df -P "${SCRIPT_DIR}" 2>/dev/null | awk 'NR==2 {out=$6; for (i=7; i<=NF; i++) out = out " " $i; print out}')"
  case "${MOUNT_POINT}" in
    /media/*|/run/media/*|/mnt/*) _rollo_try_log_dir "${MOUNT_POINT}/rollo-logs" || true ;;
  esac
fi
[[ -n "${USB_LOG_DIR}" ]] && LOG_TARGETS+=("${USB_LOG_DIR}/${LOG_NAME}.log")

if [[ ${#LOG_TARGETS[@]} -gt 0 ]]; then
  exec > >(tee -a "${LOG_TARGETS[@]}") 2>&1
fi

# The command trace is noisy, so it gets its own file. It is what pins down
# precisely which command failed on a machine we cannot watch.
TRACE_DIR="${USB_LOG_DIR:-${LOCAL_LOG_DIR}}"
TRACE_FILE=""
if [[ -d "${TRACE_DIR}" ]]; then
  if exec 19>"${TRACE_DIR}/${LOG_NAME}.trace" 2>/dev/null; then
    TRACE_FILE="${TRACE_DIR}/${LOG_NAME}.trace"
    export BASH_XTRACEFD=19
    export PS4='+ $(date +%H:%M:%S) ${BASH_SOURCE##*/}:${LINENO}: '
    set -x
  fi
fi

_rollo_finish() {
  local rc=$?
  set +x 2>/dev/null || true
  echo
  echo "=============================================================="
  echo " ${RUN_LABEL} exited with status ${rc} at $(date -Iseconds)"
  for t in "${LOG_TARGETS[@]}"; do
    echo " log   : ${t}"
  done
  [[ -n "${TRACE_FILE}" ]] && echo " trace : ${TRACE_FILE}"
  if [[ -z "${USB_LOG_DIR}" ]]; then
    echo " !! The USB drive was not writable, so logs are ONLY on this machine."
    echo " !! Copy ${LOCAL_LOG_DIR} onto the drive by hand before unplugging."
  fi
  echo "=============================================================="
  # FAT32 keeps data in cache; without this an unplug can lose the log.
  sync 2>/dev/null || true
  sleep 1
  sync 2>/dev/null || true
}
trap _rollo_finish EXIT
trap 'echo; echo "!! ${RUN_LABEL} interrupted by the user"; exit 130' INT TERM
