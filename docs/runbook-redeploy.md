# Runbook: Redeploy Fabric Paging Simulator

## Context

The Azure Function App `fabric-paging-sim` uses a Flex Consumption (FC1) plan with identity-based storage via a User-Assigned Managed Identity. The Fabric workspace `ws-paging` contains pipelines that connect to the Function App via a `WebForPipeline` connection.

## Problem Triggers

1. **MCAPS overnight policy** disables `publicNetworkAccess` on the storage account, breaking the Function App (no VNet/private endpoint in place).
2. **Bicep redeployment** may create a new storage account and Function App hostname, requiring connection and pipeline updates in Fabric.

---

## Phase 1: Fix Storage Network Access

MCAPS sets `publicNetworkAccess: Disabled` on storage accounts. The Function App has no VNet integration, so it loses access.

```powershell
# Re-enable public network access on the storage account
az storage account update `
  --name <storage-account-name> `
  --resource-group rg-fabric-paging-sim `
  --public-network-access Enabled

# Restart the Function App
az functionapp restart --name fabric-paging-sim --resource-group rg-fabric-paging-sim
```

The Bicep template includes `publicNetworkAccess: 'Enabled'` on the storage account to counteract MCAPS on subsequent deployments.

---

## Phase 2: Full Bicep Redeployment (if needed)

### Prerequisites

- The Bicep template includes full Flex Consumption config: `functionAppConfig.deployment.storage`, `runtime`, and `scaleAndConcurrency`.
- RBAC roles required for identity-based `AzureWebJobsStorage`:
  - **Storage Blob Data Owner** (`b7e6dc6d-f1e8-4753-8033-0f276bb0955b`) — runtime needs lease management
  - **Storage Queue Data Contributor** (`974c5e8b-45b9-4653-ba55-5f855dd0fb88`)
  - **Storage Table Data Contributor** (`0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3`)

### If the Function App is on a different plan than Bicep expects

ARM cannot move a Function App between plans. You must delete and recreate:

```powershell
# Check current plan
az rest --method GET `
  --uri "/subscriptions/<sub-id>/resourceGroups/rg-fabric-paging-sim/providers/Microsoft.Web/sites/fabric-paging-sim?api-version=2024-04-01" `
  --query "properties.serverFarmId" -o tsv

# Delete Function App and old plan
az functionapp delete --name fabric-paging-sim --resource-group rg-fabric-paging-sim
Start-Sleep -Seconds 10
az appservice plan delete --name <old-plan-name> --resource-group rg-fabric-paging-sim --yes

# Deploy fresh
az deployment group create `
  --resource-group rg-fabric-paging-sim `
  --template-file bicep/main.bicep `
  --parameters bicep/main.bicepparam
```

### Create the deployment container

Flex Consumption requires a blob container for deployment packages. Bicep doesn't auto-create it:

```powershell
# Get the container URI from the deployed Function App
$containerUri = az rest --method GET `
  --uri "/subscriptions/<sub-id>/resourceGroups/rg-fabric-paging-sim/providers/Microsoft.Web/sites/fabric-paging-sim?api-version=2024-04-01" `
  --query "properties.functionAppConfig.deployment.storage.value" -o tsv

# Extract container name (everything after the last /)
$containerName = ($containerUri -split '/')[-1]
$storageAccount = (($containerUri -split '//')[1] -split '\.')[0]

az storage container create --name $containerName --account-name $storageAccount --auth-mode login
```

### Publish function code

```powershell
func azure functionapp publish fabric-paging-sim
```

### Delete old storage account (if a new one was created)

```powershell
az storage account list --resource-group rg-fabric-paging-sim --query "[].{name:name, kind:kind}" -o table
# Delete the old one (Storage v1) if a new StorageV2 was created
az storage account delete --name <old-storage-name> --resource-group rg-fabric-paging-sim --yes
```

---

## Phase 3: Update Fabric Connection

If the Function App hostname changed (e.g., from a portal-created random hostname to `fabric-paging-sim.azurewebsites.net`), the Fabric connection must be recreated.

### 1. Snapshot existing connection permissions

```powershell
$token = (az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv)
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

# List connections to find the target
$connections = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/connections" -Headers $headers
$conn = $connections.value | Where-Object { $_.displayName -eq "Paging Sim Base admin" }
$oldConnectionId = $conn.id
Write-Host "Old connection ID: $oldConnectionId"

# IMPORTANT: Snapshot role assignments BEFORE deleting
$roles = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/connections/$oldConnectionId/roleAssignments" -Headers $headers
$roles.value | ConvertTo-Json -Depth 5 | Out-File "connection-roles-backup.json"
Write-Host "Backed up $($roles.value.Count) role assignments"
```

### 2. Delete old connection and create new one

