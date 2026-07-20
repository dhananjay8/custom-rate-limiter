// Azure Infrastructure for Custom Rate Limiter
// Deploys: Container App + Azure Cache for Redis + Log Analytics
// Usage: az deployment group create --resource-group <rg> --template-file infra/azure/main.bicep

@description('Base name for all resources')
param baseName string = 'rate-limiter'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Container image to deploy')
param containerImage string = 'ghcr.io/dhananjay8/custom-rate-limiter:latest'

@description('Environment (development/production)')
param appEnv string = 'production'

// --- Log Analytics Workspace ---
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${baseName}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// --- Azure Cache for Redis ---
resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${baseName}-redis'
  location: location
  properties: {
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisConfiguration: {
      'maxmemory-policy': 'volatile-lru'
    }
  }
}

// --- Container Apps Environment ---
resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-11-02-preview' = {
  name: '${baseName}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// --- Container App ---
resource containerApp 'Microsoft.App/containerApps@2023-11-02-preview' = {
  name: '${baseName}-app'
  location: location
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 5000
        transport: 'http'
        allowInsecure: false
      }
      registries: []
      secrets: [
        {
          name: 'redis-connection'
          value: '${redisCache.properties.hostName}:${redisCache.properties.sslPort},password=${redisCache.listKeys().primaryKey},ssl=True,abortConnect=False'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'rate-limiter'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'RATE_LIMIT_STORAGE', value: 'redis' }
            { name: 'REDIS_URL', secretRef: 'redis-connection' }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'APP_ENV', value: appEnv }
            { name: 'FOO_ALGORITHM', value: 'fixed_window' }
            { name: 'BAR_ALGORITHM', value: 'sliding_window_log' }
            { name: 'CLIENT_BASIC_FOO_LIMIT', value: '10' }
            { name: 'CLIENT_BASIC_FOO_WINDOW', value: '60' }
            { name: 'CLIENT_BASIC_BAR_LIMIT', value: '20' }
            { name: 'CLIENT_BASIC_BAR_WINDOW', value: '60' }
            { name: 'CLIENT_PREMIUM_FOO_LIMIT', value: '100' }
            { name: 'CLIENT_PREMIUM_FOO_WINDOW', value: '60' }
            { name: 'CLIENT_PREMIUM_BAR_LIMIT', value: '250' }
            { name: 'CLIENT_PREMIUM_BAR_WINDOW', value: '60' }
            { name: 'CIRCUIT_BREAKER_ENABLED', value: 'true' }
            { name: 'ADAPTIVE_ENABLED', value: 'true' }
            { name: 'COALESCING_ENABLED', value: 'true' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 5000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 5000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

// --- Outputs ---
output appUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output redisHost string = redisCache.properties.hostName
output logAnalyticsId string = logAnalytics.id
