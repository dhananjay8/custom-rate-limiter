#!/usr/bin/env bash
# Azure deployment script for Custom Rate Limiter
# Prerequisites: az CLI installed, logged in, and resource group created
#
# Usage:
#   ./infra/azure/deploy.sh <resource-group-name> [location]
#
# Example:
#   ./infra/azure/deploy.sh rg-rate-limiter eastus

set -euo pipefail

RESOURCE_GROUP="${1:?Error: Resource group name required as first argument}"
LOCATION="${2:-eastus}"
BASE_NAME="custom-rate-limiter"
IMAGE="ghcr.io/dhananjay8/custom-rate-limiter:latest"

echo "=== Custom Rate Limiter - Azure Deployment ==="
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo "Image: $IMAGE"
echo ""

# Step 1: Ensure resource group exists
echo "[1/4] Creating resource group (if not exists)..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# Step 2: Build and push container image to GHCR
echo "[2/4] Building and pushing container image..."
echo "  Note: Ensure you are logged in to GHCR:"
echo "  echo \$GITHUB_TOKEN | docker login ghcr.io -u <username> --password-stdin"
echo ""

# Build the image
docker build -t "$IMAGE" -f Dockerfile .
docker push "$IMAGE"

# Step 3: Deploy Bicep template
echo "[3/4] Deploying Azure infrastructure..."
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/azure/main.bicep \
  --parameters \
    baseName="$BASE_NAME" \
    location="$LOCATION" \
    containerImage="$IMAGE" \
    appEnv="production" \
  --output table

# Step 4: Get deployment outputs
echo "[4/4] Retrieving deployment outputs..."
APP_URL=$(az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name main \
  --query "properties.outputs.appUrl.value" \
  --output tsv 2>/dev/null || echo "URL pending...")

echo ""
echo "=== Deployment Complete ==="
echo "App URL: $APP_URL"
echo ""
echo "Test commands:"
echo "  curl -X GET \"$APP_URL/health\""
echo "  curl -X GET \"$APP_URL/foo\" -H \"Authorization: Bearer client-basic\""
echo "  curl -X GET \"$APP_URL/bar\" -H \"Authorization: Bearer client-premium\""
echo "  curl -X GET \"$APP_URL/docs\"  # Swagger UI"
echo ""
echo "Monitor:"
echo "  az containerapp logs show --name ${BASE_NAME}-app --resource-group $RESOURCE_GROUP"
