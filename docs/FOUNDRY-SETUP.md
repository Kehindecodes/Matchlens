# Setting up Foundry for A2

A step-by-step guide to giving A2 a real model. When you finish it, Q33 can move from **B** (scripted model) to **A** (live model).

## What you are actually creating

**Not a portal agent.** A2's agent is defined in code: `matchlens/explanation/foundry.py` builds a Microsoft Agent Framework `Agent` over a `FoundryChatClient`, and passes it `agent.INSTRUCTIONS` on every call. You do not need anything from the Foundry portal's *Agents* page. Creating an agent there would give a second set of instructions that the code never reads.

What the code needs from Azure is three things:

| Thing | Where the code reads it |
|---|---|
| A Foundry **project endpoint**, `https://<resource>.services.ai.azure.com/api/projects/<project>` | `MATCHLENS_FOUNDRY_ENDPOINT` |
| A **model deployment name** inside that project | `MATCHLENS_MODEL_NAME` |
| An identity with the **Foundry User** role on the project (formerly *Azure AI User*) | `DefaultAzureCredential`: your `az login` locally, a managed identity in Container Apps |

**The model choice is yours** (it is what Q33 asked). The commands below use `<model>`, `<version>` and `<deployment>` as placeholders. Microsoft's own quickstart uses `gpt-5-mini` as its example.

---

## 0 · Before you start

```bash
az version          # the project commands need Azure CLI 2.80.0 or later
az upgrade          # if it is older
az login
az account show --query name -o tsv   # should be the subscription rg-matchlens is in
```

The `matchlens-monthly` budget is **15 a month**. Model calls are billed per token on top of the stack. One seed-1 run makes one call per moment, roughly 30–60 calls, each sending a digest of a few thousand tokens. Do one run (step 6) before you leave anything switched on.

## 1 · Pick names

```bash
RG=rg-matchlens
LOC=uksouth                   # see step 3: the model must be offered here
FOUNDRY=matchlens-foundry-kehinde   # also the custom domain, so it must be globally unique
PROJECT=matchlens
```

Putting Foundry in `rg-matchlens` keeps one resource group for the whole stack, as `infra/README.md` describes. It also means that deleting the group deletes Foundry.

## 2 · Create the Foundry resource and the project

```bash
az cognitiveservices account create \
  --name "$FOUNDRY" --resource-group "$RG" --location "$LOC" \
  --kind AIServices --sku S0 \
  --custom-domain "$FOUNDRY" \
  --assign-identity \
  --allow-project-management true

az cognitiveservices account project create \
  --name "$FOUNDRY" --resource-group "$RG" \
  --project-name "$PROJECT" --location "$LOC"
```

- `--allow-project-management` **cannot be changed later**. Without it, there is no project and so no project endpoint.
- `--assign-identity` is required. Without it, `project create` fails, saying a managed identity must be enabled.
- `CustomDomainInUse` means the name is taken. Change `FOUNDRY` and run it again.

Check that both succeeded:

```bash
az cognitiveservices account show -n "$FOUNDRY" -g "$RG" --query properties.provisioningState -o tsv
az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" \
  --query properties.provisioningState -o tsv
```

Both should print `Succeeded`.

## 3 · Choose and deploy the model

List what `$LOC` offers, then pick a model and version:

```bash
az cognitiveservices model list --location "$LOC" \
  --query "[?model.format=='OpenAI'].{name:model.name, version:model.version, skus:join(',', model.skus[].name)}" \
  -o table
```

What A2 needs from the model: it must follow a JSON-only instruction reliably, and handle a prompt of a few thousand tokens. It does not need tools, vision or a long context.

```bash
DEPLOYMENT=<deployment>   # the name the code will use, often the same as the model's

az cognitiveservices account deployment create \
  --name "$FOUNDRY" --resource-group "$RG" \
  --deployment-name "$DEPLOYMENT" \
  --model-name <model> --model-version "<version>" --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10

az cognitiveservices account deployment show -n "$FOUNDRY" -g "$RG" \
  --deployment-name "$DEPLOYMENT" --query properties.provisioningState -o tsv
```

The second command should print `Succeeded`. `DeploymentModelNotSupported` means that model, version or SKU isn't offered in `$LOC`. Pick another row from the list, or another region.

## 4 · Give yourself access

Being Owner of the subscription lets you *create* the resource, but it does not let you *call* the model. Calling it is a data-plane permission, which comes from **Foundry User**. Assign it by ID, because the role names are still mid-rename:

