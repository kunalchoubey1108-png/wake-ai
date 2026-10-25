# Wake.ai — prep checklist (before kickoff 3 Nov 2026)

Aligned with [Vultr: Agent Rush](https://lablab.ai/ai-hackathons/vultr-hackathon) and lablab guidance that you may get a head start / use non-AI scaffolding; **core AI-powered functionality should be built during the event window** (3–8 Nov 2026).

**Kickoff:** 3 Nov 2026, 15:00 UTC = **3 Nov 2026, 20:30 IST**  
**Submissions close:** 8 Nov 2026, 22:00 UTC = **9 Nov 2026, 03:30 IST** (+ ~5 min grace per Rule Book)

## Before 3 Nov (safe prep)

- [ ] **Register on lablab.ai** and enroll in [Vultr: Agent Rush Hackathon](https://lablab.ai/ai-hackathons/vultr-hackathon)
- [ ] **Join lablab.ai Discord**; introduce yourself / find teammates
- [ ] **Form team** (1–6 people) on the event dashboard
- [ ] **Create Vultr account** with an email **not previously associated** with Vultr (credits need a fresh account). Gift code is shared **at kickoff** — do not expect $200 until then
- [ ] **Install Docker locally**; install/configure **gVisor (`runsc`)** on a throwaway VM or local Linux for runtime practice
- [ ] **Sketch the UI** (wireframes / low-fi): paste-repo → scan → triage → prove → graveyard → resurrect; plus containment status panel
- [ ] Keep demo fixtures under `demo-repos/` (tidy-todo, flask-blog, poisoned-carcass) — scaffolding only
- [ ] Finalize architecture notes (2-VM split, containment table) — this prep pack
- [ ] Draft video outline (`docs/video-script.md`); film during the build with a live containment moment
- [ ] Read Vultr Serverless Inference + Compute docs; bookmark credit redemption / Billing → Gift Code flow

## Do during the event (core product)

- [ ] Claim **$200 Vultr credits** with the kickoff gift code
- [ ] Build control-plane + sandbox-host on Vultr VMs
- [ ] Wire Vultr Serverless Inference for triage
- [ ] Implement prove loop (batch / split / restore) + `wake.md` / `wake.lock.json`
- [ ] Deploy public demo URL on Vultr
- [ ] Record ≤5 min demo video including **one containment moment** (Poisoned Carcass)
- [ ] Public GitHub with setup docs; slide deck PDF; submit before deadline

## Submission reminders (Blast Radius Zero)

- Public GitHub + setup/docs
- Vultr VM backend deployment
- Public demo URL
- Recorded demo video (show containment)
- Clear architecture / use-case explanation
