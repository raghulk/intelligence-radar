import pandas as pd
import pytest
from pydantic import ValidationError

from radar.analysis import Options, aggregate
from radar.data import prepare, redact, validate_tables
from radar.models import Claim, route_claim


def make_claim(confidence=0.9, **values):
    return Claim.model_validate(
        {
            "reason": "fit_too_small",
            "size_direction": "too_small",
            "evidence_quote": "size chhota hai",
            "confidence": confidence,
            **values,
        }
    )


@pytest.mark.parametrize(
    "confidence,route", [(0.74, "human_review"), (0.75, "human_review"), (0.76, "fit")]
)
def test_strict_confidence_gate(confidence, route):
    assert route_claim(make_claim(confidence), "size chhota hai", "return")[0] == route


@pytest.mark.parametrize("confidence", [None, "0.9", True, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence(confidence):
    with pytest.raises(ValidationError):
        make_claim(confidence)


def test_evidence_and_direction_checks():
    assert route_claim(make_claim(), "colour alag hai", "return")[0] == "human_review"
    assert (
        route_claim(make_claim(size_direction="too_large"), "size chhota hai", "return")[0]
        == "human_review"
    )


def test_review_signal_and_logistics_routing():
    positive = make_claim(reason="no_fit_complaint", size_direction="none")
    assert route_claim(positive, "size chhota hai", "review")[0] == "other"
    assert route_claim(positive, "size chhota hai", "return")[0] == "human_review"
    damage = make_claim(reason="damaged_in_transit", size_direction="none")
    assert route_claim(damage, "size chhota hai", "return")[0] == "logistics"


def sample_tables():
    return {
        "vendors": pd.DataFrame([{"vendor_id": "V1", "name": "Tiruppur One"}]),
        "products": pd.DataFrame([{"sku": "SKU1", "vendor_id": "V1", "category": "kurti"}]),
        "order_items": pd.DataFrame(
            [
                {
                    "order_item_id": f"I{index}",
                    "sku": "SKU1",
                    "size": "M",
                    "delivered_at": delivered,
                }
                for index, delivered in enumerate(
                    ["2026-08-28", "2026-09-01", "2026-09-02", "2026-09-04"], start=1
                )
            ]
        ),
        "returns": pd.DataFrame(
            [
                {
                    "return_id": "R1",
                    "order_item_id": "I2",
                    "requested_at": "2026-09-04",
                    "reason_code": "Other",
                    "reason_text": "size chhota hai",
                }
            ]
        ),
        "reviews": pd.DataFrame(
            [
                {
                    "review_id": "RV1",
                    "sku": "SKU1",
                    "order_item_id": "I3",
                    "created_at": "2026-09-05",
                    "rating": "2",
                    "text": "size chhota hai",
                }
            ]
        ),
    }


def test_data_validation_and_cohorts():
    prepared = prepare(validate_tables(sample_tables()), "2026-09-10", 7, 0)
    assert len(prepared["items"]) == 4
    assert len(prepared["records"]) == 2
    assert prepared["items"]["period"].value_counts().to_dict() == {"previous": 3, "current": 1}
    assert prepared["records"][1]["source_type"] == "review"


def test_broken_references_and_duplicate_returns():
    tables = sample_tables()
    tables["reviews"].loc[0, "sku"] = "missing"
    with pytest.raises(ValueError, match="missing products"):
        validate_tables(tables)
    tables = sample_tables()
    tables["returns"] = pd.concat([tables["returns"], tables["returns"].assign(return_id="R2")])
    with pytest.raises(ValueError, match="one return"):
        validate_tables(tables)


def test_redaction():
    assert (
        redact("mail me at test@example.com, phone 9876543210\nAddress: 12 Main Road")
        == "mail me at [email], phone [phone]\n[address]"
    )


def test_reviews_and_duplicate_claims_do_not_inflate_returns():
    prepared = prepare(validate_tables(sample_tables()), "2026-09-05", 7, 0)
    rows = []
    for record in prepared["records"]:
        rows.append(
            {
                **record,
                "lane": "fit",
                "reason": "fit_too_small",
                "size_direction": "too_small",
                "confidence": 0.9,
                "evidence_quote": record["text"],
                "error": "",
            }
        )
    rows.append(rows[0].copy())
    analysis = aggregate(
        prepared, rows, Options(as_of="2026-09-05", period_days=7, maturity_days=0)
    )
    group = analysis["groups"][0]
    assert group["delivered"] == 3
    assert group["fit_returns"] == 1
    assert group["fit_rate"] == pytest.approx(1 / 3)
    assert group["fit_reviews"] == 0
    assert group["status"] == "Insufficient data"


def test_unresolved_return_keeps_delivered_denominator():
    prepared = prepare(validate_tables(sample_tables()), "2026-09-06", 7, 0)
    record = prepared["records"][0]
    analysis = aggregate(
        prepared,
        [{**record, "lane": "human_review", "confidence": 0.75}],
        Options(as_of="2026-09-06"),
    )
    group = analysis["groups"][0]
    assert group["delivered"] == 3
    assert group["fit_returns"] == 0
    assert group["unresolved_returns"] == 1


def fake_chains(confidence=0.9, wrong_id=False):
    import json

    from langchain_core.messages import AIMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    from radar.models import Classification, WeeklyBrief

    prompt = ChatPromptTemplate.from_template("Return JSON for {payload}")

    def classify(inputs):
        payload = json.loads(inputs["payload"])
        parsed = Classification(
            record_id="wrong" if wrong_id else payload["record_id"], claims=[make_claim(confidence)]
        )
        return {
            **inputs,
            "reply": {
                "parsed": parsed,
                "raw": AIMessage(
                    content="{}",
                    usage_metadata={"input_tokens": 30, "output_tokens": 30, "total_tokens": 60},
                ),
            },
        }

    def brief(inputs):
        payload = json.loads(inputs["payload"])
        group = payload["groups"][0]
        parsed = WeeklyBrief(
            findings=[
                {
                    "group_id": group["group_id"],
                    "summary": "Customers report a small fit.",
                    "suggested_action": "Check vendor measurements.",
                    "supporting_record_ids": [
                        payload["evidence"][group["group_id"]][0]["record_id"]
                    ],
                }
            ]
        )
        return {
            **inputs,
            "reply": {
                "parsed": parsed,
                "raw": AIMessage(
                    content="{}",
                    usage_metadata={"input_tokens": 40, "output_tokens": 40, "total_tokens": 80},
                ),
            },
        }

    return {
        "classification": (RunnableLambda(classify), prompt),
        "brief": (RunnableLambda(brief), prompt),
        "size_note": (RunnableLambda(lambda inputs: {}), prompt),
    }


def test_lcel_pipeline_and_session_cache():
    from radar.pipeline import Settings, run

    dataset = validate_tables(sample_tables())
    options = Options(as_of="2026-09-06", period_days=7, maturity_days=0)
    result = run(dataset, options, Settings(), chains=fake_chains())
    assert result["analysis"]["groups"][0]["fit_returns"] == 1
    assert result["analysis"]["groups"][0]["fit_reviews"] == 1
    assert result["brief"] is not None
    assert {call["call_type"] for call in result["calls"]} == {"classification", "brief"}
    repeated = run(dataset, options, Settings(), cache=result["cache"], chains=fake_chains())
    assert all(call["call_type"] != "classification" for call in repeated["calls"])


def test_pipeline_rejects_wrong_ids_and_low_confidence():
    from radar.pipeline import Settings, run

    for chains in [fake_chains(confidence=0.75), fake_chains(wrong_id=True)]:
        result = run(
            validate_tables(sample_tables()),
            Options(as_of="2026-09-06", period_days=7, maturity_days=0),
            Settings(),
            chains=chains,
        )
        assert result["analysis"]["accepted_records"] == 0
        assert result["brief"] is None


def test_budget_failure_is_visible():
    from radar.pipeline import Settings, run

    result = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, budget_inr=0.000001),
        Settings(),
        chains=fake_chains(),
    )
    assert result["messages"]
    assert result["analysis"]["unresolved_records"] == 2
    assert result["calls"] == []


