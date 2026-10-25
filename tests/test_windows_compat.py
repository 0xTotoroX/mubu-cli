import errno
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mubu import client, config


def test_legacy_entry_help_is_utf8_under_ascii_locale():
    script = Path(__file__).resolve().parents[1] / "scripts" / "mubu_api.py"
    env = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
    result = subprocess.run([sys.executable, "-B", str(script), "--help"], env=env, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "幕布" in result.stdout.decode("utf-8")


def test_repeated_token_and_trash_replace_preserves_utf8():
    instance = client.MubuClient(phone="synthetic", password="synthetic")
    for token in ("初始凭据", "更新凭据📝"):
        instance.token = token
        instance.expires_at = 1234567890
        instance._save_token()
        assert json.loads(client.TOKEN_FILE.read_text(encoding="utf-8"))["token"] == token
    for title in ("第一版", "第二版📝"):
        instance._save_trash({"id": {"name": title}})
        assert json.loads(client.TRASH_FILE.read_text(encoding="utf-8"))["id"]["name"] == title


def test_windows_token_lock_waits_and_unlocks_on_failure(monkeypatch):
    calls = []

    def locking(fd, mode, length):
        calls.append((mode, length, os.lseek(fd, 0, os.SEEK_CUR)))
        if len(calls) == 1:
            raise OSError(errno.EACCES, "busy")

    monkeypatch.setattr(config, "fcntl", None)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=locking, LK_NBLCK=1, LK_UNLCK=2))
    pauses = []
    monkeypatch.setattr(config.time, "sleep", pauses.append)
    with pytest.raises(RuntimeError, match="cancel"):
        with config._token_file_lock():
            assert len(calls) == 2
            raise RuntimeError("cancel")
    assert calls == [(1, 1, 0), (1, 1, 0), (2, 1, 0)]
    assert pauses == [0.05]


def test_windows_lock_does_not_hide_non_contention_error(monkeypatch):
    def locking(*args):
        raise OSError(errno.EBADF, "bad handle")

    monkeypatch.setattr(config, "fcntl", None)
    monkeypatch.setitem(sys.modules, "msvcrt", SimpleNamespace(locking=locking, LK_NBLCK=1))
    with pytest.raises(OSError, match="bad handle"), config._token_file_lock():
        pytest.fail("must not enter an unlocked critical section")
