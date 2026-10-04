---
title: Intelligence Radar
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.29.1
python_version: '3.12.12'
app_file: app.py
pinned: false
---

# Intelligence Radar

Intelligence Radar helps **Neha, Category Head at Dhaga & Co.**, find vendor/category/size groups behind fit-related returns hidden in "Other." It turns return comments and supporting reviews into a weekly brief, traceable classifications and optional product-page size-note drafts.

The client brief reports 31% returns and 44% of return reasons marked Other. This MVP tests whether existing feedback can support better vendor-fit decisions. It does not prove that recommendations reduce returns.

## For Neha

1. Upload the five-table CSV bundle and select **Load data**.
2. Check the delivery dates and select **Generate weekly brief**.
3. Read suggested actions and customer quotes in **Weekly brief**.
4. Inspect every in-window return claim in **Vendor information**, including non-fit and held claims. Use **Source feedback** for reviews and **Needs review** for unresolved feedback.
5. Download the brief. Optionally enable size-note drafts before running, then review and approve eligible wording. Approval changes the report only; nothing is published.

See [Neha's user guide](docs/user-guide.md) for a complete demo, metric definitions and what to do when results are missing.

## Developer Quickstart

Prerequisites: Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), Python 3.11+ and an OpenRouter key with model access and credit. Postgres is optional.

```sh
git clone https://github.com/raghulk/intelligence-radar.git
cd intelligence-radar
uv sync --locked
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in your local environment file, then start:

```sh
uv run --locked python app.py
```

Open **http://localhost:7860**. If occupied, use `PORT=7862 uv run --locked python app.py`. Never commit credentials. See [developer setup, architecture and deployment](docs/developer-guide.md).

## Inputs and Demo

Upload [the synthetic demo bundle](data/realistic_other/inputs.zip). It contains exactly five root CSVs: vendors, products, order_items, returns and reviews. Column contracts are in [schema.sql](schema.sql); the app also downloads an empty CSV template. Each order-item row is one physical item. Reviews support findings but never count as returns. The app can alternatively read Postgres using a read-only `DATABASE_URL`.

To reproduce the latest measured run, set report date **2026-10-04**, delivery groups **18 days** and waiting period **14 days**. The UI defaults to 28-day groups; waiting time is an assumption, not a confirmed client policy. Inputs are synthetic: 5,000 physical items, 1,090 returns and 97 reviews; **600 returns are Other (55.05%)**. This stress profile exceeds the client's stated 44%.

The [separate expected results](data/realistic_other/expected_results.csv) must never be uploaded as input. The captured 18-day run made **610 classifier requests and one brief call**; the default 28-day profile needs about 691 classifier requests. Allow several minutes and watch progress. Both measured runs are retained separately.

## Models and Safety

| Task | Model | Temperature |
| --- | --- | --- |
| Free-text classification | `meta-llama/llama-4-scout` | 0.2 |
| Weekly brief | `z-ai/glm-5.3-flash` | 0.3 |
| Separate size-note draft | `z-ai/glm-5.3-flash` | 0.4 |

LangChain chaining and conditional routing are deliberate workflow patterns. Pydantic validates each model boundary; code calculates rates, checks citations and controls budgets. Canonical dropdown reasons are preserved without model calls or invented confidence. Model confidence must be **strictly greater than 0.75**; low scores, invalid output and unsupported quotes are withheld for review.

Size notes require adequate samples, coverage, above-peer rates and consistent direction. Their quotes come from current returns supporting that majority direction; all opposing feedback remains available in the inspection tables. Drafts default to zero and never block the brief.

Writers allow 15,000 output tokens, including reasoning, and 120 seconds. Classifier limits remain 600 tokens/45 seconds. There is no automatic model fallback or retry loop. Costs use provider token usage where available, otherwise labelled estimates, with **INR 96/USD**. Run budgets are not account-wide spending limits.

Only use anonymized client data. Automatic masking catches some email, phone and labelled-address patterns; it is **not complete anonymization**. Use synthetic data for a public demo, and restrict access to prevent unapproved spending.

## When Something Goes Wrong

- Bad uploads fail validation before any model call; fix the indicated columns, IDs, dates or relationships.
- Low coverage and small samples remain visible but do not qualify for size notes.
- Rate limits, budget exhaustion and model/schema failures appear in completion warnings and the review queue.
- A failed writer does not erase classifications or vendor tables. Safe diagnostics are included in the downloadable report.
- Sessions are temporary. Download reports before refreshing or restarting; approval is not saved to a database.

See [troubleshooting and writer-only replay](docs/developer-guide.md#troubleshooting) rather than rerunning all classification to diagnose a writer.

## Verification and Submission

```sh
uv run --locked pytest -q
uv run --locked ruff check .
```

Offline tests use injected model runnables, not paid calls. The [latest evaluation](data/realistic_other/evaluation/ui_run_20261004/evaluation_report.md) reports **127/180 exact raw labels (70.6%)**, **116/162 clear accepted exact labels**, 16 clear cases with review-held claims and zero distinct-case request failures. All 496 code/date controls and 68 reference-derived group flags match. These are provisional synthetic results, not certified production accuracy.

The run considered **940 comments**, with 921 containing usable labels and 83 containing review-held claims; those sets overlap. It produced a valid five-finding brief at **INR 4.3976928 provider usage**. Its settings were 18-day groups, 14-day maturity, 30 minimum samples, concurrency 16, INR 25 budget and **zero size-note drafts**. Two flagged groups were deferred because notes were disabled, not because a writer failed. Scoring reused the saved export without model calls.

The [original evaluation](data/evaluation/evaluation_report.md), with 128/180 raw labels and historical writer failures, remains unchanged. Copied model-background cases do not inflate either distinct-case score.

Separate live replays verified a five-finding brief and, after correcting conflicting quote selection, an eligible size note: **confidence 0.82, INR 0.0621168**, with no reclassification. These are not a new benchmark.

The repository includes the [discovery note](docs/discovery-note.md), [two-page-target build note](docs/build-note.md), developer guide and user guide. Public Space [raghulkrishnan/intelligence-radar](https://huggingface.co/spaces/raghulkrishnan/intelligence-radar) has been created on free ZeroGPU; deployment verification is in progress. See the [deployment checklist](docs/developer-guide.md#hugging-face-deployment) for access, secrets and operating safeguards.