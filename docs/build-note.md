# Intelligence Radar: Build Note

## Scope and Status

Neha can inspect every in-window return claim by vendor, compare fit rates, read a weekly brief and review optional size-note drafts. Non-fit and held claims remain visible without a brief. Gradio owns the UI; Python owns the backend. This is an MVP, not proof of return reduction.

Five tables serve CSV and read-only Postgres: vendors, products, physical items, returns and reviews. The stress profile contains 5,000 items, 1,090 returns and 97 reviews: 55.05% Other versus the client's stated 44%. Adapter equality is verified. Original inputs/results remain frozen. Fourteen-day maturity is an assumption, not policy.

Offline tests cover contracts, gates, cohorts, writers and saved-UI scoring. Fifteen malformed uploads fail visibly. The stress-profile run produced a valid brief; an eligible note was verified separately. HF's build succeeds, but ZeroGPU rejects this CPU-only app; the Space is paused. Dependencies use uv.

## Code Versus Model

| Plain code owns | Model owns |
| --- | --- |
| Validation, relationships, cohorts and redaction patterns | Free-text return/review classification with exact quotes |
| Canonical dropdown reasons, acceptance gates and routing | Qualitative weekly findings and suggested actions |
| Unique counts, rates, peer comparisons and coverage | Separate size-note wording, supporting IDs and confidence |
| Budgets, token arithmetic, cache, approval and exports | Nothing is automatically published |

Models never calculate rates. Reviews never enter return numerators; unlinked reviews retain Unknown size. Undelivered/RTO items are excluded. Approval changes session exports only.

## Models and Patterns

| Call | Model | Temperature |
| --- | --- | --- |
| Classification | `meta-llama/llama-4-scout` | 0.2 |
| Weekly brief | `z-ai/glm-5.3-flash` | 0.3 |
| Separate size-note call | `z-ai/glm-5.3-flash` | 0.4 |

Scout uses JSON Schema; GLM uses JSON mode. Pydantic validates each boundary. **Chaining** combines prompt, structured output and successive `RunnablePassthrough.assign` stages so writers receive code-calculated evidence. **Routing** uses `RunnableBranch` to separate fit, quality, logistics, other and review claims. Bounded `.batch()` prevents unbounded request fan-out. No evaluator/escalation loop or automatic fallback exists.

Confidence must exceed 0.75. Notes additionally require adequate own/peer samples, above-peer fit rate, at least 70% consistent direction and 80% acceptance coverage. Drafts default to zero; the brief needs no approval. Notes use current return quotes matching the majority, without hiding opposite claims from Neha's inspection tables.

## Evaluation and Cost

The independently annotated set covers 180 cases: 98 Hinglish, 65 English, 17 Hindi; 35 multi-label and 18 ambiguous. Latest raw label agreement: **127/180 (70.6%)**; clear accepted exact: **116/162**; 16 clear cases have review-held claims; 10/18 ambiguous cases are fully held. No distinct-case requests failed. Results fall short of the discovery quality target. Copied background cases do not inflate accuracy; expected labels never reach models.

Latest [captured UI evaluation](../data/realistic_other/evaluation/ui_run_20261004/evaluation_report.md): 940 comments, 610 classifier calls and one five-finding brief; **INR 4.3976928 provider usage**. Settings: cutoff 2026-10-04, 18-day groups, 14-day maturity, 30 samples, concurrency 16, INR 25 budget, **zero notes requested**. All 496 code/date controls and 68 reference-derived flags match; some counts differ. Scoring used the saved export with no model calls. The original [128/180 benchmark](../data/evaluation/evaluation_report.md), INR 1.4679552 including writing estimates, remains frozen with its historical failures.

Separate brief replay: **INR 0.3766656**, 67.8 seconds, 6,664 output tokens including 5,706 reasoning. Size-note investigation: a contradictory-evidence replay cost **INR 0.3615312** and was withheld; corrected replay cost **INR 0.0621168**, took 53.1 seconds and passed at confidence 0.82. Combined note diagnosis cost **INR 0.423648**, with zero classifier calls. This is not a new accuracy benchmark. Classifier/model/confidence gates did not change; only note evidence and wording instructions changed.

Prices per million tokens: Scout input/output USD 0.10/0.30; GLM USD 0.15/0.50; INR 96/USD. Planning volume is about 11,800 weekly classifications, combining 6,547 Other-return notes and 5,256 reviews assuming 78 weeks of history. Nominal 600/80 classification, 20,000/2,000 brief and 900/150 note tokens imply **INR 96.55/week**, about INR 5,020/year, including 50 optional notes. Actual reasoning can cost more. These are planning estimates, not guaranteed savings, invoice totals or a backfill estimate.

## What Broke

Schema braces became prompt variables; static prompt partials fixed them. Optional Postgres timestamps became `NaT`; missing-value normalization restored CSV parity. Scout routing returned 404 because endpoint capabilities differed from catalogue summaries; native JSON Schema fixed it.

The old writer's 2,000-token cap was insufficient for reasoning. Brief replay succeeded at 15,000/120 seconds. Scout stays 600/45. A later note replay exposed a separate grounding bug: the majority was too small, but the three highest-confidence pooled quotes all described oversized fit. The writer correctly withheld confidence. Notes now select current, accepted return evidence matching the majority, excluding mixed-direction records; citation gates check that exact selection. A live note then passed without lowering thresholds.

Safe diagnostics and batch/stage progress expose failures. Earlier missing exception details remain unrecoverable. The prior cohort is a date control, not realistic historical feedback.

ZeroGPU's unsupported Python 3.11 request fell back to 3.10, breaking NumPy installation. Supported 3.12.12 fixes that. HF also adds Gradio's MCP extra, requiring Pydantic <=2.12.5; the compatible pin passes all 52 tests on local/cloud-target Python without changing gates or purchasing hardware.

Startup then failed with `No @spaces.GPU function detected during startup`. The app uses remote models, not local GPU inference. The Space was paused instead of adding a fake GPU task or purchasing a plan.

## Deployment and Handoff

README, lockfile, runtime requirements, guides and discovery note are included. Credentials stay in server secrets, never Git. HF Space [raghulkrishnan/intelligence-radar](https://huggingface.co/spaces/raghulkrishnan/intelligence-radar) is paused pending eligible CPU hosting. Render Free is the recommended alternative, with cold starts and temporary state; it is not yet deployed. No working public URL is claimed. Neha owns decisions; developers own maintenance.