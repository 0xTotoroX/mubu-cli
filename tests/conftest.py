"""Keep every component test away from real credentials, desktop sessions and HTTP."""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture(autouse=True)
def isolated_user_state(tmp_path, monkeypatch):
    import mubu_api

    import mubu.client
    import mubu.config

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("MUBU_PHONE", "MUBU_PASSWORD", "MUBU_MEMBER_ID", "MUBU_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    for name in ("APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(name, str(tmp_path))
    for module in (mubu.config, mubu.client, mubu_api):
        for name, filename in (("TOKEN_FILE", "token.json"), ("ENV_FILE", ".env"), ("TRASH_FILE", "trash.json")):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, tmp_path / filename)

    def blocked(*args, **kwargs):
        pytest.fail("Tests must mock HTTP; real Mubu account operations are forbidden.")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", blocked)
