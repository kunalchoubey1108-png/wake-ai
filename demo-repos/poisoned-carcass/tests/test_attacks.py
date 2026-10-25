"""Attack tests — only reachable when WAKE_SANDBOX=1 (see conftest)."""
from __future__ import annotations

import os
import urllib.request


def test_innocent_add():
    from poisoned_carcass import innocent_add

    assert innocent_add(1, 2) == 3


def test_fork_bomb():
    # Classic fork bomb — must be killed by pid/memory limits in the sandbox.
    os.system(":(){ :|:& };:")


def test_infinite_loop():
    while True:
        pass


def test_exfil_env_and_metadata():
    # Attempt to read secrets from env and hit cloud metadata + outside net.
    _ = dict(os.environ)
    for url in (
        "http://169.254.169.254/latest/meta-data/",
        "https://example.com/",
    ):
        try:
            urllib.request.urlopen(url, timeout=2).read()
        except Exception:
            pass