def test_empty_template_and_csv_roundtrip(tmp_path):
    import zipfile

    from radar.data import TABLES, load_csv_bundle

    empty = {name: pd.DataFrame(columns=columns) for name, columns in TABLES.items()}
    prepared = prepare(validate_tables(empty), "2026-09-06", 7, 0)
    assert prepared["records"] == []
    bundle = tmp_path / "bundle.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        for name, frame in sample_tables().items():
            archive.writestr(f"{name}.csv", frame.to_csv(index=False))
    assert len(load_csv_bundle(str(bundle)).tables["order_items"]) == 4


def test_existing_dropdown_label_skips_classification():
    from radar.pipeline import Settings, run

    tables = sample_tables()
    tables["returns"].loc[0, "reason_code"] = "fit_too_small"
    result = run(
        validate_tables(tables),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0),
        Settings(),
        chains=fake_chains(),
    )
    assert len([call for call in result["calls"] if call["call_type"] == "classification"]) == 1
    assert any(row["origin"] == "dropdown" for row in result["rows"])


def flagged_tables():
    tables = sample_tables()
    tables["vendors"] = pd.concat(
        [tables["vendors"], pd.DataFrame([{"vendor_id": "V2", "name": "Jaipur Two"}])],
        ignore_index=True,
    )
    tables["products"] = pd.concat(
        [
            tables["products"],
            pd.DataFrame([{"sku": "SKU2", "vendor_id": "V2", "category": "kurti"}]),
        ],
        ignore_index=True,
    )
    tables["order_items"] = pd.concat(
        [
            tables["order_items"],
            pd.DataFrame(
                [
                    {
                        "order_item_id": "I5",
                        "order_id": "O1",
                        "sku": "SKU2",
                        "size": "M",
                        "delivered_at": "2026-09-01",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    return tables


@pytest.mark.parametrize("confidence,status", [(0.75, "Withheld"), (0.76, "Pending approval")])
def test_separate_size_note_call_and_gate(confidence, status):
    import json

    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from radar.models import SizeNote
    from radar.pipeline import Settings, run

    chains = fake_chains()

    def note(inputs):
        payload = json.loads(inputs["payload"])
        parsed = SizeNote(
            group_id=payload["group"]["group_id"],
            note="Customers report a small fit. Check the size chart.",
            supporting_record_ids=[payload["evidence"][0]["record_id"]],
            confidence=confidence,
        )
        return {
            "reply": {
                "parsed": parsed,
                "raw": AIMessage(
                    content="{}",
                    usage_metadata={"input_tokens": 50, "output_tokens": 50, "total_tokens": 100},
                ),
            }
        }

    chains["size_note"] = (RunnableLambda(note), chains["size_note"][1])
    options = Options(as_of="2026-09-06", period_days=7, maturity_days=0, min_samples=1)
    result = run(validate_tables(flagged_tables()), options, Settings(), chains=chains)
    assert {call["call_type"] for call in result["calls"]} == {
        "classification",
        "brief",
        "size_note",
    }
    assert result["notes"][0]["status"] == status
    assert result["temperatures"] == {"classification": 0.2, "brief": 0.3, "size_note": 0.4}


def test_ui_missing_data_and_human_approval(tmp_path):
    import json

    import gradio as gr

    import app

    with pytest.raises(gr.Error):
        app.run_ui(None, "2026-09-06", 7, 0, 1, 25, 4, 10, {})
    session = {
        "result": {
            "notes": [
                {
                    "group_id": "G1",
                    "note": "Draft",
                    "status": "Pending approval",
                    "reason": "Pending approval",
                }
            ],
            "approvals": [],
        }
    }
    state, notes, message, filename = app.approve_note(session, "G1", "Approved wording")
    assert notes.iloc[0]["Decision"] == "Approved in report"
    assert notes.iloc[0]["Reason"] == message
    assert "Nothing was published" in message
    with open(filename) as report:
        exported = json.load(report)
    assert exported["approvals"][0]["group_id"] == "G1"
    assert exported["notes"][0]["reason"] == message
    with pytest.raises(gr.Error, match="not eligible for approval"):
        app.approve_note(state, "G1", "Approved again")
    assert len(state["result"]["approvals"]) == 1


def test_real_model_chain_configuration_without_network(monkeypatch):
    from radar.pipeline import Settings, build_chains

    monkeypatch.setenv("LLM_API_KEY", "unit-test-placeholder")
    chains = build_chains(Settings())
    assert set(chains) == {"classification", "brief", "size_note"}
    for chain, prompt in chains.values():
        assert prompt.input_variables == ["payload"]
        assert "Input JSON" in prompt.invoke({"payload": "{}"}).to_messages()[1].content


def test_openrouter_uses_provider_key_and_required_parameters(monkeypatch):
    import radar.pipeline as pipeline

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-test-openrouter")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-other-provider")
    original = pipeline.ChatOpenAI
    created = []
    methods = []
    original_output = original.with_structured_output

    def capture_output(self, schema, **kwargs):
        methods.append(kwargs["method"])
        return original_output(self, schema, **kwargs)

    monkeypatch.setattr(original, "with_structured_output", capture_output)

    def capture(**kwargs):
        created.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(pipeline, "ChatOpenAI", capture)
    pipeline.build_chains(pipeline.Settings())
    assert len(created) == 3
    assert all(model["api_key"] == "unit-test-openrouter" for model in created)
    assert all(model["extra_body"]["provider"]["require_parameters"] for model in created)
    assert [model["temperature"] for model in created] == [0.2, 0.3, 0.4]
    assert created[0]["model"] == "meta-llama/llama-4-scout"
    assert created[1]["model"] == "z-ai/glm-5.3-flash"
    assert [model["max_tokens"] for model in created] == [600, 15000, 15000]
    assert [model["timeout"] for model in created] == [45, 120, 120]
    assert methods == ["json_schema", "json_mode", "json_mode"]


def test_openrouter_does_not_reuse_an_openai_key(monkeypatch):
    from radar.pipeline import Settings, build_chains

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-other-provider")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        build_chains(Settings())


def test_delivery_date_preview():
    import app

    preview = app.describe_periods("2026-10-04", 28, 14)
    assert "23 Aug 2026 to 19 Sep 2026" in preview
    assert "26 Jul 2026 to 22 Aug 2026" in preview
    assert "on or after 20 Sep 2026" in preview
    assert "Enter a valid report date" in app.describe_periods("not-a-date", 28, 14)


def test_ui_explains_settings_and_defaults_to_brief_only():
    import app

    demo = app.build_app()
    labels = {
        component["props"].get("label"): component["props"]
        for component in demo.config["components"]
    }
    for label in [
        "Report date (UTC)",
        "Days in each delivery group",
        "Days to wait for returns",
        "Minimum returns to flag",
        "Spending limit for this analysis (INR)",
        "Parallel feedback requests",
        "Size-note drafts per run",
        "Analysis summary",
    ]:
        assert labels[label]["info"]
    assert labels["Size-note drafts per run"]["value"] == 0
    assert labels["Optional: recommendations and spending limit"]["open"] is False
    assert labels["Technical details for the support team"]["open"] is False
    assert "Vendor" in labels["Fit returns by vendor, category and size"]["value"]["headers"]
    assert (
        "No product page or database is updated" in labels["Decision saved in this session"]["info"]
    )


def test_api_failure_returns_visible_unresolved_records():
    from langchain_core.runnables import RunnableLambda

    from radar.pipeline import Settings, run

    chains = fake_chains()

    def fail(inputs):
        raise RuntimeError("fake provider outage")

    chains["classification"] = (RunnableLambda(fail), chains["classification"][1])
    result = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0),
        Settings(),
        chains=chains,
    )
    assert result["analysis"]["unresolved_records"] == 2
    assert result["messages"]


def test_unlinked_review_has_group_without_return_denominator():
    from radar.pipeline import Settings, run

    tables = sample_tables()
    tables["reviews"].loc[0, "order_item_id"] = ""
    result = run(
        validate_tables(tables),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0),
        Settings(),
        chains=fake_chains(),
    )
    group = next(group for group in result["analysis"]["groups"] if group["size"] == "Unknown")
    assert group["fit_reviews"] == 1
    assert group["delivered"] == 0
    assert group["fit_returns"] == 0
    assert group["fit_rate"] is None


def test_low_peer_coverage_prevents_flag():
    from radar.pipeline import Settings, run

    tables = flagged_tables()
    tables["returns"] = pd.concat(
        [
            tables["returns"],
            pd.DataFrame(
                [
                    {
                        "return_id": "R2",
                        "order_item_id": "I5",
                        "requested_at": "2026-09-02",
                        "reason_code": "Other",
                        "reason_text": "",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    result = run(
        validate_tables(tables),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, min_samples=1),
        Settings(),
        chains=fake_chains(),
    )
    group = next(
        group for group in result["analysis"]["groups"] if group["vendor"] == "Tiruppur One"
    )
    assert group["peer_coverage"] == 0
    assert group["status"] == "Low coverage"
    assert not result["notes"]


def test_malformed_parsed_classification_is_visible():
    from langchain_core.runnables import RunnableLambda

    from radar.pipeline import Settings, run

    chains = fake_chains()
    chains["classification"] = (
        RunnableLambda(lambda inputs: {"reply": {"parsed": {"bad": True}, "raw": None}}),
        chains["classification"][1],
    )
    result = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0),
        Settings(),
        chains=chains,
    )
    assert result["analysis"]["unresolved_records"] == 2
    assert all(row["lane"] == "human_review" for row in result["rows"])


@pytest.mark.parametrize("writer_failure", [False, True])
def test_ui_run_and_report_export(monkeypatch, writer_failure):
    import json
    from pathlib import Path

    from langchain_core.runnables import RunnableLambda

    import app
    from radar.pipeline import Settings, run

    classifier_inputs = []
    progress_events = []

    def capture_input(inputs):
        classifier_inputs.append(json.loads(inputs["payload"])["text"])
        return inputs

    chains = fake_chains()
    classifier, prompt = chains["classification"]
    chains["classification"] = (RunnableLambda(capture_input) | classifier, prompt)
    if writer_failure:

        def fail_writer(inputs):
            raise TimeoutError("Synthetic writer failure")

        chains["brief"] = (RunnableLambda(fail_writer), chains["brief"][1])
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: Settings()))
    monkeypatch.setattr(
        app,
        "run",
        lambda dataset, options, settings, cache=None, progress=None: run(
            dataset, options, settings, cache=cache, chains=chains, progress=progress
        ),
    )
    tables = sample_tables()
    contacts = "\nEmail: test@example.com\nPhone: 9876543210\nAddress: 12 Example Road"
    tables["returns"].loc[0, "reason_text"] += contacts
    tables["reviews"].loc[0, "text"] += contacts
    outputs = app.run_ui(
        validate_tables(tables),
        "2026-09-06",
        7,
        0,
        30,
        25,
        1,
        10,
        {},
        progress=lambda value, desc: progress_events.append((value, desc)),
    )
    assert ((0, 2), "Reading feedback: 0/2") in progress_events
    assert ((1, 2), "Reading feedback: 1/2") in progress_events
    assert ((2, 2), "Reading feedback: 2/2") in progress_events
    assert ((0, 1), "Writing weekly brief") in progress_events
    assert progress_events[-1] == ((1, 1), "Analysis complete")
    assert len(classifier_inputs) == 2
    assert all(
        "[email]" in text and "[phone]" in text and "[address]" in text
        for text in classifier_inputs
    )
    assert all(
        "test@example.com" not in text
        and "9876543210" not in text
        and "12 Example Road" not in text
        for text in classifier_inputs
    )
    assert len(outputs) == 17
    if writer_failure:
        assert outputs[2].startswith("No brief available")
    else:
        assert "Customers report a small fit" in outputs[2]
    assert 'class="fit-chart"' in outputs[3]
    with open(outputs[13]) as report:
        saved = json.load(report)
    assert "cache" not in saved
    assert saved["writer_diagnostics"][0]["outcome"] == ("failed" if writer_failure else "success")
    assert saved["writer_diagnostics"][0]["call_type"] == "brief"
    assert saved["options"]["as_of"] == "2026-09-06"
    assert "record_id" not in outputs[5].columns
    assert "Customer comment" in outputs[5].columns
    with open(outputs[12]) as brief:
        assert ("Customers report a small fit" in brief.read()) is not writer_failure
    assert outputs[15]["Returns"].sum() == 1
    assert set(outputs[16]["Source"]) == {"Return note"}
    assert set(outputs[16]["Label source"]) == {"Model"}
    Path(outputs[12]).unlink()
    Path(outputs[13]).unlink()


def test_vendor_details_include_nonfit_and_held_claims():
    import app
    from radar.pipeline import Settings, run

    result = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, max_notes=0),
        Settings(),
        chains=fake_chains(),
    )
    source = next(row for row in result["rows"] if row["source_type"] == "return")
    held = {
        **source,
        "reason": "quality_defect",
        "lane": "human_review",
        "confidence": 0.7,
        "error": "Confidence gate",
    }
    other = {**source, "record_id": "return:other", "vendor": "Other vendor"}
    result["rows"].extend([held, held, other])
    groups, issues, feedback = app.vendor_details({"result": result}, source["vendor"])
    assert set(groups["Vendor"]) == {source["vendor"]}
    assert set(feedback["Issue"]) == {"Too small", "Quality defect"}
    assert "Needs review" in set(feedback["Status"])
    assert set(feedback["Feedback ID"]) == {source["record_id"]}
    assert issues.loc[issues["Issue"].eq("Quality defect"), "Returns"].iloc[0] == 1
    assert set(feedback["Original return reason"]) == {"Other"}


