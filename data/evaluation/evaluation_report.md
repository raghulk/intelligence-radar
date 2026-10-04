# Single-Run Synthetic Evaluation

Model-generated reference labels are provisional, not certified human truth. Expected labels were kept outside input ZIPs and were not sent to the classifier. Background dropdown rows are excluded from model quality metrics. No classifier prompt was tuned after this run.

## Summary

| Measure | Value |
| --- | --- |
| model_cases | 180 |
| raw_label_exact | 128 |
| raw_direction_exact | 96 |
| clear_cases | 162 |
| clear_accepted_exact | 121 |
| clear_cases_with_review | 11 |
| ambiguous_cases | 18 |
| ambiguous_held_for_review | 10 |
| request_failures | 0 |
| code_cases | 1007 |
| code_route_matches | 1007 |
| cost_inr | 1.4679552 |
| brief_valid | False |
| size_note_drafts | 2 |
| size_note_pending | 0 |
| provider_usage_cost_inr | 1.2281760000000002 |
| reserved_estimate_cost_inr | 0.23977919999999997 |
| group_flag_matches | 68 |
| groups | 68 |

## Labels: Expected Versus Actual

Multi-label counts, including raw valid model labels before confidence/evidence routing.

| reason | expected | actual | correct | missed | extra | precision | recall |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fit_too_small | 17 | 18 | 14 | 3 | 4 | 0.778 | 0.824 |
| fit_too_large | 16 | 15 | 14 | 2 | 1 | 0.933 | 0.875 |
| fit_length_or_shape | 15 | 22 | 13 | 2 | 9 | 0.591 | 0.867 |
| quality_defect | 28 | 38 | 25 | 3 | 13 | 0.658 | 0.893 |
| colour_or_look_mismatch | 24 | 25 | 24 | 0 | 1 | 0.96 | 1.0 |
| fabric_feel | 24 | 10 | 10 | 14 | 0 | 1.0 | 0.417 |
| wrong_or_missing_item | 16 | 15 | 15 | 1 | 0 | 1.0 | 0.938 |
| damaged_in_transit | 15 | 17 | 15 | 0 | 2 | 0.882 | 1.0 |
| delivery_delay | 15 | 15 | 13 | 2 | 2 | 0.867 | 0.867 |
| changed_mind | 15 | 15 | 12 | 3 | 3 | 0.8 | 0.8 |
| no_fit_complaint | 12 | 31 | 12 | 0 | 19 | 0.387 | 1.0 |
| unclear | 18 | 6 | 6 | 12 | 0 | 1.0 | 0.333 |

## Routing

Partial review means the comment has both accepted and withheld claims. Request failures are separate from semantic review.

| expected_route | auto_accepted | human_review | partial_review |
| --- | --- | --- | --- |
| auto_accepted | 151 | 3 | 8 |
| human_review | 6 | 10 | 2 |

## Classification Matrix

For multi-label comments, the primary category uses fixed taxonomy order, not model claim order. Full per-label misses/extras are above.

| primary_expected | changed_mind | colour_or_look_mismatch | damaged_in_transit | delivery_delay | fabric_feel | fit_length_or_shape | fit_too_large | fit_too_small | human_review | no_fit_complaint | quality_defect | wrong_or_missing_item |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| changed_mind | 12 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| colour_or_look_mismatch | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| damaged_in_transit | 0 | 0 | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| delivery_delay | 1 | 0 | 0 | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fabric_feel | 0 | 0 | 0 | 0 | 5 | 1 | 0 | 0 | 0 | 0 | 7 | 0 |
| fit_length_or_shape | 0 | 0 | 0 | 0 | 0 | 13 | 1 | 1 | 0 | 0 | 0 | 0 |
| fit_too_large | 0 | 0 | 0 | 0 | 0 | 0 | 14 | 2 | 0 | 0 | 0 | 0 |
| fit_too_small | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 14 | 0 | 0 | 0 | 0 |
| human_review | 1 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 10 | 4 | 0 | 0 |
| no_fit_complaint | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 0 |
| quality_defect | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 0 |
| wrong_or_missing_item | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 15 |

## Language and Certainty

| language | reference_certainty | cases | exact_labels | clear_review | request_failures |
| --- | --- | --- | --- | --- | --- |
| English | ambiguous | 6 | 0 | 0 | 0 |
| English | clear | 59 | 47 | 1 | 0 |
| Hindi | ambiguous | 1 | 0 | 0 | 0 |
| Hindi | clear | 16 | 14 | 0 | 0 |
| Hinglish | ambiguous | 11 | 6 | 0 | 0 |
| Hinglish | clear | 87 | 61 | 10 | 0 |

