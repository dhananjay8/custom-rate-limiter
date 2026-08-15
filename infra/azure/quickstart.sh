#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARAM_FILE="${SCRIPT_DIR}/parameters.json"

RESOURCE_GROUP="${RESOURCE_GROUP:-crl-rg}"
LOCATION="${LOCATION:-eastus}"
IMAGE="${IMAGE:-ghcr.io/your-org/custom-rate-limiter:latest}"
MODE="${MODE:-validate}"

if ! command -v az >/dev/null 2>&1; then
  echo "[ERROR] Azure CLI (az) is required."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  echo "[INFO] Not logged in. Launching az login..."
  az login >/dev/null
fi

TMP_PARAM_FILE="$(mktemp)"
trap 'rm -f "${TMP_PARAM_FILE}"' EXIT

sed "s|ghcr.io/your-org/custom-rate-limiter:latest|${IMAGE}|g" "${PARAM_FILE}" > "${TMP_PARAM_FILE}"

echo "[INFO] Running Azure quickstart with MODE=${MODE}"
echo "[INFO] Resource Group: ${RESOURCE_GROUP}"
echo "[INFO] Location: ${LOCATION}"
echo "[INFO] Image: ${IMAGE}"

RESOURCE_GROUP="${RESOURCE_GROUP}" \
LOCATION="${LOCATION}" \
MODE="${MODE}" \
PARAM_FILE="${TMP_PARAM_FILE}" \
"${SCRIPT_DIR}/deploy.sh"