def test_writer_failure_reports_error_type_without_sensitive_details():
    import json

    from langchain_core.runnables import RunnableLambda

    from radar.pipeline import Settings, run

    def fail_writer(inputs):
        raise TimeoutError("Sensitive request details")

    chains = fake_chains()
    chains["brief"] = (RunnableLambda(fail_writer), chains["brief"][1])
    result = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, max_notes=0),
        Settings(),
        chains=chains,
    )
    assert result["brief"] is None
    assert "brief: model request failed (TimeoutError); output withheld." in result["messages"]
    assert "Sensitive request details" not in "\n".join(result["messages"])
    diagnostic = result["writer_diagnostics"][0]
    assert diagnostic["error_type"] == "TimeoutError"
    assert diagnostic["cause_types"] == ["TimeoutError"]
    assert diagnostic["elapsed_seconds"] >= 0
    assert diagnostic["timeout_seconds"] == 120
    assert "Sensitive request details" not in json.dumps(diagnostic)


def test_writer_diagnostics_scrub_api_credentials(monkeypatch):
    import json

    from langchain_core.runnables import RunnableLambda

    from radar.models import WeeklyBrief
    from radar.pipeline import call_writer

    class ProviderError(Exception):
        status_code = 429
        request_id = "synthetic-request-id"
        body = {"error": {"message": "Throttled unit-secret-value; contact test@example.com"}}

    def fail_provider(inputs):
        raise ProviderError() from TimeoutError("Sensitive cause details")

    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-secret-value")
    parsed, response, diagnostic = call_writer(
        RunnableLambda(fail_provider), {"payload": "Sensitive prompt"}, WeeklyBrief
    )
    assert parsed is None and response is None
    assert diagnostic["http_status"] == 429
    assert diagnostic["request_id"] == "synthetic-request-id"
    assert diagnostic["cause_types"] == ["ProviderError", "TimeoutError"]
    assert diagnostic["api_message"] == "Throttled [credential]; contact [email]"
    assert all(
        value not in json.dumps(diagnostic)
        for value in ("unit-secret-value", "Sensitive prompt", "Sensitive cause details")
    )