## Examples of Label Disagreement

| case_id | language | missing_labels | extra_labels |
| --- | --- | --- | --- |
| C001 | Hinglish | ["quality_defect"] | ["fit_length_or_shape"] |
| C003 | English | ["fabric_feel"] | ["quality_defect"] |
| C004 | Hinglish | ["fabric_feel"] | ["no_fit_complaint"] |
| C005 | English | ["fit_too_small"] | ["fit_length_or_shape"] |
| C007 | English | ["fit_too_small"] | ["fit_length_or_shape"] |
| C009 | English | ["fabric_feel", "fit_too_small"] | ["fit_length_or_shape", "quality_defect"] |
| C012 | Hinglish | ["quality_defect"] | ["fit_length_or_shape"] |
| C017 | Hinglish | ["fit_too_large"] | ["fit_too_small"] |
| C023 | Hinglish | [] | ["fit_length_or_shape"] |
| C028 | Hinglish | ["fit_too_large"] | ["fit_length_or_shape", "fit_too_small"] |

## Clear References Sent to Review

These are not unreasoned reviews. The exact gate reasons are recorded below. Full claim quotes and confidence are in expected_vs_actual.csv; partial-review comments still contain accepted claims.

| case_id | actual_route | review_reasons |
| --- | --- | --- |
| C004 | partial_review | Confidence must be greater than 0.75. |
| C023 | partial_review | Confidence must be greater than 0.75. |
| C041 | partial_review | No-fit-complaint is a review-only label. |
| C056 | partial_review | Confidence must be greater than 0.75. |
| C074 | human_review | Confidence must be greater than 0.75. |
| C081 | partial_review | Confidence must be greater than 0.75. |
| C085 | partial_review | Confidence must be greater than 0.75. |
| C091 | partial_review | No-fit-complaint is a review-only label. |
| C124 | partial_review | Confidence must be greater than 0.75. |
| C132 | human_review | Confidence must be greater than 0.75. |
| C147 | human_review | No-fit-complaint is a review-only label. |

## Ambiguity Controls

| case_id | actual_labels | actual_route |
| --- | --- | --- |
| C165 | ["fit_too_small", "no_fit_complaint"] | partial_review |
| C167 | ["delivery_delay"] | auto_accepted |
| C170 | ["no_fit_complaint"] | auto_accepted |
| C173 | ["no_fit_complaint"] | auto_accepted |
| C174 | ["changed_mind"] | auto_accepted |
| C176 | ["delivery_delay", "no_fit_complaint"] | partial_review |
| C178 | ["no_fit_complaint"] | auto_accepted |
| C180 | ["no_fit_complaint"] | auto_accepted |

## Business Groups

Counts and flags use withheld labels with clear claims treated as accepted and ambiguous claims treated as review. This checks downstream effects; it is not an independent proof of the shared aggregation code.

| vendor | category | size | expected_fit_returns | actual_fit_returns | expected_flagged | actual_flagged |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic Bengaluru Stitch | kurti | M | 131 | 131 | True | True |
| Synthetic Tiruppur Loom | shirt | M | 120 | 120 | True | True |

## Calls, Cost and Writing Failures

| call_type | token_basis | calls | cost_inr |
| --- | --- | --- | --- |
| brief | reserved estimate; usage unavailable | 1 | 0.164386 |
| classification | provider usage | 180 | 1.228176 |
| size_note | reserved estimate; usage unavailable | 2 | 0.075394 |

The total combines provider-reported classification usage and reserved estimates for failed writing requests, not an invoice. All 180 classification requests produced schema-valid responses. The brief and two size-note calls failed and were visibly withheld. No approved or published notes exist. Only generic failure messages were retained, so transport/provider/parser root causes cannot be determined from this run. No retry or second paid run was made.

- brief: model request failed; output withheld.
- size_note: model request failed; output withheld.
- size_note: model request failed; output withheld.

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

Labels were generated by a separate agent, not certified by Neha. Direction exact-match distinguishes `none` from `unclear`, even where both are allowed by routing; inspect individual claims before treating every mismatch as a business error. Examples C031/C033 are stronger problems: overly long sleeves/hem were accepted as `too_small`. Feedback is concentrated in the current cohort; the previous delivery cohort is an exclusion/comparison control, not a realistic historical trend. Deterministic dropdown rows are deliberately numerous to create sample-supported groups, not to inflate model accuracy.


## Next Decision

Inspect disputed annotations, missing/extra labels, direction mismatches and clear cases sent to review before deciding on prompt changes. This small constructed set is not a production accuracy estimate.
