---
title: Intelligence Radar
colorFrom: green
colorTo: gray
sdk: gradio
sdk_version: 6.29.1
python_version: '3.11'
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

For the bundled demo, set report date **2026-10-04**, delivery groups **28 days** and waiting period **14 days**. The waiting period is an assumption, not a confirmed client policy. Inputs are synthetic: 5,000 physical items, 1,090 returns and 97 reviews; **600 returns are Other (55.05%)**. This stress profile exceeds the client's stated 44%.

The [separate expected results](data/realistic_other/expected_results.csv) must never be uploaded as input. A fresh run makes about **691 classifier requests** plus writers, so allow several minutes and watch progress. This profile has not yet been evaluated end to end; the original benchmark remains frozen.

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

Offline tests use injected model runnables, not paid calls. The [original evaluation](data/evaluation/evaluation_report.md) reports **128/180 exact raw labels (71.1%)**, including English, Hinglish and Hindi cases; this is provisional synthetic evidence, not production accuracy. Its historical writer failures remain recorded.

Separate live replays verified a five-finding brief and, after correcting conflicting quote selection, an eligible size note: **confidence 0.82, INR 0.0621168**, with no reclassification. These are not a new benchmark.

The repository includes the [discovery note](docs/discovery-note.md), [two-page-target build note](docs/build-note.md), developer guide and user guide. **Hugging Face deployment is pending; there is no verified public URL yet.** The [deployment checklist](docs/developer-guide.md#hugging-face-deployment) lists account eligibility, access and secrets required to complete that deliverable.