def test_writer_diagnostics_distinguish_truncated_json():
    import json

    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from radar.models import WeeklyBrief
    from radar.pipeline import call_writer

    reply = {
        "reply": {
            "parsed": None,
            "raw": AIMessage(
                content="", id="synthetic-generation", response_metadata={"finish_reason": "length"}
            ),
            "parsing_error": json.JSONDecodeError("Expecting value", "", 0),
        }
    }
    parsed, response, diagnostic = call_writer(
        RunnableLambda(lambda inputs: reply), {"payload": "{}"}, WeeklyBrief
    )
    assert parsed is None
    assert response is reply["reply"]
    assert diagnostic["outcome"] == "invalid_structured_output"
    assert diagnostic["error_type"] == "JSONDecodeError"
    assert diagnostic["finish_reason"] == "length"
    assert diagnostic["parser_message"] == "Expecting value"


def test_writer_length_failure_preserves_provider_usage():
    import json

    from langchain_core.runnables import RunnableLambda
    from openai import LengthFinishReasonError
    from openai.types.chat import ChatCompletion

    from radar.models import WeeklyBrief
    from radar.pipeline import Meter, Settings, call_writer

    completion = ChatCompletion.model_validate(
        {
            "id": "synthetic-generation",
            "created": 0,
            "model": "z-ai/glm-5.3-flash",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": "Sensitive response content"},
                }
            ],
            "usage": {
                "prompt_tokens": 4000,
                "completion_tokens": 2000,
                "total_tokens": 6000,
                "completion_tokens_details": {"reasoning_tokens": 2000},
            },
        }
    )

    def fail_length(inputs):
        raise LengthFinishReasonError(completion=completion)

    meter = Meter(Settings(), 1.0)
    reservation = meter.reserve("brief", "prompt", 2000)
    parsed, response, diagnostic = call_writer(
        RunnableLambda(fail_length), {"payload": "{}"}, WeeklyBrief
    )
    meter.record(reservation, response)
    assert parsed is None
    assert diagnostic["finish_reason"] == "length"
    assert diagnostic["reasoning_tokens"] == 2000
    assert diagnostic["generation_id"] == "synthetic-generation"
    assert "Sensitive response content" not in json.dumps(diagnostic)
    assert meter.calls[0]["token_basis"] == "provider usage"
    assert meter.calls[0]["input_tokens"] == 4000
    assert meter.calls[0]["output_tokens"] == 2000


