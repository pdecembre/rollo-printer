#!/usr/bin/env bash
#
# Builds the USB bundle onto a drive.
#
#     bash usb-bundle/make-usb.sh /run/media/$USER/9B99-60E5
#
# Safe to re-run: it replaces the payload and leaves rollo-logs alone.
set -euo pipefail

TARGET="${1:-}"
if [[ -z "${TARGET}" ]]; then
  echo "usage: bash make-usb.sh <mounted-drive-path>" >&2
  exit 1
fi
if [[ ! -d "${TARGET}" ]]; then
  echo "Not a directory: ${TARGET}" >&2
  exit 1
fi

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "${HERE}/.." && pwd)"
DEST="${TARGET}/rollo-x1040"

echo "Repo   : ${REPO}"
echo "Target : ${DEST}"

rm -rf "${DEST}"
mkdir -p "${DEST}/x1040"

cp -f "${HERE}/INSTALL.sh" "${HERE}/DIAGNOSE.sh" "${HERE}/_stage.inc" "${HERE}/START-HERE.txt" "${DEST}/"

for d in app install tests; do
  mkdir -p "${DEST}/x1040/${d}"
  find "${REPO}/x1040/${d}" -maxdepth 1 -type f ! -name '*.pyc' \
    -exec cp -f {} "${DEST}/x1040/${d}/" \;
done
cp -f "${REPO}/x1040/conftest.py" "${REPO}/x1040/requirements.txt" \
      "${REPO}/x1040/README.md" "${DEST}/x1040/"
mkdir -p "${DEST}/docs" && cp -f "${REPO}/docs/"*.md "${DEST}/docs/"

find "${DEST}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${DEST}" -name '*.pyc' -delete 2>/dev/null || true

mkdir -p "${TARGET}/rollo-logs"
sync

echo
echo "Bundle written. Contents:"
find "${DEST}" -type f | sed "s|${TARGET}|<USB>|" | sort
echo
echo "On the laptop, run:  bash <drive>/rollo-x1040/INSTALL.sh"
