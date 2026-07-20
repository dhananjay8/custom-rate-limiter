#!/usr/bin/env bash
# Quick Azure deployment using Azure Container Apps (no GHCR needed)
# Deploys directly from source using az containerapp up
#
# Prerequisites:
#   - az CLI installed and logged in
#   - az extension: containerapp
#
# Usage:
#   ./infra/azure/quickstart.sh [resource-group] [location]

set -euo pipefail

RESOURCE_GROUP="${1:-rg-rate-limiter}"
LOCATION="${2:-eastus}"
APP_NAME="custom-rate-limiter-app"
ENV_NAME="custom-rate-limiter-env"
REDIS_NAME="custom-rate-limiter-redis"

echo "=== Quick Deploy: Custom Rate Limiter to Azure ==="
echo ""

# Ensure extensions
az extension add --name containerapp --upgrade 2>/dev/null || true

# Step 1: Resource Group
echo "[1/5] Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# Step 2: Redis Cache
echo "[2/5] Creating Azure Cache for Redis (this takes ~5 min)..."
az redis create \
  --name "$REDIS_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Basic \
  --vm-size C0 \
  --output none

# Get Redis connection info
echo "  Waiting for Redis to be ready..."
az redis wait --name "$REDIS_NAME" --resource-group "$RESOURCE_GROUP" --created
REDIS_HOST=$(az redis show --name "$REDIS_NAME" --resource-group "$RESOURCE_GROUP" --query "hostName" -o tsv)
REDIS_KEY=$(az redis list-keys --name "$REDIS_NAME" --resource-group "$RESOURCE_GROUP" --query "primaryKey" -o tsv)
REDIS_PORT=$(az redis show --name "$REDIS_NAME" --resource-group "$RESOURCE_GROUP" --query "sslPort" -o tsv)
REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOST}:${REDIS_PORT}/0"

# Step 3: Container App Environment
echo "[3/5] Creating Container Apps environment..."
az containerapp env create \
  --name "$ENV_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# Step 4: Deploy the app from source
echo "[4/5] Deploying rate limiter app (building from source)..."
az containerapp up \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --environment "$ENV_NAME" \
  --source . \
  --target-port 5000 \
  --ingress external \
  --env-vars \
    RATE_LIMIT_STORAGE=redis \
    "REDIS_URL=$REDIS_URL" \
    LOG_LEVEL=INFO \
    APP_ENV=production \
    FOO_ALGORITHM=fixed_window \
    BAR_ALGORITHM=sliding_window_log \
    CLIENT_BASIC_FOO_LIMIT=10 \
    CLIENT_BASIC_FOO_WINDOW=60 \
    CLIENT_BASIC_BAR_LIMIT=20 \
    CLIENT_BASIC_BAR_WINDOW=60 \
    CLIENT_PREMIUM_FOO_LIMIT=100 \
    CLIENT_PREMIUM_FOO_WINDOW=60 \
    CLIENT_PREMIUM_BAR_LIMIT=250 \
    CLIENT_PREMIUM_BAR_WINDOW=60 \
    CIRCUIT_BREAKER_ENABLED=true \
    ADAPTIVE_ENABLED=true \
    COALESCING_ENABLED=true

# Step 5: Get URL
echo "[5/5] Getting application URL..."
APP_URL=$(az containerapp show \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "App URL:     https://$APP_URL"
echo "Swagger UI:  https://$APP_URL/docs"
echo "Health:      https://$APP_URL/health"
echo ""
echo "Test commands:"
echo "  curl https://$APP_URL/health"
echo "  curl https://$APP_URL/foo -H 'Authorization: Bearer client-basic'"
echo "  curl https://$APP_URL/foo -H 'Authorization: Bearer client-premium'"
echo "  curl https://$APP_URL/bar -H 'Authorization: Bearer client-basic'"
echo ""
echo "Admin:"
echo "  curl https://$APP_URL/admin/config"
echo "  curl https://$APP_URL/admin/adaptive"
echo "  curl https://$APP_URL/admin/circuit-breaker"
echo "  curl https://$APP_URL/admin/quotas"
echo ""
echo "Cleanup:"
echo "  az group delete --name $RESOURCE_GROUP --yes --no-wait"
