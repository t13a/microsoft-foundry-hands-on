// Application layer (docs/design.md 9.1): the web app (BFF + SPA) on Container Apps and the
// catalog CSV in Blob Storage. Runs after the Foundry layer and uses its outputs.
targetScope = 'resourceGroup'

@description('Azure region.')
param location string = resourceGroup().location

@description('azd environment name, used for the resource token and tags.')
param environmentName string

@description('Foundry account name (output of the Foundry layer).')
param aiAccountName string

@description('Foundry project endpoint (output of the Foundry layer).')
param projectEndpoint string

@description('Log Analytics workspace resource ID (output of the Foundry layer).')
param logAnalyticsWorkspaceResourceId string

@description('Application Insights resource ID (output of the Foundry layer).')
param applicationInsightsResourceId string = ''

@description('Hosted agent name the web app relays to.')
param agentName string = 'consultation-workflow'

@description('Container image of the web app. Built by GitHub Actions and published on GHCR (DR-12).')
param webImage string

@description('User name for the Basic auth in front of the site (N-SEC-01).')
param basicAuthUser string = 'demo'

@secure()
@description('Password for the Basic auth. Kept in the azd environment, not in the repository.')
param basicAuthPassword string

@description('Principal that runs azd, granted write access to the catalog container to upload the CSV.')
param deployerPrincipalId string = ''

@description('Monthly budget for this resource group, in the billing currency (N-COST-04).')
param budgetAmount int = 1000

@description('Address that receives budget alerts. Kept in the azd environment (BUDGET_EMAIL), not in the repository.')
param budgetEmail string = ''

@description('First day of the budget period. Fixed, because a budget cannot move its start date.')
param budgetStartDate string = '2026-11-01'

var token = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var tags = { 'azd-env-name': environmentName }
var catalogContainer = 'catalog'

// Built-in roles.
var storageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var storageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var azureAiUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiAccountName
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: last(split(logAnalyticsWorkspaceResourceId, '/'))
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = if (!empty(applicationInsightsResourceId)) {
  name: last(split(applicationInsightsResourceId, '/'))
}

// --- Catalog CSV (DR-11): versioning keeps past uploads (F-DAT-32) ---

resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: 'st${token}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2024-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: catalogContainer
}

// --- Web app (DR-7): scale to zero, at most one replica (6.3) ---

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${token}'
  location: location
  tags: tags
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

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'web'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      secrets: [
        { name: 'basic-auth-password', value: basicAuthPassword }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'CATALOG_BLOB_URL', value: '${storage.properties.primaryEndpoints.blob}${catalogContainer}' }
            { name: 'AGENT_RESPONSES_URL', value: '${projectEndpoint}/agents/${agentName}/endpoint/protocols/openai/responses?api-version=v1' }
            { name: 'AGENT_AUTH', value: 'managed_identity' }
            { name: 'AGENT_PLATFORM_SESSIONS', value: '1' }
            { name: 'BASIC_AUTH_USER', value: basicAuthUser }
            { name: 'BASIC_AUTH_PASSWORD', secretRef: 'basic-auth-password' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: empty(applicationInsightsResourceId) ? '' : appInsights!.properties.ConnectionString }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

// --- Role assignments (N-SEC-02: managed identities, no keys) ---

resource webReadsCatalog 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, web.id, storageBlobDataReader)
  properties: {
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReader)
  }
}

resource webCallsAgent 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiAccount
  name: guid(aiAccount.id, web.id, azureAiUser)
  properties: {
    principalId: web.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiUser)
  }
}

resource deployerWritesCatalog 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: storage
  name: guid(storage.id, deployerPrincipalId, storageBlobDataContributor)
  properties: {
    principalId: deployerPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributor)
  }
}

// --- Budget alert (N-COST-04) ---

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (!empty(budgetEmail)) {
  name: 'budget-${environmentName}'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [budgetEmail]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [budgetEmail]
      }
    }
  }
}

output WEB_URL string = 'https://${web.properties.configuration.ingress.fqdn}'
output CATALOG_STORAGE_ACCOUNT string = storage.name
output CATALOG_CONTAINER string = catalogContainer
