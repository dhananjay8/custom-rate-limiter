#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RESOURCE_GROUP="${RESOURCE_GROUP:-}"
LOCATION="${LOCATION:-eastus}"
PARAM_FILE="${PARAM_FILE:-${SCRIPT_DIR}/parameters.json}"
TEMPLATE_FILE="${TEMPLATE_FILE:-${SCRIPT_DIR}/main.bicep}"
MODE="${MODE:-deploy}"

usage() {
  cat <<EOF
Usage:
  RESOURCE_GROUP=<rg-name> [LOCATION=eastus] [MODE=validate|deploy] [PARAM_FILE=...] ./infra/azure/deploy.sh

Examples:
  RESOURCE_GROUP=crl-rg LOCATION=eastus MODE=validate ./infra/azure/deploy.sh
  RESOURCE_GROUP=crl-rg LOCATION=eastus MODE=deploy ./infra/azure/deploy.sh
EOF
}

if ! command -v az >/dev/null 2>&1; then
  echo "[ERROR] Azure CLI (az) is required."
  exit 1
fi

if [[ -z "${RESOURCE_GROUP}" ]]; then
  echo "[ERROR] RESOURCE_GROUP is required."
  usage
  exit 1
fi

if [[ ! -f "${TEMPLATE_FILE}" ]]; then
  echo "[ERROR] Missing template file: ${TEMPLATE_FILE}"
  exit 1
fi

if [[ ! -f "${PARAM_FILE}" ]]; then
  echo "[ERROR] Missing parameters file: ${PARAM_FILE}"
  exit 1
fi

echo "[INFO] Ensuring resource group '${RESOURCE_GROUP}' in '${LOCATION}'"
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" >/dev/null

if [[ "${MODE}" == "validate" ]]; then
  echo "[INFO] Validating deployment template"
  az deployment group validate \
    --resource-group "${RESOURCE_GROUP}" \
    --template-file "${TEMPLATE_FILE}" \
    --parameters "@${PARAM_FILE}" >/dev/null
  echo "[OK] Validation passed"
  exit 0
fi

if [[ "${MODE}" != "deploy" ]]; then
  echo "[ERROR] Unsupported MODE: ${MODE}"
  usage
  exit 1
fi

echo "[INFO] Running deployment"
az deployment group create \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "${TEMPLATE_FILE}" \
  --parameters "@${PARAM_FILE}" \
  --query "properties.outputs" \
  --output json

echo "[OK] Deployment complete"