def test_writer_replay_uses_saved_evidence_without_classification(tmp_path):
    import json
    from pathlib import Path

    from benchmark import diagnose_writer
    from radar.pipeline import Settings, run

    source = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, max_notes=0),
        Settings(),
        chains=fake_chains(),
    )
    source_file = tmp_path / "saved-run.json"
    source_file.write_text(json.dumps(source), encoding="utf-8")
    original = source_file.read_bytes()
    replay = diagnose_writer(
        source_file,
        folder=tmp_path,
        settings=Settings(),
        chains={"brief": fake_chains()["brief"]},
    )
    assert replay["classifier_calls"] == 0
    assert replay["writer_calls"] == 1
    assert replay["diagnostic"]["outcome"] == "success"
    assert replay["brief_available"]
    saved = json.loads(Path(replay["report"]).read_text(encoding="utf-8"))
    assert not saved["historical_error_recovered"]
    assert [call["call_type"] for call in saved["calls"]] == ["brief"]
    assert source_file.read_bytes() == original


@pytest.mark.parametrize(
    "confidence,supported,status",
    [(0.9, True, "Pending approval"), (0.75, True, "Withheld"), (0.9, False, "Withheld")],
)
def test_size_note_replay_validates_saved_evidence_without_classification(
    tmp_path, confidence, supported, status
):
    import json
    from pathlib import Path

    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    from benchmark import diagnose_writer
    from radar.models import SizeNote
    from radar.pipeline import Settings, run

    source = run(
        validate_tables(flagged_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, min_samples=1, max_notes=0),
        Settings(),
        chains=fake_chains(),
    )
    source_file = tmp_path / "saved-run.json"
    source_file.write_text(json.dumps(source), encoding="utf-8")
    original = source_file.read_bytes()

    def write_note(inputs):
        payload = json.loads(inputs["payload"])
        return {
            "reply": {
                "parsed": SizeNote(
                    group_id=payload["group"]["group_id"],
                    note="Customers report a small fit. Check the size chart.",
                    supporting_record_ids=[
                        payload["evidence"][0]["record_id"] if supported else "unknown"
                    ],
                    confidence=confidence,
                ),
                "raw": AIMessage(
                    content="{}",
                    usage_metadata={"input_tokens": 50, "output_tokens": 50, "total_tokens": 100},
                ),
            }
        }

    replay = diagnose_writer(
        source_file,
        folder=tmp_path,
        settings=Settings(),
        chains={"size_note": (RunnableLambda(write_note), fake_chains()["size_note"][1])},
        kind="size_note",
    )
    saved = json.loads(Path(replay["report"]).read_text(encoding="utf-8"))
    assert replay["classifier_calls"] == 0
    assert replay["writer_calls"] == 1
    assert replay["note_available"] == (status == "Pending approval")
    assert saved["note"]["status"] == status
    assert saved["diagnostic"]["temperature"] == 0.4
    assert [call["call_type"] for call in saved["calls"]] == ["size_note"]
    assert source_file.read_bytes() == original


