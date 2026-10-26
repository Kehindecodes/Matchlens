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


@pytest.fixture(scope="session", autouse=True)
def _a_slow_machine_changes_nothing():
    """The verifier's budget is wall-clock time, and the suite's process is large: a garbage
    collection there stops every thread for up to a second, and on a loaded CI runner longer. One
    that lands between a claim's checks fails the rest of them, drops the claim from its card, and
    fails whichever test compares two runs' cards, a different one each time. The budget is for a
    runaway check, so the suite lifts it far out of reach; the tests of the budget itself set their
    own, and the live value is read from the setting's default."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "verifier_budget_ms", 60_000)
        yield


@pytest.fixture(scope="session")
def played():
    """Seed 1 played through to the end once: its moments, their claims and their records.

    For the tests that need real claims and the real verifier's verdicts on them (P3).
    """
    from tests.verification.test_verify import _play

    return _play()
