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


@pytest.fixture(scope="session")
def played():
    """Seed 1 played through to the end once: its moments, their claims and their records.

    For the tests that need real claims and the real verifier's verdicts on them (P3).
    """
    from tests.verification.test_verify import _play

    return _play()
