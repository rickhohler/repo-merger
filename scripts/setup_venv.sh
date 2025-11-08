#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${1:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[repo-merger] Creating virtual environment at ${VENV_DIR}"
"${PYTHON_BIN}" -m venv "${VENV_DIR}"

ACTIVATE_PATH="${VENV_DIR}/bin/activate"
if [[ ! -f "${ACTIVATE_PATH}" ]]; then
  echo "Failed to locate activate script at ${ACTIVATE_PATH}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ACTIVATE_PATH}"

echo "[repo-merger] Upgrading pip and installing requirements"
python -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  python -m pip install -r requirements.txt
fi

echo "[repo-merger] Virtual environment ready. Activate via 'source ${ACTIVATE_PATH}'"
