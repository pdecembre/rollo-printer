#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${HOME}/.rollo-printer"
LOG_FILE="${LOG_DIR}/install.log"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${HOME}/apps/rollo-copies"
VENV_DIR="${HOME}/.venvs/rollo-copies"

echo "=== Rollo print helper install started ==="
echo "Timestamp: $(date -Iseconds)"
echo "User: $(id -un)"
echo "Home: ${HOME}"

echo "Source dir: ${SOURCE_DIR}"

if [[ "${EUID}" -eq 0 ]]; then
  echo "Do not run this script as root. Run it as the desktop user." >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install dependencies." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Installing Python 3..."
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-pip
fi

echo "Installing required packages..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip

mkdir -p "${APP_DIR}"
rsync -a --delete "${SOURCE_DIR}/app/" "${APP_DIR}/app/"
cp "${SOURCE_DIR}/requirements.txt" "${APP_DIR}/requirements.txt"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

mkdir -p "${HOME}/.config/systemd/user"
mkdir -p "${HOME}/.config/autostart"

SERVICE_PATH="${HOME}/.config/systemd/user/rollo-copies.service"
DESKTOP_PATH="${HOME}/.config/autostart/rollo-copies.desktop"

sed "s|%h|${HOME}|g" "${SOURCE_DIR}/install/rollo-copies.service" > "${SERVICE_PATH}"
sed "s|\${HOME}|${HOME}|g" "${SOURCE_DIR}/install/rollo-copies.desktop" > "${DESKTOP_PATH}"

systemctl --user daemon-reload
systemctl --user enable --now rollo-copies.service
loginctl enable-linger "$(id -un)"

chmod +x "${APP_DIR}/app/main.py"

echo "Rollo printer helper installed successfully."
echo "The tray app will start automatically after login."
echo "Menu label: # of pages to print"
echo "=== install completed ==="
