// ===========================================================================
// AURA — Adversarial Unified Reasoning Arena
// Single-RG deployment: Container Apps + ACR + AOAI + AI Search + observability.
// ===========================================================================

targetScope = 'resourceGroup'

@minLength(3)
@maxLength(20)
@description('Short app name; used to derive globally-unique resource names.')
param appName string = 'aura'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container image (e.g. <acr>.azurecr.io/aura:latest). Leave empty to skip Container App.')
param containerImage string = ''

@description('Azure OpenAI model deployment name to expose to the app.')
param aoaiDeployment string = 'gpt-4.1'

@description('Azure OpenAI API version.')
param aoaiApiVersion string = '2024-10-21'

@description('Azure AI Search index name (the corpus AURA queries).')
param knowledgeIndex string = 'aura-corpus'

var uniq = uniqueString(resourceGroup().id, appName)
var names = {
  identity: '${appName}-mi-${uniq}'
  logs: '${appName}-logs-${uniq}'
  appi: '${appName}-appi-${uniq}'
  acr: toLower('${appName}acr${uniq}')
  aoai: '${appName}-aoai-${uniq}'
  search: '${appName}-search-${uniq}'
  cae: '${appName}-cae-${uniq}'
  capp: '${appName}-app-${uniq}'
}

// ── Identity (workload uses this against AOAI + AI Search via MI) ────────
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.identity
  location: location
}

// ── Observability ────────────────────────────────────────────────────────
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: names.logs
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: names.appi
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ── Container Registry ───────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: names.acr
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Azure OpenAI ─────────────────────────────────────────────────────────
resource aoai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: names.aoai
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: names.aoai
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource aoaiDeploymentRes 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aoai
  name: aoaiDeployment
  sku: { name: 'GlobalStandard', capacity: 10 }
  properties: {
    model: { format: 'OpenAI', name: 'gpt-4o', version: '2024-08-06' }
  }
}

resource aoaiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aoai.id, identity.id, 'CognitiveServicesOpenAIUser')
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
    )
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Azure AI Search (Foundry IQ Knowledge Sources backend) ───────────────
resource search 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: names.search
  location: location
  sku: { name: 'basic' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    authOptions: { aadOrApiKey: { aadAuthFailureMode: 'http401WithBearerChallenge' } }
    disableLocalAuth: false
  }
}

resource searchDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, identity.id, 'SearchIndexDataContributor')
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '8ebe5a00-799e-43f5-93ac-243d3dce84a7' // Search Index Data Contributor
    )
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource searchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, identity.id, 'SearchServiceContributor')
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7ca78c08-252a-4471-8644-bb5ff32d4ba0' // Search Service Contributor
    )
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Container Apps Environment + App ─────────────────────────────────────
resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: names.cae
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = if (!empty(containerImage)) {
  name: names.capp
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'aura'
          image: containerImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'AURA_AOAI_ENDPOINT', value: aoai.properties.endpoint }
            { name: 'AURA_AOAI_DEPLOYMENT', value: aoaiDeployment }
            { name: 'AURA_AOAI_API_VERSION', value: aoaiApiVersion }
            { name: 'AURA_FOUNDRY_PROJECT_ENDPOINT', value: 'https://${search.name}.search.windows.net' }
            { name: 'AURA_FOUNDRY_KNOWLEDGE_INDEX', value: knowledgeIndex }
            { name: 'AURA_USE_MANAGED_IDENTITY', value: 'true' }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: { metadata: { concurrentRequests: '50' } }
          }
        ]
      }
    }
  }
}

output acrLoginServer string = acr.properties.loginServer
output identityClientId string = identity.properties.clientId
output identityPrincipalId string = identity.properties.principalId
output aoaiEndpoint string = aoai.properties.endpoint
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output containerAppFqdn string = empty(containerImage) ? '' : containerApp.properties.configuration.ingress.fqdn
