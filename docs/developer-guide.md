# Developer Guide

## Start from a Clean Machine

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.11+ is supported; the local verified environment uses 3.13.1 and Hugging Face metadata selects 3.11. uv can install a compatible interpreter. GitHub authentication is required while this repository is private.

```sh
git clone https://github.com/raghulk/intelligence-radar.git
cd intelligence-radar
uv sync --locked
cp .env.example .env
```

Edit the copied configuration locally and set `OPENROUTER_API_KEY`. Do not put a key in a command argument, source file, issue or chat. OpenRouter must have credit and access to the configured models. Leave `DATABASE_URL` unused for CSV mode.

```sh
uv run --locked python app.py
```

Open http://localhost:7860. To use another port:

```sh
PORT=7862 uv run --locked python app.py
```

Follow [the user guide](user-guide.md#synthetic-demo) with [the demo bundle](../data/realistic_other/inputs.zip). Loading/validation is free; generating analysis makes paid model calls. There is no need to install Docker or Postgres for this path.

## Configuration

Defaults are documented in [.env.example](../.env.example). Restart the app after changing them.

| Setting | Purpose / default |
| --- | --- |
| `OPENROUTER_API_KEY` | Server-side provider credential; required for OpenRouter |
| `BASE_URL` | `https://openrouter.ai/api/v1` |
| `CLASSIFIER_MODEL` | `meta-llama/llama-4-scout` |
| `WRITER_MODEL` | `z-ai/glm-5.3-flash`; must differ from classifier |
| `WRITER_MAX_TOKENS` | 15000; shared brief/note ceiling, including reasoning |
| `WRITER_TIMEOUT_SECONDS` | 120; no automatic retries |
| `EXCHANGE_RATE` | 96 INR/USD |
| `CLASSIFIER_INPUT_PRICE`, `CLASSIFIER_OUTPUT_PRICE` | USD 0.10/0.30 per million tokens |
| `WRITER_INPUT_PRICE`, `WRITER_OUTPUT_PRICE` | USD 0.15/0.50 per million tokens |
| `DATABASE_URL` | Optional read-only Postgres connection; treat as a secret |
| `PORT` | 7860 |
| `APP_USERNAME`, `APP_PASSWORD` | Set both to enable Gradio login; neither is committed |

`LLM_API_KEY`, when explicitly set, overrides the provider-specific key. Otherwise the endpoint determines `OPENROUTER_API_KEY`, `HF_TOKEN` or `OPENAI_API_KEY`. Do not confuse these credentials. Switching models also requires reviewing capabilities and prices; OpenRouter endpoints must support the requested structured-output parameters.

UI defaults: 28-day delivery groups, 14-day maturity, 30 return samples, INR 25 estimated budget, concurrency 4 and zero size-note calls. Classification temperature is 0.2; brief 0.3; size note 0.4. Scout uses JSON Schema, GLM JSON mode, and every parsed result passes Pydantic validation.

## Data Contract

[schema.sql](../schema.sql) and [data.py](../radar/data.py) own the same five-table contract. The CSV template in the app supplies headers. A ZIP must contain exactly those five CSVs at its root, with no answer key or enclosing folder; uploads are limited to 25 MB compressed / 50 MB expanded.

- `vendors`: unique vendor ID and name.
- `products`: unique SKU, existing vendor ID and category.
- `order_items`: unique physical-item ID, existing SKU, size and optional delivery timestamp.
- `returns`: unique return ID, existing physical-item ID, request timestamp, original reason and optional comment. At most one return per physical item.
- `reviews`: unique review ID, existing SKU, optional physical-item link, creation timestamp, integer rating 1-5 and nonempty comment. A linked item must have the same SKU and valid delivery chronology.

Dates are ISO timestamps interpreted in UTC. Undelivered/RTO items have no delivery timestamp and never enter delivered denominators. Unlinked reviews have Unknown size and cannot be assigned to a size-specific return rate. An empty reviews table is valid, but its CSV/table and headers remain required. No orders/payment table is used.

The report cutoff is exclusive. Two adjacent delivery cohorts end the selected maturity period before it. Feedback must predate the cutoff; reviews are evidence, not return events. Rates deduplicate physical return IDs. Multi-issue claim counts must not be summed as unique returns.

Expected-result files are evaluation-only. Never put them inside the input ZIP. Synthetic scenarios include deliberate ambiguity, inconsistent directions, multiple issues, Hinglish/Hindi, dates and invalid uploads.

## Optional Postgres

Use a separate application database. An administrator applies [schema.sql](../schema.sql), loads the five tables and grants a dedicated application role only `CONNECT`, schema `USAGE` and table `SELECT`. Set its connection as `DATABASE_URL`; no administrator credential belongs in the app. The adapter opens read-only repeatable-read transactions and uses bounded queries.

For example, after an administrator creates the database and login role:

```sql
GRANT CONNECT ON DATABASE intelligence_radar TO intelligence_radar_reader;
GRANT USAGE ON SCHEMA public TO intelligence_radar_reader;
GRANT SELECT ON vendors, products, order_items, returns, reviews TO intelligence_radar_reader;
ALTER ROLE intelligence_radar_reader SET default_transaction_read_only = on;
```

Run schema/table grants while connected to that database. Set passwords securely through your database tooling, not in committed SQL.

The author's local fixture uses Postgres 16 in `trading-agent-postgres-1`, database `intelligence_radar_other`, with matching CSV rows. That container is not a prerequisite on another machine. Benchmark loading helpers target this existing local infrastructure, refuse to replace databases, and are not a portable Postgres provisioning system.

## Architecture and Ownership

| Module | Responsibility |
| --- | --- |
| [app.py](../app.py) | Gradio controls, session state, readable tables, approval and exports |
| [models.py](../radar/models.py) | Typed contracts, taxonomy and claim routing rules |
| [data.py](../radar/data.py) | CSV/Postgres adapters, validation, redaction and cohort preparation |
| [analysis.py](../radar/analysis.py) | Deduplicated metrics, flags, note evidence and eligibility |
| [pipeline.py](../radar/pipeline.py) | LCEL orchestration, prompts, concurrency, cache, budget and diagnostics |
| [benchmark.py](../benchmark.py) | Fixture creation, evaluation and writer-only replay |
| [tests/test_radar.py](../tests/test_radar.py) | Offline contracts, failures and regression checks |

The backend does not import Gradio. Both data adapters return the same validated `Dataset`. LCEL chaining composes classification, aggregation and writers; `RunnableBranch` routes accepted claims into fit, quality, logistics, other or review. Models interpret text and propose wording; code owns arithmetic and acceptance rules.

Confidence must be strictly greater than 0.75. Quotes must exactly match sanitized input and IDs must be supported. A size-note flag additionally needs minimum return/peer samples, at least 80% acceptance coverage, fit rate above 1.5 times peers, and at least 70% direction consistency. Notes use accepted, current-cohort return quotes consistent with that majority; mixed-direction records and opposite-direction, old or review quotes cannot ground the note. Other feedback remains visible.

## Tests and Evaluation

```sh
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked python benchmark.py validate --data-dir data/realistic_other
```

These commands do not call paid models. The baseline [evaluation report](../data/evaluation/evaluation_report.md) and [saved synthetic run](../data/evaluation/actual_run.json) are preserved. To recompute its scores without model calls:

```sh
uv run --locked python benchmark.py score
```

The original 180 distinct cases have raw exact-label agreement 128/180. This is not certified production accuracy. The 55%-Other profile adds 511 copied model-background cases and needs about 691 fresh classifier requests. Copied cases are excluded from distinct-case accuracy. It has not been scored as a new live run.

To evaluate it once, deliberately authorize provider spending, then run:

```sh
uv run --locked python benchmark.py evaluate --data-dir data/realistic_other
```

This is a **paid** full pipeline, with benchmark options of report cutoff 2026-10-04, 28-day groups, 14-day maturity, 30 samples, concurrency 6, INR 15 estimated budget and two notes. It refuses an existing result instead of silently overwriting it. Do not rebuild the baseline inputs or replace its result to make metrics look better.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Upload rejected | Fix the reported schema, relationship, rating or chronology error; no model call has occurred |
| Missing provider key / 401 | Configure the server secret and restart; do not paste secrets into error reports |
| Scout routing 404 | Verify an endpoint supports native JSON Schema; do not silently change models |
| Progress continues for minutes | Wait for reading, brief and optional note stages; results appear at the end |
| Feedback held for review | Inspect the reason and quote; do not lower confidence solely to increase coverage |
| No size notes | Draft limit defaults to 0; also check samples, coverage, rate/direction gates and remaining budget |
| Note withheld | Check confidence, supported current-return IDs and its specific reason |
| Writer `LengthFinishReasonError` | Check output/reasoning usage and configured ceiling; replay writer only |
| Writer timeout | Check safe timing/HTTP diagnostics and provider status; no automatic retry is made |
| Results lost after restart | Sessions are temporary; use downloaded brief and diagnostic reports |

Export the diagnostic JSON from the support section. It contains classifications, metrics, source evidence, costs and safe writer diagnostics, but not the reusable cache. Full source text in the report can still be sensitive: keep real-client exports private.

Replay a saved run's first eligible size note, or its brief, without reclassifying:

```sh
uv run --locked python benchmark.py diagnose-writer --writer-kind size_note --run-report data/evaluation/actual_run.json --budget-inr 1
uv run --locked python benchmark.py diagnose-writer --writer-kind brief --run-report path/to/private-export.json --budget-inr 1
```

Each command makes **one paid writer request**, not a full rerun. Replace the second path with your local export. Reports are timestamped under `data/evaluation/writer_diagnostics`; original runs are not altered. A size-note replay uses the same evidence selector and confidence/citation checks as the pipeline. It is a diagnostic, not an automatic UI update or approval. Missing historical exceptions cannot be recovered retrospectively.

The verified size-note replay used current matching quotes, confidence 0.82, 53.127 seconds, 1,007 input / 992 output tokens and INR 0.0621168. A preceding replay correctly withheld contradictory evidence at confidence 0.6. See [the build note](build-note.md) for the actual failure and cost caveats.

## Hugging Face Deployment

Deployment is not yet complete. Required from the owner:

1. A Hugging Face account or organization with permission to create a Gradio Space, and the desired Space owner/name, such as `<owner>/intelligence-radar`.
2. An eligible compute plan. Current [Spaces documentation](https://huggingface.co/docs/hub/spaces-overview) requires PRO for personal Gradio/Docker creation or an organization plan; eligible free personal accounts have a limited ZeroGPU exception. Do not assume CPU Basic alone removes account eligibility requirements. This app uses remote models and does not need a GPU.
3. A visibility choice and reviewer access. Public demos must use synthetic data. Private Spaces require reviewer collaboration; protected access is plan-dependent.
4. `OPENROUTER_API_KEY` entered directly in the Space's **Settings > Secrets**, with provider credit. Use a separate limited-credit deployment key where possible. For a publicly reachable demo, also set both `APP_USERNAME` and `APP_PASSWORD` as secrets and share access securely with reviewers.

Never send passwords or tokens through chat. For automated publishing, authenticate locally with a fine-grained Hugging Face write token scoped to the Space; keep it out of code and Git remotes. The local OpenRouter configuration is not automatically copied to the cloud.

Create a **Gradio** Space with CPU Basic if the account is eligible. Push the repository's committed contents to the Space repository. The root [README](../README.md) selects Gradio 6.29.1, Python 3.11 and [app.py](../app.py); [requirements.txt](../requirements.txt) supplies runtime dependencies. GitHub pushes do not automatically deploy to Hugging Face: publishing/synchronization is a separate step.

Use CSV mode. Do not copy `DATABASE_URL` or point the cloud app at your Mac. Hugging Face permits outbound ports 80/443/8080, not Postgres 5432; the existing psycopg adapter cannot use a database's HTTP API. The default disk and Gradio sessions are temporary.

Add non-sensitive model settings, prices, exchange rate and writer limits as Space **Variables** using the defaults above. Leave `PORT` unset or 7860. Regenerate runtime requirements after dependency changes:

```sh
uv export --locked --no-dev --no-emit-project --no-hashes --output-file requirements.txt
```

Before sharing a URL, verify startup/build logs, login, CSV loading, a small paid classification/brief run, an eligible note, a visible rejection/failure case and exports. Check the URL on another device/account with the intended reviewer access. Record the tested URL in the README only after verification.

## Limits and Operating Responsibility

Neha owns business interpretation, sample checking and approval. Developers own provider credit/rate limits, schema compatibility, configuration and incidents. Validate a randomly sampled real cohort with Neha before relying on labels for vendor action; the discovery quality target has not been met by the provisional benchmark.

There is no automatic publishing, product-page integration, persistent approval log, durable job queue, complete anonymization, account-wide spending control or proven return reduction. Regex masking is a secondary safeguard, not permission to upload PII. Confidence is model output, not measured accuracy. The full 55%-Other pipeline and a deployed public URL remain unverified.