```powershell
# Delete
Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/connections/$oldConnectionId" -Headers $headers -Method DELETE

# Create with new URL
$body = @'
{
  "connectivityType": "ShareableCloud",
  "displayName": "Paging Sim Base admin",
  "connectionDetails": {
    "type": "WebForPipeline",
    "creationMethod": "WebForPipeline.Contents",
    "parameters": [
      {
        "dataType": "Text",
        "name": "baseUrl",
        "value": "https://fabric-paging-sim.azurewebsites.net/api/"
      }
    ]
  },
  "credentialDetails": {
    "singleSignOnType": "None",
    "connectionEncryption": "NotEncrypted",
    "skipTestConnection": false,
    "credentials": {
      "credentialType": "Anonymous"
    }
  }
}
'@

$newConn = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/connections" -Headers $headers -Method POST -Body $body
$newConnectionId = $newConn.id
Write-Host "New connection ID: $newConnectionId"
```

### 3. Restore role assignments

```powershell
$savedRoles = Get-Content "connection-roles-backup.json" | ConvertFrom-Json

foreach ($role in $savedRoles) {
    # Skip the owner (auto-assigned to creator)
    if ($role.role -eq "Owner" -and $role.principal.id -eq (az ad signed-in-user show --query id -o tsv)) { continue }

    $roleBody = @{
        principal = @{ id = $role.principal.id; type = $role.principal.type }
        role = $role.role
    } | ConvertTo-Json -Depth 3

    Invoke-RestMethod `
      -Uri "https://api.fabric.microsoft.com/v1/connections/$newConnectionId/roleAssignments" `
      -Headers $headers -Method POST -Body $roleBody
}
```

---

## Phase 4: Update Fabric Pipelines

All pipelines referencing the old connection ID must be updated.

```powershell
$token = (az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv)
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }

$workspaceId = "9fbb5e82-ea3b-49b1-b7c5-3a3df689dc1f"
$oldConnectionId = "<old-connection-id>"
$newConnectionId = "<new-connection-id>"

# List all pipelines in the workspace
$items = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items?type=DataPipeline" -Headers $headers

foreach ($pipeline in $items.value) {
    $def = Invoke-RestMethod `
      -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items/$($pipeline.id)/getDefinition" `
      -Headers $headers -Method POST

    # Check if this pipeline references the old connection
    $content = [System.Text.Encoding]::UTF8.GetString(
        [System.Convert]::FromBase64String(
            ($def.definition.parts | Where-Object { $_.path -eq 'pipeline-content.json' }).payload
        )
    )

    if ($content -match $oldConnectionId) {
        Write-Host "Updating pipeline: $($pipeline.displayName)"

        $updatedParts = @()
        foreach ($part in $def.definition.parts) {
            $decoded = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($part.payload))
            $updated = $decoded -replace $oldConnectionId, $newConnectionId
            $encoded = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($updated))
            $updatedParts += @{ path = $part.path; payload = $encoded; payloadType = "InlineBase64" }
        }

        $body = @{ definition = @{ parts = $updatedParts } } | ConvertTo-Json -Depth 5
        Invoke-RestMethod `
          -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items/$($pipeline.id)/updateDefinition" `
          -Headers $headers -Method POST -Body $body

        Write-Host "  Updated successfully"
    } else {
        Write-Host "Skipping pipeline: $($pipeline.displayName) (no reference to old connection)"
    }
}
```

---

## Reference

| Item | Value |
|------|-------|
| Resource Group | `rg-fabric-paging-sim` |
| Function App | `fabric-paging-sim` |
| Function App URL | `https://fabric-paging-sim.azurewebsites.net` |
| Fabric Workspace | `ws-paging` (`9fbb5e82-ea3b-49b1-b7c5-3a3df689dc1f`) |
| Connection Name | `Paging Sim Base admin` |
| Connection Type | `WebForPipeline` / Anonymous |
| Pipelines | `pl_paging1`, `pl_paging2` |
| UAMI | `fabric-paging-sim-uami` |

## Lessons Learned

1. **Always snapshot connection role assignments before deleting** — the Fabric API doesn't support updating connection details in place; you must delete/recreate.
2. **Flex Consumption deployment container** is not auto-created by Bicep — must be created manually or via script before `func publish`.
3. **MCAPS will revert `publicNetworkAccess`** overnight — either keep re-enabling via Bicep deployments, or move to VNet + private endpoints for a durable fix.
4. **Storage Blob Data Contributor is insufficient** for `AzureWebJobsStorage` — the Functions runtime needs **Blob Data Owner** (for leases) plus **Queue** and **Table Data Contributor**.
5. **ARM cannot move a Function App between App Service Plans** — if the plan name changed (e.g., portal-created vs. Bicep-managed), you must delete and recreate both.
