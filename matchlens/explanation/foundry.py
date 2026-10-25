"""The A2 proposer over a Foundry model deployment, through Microsoft Agent Framework.

Nothing builds it unless both `foundry_endpoint` and `model_name` are set. One call per moment:
the agent has no tools, so a run is a single structured round trip, never a loop (D36).

The pipeline is synchronous and the agent is not, so the agent runs on an event loop of its
own, on its own thread, and a call waits for it up to `explainer_timeout_s`.
"""

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any, override

from matchlens.config import settings
from matchlens.explanation.agent import Answer, Proposer
from matchlens.explanation.cache import Cached

logger = logging.getLogger(__name__)


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

    def warm(self) -> None:
        """One throwaway call, so the first viewer does not pay the model's cold start (D36)."""
        try:
            self.propose("Answer with JSON only.", '{"claims": []}')
        except Exception as failure:
            logger.warning("explainer: warm-up call failed: %r", failure)

    async def _run(self, instructions: str, prompt: str) -> Answer:
        agent: Any = self._agent_type(client=self._client, instructions=instructions)
        effort = {"reasoning": {"effort": settings.explainer_reasoning_effort}}
        response = await agent.run(prompt, options=effort)
        served = getattr(response.raw_representation, "model", None) or self._model
        return Answer(text=response.text, model=self._model, model_version=served)


def live() -> FoundryProposer | None:
    """The configured model, or None when none is configured."""
    if not (settings.foundry_endpoint and settings.model_name):
        return None
    return FoundryProposer(
        settings.foundry_endpoint, settings.model_name, settings.explainer_timeout_s
    )


def warm(proposer: Proposer | None) -> None:
    """Warm the live model behind `proposer`, if there is one, without waiting for it."""
    model = proposer.live if isinstance(proposer, Cached) else proposer
    if isinstance(model, FoundryProposer):
        threading.Thread(target=model.warm, name="explainer-warm", daemon=True).start()


def from_settings() -> Proposer | None:
    """The demo cache in front of the configured model; either alone; or None (D35: L7 alone).

    With a cache and no model, a prompt the cache holds is answered and any other is not.
    """
    model = live()
    path = settings.explainer_cache_path
    if path and Path(path).exists():
        return Cached.load(path, model)
    return model
