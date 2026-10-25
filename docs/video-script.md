# Wake.ai — 3-minute demo script

**Target length:** 3:00  
**Challenge:** Blast Radius Zero (containment moment required)

---

### 0:00 – 0:20 · Hook
> "Dead code is a liability — until you delete the wrong thing. Wake.ai is the cleanup crew for your code: it finds unused Python, proves every removal with your own tests, and keeps a graveyard so nothing stays dead forever. And the whole job runs inside a sandbox that cannot touch your keys or your host."

Show: Wake.ai landing → paste-repo field.

---

### 0:20 – 1:20 · flask-blog run
> "Here's `flask-blog` — a tiny Flask app with planted dead imports, an unused slugify helper, and a draft cache nobody calls."

Actions on screen:
1. Paste `flask-blog` repo URL → Start cleanup.
2. Scan panel: Vulture + ruff findings light up.
3. LLM triage (Vultr Serverless Inference): marks safe removals vs keep.
4. Prove step: pytest green after batch delete.
5. Diff view: dead code gone; `/posts` still works.

Line: "Real executed results — not a slide that says we would delete it."

---

### 1:20 – 1:40 · Split / restore loop
> "If a batch fails tests, Wake.ai splits the set, retries halves, and restores the guilty hunk. No silent breakage."

Show: one intentional bad candidate → fail → restore → smaller batch → pass.

---

### 1:40 – 2:00 · Graveyard and resurrect
> "Every successful removal is written to `wake.md` and locked in `wake.lock.json` — file, base SHA, hunk, hash."

Show: open `wake.md` → click **Resurrect** on one id → code returns → tests still green.

---

### 2:00 – 2:40 · Poisoned Carcass containment ⚡ required moment
> "Blast radius zero means the agent must survive hostile code. Meet `poisoned-carcass`: fork bomb, infinite loop, `rm -rf /`, env exfil, and hits on `169.254.169.254`."

Show (sandbox only):
- Job starts → attacks fire → container limits kill the bomb / loop.
- Network none + firewall: metadata and egress blocked.
- Control plane keys never inside the sandbox.
- Container `--rm`'d; sweeper would reap anything left.

Line: "The carcass tried to burn the room down. The room was disposable."

---

### 2:40 – 3:00 · Architecture
> "Two VMs: control plane holds the keys and never runs user code; sandbox host runs code and holds nothing. gVisor, cap-drop ALL, no-new-privileges, non-root, read-only rootfs, tmpfs workspace, 512m / 1 CPU / 128 pids, 60s per test run."

End card: Wake.ai — the cleanup crew for your code · Demo URL · GitHub.
