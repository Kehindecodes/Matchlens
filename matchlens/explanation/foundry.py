"""The A2 proposer over a Foundry model deployment, through Microsoft Agent Framework.

Untested against a live endpoint until one exists (Q33: B). Nothing builds it unless both
`foundry_endpoint` and `model_name` are set, so a process with neither runs on L7's claims.

The pipeline is synchronous and the agent is not, so the agent runs on an event loop of its
own, on its own thread, and a call waits for it up to `explainer_timeout_s`.
"""

import asyncio
import threading
from typing import Any, override

from matchlens.config import settings
from matchlens.explanation.agent import Answer, Proposer


class FoundryProposer(Proposer):
    def __init__(self, endpoint: str, model: str, timeout_s: float):
        # Imported here so that the runtime image, which leaves the agents group out, never
        # needs them until an endpoint is configured.
        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        self._agent_type = Agent
        self._client = FoundryChatClient(
            project_endpoint=endpoint, model=model, credential=DefaultAzureCredential()
        )
        self._model = model
        self._timeout_s = timeout_s
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

    @override
    def propose(self, instructions: str, prompt: str) -> Answer:
        future = asyncio.run_coroutine_threadsafe(self._run(instructions, prompt), self._loop)
        try:
            return future.result(timeout=self._timeout_s)
        except TimeoutError:
            future.cancel()
            raise

    async def _run(self, instructions: str, prompt: str) -> Answer:
        agent: Any = self._agent_type(client=self._client, instructions=instructions)
        response = await agent.run(prompt)
        served = getattr(response.raw_representation, "model", None) or self._model
        return Answer(text=response.text, model=self._model, model_version=served)


def from_settings() -> Proposer | None:
    """The configured proposer, or None when no model is configured (D35: L7 alone)."""
    if not (settings.foundry_endpoint and settings.model_name):
        return None
    return FoundryProposer(
        settings.foundry_endpoint, settings.model_name, settings.explainer_timeout_s
    )
