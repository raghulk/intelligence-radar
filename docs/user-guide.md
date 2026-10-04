# User Guide: Neha's Fit-Return Review

## What This Product Does

Intelligence Radar helps you decide which vendor, category and size to investigate when return comments mention fit. It reads free-text return reasons, uses product reviews as supporting evidence, and presents a short weekly brief with traceable customer quotes.

It does not determine that a vendor caused a return, change a size chart or publish customer-facing text. Use the findings to check measurements, compare comments and agree corrective action with the vendor or listing team.

## Before You Start

Ask the support team for an anonymized export of vendors, products, physical delivered items, returns and reviews in the five-file ZIP format. The app's **CSV template** provides the required headers. Reviews may be empty, but the reviews file is still required.

For a demonstration, use [the synthetic bundle](../data/realistic_other/inputs.zip), not real customer data. Do not upload [the expected-results answer key](../data/realistic_other/expected_results.csv). Automatic masking catches only some identifying patterns; input must already be safe to share with the model provider.

## Synthetic Demo

1. Open the app and choose **Upload data**.
2. Upload the synthetic bundle, then select **Load data**. Wait for "Data validated. Ready to run."
3. To reproduce the latest measured run, set **Report date (UTC)** to `2026-10-04`, **Days in each delivery group** to `18`, and **Days to wait for returns** to `14`. The UI's default group length is 28.
4. Check **Delivery dates included**: latest 2 September-19 September 2026; previous 15 August-1 September. Deliveries on or after 20 September are excluded.
5. Leave the minimum at 30 and spending limit at INR 25. For optional notes, expand **Optional: recommendations and spending limit** and set **Size-note drafts per run** to `2`. Leaving it at `0` generates the brief only.
6. Select **Generate weekly brief**. Reading progress, brief writing and optional note stages can take several minutes. The measured 18-day run made 610 feedback requests; 28-day groups need about 691, plus writers. Results appear after processing finishes.

The captured evaluation used concurrency 16 and zero requested drafts. Enabling two drafts is a separate optional workflow, not an exact replay of that evaluation. Setting drafts to 0 makes no size-note request; a deferred-group warning does not mean generation failed.

The synthetic profile has 5,000 physical items, 1,090 returns and 97 reviews. Its 55.05% Other share is a stress scenario, not a revised client statistic; the client brief states 44%.

## Read the Results

**Weekly brief:** up to five findings with suggested actions and supporting quotes. Download the category brief as text for your weekly review. A brief needs no approval and is a summary, not the complete dataset.

**Vendor information:** select a vendor to inspect fit metrics, all issue counts and every in-window return classification claim. Non-fit issues and claims held for review stay visible even if the brief writer fails. Check the original reason, comment, supporting quote, confidence and label source. Dropdown labels are existing structured reasons, not new model judgements.

**Source feedback:** includes return and review comments. Filter by issue group or search for a relevant phrase or record. Reviews support findings but cannot increase a return rate.

**Needs review:** inspect comments whose evidence did not match, confidence was low, meaning was unclear or the request failed. A comment can contain both an accepted issue and another issue needing review. This MVP does not save manual reclassifications; escalate corrections to the support team.

**Input data:** check table row counts to confirm you loaded the intended export. Raw row counts are not the same as the items included in the delivery windows.

## Understand the Numbers

- **Fit-return rate:** unique accepted fit-related returns divided by delivered physical items in that vendor/category/size delivery group. It is not a percentage of reviews or of all returns.
- **Latest versus previous:** compares delivery dates, not purchase dates. The newest deliveries wait long enough to allow returns to appear. Fourteen days is a demo assumption, not a confirmed policy.
- **Change in percentage points:** 10% to 15% is a 5-point increase, not a 5% relative increase.
- **Coverage:** how many return records have at least one usable label. High coverage does not prove those labels are correct.
- **Peer fit rate:** the same category and size at other vendors, not all products at the company.
- **Confidence:** the model's score for its claim. It is not measured accuracy. Scores at or below 75% are held for review.
- **Issue counts:** a return with multiple issues can appear more than once. Do not add those counts to calculate unique total returns.

Undelivered/RTO items, deliveries outside the selected windows and feedback after the report cutoff do not enter the relevant results. Reviews without a delivered-item link have Unknown size.

## Review a Size Note

A draft is optional shopping guidance, separate from the weekly brief. A group must have enough returns and peer deliveries, adequate usable-label coverage, a fit rate above peers and a consistent size direction. The note cites current return quotes supporting that majority signal. Opposing comments remain visible and should still be checked before any business action.

1. Enable one or more drafts **before** generating analysis.
2. Open **Size-note drafts** and check status. Only **Pending approval** drafts can be approved; withheld drafts show their reason.
3. Choose the draft, inspect its cited comments and check the proposed wording with the listing team. Keep any edits within 300 characters.
4. Select **Mark draft approved (report only)**.
5. Download the updated diagnostic report from the support section before leaving the session.

Approval only records your decision in the current session/report. It does not publish anything or change a database. The listing team must separately validate and apply any wording. Do not add invented measurements, a guaranteed fit or a size-up/down instruction unsupported by measured sizing data.

## Missing or Failed Results

| What you see | What it means / next step |
| --- | --- |
| Data validation error | Correct the export with support before running again |
| Insufficient data | The group is visible, but does not meet the configured sample rule |
| Low coverage | Too many return labels are unresolved; inspect Needs review |
| No flag | The peer-rate or consistency conditions are not met; not proof that fit is good |
| No drafts | Draft limit may be 0, no group may qualify, or the spending limit may stop a writer |
| Withheld note | Its confidence, evidence or generation did not pass checks; do not publish it |
| Brief unavailable | Classifications and vendor tables still work; download diagnostics and ask support to retry the writer only |
| Spending warning | Some requests were not made; remaining feedback needs review |

Do not reduce sample or confidence requirements solely to obtain a draft. Budget is an estimated limit for this analysis, not a guarantee about the provider's invoice. Closing or refreshing the app can lose session results; download the brief and report first.

## Current Evidence and Limits

The data is synthetic. The [latest 55%-Other evaluation](../data/realistic_other/evaluation/ui_run_20261004/evaluation_report.md) matched 127 of 180 raw label sets exactly (70.6%), with 16 clear-reference cases containing review-held claims. It considered 940 comments and produced a valid brief at INR 4.398. Notes were disabled in that run; an eligible live note was verified separately after fixing quote selection. Results are not certified for unsupervised vendor decisions.

The earlier 128/180 benchmark remains available for comparison; neither score is a production accuracy guarantee. A public Hugging Face Space needs no reviewer invitation. If app login is enabled to protect provider spending, reviewers also need the app credentials shared securely by the owner.

Before real use, review a random sample with developers, agree the return waiting period and check whether flagged groups lead to useful vendor actions. Return reduction, production integrations and persistent review history are not established by this MVP.