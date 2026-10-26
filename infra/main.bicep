// The MatchLens stack: one container app behind a public URL, pulling its image from ACR (D23).
//
//   az deployment group create -g rg-matchlens -f infra/main.bicep -p image=<current image>
//
// Run it against the live group with the running image, or the app reverts to the bootstrap
// image; infra/README.md has the command. Into an empty group, leave `image` out: the app starts
// on a public placeholder, and the next deploy workflow run swaps in the real image.

@description('Region for every resource.')
param location string = resourceGroup().location

@description('Registry name; globally unique, alphanumeric only.')
param registryName string = 'matchlenskehinde'

@description('Log Analytics workspace for the container app environment.')
param workspaceName string = 'workspace-rgmatchlensOYCX'

param environmentName string = 'matchlens-env'
param appName string = 'matchlens'

@description('The image to run. Empty means the placeholder, for a stack whose registry is still empty.')
param image string = ''

@description('Match clock seconds per wall clock second (MATCHLENS_REPLAY_SPEED).')
param replaySpeed string = '25'

@description('Serve the producer view at /producer (MATCHLENS_PRODUCER_VIEW). Off, it is not there at all.')
param producerView string = 'true'

@description('Replicas kept running. 1 through the judging window to 10 Nov (X4), so no visitor waits for a cold start; 0 after it, or the app keeps billing. infra/README.md has the cost.')
@minValue(0)
@maxValue(1)
param minReplicas int = 1

var bootstrap = empty(image)
var placeholderImage = 'mcr.microsoft.com/k8se/quickstart:latest' // listens on 80, not 8000
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false // the app pulls with its managed identity, CI pushes with OIDC
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Traces land in the same workspace as the container logs (S6).
resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${appName}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

// The app's pull identity exists, with AcrPull, before the app does: a system identity only
// exists once the app does, so the app's first pull would come before its permission.
resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${appName}-pull'
  location: location
}

resource pullFromRegistry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, pullIdentity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${pullIdentity.id}': {}
    }
  }
  dependsOn: [
    pullFromRegistry
  ]
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: bootstrap ? 80 : 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: pullIdentity.id
        }
      ]
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: insights.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: appName
          image: bootstrap ? placeholderImage : image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'MATCHLENS_REPLAY_SPEED'
              value: replaySpeed
            }
            {
              name: 'MATCHLENS_PRODUCER_VIEW'
              value: producerView
            }
            {
              name: 'MATCHLENS_TRUST_FORWARDED_FOR' // every visitor reaches the app from the ingress; the limits need the address it forwards
              value: 'true'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING' // read by configure_azure_monitor()
              secretRef: 'appinsights-connection-string'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 1 // one match runs per process (D23, D33), so a second replica would play a second one
      }
    }
  }
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
