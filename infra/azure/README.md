# Azure Deployment Guide

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Azure Container Apps                                    │
│  ┌──────────────────────────────────────────────┐       │
│  │  rate-limiter-app (1-5 replicas, auto-scale) │       │
│  │  ┌────────────┐ ┌────────────┐              │       │
│  │  │ Gunicorn   │ │ Flask App  │              │       │
│  │  │ Workers    │→│ Rate Limit │              │       │
│  │  └────────────┘ └─────┬──────┘              │       │
│  └────────────────────────┼─────────────────────┘       │
│                           │                              │
│  ┌────────────────────────▼─────────────────────┐       │
│  │  Azure Cache for Redis (Basic C0)            │       │
│  │  • TLS 1.2 only                              │       │
│  │  • volatile-lru eviction                     │       │
│  └──────────────────────────────────────────────┘       │
│                                                          │
│  ┌──────────────────────────────────────────────┐       │
│  │  Log Analytics Workspace                     │       │
│  │  • Container logs                            │       │
│  │  • 30-day retention                          │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

1. Azure CLI installed: `brew install azure-cli`
2. Logged in: `az login`
3. Container Apps extension: `az extension add --name containerapp --upgrade`

## Quick Deploy (Recommended)

The quickstart script deploys everything from source in one command:

```bash
./infra/azure/quickstart.sh rg-rate-limiter eastus
```

This creates:
- Resource Group
- Azure Cache for Redis (Basic C0, ~$13/month)
- Container Apps Environment
- Container App (built from source)

## Deploy with Bicep (Production)

For production with CI/CD:

```bash
# 1. Create resource group
az group create --name rg-rate-limiter --location eastus

# 2. Deploy infrastructure
az deployment group create \
  --resource-group rg-rate-limiter \
  --template-file infra/azure/main.bicep \
  --parameters @infra/azure/parameters.json
```

## CI/CD (GitHub Actions)

The `.github/workflows/ci-cd.yml` workflow handles:
1. Run tests on every push/PR
2. Build and push Docker image to GHCR
3. Deploy to Azure on push to `main` or `azure-deploy`

### Required Secrets

Set these in GitHub repo → Settings → Secrets:

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | Service principal JSON from `az ad sp create-for-rbac` |

### Required Variables

Set these in GitHub repo → Settings → Variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_RESOURCE_GROUP` | Target resource group | `rg-rate-limiter` |
| `AZURE_LOCATION` | Azure region | `eastus` |

### Create Service Principal

```bash
az ad sp create-for-rbac \
  --name "github-rate-limiter" \
  --role contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-rate-limiter \
  --sdk-auth
```

Copy the JSON output to the `AZURE_CREDENTIALS` secret.

## Environment Configuration

All rate limiter settings are passed as environment variables to the container.
See `.env.example` for all available options.

Key Azure-specific settings:
- `REDIS_URL`: Automatically configured to use Azure Cache for Redis with TLS
- `CIRCUIT_BREAKER_ENABLED=true`: Essential for cloud reliability
- `ADAPTIVE_ENABLED=true`: Auto-adjusts limits based on container load

## Scaling

The Container App auto-scales from 1 to 5 replicas based on concurrent HTTP requests (threshold: 50).

To change scaling:
```bash
az containerapp update \
  --name custom-rate-limiter-app \
  --resource-group rg-rate-limiter \
  --min-replicas 2 \
  --max-replicas 10
```

## Monitoring

```bash
# View logs
az containerapp logs show \
  --name custom-rate-limiter-app \
  --resource-group rg-rate-limiter \
  --follow

# View metrics
curl https://<app-url>/metrics
curl https://<app-url>/admin/adaptive
curl https://<app-url>/admin/circuit-breaker
```

## Cost Estimate

| Resource | SKU | Monthly Cost |
|----------|-----|--------------|
| Azure Cache for Redis | Basic C0 | ~$13 |
| Container Apps | 0.5 vCPU, 1 GB | ~$15 |
| Log Analytics | PerGB2018 | ~$2 |
| **Total** | | **~$30/month** |

## Cleanup

```bash
az group delete --name rg-rate-limiter --yes --no-wait
```