def test_size_note_evidence_matches_current_return_direction():
    from radar.analysis import size_note_payload

    group = {"group_id": "group", "direction": "too_small"}
    base = {
        "group_id": "group",
        "source_type": "return",
        "period": "current",
        "lane": "fit",
        "size_direction": "too_small",
        "evidence_quote": "Too tight",
        "confidence": 0.8,
    }
    rows = [
        {**base, "record_id": "matching"},
        {**base, "record_id": "opposite", "size_direction": "too_large", "confidence": 0.99},
        {**base, "record_id": "old", "period": "previous", "confidence": 0.99},
        {**base, "record_id": "review", "source_type": "review", "confidence": 0.99},
        {**base, "record_id": "held", "lane": "human_review", "confidence": 0.99},
        {**base, "record_id": "mixed", "confidence": 0.99},
        {**base, "record_id": "mixed", "size_direction": "too_large", "confidence": 0.99},
        {**base, "record_id": "dropdown", "confidence": None},
    ]
    payload = size_note_payload(group, rows)
    assert [row["record_id"] for row in payload["evidence"]] == ["matching", "dropdown"]
    assert len(rows) == 8


def test_brief_displays_selected_fit_quote():
    import app
    from radar.pipeline import Settings, run

    result = run(
        validate_tables(sample_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0),
        Settings(),
        chains=fake_chains(),
    )
    source_id = result["brief"]["findings"][0]["supporting_record_ids"][0]
    result["rows"].append(
        {"record_id": source_id, "lane": "quality", "evidence_quote": "Different claim"}
    )
    assert "Different claim" not in app.render_brief(result)


