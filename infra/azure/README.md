# Azure Deployment (Container Apps)

This folder contains a minimal Azure Container Apps deployment for `custom-rate-limiter`.

## Files

- `main.bicep`: Infrastructure template (Log Analytics + Container Apps Environment + Container App)
- `parameters.json`: Default deployment parameters
- `deploy.sh`: Deployment/validation script
- `quickstart.sh`: Wrapper script for fast setup

## Prerequisites

- Azure CLI (`az`)
- Logged-in Azure session (`az login`)
- An image available in a registry (default placeholder uses GHCR)

## Quickstart

Validate template first:

```bash
RESOURCE_GROUP=crl-rg LOCATION=eastus MODE=validate \
IMAGE=ghcr.io/<your-org>/custom-rate-limiter:latest \
./infra/azure/quickstart.sh
```

Deploy:

```bash
RESOURCE_GROUP=crl-rg LOCATION=eastus MODE=deploy \
IMAGE=ghcr.io/<your-org>/custom-rate-limiter:latest \
./infra/azure/quickstart.sh
```

## Notes

- The template defaults to `RATE_LIMIT_STORAGE=memory` for easy startup.
- If you switch to `redis`, configure and inject Redis connection settings before deployment.
- Deployment output includes the app endpoint URL.
