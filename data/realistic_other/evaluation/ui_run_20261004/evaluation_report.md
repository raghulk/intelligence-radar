# Single-Run Synthetic Evaluation

Model-generated reference labels are provisional, not certified human truth. Expected labels were kept outside input ZIPs and were not sent to the classifier. Copied background cases and dropdown rows are excluded from distinct model quality metrics; out-of-window anchors are excluded rather than counted as classifier failures. No classifier prompt was tuned after this run.

## Run Settings

| Setting | Value |
| --- | --- |
| as_of | 2026-10-04 |
| period_days | 18 |
| maturity_days | 14 |
| min_samples | 30 |
| relative_rate | 1.5 |
| direction_share | 0.7 |
| concurrency | 16 |
| budget_inr | 25.0 |
| max_notes | 0 |

## Summary

| Measure | Value |
| --- | --- |
| model_cases | 180 |
| model_cases_out_of_window | 0 |
| raw_label_exact | 127 |
| raw_direction_exact | 87 |
| clear_cases | 162 |
| clear_accepted_exact | 116 |
| clear_cases_with_review | 16 |
| ambiguous_cases | 18 |
| ambiguous_held_for_review | 10 |
| request_failures | 0 |
| code_cases | 496 |
| code_route_matches | 496 |
| cost_inr | 4.3976928 |
| brief_valid | True |
| size_note_drafts | 0 |
| size_note_pending | 0 |
| provider_usage_cost_inr | 4.3976928 |
| reserved_estimate_cost_inr | 0.0 |
| group_flag_matches | 68 |
| groups | 68 |

## Labels: Expected Versus Actual

Multi-label counts, including raw valid model labels before confidence/evidence routing.

| reason | expected | actual | correct | missed | extra | precision | recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fit_too_small | 17 | 16 | 14 | 3 | 2 | 0.875 | 0.824 |
| fit_too_large | 16 | 16 | 15 | 1 | 1 | 0.938 | 0.938 |
| fit_length_or_shape | 15 | 23 | 13 | 2 | 10 | 0.565 | 0.867 |
| quality_defect | 28 | 39 | 25 | 3 | 14 | 0.641 | 0.893 |
| colour_or_look_mismatch | 24 | 26 | 24 | 0 | 2 | 0.923 | 1.0 |
| fabric_feel | 24 | 11 | 11 | 13 | 0 | 1.0 | 0.458 |
| wrong_or_missing_item | 16 | 16 | 16 | 0 | 0 | 1.0 | 1.0 |
| damaged_in_transit | 15 | 16 | 15 | 0 | 1 | 0.938 | 1.0 |
| delivery_delay | 15 | 15 | 13 | 2 | 2 | 0.867 | 0.867 |
| changed_mind | 15 | 13 | 11 | 4 | 2 | 0.846 | 0.733 |
| no_fit_complaint | 12 | 29 | 12 | 0 | 17 | 0.414 | 1.0 |
| unclear | 18 | 10 | 9 | 9 | 1 | 0.9 | 0.5 |

## Routing

Partial review means the comment has both accepted and withheld claims. Request failures are separate from semantic review.

| expected_route | auto_accepted | human_review | partial_review |
| --- | --- | --- | --- |
| auto_accepted | 146 | 3 | 13 |
| human_review | 7 | 10 | 1 |

## Classification Matrix

For multi-label comments, the primary category uses fixed taxonomy order, not model claim order. Full per-label misses/extras are above.

| primary_expected | changed_mind | colour_or_look_mismatch | damaged_in_transit | delivery_delay | fabric_feel | fit_length_or_shape | fit_too_large | fit_too_small | human_review | no_fit_complaint | quality_defect | wrong_or_missing_item |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| changed_mind | 11 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| colour_or_look_mismatch | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| damaged_in_transit | 0 | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| delivery_delay | 1 | 0 | 0 | 12 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| fabric_feel | 0 | 0 | 0 | 0 | 4 | 1 | 0 | 0 | 0 | 0 | 8 | 0 |
| fit_length_or_shape | 0 | 0 | 0 | 0 | 0 | 13 | 1 | 1 | 0 | 0 | 0 | 0 |
| fit_too_large | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 1 | 0 | 0 | 0 | 0 |
| fit_too_small | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 14 | 0 | 0 | 0 | 0 |
| human_review | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 10 | 5 | 0 | 0 |
| no_fit_complaint | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 0 |
| quality_defect | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 |
| wrong_or_missing_item | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 |

## Language and Certainty

| language | reference_certainty | cases | exact_labels | clear_review | request_failures |
| --- | --- | --- | --- | --- | --- |
| English | ambiguous | 6 | 1 | 0 | 0 |
| English | clear | 59 | 46 | 4 | 0 |
| Hindi | ambiguous | 1 | 0 | 0 | 0 |
| Hindi | clear | 16 | 14 | 0 | 0 |
| Hinglish | ambiguous | 11 | 8 | 0 | 0 |
| Hinglish | clear | 87 | 58 | 12 | 0 |

## Examples of Label Disagreement

| case_id | language | missing_labels | extra_labels |
| --- | --- | --- | --- |
| C001 | Hinglish | ["quality_defect"] | ["fit_length_or_shape"] |
| C003 | English | ["fabric_feel"] | ["quality_defect"] |
| C005 | English | ["fit_too_small"] | ["fit_length_or_shape"] |
| C007 | English | ["fit_too_small"] | ["fit_length_or_shape"] |
| C008 | Hinglish | [] | ["fit_length_or_shape"] |
| C009 | English | ["fit_too_small"] | ["fit_length_or_shape"] |
| C012 | Hinglish | ["quality_defect"] | ["fit_length_or_shape"] |
| C017 | Hinglish | ["fit_too_large"] | ["fit_too_small"] |
| C023 | Hinglish | [] | ["fit_length_or_shape"] |
| C025 | Hinglish | ["fabric_feel"] | ["quality_defect"] |

