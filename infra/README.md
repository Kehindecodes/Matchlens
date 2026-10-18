# Infra

`main.bicep` is the whole MatchLens stack in one resource group: the container registry, the Log Analytics workspace, the Container Apps environment, the `matchlens` app (scale 0–1, public ingress on 8000) and the app's AcrPull role on the registry.

## Into an empty resource group

```bash
az group create -n rg-matchlens -l uksouth
az deployment group create -g rg-matchlens -f infra/main.bicep
```

With no `image`, the app starts on the public Container Apps placeholder, because the registry is still empty. The next run of the Deploy workflow builds the image, pushes it and points the app at it.

## Against the live stack

Pass the image that is running, so the app does not go back to the placeholder:

```bash
IMAGE=$(az containerapp show -n matchlens -g rg-matchlens --query "properties.template.containers[0].image" -o tsv)
az deployment group what-if -g rg-matchlens -f infra/main.bicep -p image="$IMAGE"
az deployment group create  -g rg-matchlens -f infra/main.bicep -p image="$IMAGE"
```

## Outside this file

These live at subscription or tenant level, were set up once by hand, and are not part of the resource group:

- **The budget**, `matchlens-monthly`: 15 a month in the billing currency, alerting at 50, 80 and 100 per cent, created before any resource.
- **The deploy identity**, the Entra app `matchlens-github-deploy`: a federated credential for `main` of this repo, Contributor on `rg-matchlens` and AcrPush on the registry. GitHub Actions signs in as it with OIDC.