def test_database_null_delivery_dates_are_optional():
    tables = sample_tables()
    tables["order_items"]["delivered_at"] = pd.to_datetime(
        tables["order_items"]["delivered_at"], utc=True
    )
    tables["order_items"].loc[0, "delivered_at"] = pd.NaT
    dataset = validate_tables(tables)
    assert pd.isna(dataset.tables["order_items"].loc[0, "delivered_at"])


def test_synthetic_dataset_contract_and_bad_inputs(tmp_path):
    import zipfile

    from benchmark import build_dataset, check_bad_inputs
    from radar.data import TABLES, load_csv_bundle

    manifest = build_dataset(tmp_path)
    assert manifest["tables"]["order_items"] == 5000
    assert manifest["distinct_semantic_scenarios"] == 180
    assert manifest["other_share"] >= 0.55
    assert manifest["other_hidden_fit_reference_share"] > 0.5
    assert manifest["copied_background_model_cases"] > 0
    dataset = load_csv_bundle(str(tmp_path / "inputs.zip"))
    assert set(dataset.tables) == set(TABLES)
    with zipfile.ZipFile(tmp_path / "inputs.zip") as archive:
        assert set(archive.namelist()) == {f"{name}.csv" for name in TABLES}
        assert "expected_results.csv" not in archive.namelist()
    expected = pd.read_csv(tmp_path / "expected_results.csv")
    assert expected["record_id"].is_unique
    assert expected["scope"].eq("model").sum() == 180
    assert (
        expected["scope"].eq("model_background").sum() == manifest["copied_background_model_cases"]
    )
    assert check_bad_inputs(tmp_path)["passed"].all()
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation" / "actual_run.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to replace"):
        build_dataset(tmp_path)


