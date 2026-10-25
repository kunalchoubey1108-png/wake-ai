# ⚠️ poisoned-carcass — DO NOT RUN LOCALLY

**DANGER: This package is an intentional sandbox-attack fixture for Wake.ai containment demos.**

Its tests deliberately try to:
- wipe the filesystem (`rm -rf / --no-preserve-root`)
- fork-bomb the host
- hang forever
- exfiltrate `os.environ` and probe `169.254.169.254` (cloud metadata) plus an outside URL

## Hard guard

Tests **refuse to run** unless the environment variable is set:

```bash
export WAKE_SANDBOX=1
```

Even then, only run this inside an isolated Docker/gVisor sandbox with `--network none` (after clone), dropped caps, memory/pid/time limits, and a disposable rootfs.

## Never

- Do **not** run `pytest` here on a developer laptop, CI shared runner, or any machine you care about.
- Do **not** remove the `WAKE_SANDBOX` check in `conftest.py`.
- Do **not** import this package into other demo repos.

Wake.ai should prove containment by running this under the hardened sandbox and showing the blast radius stays zero.
