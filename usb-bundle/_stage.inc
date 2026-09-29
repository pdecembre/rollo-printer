# shellcheck shell=bash
# ---------------------------------------------------------------------------
# Copies the bundle off the USB drive and re-runs it from local disk.
#
# Why this exists: USB drives are FAT32 and get mounted with "showexec" (and
# often "noexec"), so scripts on them are not executable -- "./install.sh"
# fails with Permission denied and double-clicking does nothing. Staging also
# means a long install never depends on the drive staying readable, and it is
# exactly the manual copy step a person would otherwise have to do by hand.
#
# Caller must set BUNDLE_DIR and WRAPPER_NAME before sourcing.
# ---------------------------------------------------------------------------

# Remember where the logs must go, because after staging we are no longer on
# the drive and cannot work it out from our own path.
if [[ -z "${ROLLO_USB_LOG_DIR:-}" ]]; then
  _stage_mount="$(df -P "${BUNDLE_DIR}" 2>/dev/null | awk 'NR==2 {out=$6; for (i=7; i<=NF; i++) out = out " " $i; print out}')"
  case "${_stage_mount}" in
    /media/*|/run/media/*|/mnt/*)
      if mkdir -p "${_stage_mount}/rollo-logs" 2>/dev/null; then
        export ROLLO_USB_LOG_DIR="${_stage_mount}/rollo-logs"
      fi
      ;;
  esac
fi

_rollo_needs_staging() {
  [[ "${ROLLO_STAGED:-0}" == "1" ]] && return 1        # already staged
  [[ "${ROLLO_NO_STAGE:-0}" == "1" ]] && return 1      # explicitly disabled
  case "${BUNDLE_DIR}" in
    /media/*|/run/media/*|/mnt/*) return 0 ;;
  esac
  return 1
}

if _rollo_needs_staging; then
  STAGE_DIR="${HOME}/.cache/rollo-copies-install"
  echo "The installer is on a USB drive, which Linux mounts as non-executable."
  echo "Copying it to local disk first:"
  echo "    ${STAGE_DIR}"
  echo

  if rm -rf "${STAGE_DIR}" 2>/dev/null \
     && mkdir -p "${STAGE_DIR}" 2>/dev/null \
     && cp -r "${BUNDLE_DIR}/." "${STAGE_DIR}/" 2>/dev/null; then

    # FAT32 carries no permission bits, and a file that has ever been near
    # Windows may have CRLF line endings, which makes bash fail with
    # "$'\r': command not found". Fix both while we have the files locally.
    while IFS= read -r -d '' f; do
      sed -i 's/\r$//' "${f}" 2>/dev/null || true
      chmod +x "${f}" 2>/dev/null || true
    done < <(find "${STAGE_DIR}" -type f \( -name '*.sh' -o -name '*.inc' -o -name '*.py' \) -print0 2>/dev/null)

    if [[ -f "${STAGE_DIR}/${WRAPPER_NAME}" ]]; then
      export ROLLO_STAGED=1
      echo "Copy complete. Continuing from local disk."
      echo
      exec bash "${STAGE_DIR}/${WRAPPER_NAME}" "$@"
    fi
    echo "!! Staged copy is incomplete; continuing directly from the drive." >&2
  else
    echo "!! Could not copy to local disk; continuing directly from the drive." >&2
  fi
  echo
fi
