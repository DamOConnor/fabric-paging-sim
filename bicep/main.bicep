// ---------------------------------------------------------------------------
// Fabric Paging Simulator — Azure Function App (Flex Consumption, Linux)
// Deploys: Storage Account, User-Assigned MI, App Service Plan, Function App,
//          RBAC role assignment, and configures identity-based storage access.
// ---------------------------------------------------------------------------

@description('Location for all resources')
param location string = resourceGroup().location

@description('Base name used to derive resource names')
param appName string = 'fabric-paging-sim'

@description('Storage account SKU')
param storageSku string = 'Standard_LRS'

// ---------------------------------------------------------------------------
// Naming
// ---------------------------------------------------------------------------
var rawStorageName = toLower(replace(replace(resourceGroup().name, '-', ''), ' ', ''))
var storageNameSuffix = uniqueString(resourceGroup().id)
var truncatedStorageName = take('${rawStorageName}${storageNameSuffix}', 24)
var planName = '${appName}-plan'
var uamiName = '${appName}-uami'

// ---------------------------------------------------------------------------
// User-Assigned Managed Identity
// ---------------------------------------------------------------------------
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: uamiName
  location: location
}

// ---------------------------------------------------------------------------
// Storage Account (shared key access disabled — required by Azure Policy)
// ---------------------------------------------------------------------------
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: truncatedStorageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: storageSku
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

// ---------------------------------------------------------------------------
// Disable soft delete, versioning, and change feed to minimise storage costs
// ---------------------------------------------------------------------------
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: false
    }
    containerDeleteRetentionPolicy: {
      enabled: false
    }
    isVersioningEnabled: false
    changeFeed: {
      enabled: false
    }
  }
}

// ---------------------------------------------------------------------------
// RBAC — identity-based AzureWebJobsStorage requires Owner (blob lease mgmt),
// plus Queue and Table Contributor roles for the Functions runtime.
// ---------------------------------------------------------------------------
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'

resource blobDataOwnerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, uami.id, storageBlobDataOwnerRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageBlobDataOwnerRoleId
    )
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource queueDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, uami.id, storageQueueDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageQueueDataContributorRoleId
    )
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource tableDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, uami.id, storageTableDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      storageTableDataContributorRoleId
    )
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// App Service Plan — Flex Consumption (FC1)
// ---------------------------------------------------------------------------
resource hostingPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

// ---------------------------------------------------------------------------
// Function App — Python on Linux, identity-based storage via UAMI
// ---------------------------------------------------------------------------
resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${uami.id}': {}
    }
  }
  properties: {
    serverFarmId: hostingPlan.id
    reserved: true
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storageAccount.properties.primaryEndpoints.blob}app-package-${appName}-${uniqueString(resourceGroup().id)}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: uami.id
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
      scaleAndConcurrency: {
        maximumInstanceCount: 2
        instanceMemoryMB: 2048
      }
    }
    siteConfig: {
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'AzureWebJobsStorage__clientId'
          value: uami.properties.clientId
        }
        {
          name: 'AzureWebJobsStorage__blobServiceUri'
          value: 'https://${storageAccount.name}.blob.${environment().suffixes.storage}'
        }
        {
          name: 'AzureWebJobsStorage__queueServiceUri'
          value: 'https://${storageAccount.name}.queue.${environment().suffixes.storage}'
        }
        {
          name: 'AzureWebJobsStorage__tableServiceUri'
          value: 'https://${storageAccount.name}.table.${environment().suffixes.storage}'
        }
      ]
    }
  }
  dependsOn: [
    blobDataOwnerRole
    queueDataContributorRole
    tableDataContributorRole
  ]
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

@description('The default hostname of the Function App')
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'

@description('The name of the Function App (for func azure functionapp publish)')
output functionAppName string = functionApp.name

@description('The client ID of the User-Assigned Managed Identity')
output uamiClientId string = uami.properties.clientId

@description('The storage account name')
output storageAccountName string = storageAccount.name