## Clear References Sent to Review

These are not unreasoned reviews. The exact gate reasons are recorded below. Full claim quotes and confidence are in expected_vs_actual.csv; partial-review comments still contain accepted claims.

| case_id | actual_route | review_reasons |
| --- | --- | --- |
| C001 | partial_review | Confidence must be greater than 0.75. |
| C023 | partial_review | Confidence must be greater than 0.75. |
| C025 | partial_review | Confidence must be greater than 0.75. |
| C028 | partial_review | Confidence must be greater than 0.75. |
| C029 | partial_review | Confidence must be greater than 0.75. |
| C033 | partial_review | Evidence quote does not match source text. |
| C041 | partial_review | No-fit-complaint is a review-only label. |
| C045 | partial_review | No-fit-complaint is a review-only label. |
| C056 | partial_review | Confidence must be greater than 0.75. |
| C074 | human_review | Confidence must be greater than 0.75. |
| C085 | partial_review | Confidence must be greater than 0.75. |
| C091 | partial_review | No-fit-complaint is a review-only label. |
| C102 | partial_review | Confidence must be greater than 0.75. |
| C124 | partial_review | Confidence must be greater than 0.75. |
| C129 | human_review | Confidence must be greater than 0.75. |
| C147 | human_review | No-fit-complaint is a review-only label. |

## Ambiguity Controls

| case_id | actual_labels | actual_route |
| --- | --- | --- |
| C167 | ["delivery_delay"] | auto_accepted |
| C170 | ["no_fit_complaint"] | auto_accepted |
| C171 | ["no_fit_complaint"] | auto_accepted |
| C173 | ["no_fit_complaint"] | auto_accepted |
| C174 | ["changed_mind"] | auto_accepted |
| C176 | ["delivery_delay", "no_fit_complaint"] | partial_review |
| C178 | ["no_fit_complaint"] | auto_accepted |
| C180 | ["no_fit_complaint"] | auto_accepted |

## Business Groups

Counts and flags use withheld labels with clear claims treated as accepted and ambiguous claims treated as review. This checks downstream effects; it is not an independent proof of the shared aggregation code.

| vendor | category | size | expected_fit_returns | actual_fit_returns | expected_flagged | actual_flagged |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic Bengaluru Stitch | kurti | M | 73 | 71 | True | True |
| Synthetic Tiruppur Loom | shirt | M | 86 | 86 | True | True |

## Calls, Cost and Writing Failures

| call_type | token_basis | calls | cost_inr |
| --- | --- | --- | --- |
| brief | provider usage | 1 | 0.261619 |
| classification | provider usage | 610 | 4.136074 |

Cost combines provider usage where available with labelled reservations otherwise; it is not an invoice. Brief valid: True. Size-note drafts: 0; pending approval: 0. Configured maximum note calls: 0. Zero requested drafts are disabled, not failed. No output is automatically published. Safe writer diagnostics remain in the saved run; older generic failures cannot be retrospectively diagnosed. Scoring makes no model calls.

- Size-note limit reached: 2 eligible groups deferred.

## Malformed Inputs

Every invalid ZIP was checked both at the input adapter and at the UI boundary. None was inserted into Postgres.

| case_id | expected_error_contains | actual_error | passed |
| --- | --- | --- | --- |
| duplicate_id | IDs must be nonempty and unique | ValueError: vendors: IDs must be nonempty and unique. | True |
| missing_column | missing columns category | ValueError: products: missing columns category. | True |
| broken_foreign_key | missing products | ValueError: reviews.sku: reference to a missing products row. | True |
| invalid_date | valid ISO timestamps | ValueError: order_items.delivered_at: use valid ISO timestamps. | True |
| invalid_rating | integer from 1 to 5 | ValueError: reviews.rating: expected an integer from 1 to 5. | True |
| fractional_rating | integer from 1 to 5 | ValueError: reviews.rating: expected an integer from 1 to 5. | True |
| empty_review | empty values | ValueError: reviews.text: empty values are not allowed. | True |
| undelivered_return | delivered before the return | ValueError: returns: items must have been delivered before the return. | True |
| return_before_delivery | delivered before the return | ValueError: returns: items must have been delivered before the return. | True |
| duplicate_physical_return | one return per physical | ValueError: returns: only one return per physical order item is supported. | True |
| review_wrong_item | linked item must match SKU | ValueError: reviews: linked item must match SKU and precede the review. | True |
| review_before_delivery | precede the review | ValueError: reviews: linked item must match SKU and precede the review. | True |
| empty_size | empty values | ValueError: order_items.size: empty values are not allowed. | True |
| answer_key_leak | five named CSV files | ValueError: ZIP must contain exactly the five named CSV files at its root. | True |
| not_a_zip | BadZipFile | BadZipFile: File is not a zip file | True |

## Limits

Labels were generated by a separate agent, not certified by Neha. Direction exact-match distinguishes `none` from `unclear`, even where both are allowed by routing; inspect individual claims before treating every mismatch as a business error. Repeated synthetic background comments and constructed delivery cohorts are controls, not independent examples or realistic historical trends. Dropdown rows and copied model-background cases never inflate distinct-case accuracy. Results apply to the recorded options and in-window cases, not an assumed 28-day benchmark.


## Next Decision

Inspect disputed annotations, missing/extra labels, direction mismatches and clear cases sent to review before deciding on prompt changes. This small constructed set is not a production accuracy estimate.
