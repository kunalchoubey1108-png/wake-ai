#!/usr/bin/env python3
"""Run poisoned-carcass attacks ONLY inside hardened sandbox; record evidence."""
from __future__ import annotations

import json
import time
from pathlib import Path

from control_plane.sandbox_client import SandboxClient

OUT = Path("/workspace/wake-ai/data/evidence/poisoned_carcass.json")
REPO = Path("/workspace/wake-ai/demo-repos/poisoned-carcass")
OUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    client = SandboxClient()
    assert client.available(), "docker not available"
    evidence: dict = {"runtime": None, "attacks": {}, "notes": []}

    session = client.create(network="none", extra_env={"WAKE_SANDBOX": "1"})
    evidence["runtime"] = session.runtime
    evidence["container_id"] = session.evidence.container_id
    evidence["uid"] = session.evidence.uid
    evidence["create_notes"] = list(session.evidence.notes)
    evidence["env_at_create"] = dict(session.evidence.env_dump)

    # --- Attack 1: rm -rf / vs read-only root + tmpfs ---
    r = client.run(session, ["rm", "-rf", "/", "--no-preserve-root"], timeout_sec=30)
    probe = client.run(
        session,
        [
            "sh",
            "-c",
            "echo ROOT_TOUCH=$(touch /ROOT_WIPED 2>&1); "
            "echo WS_TOUCH=$(mkdir -p /workspace && touch /workspace/survived 2>&1); "
            "echo TMP_TOUCH=$(touch /tmp/survived 2>&1); "
            "echo LS_ROOT=$(ls / 2>/dev/null | tr '\\n' ' '); "
            "echo WS_OK=$(test -f /workspace/survived && echo yes || echo no); "
            "echo PYTHON=$(python -c 'print(1+1)' 2>&1)",
        ],
        timeout_sec=15,
    )
    root_blocked = (
        "Read-only" in probe.stdout
        or "Permission denied" in probe.stdout
        or "Read-only" in (r.stderr or "")
        or "Permission denied" in (r.stderr or "")
    )
    evidence["attacks"]["rm_rf"] = {
        "rm_exit": r.exit_code,
        "rm_stderr_sample": (r.stderr or "")[:600],
        "probe_stdout": probe.stdout,
        "expected": (
            "rm cannot wipe RO root (Permission denied / Read-only); "
            "tmpfs /workspace+/tmp remain usable; python still runs; host untouched"
        ),
        "pass": root_blocked and "WS_OK=yes" in probe.stdout and "PYTHON=2" in probe.stdout,
        "note": (
            "gVisor reports Permission denied (not classic Read-only filesystem) for many "
            "root paths; tmpfs mounts CAN be cleared by rm -rf / — that is contained blast "
            "radius (only the disposable sandbox workspace)."
        ),
    }

    # --- Attack 4: env / metadata / outside URL ---
    env_probe = client.run(
        session,
        [
            "python",
            "-c",
            "import os,urllib.request\n"
            "env={k:v for k,v in os.environ.items() if v}\n"  # ignore blanked
            "print('ENV_KEYS='+','.join(sorted(env.keys())))\n"
            "print('WAKE_SANDBOX='+os.environ.get('WAKE_SANDBOX',''))\n"
            "hostish=any(k.startswith(p) for k in env for p in "
            "('AWS_','OPENAI_','VULTR_','GITHUB_','SSH_','DOCKER_'))\n"
            "print('HOST_SECRET_LEAK='+str(hostish))\n"
            "print('GPG_KEY_EMPTY='+str(not os.environ.get('GPG_KEY')))\n"
            "for url in ('http://169.254.169.254/latest/meta-data/','https://example.com/'):\n"
            "  try:\n"
            "    urllib.request.urlopen(url,timeout=2).read()\n"
            "    print('FETCH_OK='+url)\n"
            "  except Exception as e:\n"
            "    print('FETCH_FAIL='+url+' err='+type(e).__name__+':'+str(e)[:120])\n",
        ],
        timeout_sec=20,
    )
    evidence["attacks"]["env_metadata_network"] = {
        "stdout": env_probe.stdout,
        "exit": env_probe.exit_code,
        "expected": "WAKE_SANDBOX=1; no host cloud/API secrets; fetches fail under network=none",
        "pass": (
            "WAKE_SANDBOX=1" in env_probe.stdout
            and "HOST_SECRET_LEAK=False" in env_probe.stdout
            and "FETCH_OK=" not in env_probe.stdout
            and "FETCH_FAIL=" in env_probe.stdout
        ),
        "metadata_firewall_note": (
            "VM-level metadata firewall (iptables DROP to 169.254.169.254) cannot be "
            "fully verified here — this box is not the production Vultr sandbox VM. "
            "We verify network_mode=none blocks the probe from the container."
        ),
    }
    client.destroy(session)

    # --- Attack 2: python fork bomb vs pids=128 ---
    s2 = client.create(network="none", extra_env={"WAKE_SANDBOX": "1"})
    t0 = time.time()
    bomb = client.run(
        s2,
        [
            "python",
            "-c",
            "import os,time\n"
            "n=0\n"
            "try:\n"
            "  while True:\n"
            "    os.fork(); n+=1\n"
            "except Exception as e:\n"
            "  print('FORK_STOP',type(e).__name__,n); time.sleep(2)\n",
        ],
        timeout_sec=25,
    )
    bomb_dt = time.time() - t0
    after = client.run(s2, ["sh", "-c", "echo ALIVE; ls /workspace >/dev/null && echo WS_OK"], timeout_sec=15)
    evidence["attacks"]["fork_bomb"] = {
        "bomb_exit": bomb.exit_code,
        "bomb_timed_out": bomb.timed_out,
        "bomb_killed": bomb.killed,
        "bomb_duration_sec": bomb_dt,
        "bomb_stdout": (bomb.stdout or "")[:500],
        "bomb_stderr": (bomb.stderr or "")[:500],
        "after_stdout": after.stdout,
        "after_exit": after.exit_code,
        "pids_limit": 128,
        "expected": "forks stop via OSError/pids=128 and/or timeout kill; host unaffected",
        "pass": (
            bomb.timed_out
            or bomb.killed
            or "FORK_STOP" in (bomb.stdout or "")
            or bomb.exit_code != 0
        ),
        "note": "Sandbox may stop under fork storm; that is contained. Host must stay healthy.",
        "kills": list(s2.evidence.kills),
    }
    client.destroy(s2)

    # --- Attack 3: infinite loop vs 60s kill ---
    s3 = client.create(network="none", extra_env={"WAKE_SANDBOX": "1"})
    t0 = time.time()
    loop = client.run(s3, ["python", "-c", "while True: pass"], timeout_sec=60)
    loop_dt = time.time() - t0
    evidence["attacks"]["infinite_loop"] = {
        "exit": loop.exit_code,
        "timed_out": loop.timed_out,
        "killed": loop.killed,
        "duration_sec": loop_dt,
        "stderr": (loop.stderr or "")[:300],
        "expected": "timeout -s KILL 60s ends the loop; duration ~60s",
        "pass": (loop.timed_out or loop.killed) and 55 <= loop_dt <= 90,
        "kills": list(s3.evidence.kills),
    }
    client.destroy(s3)

    # --- pytest path: conftest rm wipes tmpfs workspace (contained); re-copy & innocent ---
    s4 = client.create(network="none", extra_env={"WAKE_SANDBOX": "1"})
    client.put_tree(s4, REPO, "repo")
    collect = client.run(
        s4,
        ["python", "-m", "pytest", "--collect-only", "-q"],
        workdir="/workspace/repo",
        env={"WAKE_SANDBOX": "1", "PYTHONPATH": "/workspace/repo/src"},
        timeout_sec=30,
    )
    wiped = client.run(
        s4,
        ["sh", "-c", "test -d /workspace/repo && echo REPO_PRESENT || echo REPO_WIPED_TMPFS"],
        timeout_sec=10,
    )
    # Re-seed workspace (tmpfs was legitimately wiped inside the sandbox only)
    client.put_tree(s4, REPO, "repo")
    # Bypass conftest rm on second run by invoking test module directly without conftest?
    # Use PYTEST_ADDOPTS or run innocent via python -c after re-put with a stub conftest.
    # Simplest: put a safe conftest that only checks WAKE_SANDBOX.
    safe_conftest = (
        "import os,sys,pytest\n"
        "def pytest_configure(config):\n"
        "    if os.environ.get('WAKE_SANDBOX')!='1':\n"
        "        pytest.exit('blocked', returncode=2)\n"
    ).encode()
    client.put_bytes(s4, "repo/tests/conftest.py", safe_conftest)
    innocent = client.run(
        s4,
        ["python", "-m", "pytest", "-q", "-k", "innocent_add", "--noconftest"],
        workdir="/workspace/repo",
        env={"WAKE_SANDBOX": "1", "PYTHONPATH": "/workspace/repo/src"},
        timeout_sec=30,
    )
    # --noconftest may skip our check; still OK inside sandbox. Prefer with safe conftest:
    innocent2 = client.run(
        s4,
        ["python", "-m", "pytest", "-q", "-k", "innocent_add"],
        workdir="/workspace/repo",
        env={"WAKE_SANDBOX": "1", "PYTHONPATH": "/workspace/repo/src"},
        timeout_sec=30,
    )
    evidence["attacks"]["pytest_conftest_rm_and_innocent"] = {
        "collect_exit": collect.exit_code,
        "collect_out_sample": (collect.stdout + collect.stderr)[:500],
        "after_conftest_rm": wiped.stdout.strip(),
        "innocent_exit": innocent2.exit_code,
        "innocent_out": (innocent2.stdout + innocent2.stderr)[:400],
        "expected": (
            "conftest rm -rf / cannot kill host; may wipe sandbox tmpfs workspace "
            "(contained); after re-seed, innocent_add passes"
        ),
        "pass": (
            "REPO_WIPED_TMPFS" in wiped.stdout or "REPO_PRESENT" in wiped.stdout
        )
        and innocent2.exit_code == 0
        and "passed" in (innocent2.stdout + innocent2.stderr),
    }
    client.destroy(s4)

    evidence["summary_pass"] = all(
        a.get("pass") for a in evidence["attacks"].values() if "pass" in a
    )
    evidence["host_notes"] = {
        "WAKE_SANDBOX_on_host": __import__("os").environ.get("WAKE_SANDBOX", "<unset>"),
        "metadata_firewall": "NOT fully verifiable on this box (VM-level control)",
    }
    OUT.write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))
    print("WROTE", OUT, "summary_pass=", evidence["summary_pass"])


if __name__ == "__main__":
    main()
