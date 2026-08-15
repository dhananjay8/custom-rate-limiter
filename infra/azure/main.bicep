targetScope = 'resourceGroup'

@description('Azure location for all resources')
param location string = resourceGroup().location

@description('Deployment name prefix used for resource naming')
param namePrefix string = 'custom-rate-limiter'

@description('Container image to deploy')
param containerImage string

@description('Container app CPU cores')
param containerCpu string = '0.5'

@description('Container app memory size')
param containerMemory string = '1Gi'

@description('Public target port exposed by the container app')
param targetPort int = 5000

@description('Minimum number of running replicas')
param minReplicas int = 1

@description('Maximum number of running replicas')
param maxReplicas int = 5

@description('Storage backend used by the app (memory|sqlite|redis)')
@allowed([
  'memory'
  'sqlite'
  'redis'
])
param rateLimitStorage string = 'memory'

@description('Default algorithm for /foo')
param fooAlgorithm string = 'fixed_window'

@description('Default algorithm for /bar')
param barAlgorithm string = 'sliding_window_log'

@description('Enable adaptive limiter')
param adaptiveEnabled bool = true

@description('Enable request coalescing')
param coalescingEnabled bool = true

@description('Enable storage circuit breaker')
param circuitBreakerEnabled bool = true

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${namePrefix}-law'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: listKeys(logAnalytics.id, '2022-10-01').primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-app'
  location: location
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
      }
      registries: []
      secrets: []
    }
    template: {
      containers: [
        {
          name: 'rate-limiter'
          image: containerImage
          resources: {
            cpu: json(containerCpu)
            memory: containerMemory
          }
          env: [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'RATE_LIMIT_STORAGE'
              value: rateLimitStorage
            }
            {
              name: 'FOO_ALGORITHM'
              value: fooAlgorithm
            }
            {
              name: 'BAR_ALGORITHM'
              value: barAlgorithm
            }
            {
              name: 'ADAPTIVE_ENABLED'
              value: string(adaptiveEnabled)
            }
            {
              name: 'COALESCING_ENABLED'
              value: string(coalescingEnabled)
            }
            {
              name: 'CIRCUIT_BREAKER_ENABLED'
              value: string(circuitBreakerEnabled)
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output containerAppName string = containerApp.name
output managedEnvironmentName string = managedEnvironment.name
output endpoint string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
