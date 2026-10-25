import pytest

from matchlens.config import settings


@pytest.fixture(scope="session", autouse=True)
def _no_live_model():
    """No test calls a real model or reads the demo cache, whatever `.env` configures (A2):
    each one that wants a model passes a scripted one. A live call would bill the run and wait
    on the network, and cached answers would put the model's claims on cards the tests pin."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "foundry_endpoint", "")
        mp.setattr(settings, "model_name", "")
        mp.setattr(settings, "explainer_cache_path", "")
        yield
