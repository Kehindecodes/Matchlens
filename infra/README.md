# Infra

`main.bicep` is the whole MatchLens stack in one resource group: the container registry, the Log Analytics workspace, the Application Insights resource that stores its traces in that workspace (S6), the Container Apps environment, the `matchlens` app (at most one replica, kept running through the judging window, public ingress on 8000), and the managed identity the app pulls its image with, which has AcrPull on the registry.

## Into an empty resource group

```bash
az group create -n rg-matchlens -l uksouth
az deployment group create -g rg-matchlens -f infra/main.bicep
```

With no `image`, the app starts on the public Container Apps placeholder, because the registry is still empty. The next run of the Deploy workflow builds the image, pushes it and points the app at it.

Deleting the group also deletes the deploy identity's two roles, which sit on the group and the registry. Grant them again before the Deploy workflow runs:

```bash
SP=$(az ad sp show --id <deploy identity client id> --query id -o tsv)
az role assignment create --assignee-object-id "$SP" --assignee-principal-type ServicePrincipal --role Contributor --scope "$(az group show -n rg-matchlens --query id -o tsv)"
az role assignment create --assignee-object-id "$SP" --assignee-principal-type ServicePrincipal --role AcrPush --scope "$(az acr show -n matchlenskehinde --query id -o tsv)"
```

A new environment gets a new domain, so the URL changes.

## Against the live stack

Pass the image that is running, so the app does not go back to the placeholder:

```bash
IMAGE=$(az containerapp show -n matchlens -g rg-matchlens --query "properties.template.containers[0].image" -o tsv)
az deployment group what-if -g rg-matchlens -f infra/main.bicep -p image="$IMAGE"
az deployment group create  -g rg-matchlens -f infra/main.bicep -p image="$IMAGE"
```

## The judging window (X4): one replica, through 10 November

`minReplicas` is a parameter and defaults to **1**, so a visitor never waits for a container to boot. It bills for as long as it is on, so **put it back to 0 after 10 November**:

```bash
az containerapp update -n matchlens -g rg-matchlens --min-replicas 0 -o none
```

Running `main.bicep` against the live stack applies it, along with everything else in the file, so read the `what-if` first. The Deploy workflow does not: it only changes the image.

**What it costs**, for 26 October to 10 November at the allocation the app already has (0.5 vCPU, 1 GiB). Prices are the Azure retail prices for UK South on 26 October; the free grants are 180,000 vCPU-seconds and 360,000 GiB-seconds per subscription per calendar month, so October and November each get one.

| The replica is | Oct 26–31 | Nov 1–10 | Total |
|---|---|---|---|
| active all the time (an open stream counts as active) | $3.33 | $10.58 | **$13.91** |
| active a quarter of the time | $1.54 | $4.91 | $6.46 |
| idle all the time | $0.95 | $3.02 | $3.97 |
| *for comparison, active all the time with no free grant* | *$10.89* | *$18.14* | *$29.03* |

The budget is $15 a month for the whole subscription, and the registry alone is $5 a month ($0.1666 a day), so November's headroom for the app is about $10. Even the worst row above is inside the budget through 31 October and reaches about 100 per cent in November. A replica only counts as idle with no open stream, so one judge leaving a tab open keeps it on the active rate. Expect between the second and third rows.

A budget **alerts, it does not cap**: nothing here stops the app at 100 per cent. If the 80 per cent alert arrives, the first fallback is a smaller allocation (`cpu: json('0.25')`, `memory: '0.5Gi'`), which costs under $2 even when active all the time. The app used 142 MiB and 1.6 per cent of one core with nobody watching, measured locally at 25×.

## Rate limits (X4)

Every request is counted against its client for the last minute (`matchlens/delivery/limits.py`). A client over its budget gets `429` and `Retry-After`; a server with every stream slot taken gets `503`. The pages retry a refused stream every two seconds, so a viewer who is turned away comes in when a slot frees.

| What | Limit | Setting (`MATCHLENS_` prefix) |
|---|---|---|
| New sessions (`POST /session`), per client | 30 a minute | `LIMIT_NEW_SESSIONS_PER_MIN` |
| Other changes (speed, model switch, lens, mute), per client | 30 a minute | `LIMIT_CHANGES_PER_MIN` |
| Reads, including opening a stream, per client | 600 a minute | `LIMIT_READS_PER_MIN` |
| Open streams, per client | 15 | `LIMIT_STREAMS_PER_CLIENT` |
| Open streams, whole app | 40 | `LIMIT_STREAMS_TOTAL` |
| Sessions held in memory, whole app | 10,000 | `MAX_SESSIONS` |

A page opens three streams, so 15 is five pages from one address and 40 is thirteen visitors at once. **The stream cap is the one that protects the replay.** Measured locally, with the match playing at 25× and the demo's real app:

| Open streams | Server CPU, share of one core | Memory |
|---|---|---|
| 0 | 1.6% | 142 MiB |
| 100 | 44.5% | 149 MiB |
| 300 | 98.9% (the event loop is full and events are being dropped) | 161 MiB |

That is 0.43% of a core for each open stream, because each is woken and sent a state 25 times a second. The app has 0.5 vCPU. A cloud core may be slower than the laptop it was measured on, so the cap assumes 2.5 times slower: 40 streams is then about 43% of the allocation, which leaves room for the pipeline's start-up burst. After the whistle a stream costs about a sixth of that, so the cap is cautious there. Sessions are 2.8 KiB each, so 10,000 is under 30 MiB and the ceiling only matters to stop a loop.

The client is the **rightmost** address in `X-Forwarded-For`, and only where `MATCHLENS_TRUST_FORWARDED_FOR=true`, which `main.bicep` sets. The ingress is the only thing that writes that entry; anything to its left is the client's own (Container Apps, "Ingress"). Without it every visitor would arrive from the ingress's address and share one budget.

To change a limit on the running app, without a build:

```bash
az containerapp update -n matchlens -g rg-matchlens --set-env-vars MATCHLENS_LIMIT_STREAMS_TOTAL=60 -o none
```

Two things the limits do not do. They do not stop one visitor changing the speed or switching the model off for everyone, which is how those controls are designed (D33, A5); they only stop it being done more than 30 times a minute. And nothing evicts a session, so the ceiling refuses new ones with `503` rather than making room.

## Checked on 26 October

- **The budget** `matchlens-monthly` is live: $15 a month, from 1 October 2026 to 30 September 2027, alerting at 50, 80 and 100 per cent. All three go to `oluwawafunmi1@gmail.com` and to no one else. Nothing here can show whether that inbox is read, so someone who reads it needs to look before 10 November.
- **The deploy identity's roles** are in place: `matchlens-github-deploy` has Contributor on `rg-matchlens` and AcrPush on the registry, and the app's pull identity has AcrPull. They sit on the group and the registry, so deleting the group takes them with it.
- **The producer view is off on the live app**: the running app has no `MATCHLENS_PRODUCER_VIEW`, and the default in `main.bicep` is `'true'`. Running the file against the live stack therefore turns on `/producer`, including its mute controls, for anyone with the URL.

## Outside this file

These live at subscription or tenant level, were set up once by hand, and are not part of the resource group:

- **The budget**, `matchlens-monthly`: 15 a month in the billing currency, alerting at 50, 80 and 100 per cent, created before any resource.
- **The deploy identity**, the Entra app `matchlens-github-deploy`: a federated credential for `main` of this repo, Contributor on `rg-matchlens` and AcrPush on the registry. GitHub Actions signs in as it with OIDC.
