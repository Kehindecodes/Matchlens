from pathlib import Path

from matchlens.config.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_defaults_for_local_runs(monkeypatch):
    monkeypatch.chdir(REPO_ROOT / "tests")  # no .env here
    s = Settings(_env_file=None)
    assert s.frame_rate_hz == 2  # D13
    assert s.signal_window_ms == 300_000
    assert s.baseline_k_minutes == 15
    assert s.log_level == "INFO"


def test_reads_environment(monkeypatch):
    monkeypatch.setenv("MATCHLENS_MATCH_SEED", "99")
    monkeypatch.setenv("MATCHLENS_LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.match_seed == 99
    assert s.log_level == "DEBUG"


def test_reads_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MATCHLENS_MODEL_NAME", raising=False)
    env = tmp_path / ".env"
    env.write_text("MATCHLENS_MODEL_NAME=from-dotenv\n")
    assert Settings(_env_file=env).model_name == "from-dotenv"


def test_module_level_settings_instance():
    from matchlens.config import settings

    assert isinstance(settings, Settings)


def test_nothing_outside_config_reads_os_environ():
    offenders = []
    for root in ("matchlens", "apps"):
        for path in (REPO_ROOT / root).rglob("*.py"):
            if "config" in path.relative_to(REPO_ROOT).parts[:2]:
                continue
            text = path.read_text()
            if "os.environ" in text or "os.getenv" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