```bash
PROJECT_ID=$(az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" \
  --project-name "$PROJECT" --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)

az role assignment create \
  --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" \
  --assignee-object-id "$ME" --assignee-principal-type User \
  --scope "$PROJECT_ID"
```

Role assignments can take a few minutes to apply. A `401` or `403` in step 5 straight after this usually means waiting, not fixing anything.

## 5 · Point the code at it, and make one call

```bash
ENDPOINT=$(az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" \
  --project-name "$PROJECT" --query 'properties.endpoints."AI Foundry API"' -o tsv)
echo "$ENDPOINT"   # https://<resource>.services.ai.azure.com/api/projects/<project>
```

Set the two lines in `.env` (it is git-ignored, and holds no secret: the credential is your login):

```
MATCHLENS_FOUNDRY_ENDPOINT=<the endpoint above>
MATCHLENS_MODEL_NAME=<deployment>
```

One call, outside the pipeline:

```bash
.venv/bin/python -c "
from matchlens.explanation.foundry import from_settings
p = from_settings()
print(p.propose('Answer with JSON only.', 'Reply with {\"claims\": []}'))
"
```

You should see `Answer(text='{\"claims\": []}', model='<deployment>', model_version='<served model id>')`. If `from_settings()` returns `None`, one of the two `.env` lines is empty.

## 6 · Run A2 over seed 1, and read what it got wrong

This is the evidence the A2 walkthrough is missing:

```bash
.venv/bin/python - <<'EOF'
import logging
from tests.explanation.test_builder import _play
from matchlens.explanation.foundry import from_settings

logging.basicConfig(level=logging.WARNING, format="%(message)s")
played = _play(1, proposer=from_settings())
added = [c for x in played.explained for c in x.claims if c.model != "deterministic"]
print(f"{len(played.explained)} moments, {len(added)} claims added by the model")
for c in added:
    print(c.claim_id, c.claim_type, [(o.metric, o.value) for o in c.operands])
EOF
```

Every `explainer: non-conforming answer …` line is a whole answer thrown away, with the validation error that sank it. Every `explainer: dropped …, which cites …` line is a claim that invented its evidence. Those are the *"what the model got wrong before it got it right"* for `docs/walkthroughs/A2.md`. If you change `agent.INSTRUCTIONS` to fix them, bump `PROMPT_VERSION`.

No card changes whatever the model says: A2's claims are held out of Selection until A3 (Q32: A).

## 7 · The deployed app

Steps 1–6 give the model to your laptop only. The Container Apps app needs four changes, all of them in the repo. Ask Claude Code to make them; they are listed here so you know what to expect:

1. **`Dockerfile`**: install the `agents` group. Today it builds with `--no-default-groups`, so `FoundryProposer` would fail to import.
2. **`infra/main.bicep`, env**: `MATCHLENS_FOUNDRY_ENDPOINT` and `MATCHLENS_MODEL_NAME` on the container.
3. **`infra/main.bicep`, identity**: a Foundry User role assignment on the project for the app's identity, plus `AZURE_CLIENT_ID` set to that identity's client ID. The app has only a user-assigned identity, and `DefaultAzureCredential` picks a user-assigned identity only when it is told which one. The only identity it has today is `matchlens-pull`, named for pulling images. Whether to reuse it or add a second identity for the model is a small choice to make when this is done.
4. **`infra/main.bicep`, the Foundry resource itself**, so the stack is reproducible from the file. Otherwise, add it to *"Outside this file"* in `infra/README.md` as set up by hand.

## 8 · Close the question

In `docs/QUESTIONS.md`, answer Q33 with **A**, the model and version you deployed, and the region.

## Switching it off

Without the two `.env` lines, the code runs on L7's claims alone (D35). To stop the spend but keep the resource, delete the deployment:

```bash
az cognitiveservices account deployment delete -n "$FOUNDRY" -g "$RG" --deployment-name "$DEPLOYMENT"
```

Judging runs to 10 November, so leave the deployment in place until then if the demo uses it.

---

Sources: [Quickstart: Set up Microsoft Foundry resources](https://learn.microsoft.com/en-ca/azure/foundry/tutorials/quickstart-create-foundry-resources) · [Create projects](https://learn.microsoft.com/azure/foundry/how-to/create-projects) · [Foundry SDK overview](https://learn.microsoft.com/azure/foundry/how-to/develop/sdk-overview). The code side was checked against the installed `agent-framework==1.21.0` and `agent-framework-foundry==1.14.1`.