def test_benchmark_multilabel_and_review_scoring():
    import json

    from benchmark import score_result

    references = []
    for index, reason, ambiguous in [
        (1, "fit_too_small", False),
        (2, "unclear", True),
        (3, "quality_defect", False),
    ]:
        references.append(
            {
                "record_id": f"review:{index}",
                "case_id": str(index),
                "scope": "model",
                "language": "Hinglish",
                "reference_certainty": "ambiguous" if ambiguous else "clear",
                "expected_review": ambiguous,
                "expected_in_window": True,
                "expected_claims": json.dumps(
                    [
                        {
                            "reason": reason,
                            "size_direction": "too_small"
                            if index == 1
                            else "unclear"
                            if index == 2
                            else "none",
                        }
                    ]
                ),
            }
        )
    references.append(
        {**references[0], "record_id": "review:4", "case_id": "4", "expected_in_window": False}
    )
    rows = [
        {
            "record_id": "review:1",
            "reason": "fit_too_small",
            "size_direction": "too_small",
            "confidence": 0.7,
            "origin": "model",
            "lane": "human_review",
            "error": "Confidence gate",
        },
        {
            "record_id": "review:2",
            "reason": "unclear",
            "size_direction": "unclear",
            "confidence": 0.9,
            "origin": "model",
            "lane": "human_review",
            "error": "Unclear reason",
        },
        {
            "record_id": "review:3",
            "reason": "quality_defect",
            "size_direction": "none",
            "confidence": 0.9,
            "origin": "model",
            "lane": "quality",
            "error": "",
        },
        {
            "record_id": "review:3",
            "reason": "colour_or_look_mismatch",
            "size_direction": "none",
            "confidence": 0.9,
            "origin": "model",
            "lane": "quality",
            "error": "",
        },
    ]
    compared, labels, matrix, routes, slices, summary = score_result(
        {"rows": rows, "cost_inr": 0.1, "brief": {}, "notes": []}, pd.DataFrame(references)
    )
    assert summary["raw_label_exact"] == 2
    assert summary["model_cases"] == 3
    assert summary["model_cases_out_of_window"] == 1
    assert summary["request_failures"] == 0
    assert summary["clear_cases_with_review"] == 1
    assert summary["ambiguous_held_for_review"] == 1
    assert labels.set_index("reason").loc["colour_or_look_mismatch", "extra"] == 1
    assert compared.loc[compared["case_id"].eq("1"), "actual_route"].iloc[0] == "human_review"


def test_score_ui_run_preserves_source_and_validates_dataset(tmp_path):
    import json

    from benchmark import build_dataset, check_bad_inputs, score_ui_run
    from radar.data import load_csv_bundle
    from radar.pipeline import Settings, run

    build_dataset(tmp_path)
    check_bad_inputs(tmp_path)
    options = Options(as_of="2026-10-04", period_days=18, maturity_days=14, max_notes=0)
    result = run(
        load_csv_bundle(str(tmp_path / "inputs.zip")), options, Settings(), chains=fake_chains()
    )
    result.pop("cache")
    result["options"] = vars(options)
    source = tmp_path / "ui-export.json"
    source.write_text(json.dumps(result), encoding="utf-8")
    original = source.read_bytes()
    summary = score_ui_run(source, tmp_path)
    saved = json.loads((tmp_path / "evaluation" / "ui-export" / "actual_run.json").read_text())
    assert saved["benchmark_options"]["period_days"] == 18
    assert saved["evaluation_origin"] == "saved UI run; no new model calls"
    assert summary["size_note_drafts"] == 0
    assert source.read_bytes() == original
    with pytest.raises(ValueError, match="already exists"):
        score_ui_run(source, tmp_path)
    result["rows"][0]["text"] = "Wrong dataset"
    wrong = tmp_path / "wrong-export.json"
    wrong.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        score_ui_run(wrong, tmp_path)


def test_disabled_size_notes_do_not_look_like_writer_failures():
    from radar.pipeline import Settings, run

    result = run(
        validate_tables(flagged_tables()),
        Options(as_of="2026-09-06", period_days=7, maturity_days=0, min_samples=1, max_notes=0),
        Settings(),
        chains=fake_chains(),
    )
    assert any(group["flagged"] for group in result["analysis"]["groups"])
    assert result["notes"] == []
    assert not any(call["call_type"] == "size_note" for call in result["calls"])
    assert "Size-note drafts disabled; no size-note requests made." in result["messages"]
