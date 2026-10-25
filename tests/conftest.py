import pytest

from matchlens.config import settings


@pytest.fixture(scope="session", autouse=True)
def _no_live_model():
    """No test calls a real model, whatever `.env` configures (A2): each one that wants a model
    passes a scripted one. A live call would bill the run and wait on the network."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "foundry_endpoint", "")
        mp.setattr(settings, "model_name", "")
        yield
