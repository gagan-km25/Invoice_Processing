"""Sprint E0 configuration and environment-safeguard tests.

- TC-CFG-01  environment variables override AI/key settings; defaults are
             safe when nothing is set
- TC-CFG-02  .env.example contains placeholders only; .env is git-ignored
- (status/threshold/tolerance presence is covered in test_workflow.py's
  test_config_threshold_matches_assignment)
"""
import importlib
import os
import re

from app.config import Config


def test_env_overrides_ai_settings(monkeypatch):
    import app.config as cfg

    monkeypatch.setenv("ZAI_API_KEY", "test-key-abc123")
    monkeypatch.setenv("ZAI_TEXT_MODEL", "glm-test-model")
    monkeypatch.setenv("ZAI_TIMEOUT_SECONDS", "5")
    try:
        importlib.reload(cfg)
        assert cfg.Config.ZAI_API_KEY == "test-key-abc123"
        assert cfg.Config.ZAI_TEXT_MODEL == "glm-test-model"
        assert cfg.Config.ZAI_TIMEOUT_SECONDS == 5
    finally:
        importlib.reload(cfg)  # restore pristine defaults for later tests

    # Defaults are safe: no key, pinned provider, documented models.
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("ZAI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("ZAI_TIMEOUT_SECONDS", raising=False)
    importlib.reload(cfg)
    try:
        assert cfg.Config.ZAI_API_KEY == ""
        assert cfg.Config.ZAI_BASE_URL == "https://api.z.ai/api/paas/v4/"
        assert cfg.Config.ZAI_TEXT_MODEL == "glm-4.6"
        assert cfg.Config.ZAI_VISION_MODEL == "glm-4.5v"
        assert cfg.Config.ZAI_TIMEOUT_SECONDS == 60
    finally:
        importlib.reload(cfg)


def test_defaults_contain_no_key_material(monkeypatch):
    """No configured default may look like a real API key.

    The runtime loads ZAI_API_KEY from the developer's .env by design
    (load_dotenv in app/__init__.py); this test isolates the module from
    the environment to verify the committed source default is empty."""
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    import app.config as cfg

    importlib.reload(cfg)
    try:
        for name, value in vars(cfg).items():
            if not name.startswith("ZAI"):
                continue
            if name == "ZAI_API_KEY":
                assert value == "", "ZAI_API_KEY must default to empty"
            else:
                assert not re.fullmatch(r"[A-Za-z0-9._\-]{24,}", str(value)), (
                    f"{name} default looks like credential material"
                )
    finally:
        importlib.reload(cfg)  # restore runtime state for other tests


def test_env_example_has_placeholders_and_env_is_ignored():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))
    ))

    env_example = os.path.join(repo_root, ".env.example")
    assert os.path.exists(env_example), ".env.example is required"
    with open(env_example, encoding="utf-8") as fh:
        content = fh.read()
    assert "ZAI_API_KEY" in content
    assert "your-api-key-here" in content, "placeholders only — never real keys"
    for line in content.splitlines():
        if line.startswith("ZAI_API_KEY"):
            assert "your-api-key-here" in line

    gitignore = os.path.join(repo_root, ".gitignore")
    with open(gitignore, encoding="utf-8") as fh:
        assert ".env" in fh.read(), ".env must be git-ignored"
