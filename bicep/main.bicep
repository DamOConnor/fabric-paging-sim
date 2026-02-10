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
  kind: 'Storage'
  sku: {
    name: storageSku
  }
  properties: {
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

// ---------------------------------------------------------------------------
// Storage Blob Data Owner — allows the UAMI to manage blobs for the Function
// ---------------------------------------------------------------------------
var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'

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
    siteConfig: {
      ftpsState: 'FtpsOnly'
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
    blobDataOwnerRole // Ensure RBAC is in place before the Function App starts
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
