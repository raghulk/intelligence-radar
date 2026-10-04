import argparse
import hashlib
import json
import math
import random
import subprocess
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv, set_key
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from radar.analysis import Options
from radar.data import TABLES, load_csv_bundle, load_postgres, prepare, validate_tables
from radar.models import Reason

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUN_OPTIONS = dict(
    as_of="2026-10-04",
    period_days=28,
    maturity_days=14,
    min_samples=30,
    concurrency=6,
    budget_inr=15,
    max_notes=2,
)


def write_bundle(path, tables, extra=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, frame in tables.items():
            archive.writestr(f"{name}.csv", frame.to_csv(index=False))
        for name, text in (extra or {}).items():
            archive.writestr(name, text)


def read_scenarios(path):
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len({row["case_id"] for row in rows}) != len(rows) or len(
        {row["text"] for row in rows}
    ) != len(rows):
        raise ValueError("Scenario IDs and text must be unique.")
    for row in rows:
        for claim in row["expected_claims"]:
            Reason(claim["reason"])
            if not claim["evidence_quote"] or claim["evidence_quote"] not in row["text"]:
                raise ValueError(f"Invalid reference quote: {row['case_id']}")
    return rows


def build_dataset(folder=DATA, other_share=0.55):
    if not 0 <= other_share <= 1:
        raise ValueError("Other-return share must be between 0 and 1.")
    if (folder / "evaluation" / "actual_run.json").exists():
        raise ValueError(
            "A scored run exists; refusing to replace its input data or expected labels."
        )
    folder.mkdir(parents=True, exist_ok=True)
    scenarios = read_scenarios(DATA / "feedback_scenarios.jsonl")
    rng = random.Random(20261004)
    vendors = [
        {"vendor_id": f"SYN_V{index}", "name": name}
        for index, name in enumerate(
            [
                "Synthetic Bengaluru Stitch",
                "Synthetic Jaipur Thread",
                "Synthetic Tiruppur Loom",
                "Synthetic Surat Weave",
            ],
            1,
        )
    ]
    categories = ["kurti", "shirt", "dress", "trousers"]
    products = [
        {"sku": f"SYN_V{vendor}_{category}", "vendor_id": f"SYN_V{vendor}", "category": category}
        for vendor in range(1, 5)
        for category in categories
    ]
    items = []
    for period, count, start in [
        ("current", 2500, date(2026, 8, 23)),
        ("previous", 2000, date(2026, 7, 26)),
        ("recent", 200, date(2026, 9, 20)),
        ("old", 200, date(2026, 6, 15)),
        ("undelivered", 100, None),
    ]:
        for index in range(count):
            vendor = index % 4 + 1
            core = index < (2000 if period == "current" else 1200) and period in {
                "current",
                "previous",
            }
            category = (
                ("kurti" if vendor <= 2 else "shirt") if core else categories[rng.randrange(4)]
            )
            size = "M" if core else rng.choice(["S", "M", "L", "XL"])
            delivered = (
                (start + timedelta(days=index % (14 if period == "recent" else 28))).isoformat()
                if start
                else ""
            )
            items.append(
                {
                    "order_item_id": f"SYN_I{len(items) + 1:05}",
                    "sku": f"SYN_V{vendor}_{category}",
                    "size": size,
                    "delivered_at": delivered,
                    "fixture_period": period,
                }
            )
    returned_items = set()
    returns = []
    reviews = []
    reviewed_items = set()
    expected = []

    def choose_item(category=None, vendor=None, period=None):
        choices = [
            item
            for item in items
            if item["order_item_id"] not in returned_items
            and item["order_item_id"] not in reviewed_items
            and item["fixture_period"] in ({period} if period else {"current", "previous"})
            and (not category or item["sku"].endswith("_" + category))
            and (not vendor or item["sku"].startswith(f"SYN_V{vendor}_"))
        ]
        if not choices:
            raise ValueError("Fixture ran out of compatible items.")
        return choices[0]

    def add_feedback(
        case, item, code="Other", in_window=True, scope="model", timestamp=None, linked=True
    ):
        source = case["source_type"]
        if source == "return":
            record_id = f"SYN_R{len(returns) + 1:04}"
            returns.append(
                {
                    "return_id": record_id,
                    "order_item_id": item["order_item_id"],
                    "requested_at": timestamp
                    or (date.fromisoformat(item["delivered_at"]) + timedelta(days=4)).isoformat(),
                    "reason_code": code,
                    "reason_text": case["text"],
                }
            )
            returned_items.add(item["order_item_id"])
        else:
            record_id = f"SYN_RV{len(reviews) + 1:04}"
            reviewed_items.add(item["order_item_id"])
            reviews.append(
                {
                    "review_id": record_id,
                    "sku": item["sku"],
                    "order_item_id": item["order_item_id"] if linked else "",
                    "created_at": timestamp
                    or (date.fromisoformat(item["delivered_at"]) + timedelta(days=5)).isoformat(),
                    "rating": rng.choice([1, 2, 3, 4, 5]),
                    "text": case["text"],
                }
            )
        expected.append(
            {
                "record_id": f"{source}:{record_id}",
                "case_id": case["case_id"],
                "scope": scope,
                "reference_origin": "delegated synthetic annotation"
                if scope == "model"
                else "deterministic code fixture",
                "language": case["language"],
                "reference_certainty": case["reference_certainty"],
                "expected_review": case["expected_review"],
                "expected_in_window": in_window,
                "expected_claims": json.dumps(case["expected_claims"], ensure_ascii=False),
                "tags": json.dumps(case["tags"]),
                "rationale": case["rationale"],
            }
        )

    for index, case in enumerate(scenarios):
        text = case["text"].lower()
        category = (
            "trousers"
            if any(word in text for word in ["jeans", "trouser", "pant "])
            else "shirt"
            if "shirt" in text
            else "dress"
            if "dress" in text
            else "kurti"
        )
        add_feedback(case, choose_item(category=category), linked=index % 9 != 0)

    single = {
        reason.value: [
            case
            for case in scenarios
            if not case["expected_review"]
            and len(case["expected_claims"]) == 1
            and case["expected_claims"][0]["reason"] == reason.value
        ]
        for reason in Reason
    }
    for vendor, reason, count in [
        (1, "fit_too_small", 120),
        (2, "fit_too_small", 30),
        (3, "fit_too_large", 120),
        (4, "fit_too_large", 30),
    ]:
        for index in range(count):
            case = dict(
                single[reason][index % len(single[reason])],
                case_id=f"DROPDOWN_{vendor}_{index:03}",
                source_type="return",
            )
            add_feedback(
                case,
                choose_item(
                    category="kurti" if vendor <= 2 else "shirt", vendor=vendor, period="current"
                ),
                code=reason,
                scope="dropdown",
            )
    other_reasons = [
        "quality_defect",
        "colour_or_look_mismatch",
        "fabric_feel",
        "wrong_or_missing_item",
        "damaged_in_transit",
        "delivery_delay",
        "changed_mind",
    ]
    remaining = [
        item
        for item in items
        if item["fixture_period"] in {"current", "previous"}
        and item["order_item_id"] not in returned_items
    ]
    rng.shuffle(remaining)
    for index in range(700):
        reason = other_reasons[index % len(other_reasons)]
        case = dict(
            single[reason][index % len(single[reason])],
            case_id=f"DROPDOWN_BACKGROUND_{index:03}",
            source_type="return",
        )
        add_feedback(case, remaining[index], code=reason, scope="dropdown")

    template = scenarios[0]
    for case_id, text in [("CONTROL_EMPTY", ""), ("CONTROL_TOO_LONG", "size chhota hai " * 800)]:
        case = dict(
            template,
            case_id=case_id,
            source_type="return",
            text=text,
            expected_claims=[],
            expected_review=True,
            reference_certainty="procedural",
            language="Hinglish",
            tags=["input_guard"],
            rationale="Must be held for review by the empty/oversized input guard, without a model call.",
        )
        add_feedback(case, choose_item(), scope="input_guard")
    reason = "changed_mind"
    case = dict(
        single[reason][0],
        case_id="CONTROL_STRUCTURED_EMPTY",
        source_type="return",
        text="",
        expected_claims=[{"reason": reason, "size_direction": "none", "evidence_quote": ""}],
    )
    add_feedback(case, choose_item(), code=reason, scope="dropdown")
    for period in ["recent", "old"]:
        case = dict(
            single["fit_too_small"][0], case_id=f"EXCLUDED_DELIVERY_{period}", source_type="return"
        )
        add_feedback(case, choose_item(period=period), in_window=False, scope="date_filter")
    case = dict(single["fit_too_small"][0], case_id="EXCLUDED_RETURN_CUTOFF", source_type="return")
    add_feedback(case, choose_item(), timestamp="2026-10-04", in_window=False, scope="date_filter")
    positive = next(
        case
        for case in scenarios
        if case["source_type"] == "review"
        and case["expected_claims"][0]["reason"] == "no_fit_complaint"
    )
    add_feedback(
        dict(positive, case_id="EXCLUDED_REVIEW_CUTOFF"),
        choose_item(),
        timestamp="2026-10-04",
        in_window=False,
        scope="date_filter",
    )

    references = {case["record_id"]: case for case in expected}
    candidates = [
        row
        for row in returns
        if references[f"return:{row['return_id']}"]["scope"] == "dropdown"
        and row["reason_text"].strip()
    ]
    rng.shuffle(candidates)
    candidates.sort(key=lambda row: not row["reason_code"].startswith("fit_"))
    target_other = math.ceil(len(returns) * other_share)
    current_other = sum(row["reason_code"] == "Other" for row in returns)
    if target_other - current_other > len(candidates):
        raise ValueError("Requested Other share exceeds available annotated background rows.")
    for row in candidates[: max(0, target_other - current_other)]:
        row["reason_code"] = "Other"
        reference = references[f"return:{row['return_id']}"]
        reference["scope"] = "model_background"
        reference["reference_origin"] = "copied synthetic background annotation"
    other_rows = [row for row in returns if row["reason_code"] == "Other"]
    hidden_fit = sum(
        any(
            claim["reason"].startswith("fit_")
            for claim in json.loads(references[f"return:{row['return_id']}"]["expected_claims"])
        )
        for row in other_rows
    )

    tables = {
        "vendors": pd.DataFrame(vendors),
        "products": pd.DataFrame(products),
        "order_items": pd.DataFrame(items)[TABLES["order_items"]],
        "returns": pd.DataFrame(returns),
        "reviews": pd.DataFrame(reviews),
    }
    validate_tables(tables)
    for name, frame in tables.items():
        frame.to_csv(folder / f"{name}.csv", index=False)
    pd.DataFrame(expected).to_csv(folder / "expected_results.csv", index=False)
    write_bundle(folder / "inputs.zip", tables)
    build_bad_inputs(folder, tables)
    manifest = {
        "synthetic_only": True,
        "seed": 20261004,
        "tables": {name: len(frame) for name, frame in tables.items()},
        "distinct_semantic_scenarios": len(scenarios),
        "other_returns": len(other_rows),
        "other_share": len(other_rows) / len(returns),
        "other_hidden_fit_reference_share": hidden_fit / len(other_rows) if other_rows else 0,
        "copied_background_model_cases": sum(
            case["scope"] == "model_background" for case in expected
        ),
        "languages": dict(Counter(case["language"] for case in scenarios)),
        "reference_warning": "Model-generated annotations, not certified human truth; copied background model/dropdown rows do not count as distinct model accuracy samples.",
        "run_options": RUN_OPTIONS,
        "inputs_sha256": hashlib.sha256((folder / "inputs.zip").read_bytes()).hexdigest(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_bad_inputs(folder, tables):
    def duplicate(frames):
        frames["vendors"] = pd.concat([frames["vendors"], frames["vendors"].iloc[:1]])

    def missing_column(frames):
        frames["products"] = frames["products"].drop(columns="category")

    def duplicate_return(frames):
        frames["returns"] = pd.concat(
            [frames["returns"], frames["returns"].iloc[:1].assign(return_id="BAD_DUPLICATE")]
        )

    def undelivered_return(frames):
        item_id = frames["returns"].iloc[0]["order_item_id"]
        frames["order_items"].loc[
            frames["order_items"]["order_item_id"].eq(item_id), "delivered_at"
        ] = ""

    def wrong_review_sku(frames):
        linked = frames["reviews"].index[frames["reviews"]["order_item_id"].ne("")][0]
        current = frames["reviews"].loc[linked, "sku"]
        frames["reviews"].loc[linked, "sku"] = next(
            sku for sku in frames["products"]["sku"] if sku != current
        )

    cases = [
        ("duplicate_id", duplicate, "IDs must be nonempty and unique"),
        ("missing_column", missing_column, "missing columns category"),
        (
            "broken_foreign_key",
            lambda frames: frames["reviews"].__setitem__("sku", "MISSING_SKU"),
            "missing products",
        ),
        (
            "invalid_date",
            lambda frames: frames["order_items"].loc.__setitem__((0, "delivered_at"), "2026-99-99"),
            "valid ISO timestamps",
        ),
        (
            "invalid_rating",
            lambda frames: frames["reviews"].loc.__setitem__((0, "rating"), 6),
            "integer from 1 to 5",
        ),
        (
            "fractional_rating",
            lambda frames: frames["reviews"].loc.__setitem__((0, "rating"), 2.5),
            "integer from 1 to 5",
        ),
        (
            "empty_review",
            lambda frames: frames["reviews"].loc.__setitem__((0, "text"), ""),
            "empty values",
        ),
        ("undelivered_return", undelivered_return, "delivered before the return"),
        (
            "return_before_delivery",
            lambda frames: frames["returns"].loc.__setitem__((0, "requested_at"), "2026-01-01"),
            "delivered before the return",
        ),
        ("duplicate_physical_return", duplicate_return, "one return per physical"),
        ("review_wrong_item", wrong_review_sku, "linked item must match SKU"),
        (
            "review_before_delivery",
            lambda frames: frames["reviews"].loc.__setitem__((1, "created_at"), "2026-01-01"),
            "precede the review",
        ),
        (
            "empty_size",
            lambda frames: frames["order_items"].loc.__setitem__((0, "size"), ""),
            "empty values",
        ),
    ]
    expected = []
    for case_id, mutate, error in cases:
        frames = {name: frame.astype(object).copy() for name, frame in tables.items()}
        mutate(frames)
        write_bundle(folder / "bad_inputs" / f"{case_id}.zip", frames)
        expected.append(
            {
                "case_id": case_id,
                "file": f"bad_inputs/{case_id}.zip",
                "expected_error_contains": error,
            }
        )
    write_bundle(
        folder / "bad_inputs" / "answer_key_leak.zip",
        tables,
        {"expected_results.csv": "not allowed in app inputs"},
    )
    expected.append(
        {
            "case_id": "answer_key_leak",
            "file": "bad_inputs/answer_key_leak.zip",
            "expected_error_contains": "five named CSV files",
        }
    )
    (folder / "bad_inputs" / "not_a_zip.zip").write_bytes(b"synthetic invalid archive")
    expected.append(
        {
            "case_id": "not_a_zip",
            "file": "bad_inputs/not_a_zip.zip",
            "expected_error_contains": "BadZipFile",
        }
    )
    pd.DataFrame(expected).to_csv(folder / "expected_input_errors.csv", index=False)


def load_database(folder=DATA, database="intelligence_radar_eval"):
    database_identifier = sql.Identifier(database).as_string()
    container = "trading-agent-postgres-1"
    prefix = ["docker", "exec", "-i", container, "psql", "-X", "-U", "brain"]
    exists = subprocess.run(
        prefix
        + [
            "-d",
            "postgres",
            "-tAc",
            sql.SQL("SELECT datname FROM pg_database WHERE datname = {}")
            .format(sql.Literal(database))
            .as_string(),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if exists:
        raise ValueError("Evaluation database exists; refusing to replace its data.")
    subprocess.run(
        prefix
        + [
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f"CREATE DATABASE {database_identifier}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        prefix + ["-d", database, "-v", "ON_ERROR_STOP=1"],
        input=(ROOT / "schema.sql").read_text(),
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    for name, columns in TABLES.items():
        quoted = ", ".join(f'"{column}"' for column in columns)
        options = "FORMAT CSV, HEADER TRUE" + (
            ", FORCE_NOT_NULL (reason_text)" if name == "returns" else ""
        )
        command = f'COPY "{name}" ({quoted}) FROM STDIN WITH ({options})'
        subprocess.run(
            prefix + ["-d", database, "-v", "ON_ERROR_STOP=1", "-c", command],
            input=(folder / f"{name}.csv").read_text(),
            text=True,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    grants = f"GRANT CONNECT ON DATABASE {database_identifier} TO intelligence_radar_reader; GRANT USAGE ON SCHEMA public TO intelligence_radar_reader; GRANT SELECT ON ALL TABLES IN SCHEMA public TO intelligence_radar_reader; ALTER ROLE intelligence_radar_reader IN DATABASE {database_identifier} SET default_transaction_read_only = on;"
    subprocess.run(
        prefix + ["-d", database, "-v", "ON_ERROR_STOP=1"],
        input=grants,
        text=True,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return verify_database(folder, database)


def verify_database(folder=DATA, database="intelligence_radar_eval"):
    load_dotenv(ROOT / ".env", override=True)
    import os

    values = conninfo_to_dict(os.environ["DATABASE_URL"])
    values["dbname"] = database
    connection = make_conninfo(**values)
    csv_dataset = load_csv_bundle(str(folder / "inputs.zip"))
    postgres = load_postgres(connection)
    for name, columns in TABLES.items():
        key = columns[0]
        pd.testing.assert_frame_equal(
            csv_dataset.tables[name].sort_values(key).reset_index(drop=True),
            postgres.tables[name].sort_values(key).reset_index(drop=True),
        )
    set_key(ROOT / ".env", "DATABASE_URL", connection)
    return {
        "database": database,
        "csv_postgres_equal": True,
        "rows": {name: len(frame) for name, frame in postgres.tables.items()},
    }


def check_bad_inputs(folder=DATA):
    import gradio as gr

    from app import load_data

    reports = []
    for case in pd.read_csv(folder / "expected_input_errors.csv", keep_default_na=False).to_dict(
        "records"
    ):
        path = str(folder / case["file"])
        error_text = "Accepted unexpectedly"
        try:
            load_csv_bundle(path)
        except Exception as error:
            error_text = f"{type(error).__name__}: {error}"
        visible_error = ""
        try:
            load_data("Upload data", path)
        except gr.Error as error:
            visible_error = str(error)
        reports.append(
            {
                **case,
                "actual_error": error_text,
                "ui_error": visible_error,
                "passed": case["expected_error_contains"] in error_text and bool(visible_error),
            }
        )
    frame = pd.DataFrame(reports)
    frame.to_csv(folder / "input_validation_results.csv", index=False)
    return frame


def score_result(result, expected):
    rank = {reason.value: index for index, reason in enumerate(Reason)}
    actual = {}
    for row in result["rows"]:
        actual.setdefault(row["record_id"], []).append(row)
    comparisons = []
    for reference in expected.to_dict("records"):
        rows = actual.get(reference["record_id"], [])
        claims = json.loads(reference["expected_claims"])
        expected_labels = {claim["reason"] for claim in claims}
        expected_pairs = {(claim["reason"], claim["size_direction"]) for claim in claims}
        parsed = [
            row for row in rows if row["confidence"] is not None or row["origin"] == "dropdown"
        ]
        raw_labels = {row["reason"] for row in parsed}
        accepted = {row["reason"] for row in rows if row["lane"] != "human_review"}
        pairs = {(row["reason"], row["size_direction"]) for row in parsed}
        held = [row for row in rows if row["lane"] == "human_review"]
        request_failed = (
            reference["scope"] in {"model", "model_background"}
            and reference["expected_in_window"]
            and not parsed
        )
        route = (
            "not_in_window"
            if not rows
            else "request_failed"
            if request_failed
            else "human_review"
            if len(held) == len(rows)
            else "partial_review"
            if held
            else "auto_accepted"
        )
        expected_route = (
            "not_in_window"
            if not reference["expected_in_window"]
            else "human_review"
            if reference["expected_review"]
            else "auto_accepted"
        )
        primary_expected = (
            "human_review"
            if reference["expected_review"]
            else min(expected_labels, key=rank.get)
            if expected_labels
            else "human_review"
        )
        primary_actual = min(accepted, key=rank.get) if accepted else route
        comparisons.append(
            {
                **reference,
                "source_type": "return"
                if reference["record_id"].startswith("return:")
                else "review",
                "actual_claims": json.dumps(rows, ensure_ascii=False),
                "expected_labels": json.dumps(sorted(expected_labels)),
                "actual_labels": json.dumps(sorted(raw_labels)),
                "accepted_labels": json.dumps(sorted(accepted)),
                "missing_labels": json.dumps(sorted(expected_labels - raw_labels)),
                "extra_labels": json.dumps(sorted(raw_labels - expected_labels)),
                "expected_route": expected_route,
                "actual_route": route,
                "label_exact": raw_labels == expected_labels,
                "direction_exact": pairs == expected_pairs,
                "accepted_exact": accepted == expected_labels and not held,
                "clear_reference_sent_to_review": reference["reference_certainty"] == "clear"
                and bool(held),
                "request_failed": request_failed,
                "primary_expected": primary_expected,
                "primary_actual": primary_actual,
                "review_reasons": " | ".join(sorted({row["error"] for row in held})),
            }
        )
    compared = pd.DataFrame(comparisons)
    semantic = compared.loc[compared["scope"].eq("model") & compared["expected_in_window"]].copy()
    label_metrics = []
    for reason in Reason:
        true_positive = false_positive = false_negative = expected_count = actual_count = 0
        for case in semantic.to_dict("records"):
            gold = reason.value in json.loads(case["expected_labels"])
            prediction = reason.value in json.loads(case["actual_labels"])
            expected_count += gold
            actual_count += prediction
            true_positive += gold and prediction
            false_positive += prediction and not gold
            false_negative += gold and not prediction
        label_metrics.append(
            {
                "reason": reason.value,
                "expected": expected_count,
                "actual": actual_count,
                "correct": true_positive,
                "missed": false_negative,
                "extra": false_positive,
                "precision": true_positive / actual_count if actual_count else 0.0,
                "recall": true_positive / expected_count if expected_count else 0.0,
            }
        )
    matrix = pd.crosstab(semantic["primary_expected"], semantic["primary_actual"])
    routes = pd.crosstab(semantic["expected_route"], semantic["actual_route"])
    slices = (
        semantic.groupby(["language", "reference_certainty"])
        .agg(
            cases=("case_id", "count"),
            exact_labels=("label_exact", "sum"),
            clear_review=("clear_reference_sent_to_review", "sum"),
            request_failures=("request_failed", "sum"),
        )
        .reset_index()
    )
    clear = semantic.loc[semantic["reference_certainty"].eq("clear")]
    ambiguous = semantic.loc[semantic["reference_certainty"].eq("ambiguous")]
    code = compared.loc[compared["scope"].isin(["dropdown", "input_guard", "date_filter"])]
    summary = {
        "model_cases": len(semantic),
        "model_cases_out_of_window": int(
            (compared["scope"].eq("model") & ~compared["expected_in_window"]).sum()
        ),
        "raw_label_exact": int(semantic["label_exact"].sum()),
        "raw_direction_exact": int(semantic["direction_exact"].sum()),
        "clear_cases": len(clear),
        "clear_accepted_exact": int(clear["accepted_exact"].sum()),
        "clear_cases_with_review": int(clear["clear_reference_sent_to_review"].sum()),
        "ambiguous_cases": len(ambiguous),
        "ambiguous_held_for_review": int(ambiguous["actual_route"].eq("human_review").sum()),
        "request_failures": int(semantic["request_failed"].sum()),
        "code_cases": len(code),
        "code_route_matches": int(code["expected_route"].eq(code["actual_route"]).sum()),
        "cost_inr": result["cost_inr"],
        "brief_valid": result["brief"] is not None,
        "size_note_drafts": len(result["notes"]),
        "size_note_pending": sum(note["status"] == "Pending approval" for note in result["notes"]),
    }
    return compared, pd.DataFrame(label_metrics), matrix, routes, slices, summary


def compare_groups(result, expected, dataset):
    from radar.analysis import aggregate

    options = result["benchmark_options"]
    prepared = prepare(
        dataset, **{key: options[key] for key in ("as_of", "period_days", "maturity_days")}
    )
    records = {record["record_id"]: record for record in prepared["records"]}
    reference_rows = []
    for case in expected.to_dict("records"):
        record = records.get(case["record_id"])
        if record is None:
            continue
        for claim in json.loads(case["expected_claims"]):
            reason = claim["reason"]
            lane = (
                "human_review"
                if case["expected_review"]
                else "fit"
                if reason.startswith("fit_")
                else "other"
            )
            reference_rows.append(
                {
                    **record,
                    **claim,
                    "lane": lane,
                    "confidence": 1.0,
                    "error": "Reference ambiguity" if case["expected_review"] else "",
                }
            )
    reference_groups = aggregate(prepared, reference_rows, Options(**options))["groups"]
    actual = {group["group_id"]: group for group in result["analysis"]["groups"]}
    compared = []
    for reference in reference_groups:
        observed = actual[reference["group_id"]]
        row = {key: reference[key] for key in ("group_id", "vendor", "category", "size")}
        for key in (
            "delivered",
            "returns",
            "fit_returns",
            "fit_reviews",
            "fit_rate",
            "direction",
            "coverage",
            "flagged",
            "status",
        ):
            row[f"expected_{key}"] = reference[key]
            row[f"actual_{key}"] = observed[key]
        row["counts_match"] = all(
            reference[key] == observed[key]
            for key in ("delivered", "returns", "fit_returns", "fit_reviews")
        )
        row["flag_matches"] = reference["flagged"] == observed["flagged"]
        compared.append(row)
    return pd.DataFrame(compared)


def markdown_table(frame):
    headers = [str(column) for column in frame.columns]
    rows = [
        [str(value).replace("|", "/").replace("\n", " ") for value in values]
        for values in frame.itertuples(index=False, name=None)
    ]
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(row) + " |" for row in rows],
        ]
    )


def score_ui_run(run_report, folder=DATA):
    source_path = Path(run_report)
    source_bytes = source_path.read_bytes()
    result = json.loads(source_bytes)
    options = result["options"]
    dataset = load_csv_bundle(str(folder / "inputs.zip"))
    prepared = prepare(
        dataset, **{key: options[key] for key in ("as_of", "period_days", "maturity_days")}
    )
    records = {record["record_id"]: record for record in prepared["records"]}
    if {row["record_id"] for row in result["rows"]} != set(records):
        raise ValueError("Saved UI records do not match the supplied dataset and delivery windows.")
    for row in result["rows"]:
        if any(
            row[key] != records[row["record_id"]][key]
            for key in ("text", "group_id", "source_type", "period")
        ):
            raise ValueError(
                "Saved UI feedback differs from the supplied dataset; refusing mismatched scoring."
            )
    report = folder / "evaluation" / source_path.stem
    if (report / "actual_run.json").exists():
        raise ValueError("A scored UI run already exists; refusing to replace it.")
    report.mkdir(parents=True, exist_ok=True)
    result.update(
        benchmark_options=options,
        input_sha256=hashlib.sha256((folder / "inputs.zip").read_bytes()).hexdigest(),
        reference_sha256=hashlib.sha256((folder / "expected_results.csv").read_bytes()).hexdigest(),
        source_run_sha256=hashlib.sha256(source_bytes).hexdigest(),
        evaluation_origin="saved UI run; no new model calls",
    )
    (report / "actual_run.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return write_scores(folder, report=report)


def write_scores(folder=DATA, report=None):
    report = Path(report) if report is not None else folder / "evaluation"
    result = json.loads((report / "actual_run.json").read_text(encoding="utf-8"))
    if hashlib.sha256((folder / "inputs.zip").read_bytes()).hexdigest() != result["input_sha256"]:
        raise ValueError(
            "Input bundle has changed since the single evaluation; refusing mismatched scoring."
        )
    if (
        "reference_sha256" in result
        and hashlib.sha256((folder / "expected_results.csv").read_bytes()).hexdigest()
        != result["reference_sha256"]
    ):
        raise ValueError(
            "Expected labels have changed since the single evaluation; refusing mismatched scoring."
        )
    expected = pd.read_csv(folder / "expected_results.csv", keep_default_na=False)
    dataset = load_csv_bundle(str(folder / "inputs.zip"))
    options = result["benchmark_options"]
    prepared = prepare(
        dataset, **{key: options[key] for key in ("as_of", "period_days", "maturity_days")}
    )
    eligible_ids = {record["record_id"] for record in prepared["records"]}
    expected["expected_in_window"] = expected["record_id"].isin(eligible_ids)
    compared, labels, matrix, routes, slices, summary = score_result(result, expected)
    groups = compare_groups(result, expected, dataset)
    groups.to_csv(report / "group_expected_vs_actual.csv", index=False)
    calls = pd.DataFrame(result["calls"])
    calls.to_csv(report / "call_costs.csv", index=False)
    usage = calls.groupby(["call_type", "token_basis"], as_index=False).agg(
        calls=("cost_inr", "count"), cost_inr=("cost_inr", "sum")
    )
    summary.update(
        {
            "provider_usage_cost_inr": float(
                calls.loc[calls["token_basis"].eq("provider usage"), "cost_inr"].sum()
            ),
            "reserved_estimate_cost_inr": float(
                calls.loc[~calls["token_basis"].eq("provider usage"), "cost_inr"].sum()
            ),
            "group_flag_matches": int(groups["flag_matches"].sum()),
            "groups": len(groups),
        }
    )
    compared.to_csv(report / "expected_vs_actual.csv", index=False)
    labels.to_csv(report / "label_metrics.csv", index=False)
    matrix.to_csv(report / "classification_confusion_matrix.csv")
    routes.to_csv(report / "routing_confusion_matrix.csv")
    slices.to_csv(report / "language_and_certainty.csv", index=False)
    compared.loc[compared["clear_reference_sent_to_review"]].to_csv(
        report / "clear_cases_sent_to_review.csv", index=False
    )
    compared.loc[
        compared["scope"].eq("model")
        & compared["expected_in_window"]
        & (~compared["label_exact"] | ~compared["direction_exact"])
    ].to_csv(report / "classification_errors.csv", index=False)
    (report / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    text = "# Single-Run Synthetic Evaluation\n\nModel-generated reference labels are provisional, not certified human truth. Expected labels were kept outside input ZIPs and were not sent to the classifier. Copied background cases and dropdown rows are excluded from distinct model quality metrics; out-of-window anchors are excluded rather than counted as classifier failures. No classifier prompt was tuned after this run.\n\n"
    text += (
        "## Run Settings\n\n"
        + markdown_table(
            pd.DataFrame([options]).T.reset_index().set_axis(["Setting", "Value"], axis=1)
        )
        + "\n\n"
    )
    text += "## Summary\n\n" + markdown_table(
        pd.DataFrame([summary]).T.reset_index().set_axis(["Measure", "Value"], axis=1)
    )
    text += (
        "\n\n## Labels: Expected Versus Actual\n\nMulti-label counts, including raw valid model labels before confidence/evidence routing.\n\n"
        + markdown_table(labels.round(3))
    )
    text += (
        "\n\n## Routing\n\nPartial review means the comment has both accepted and withheld claims. Request failures are separate from semantic review.\n\n"
        + markdown_table(routes.reset_index())
    )
    text += (
        "\n\n## Classification Matrix\n\nFor multi-label comments, the primary category uses fixed taxonomy order, not model claim order. Full per-label misses/extras are above.\n\n"
        + markdown_table(matrix.reset_index())
    )
    text += "\n\n## Language and Certainty\n\n" + markdown_table(slices)
    semantic = compared.loc[compared["scope"].eq("model") & compared["expected_in_window"]]
    misses = semantic.loc[
        ~semantic["label_exact"], ["case_id", "language", "missing_labels", "extra_labels"]
    ].head(10)
    text += "\n\n## Examples of Label Disagreement\n\n" + markdown_table(misses)
    text += (
        "\n\n## Clear References Sent to Review\n\nThese are not unreasoned reviews. The exact gate reasons are recorded below. Full claim quotes and confidence are in expected_vs_actual.csv; partial-review comments still contain accepted claims.\n\n"
        + markdown_table(
            semantic.loc[
                semantic["clear_reference_sent_to_review"],
                ["case_id", "actual_route", "review_reasons"],
            ]
        )
    )
    text += "\n\n## Ambiguity Controls\n\n" + markdown_table(
        semantic.loc[
            semantic["reference_certainty"].eq("ambiguous")
            & ~semantic["actual_route"].eq("human_review"),
            ["case_id", "actual_labels", "actual_route"],
        ]
    )
    text += (
        "\n\n## Business Groups\n\nCounts and flags use withheld labels with clear claims treated as accepted and ambiguous claims treated as review. This checks downstream effects; it is not an independent proof of the shared aggregation code.\n\n"
        + markdown_table(
            groups.loc[
                groups["expected_flagged"] | groups["actual_flagged"],
                [
                    "vendor",
                    "category",
                    "size",
                    "expected_fit_returns",
                    "actual_fit_returns",
                    "expected_flagged",
                    "actual_flagged",
                ],
            ]
        )
    )
    text += "\n\n## Calls, Cost and Writing Failures\n\n" + markdown_table(usage.round(6))
    text += f"\n\nCost combines provider usage where available with labelled reservations otherwise; it is not an invoice. Brief valid: {summary['brief_valid']}. Size-note drafts: {summary['size_note_drafts']}; pending approval: {summary['size_note_pending']}. Configured maximum note calls: {options['max_notes']}. Zero requested drafts are disabled, not failed. No output is automatically published. Safe writer diagnostics remain in the saved run; older generic failures cannot be retrospectively diagnosed. Scoring makes no model calls.\n\n"
    text += "\n".join(f"- {message}" for message in result["messages"])
    bad_inputs = pd.read_csv(folder / "input_validation_results.csv", keep_default_na=False)
    text += (
        "\n\n## Malformed Inputs\n\nEvery invalid ZIP was checked both at the input adapter and at the UI boundary. None was inserted into Postgres.\n\n"
        + markdown_table(
            bad_inputs[["case_id", "expected_error_contains", "actual_error", "passed"]]
        )
    )
    text += "\n\n## Limits\n\nLabels were generated by a separate agent, not certified by Neha. Direction exact-match distinguishes `none` from `unclear`, even where both are allowed by routing; inspect individual claims before treating every mismatch as a business error. Repeated synthetic background comments and constructed delivery cohorts are controls, not independent examples or realistic historical trends. Dropdown rows and copied model-background cases never inflate distinct-case accuracy. Results apply to the recorded options and in-window cases, not an assumed 28-day benchmark.\n"
    text += "\n\n## Next Decision\n\nInspect disputed annotations, missing/extra labels, direction mismatches and clear cases sent to review before deciding on prompt changes. This small constructed set is not a production accuracy estimate.\n"
    (report / "evaluation_report.md").write_text(text, encoding="utf-8")
    return summary


def evaluate_once(folder=DATA):
    from radar.pipeline import Settings, run

    report = folder / "evaluation"
    report.mkdir(exist_ok=True)
    if (report / "actual_run.json").exists():
        raise ValueError(
            "A scored run already exists. Use score to recompute reports without model calls."
        )
    load_dotenv(ROOT / ".env", override=True)
    dataset = load_csv_bundle(str(folder / "inputs.zip"))
    result = run(dataset, Options(**RUN_OPTIONS), Settings.from_env())
    result.pop("cache")
    result["benchmark_options"] = RUN_OPTIONS
    result["input_sha256"] = hashlib.sha256((folder / "inputs.zip").read_bytes()).hexdigest()
    result["reference_sha256"] = hashlib.sha256(
        (folder / "expected_results.csv").read_bytes()
    ).hexdigest()
    (report / "actual_run.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return write_scores(folder)


def diagnose_writer(
    run_report, folder=DATA, budget_inr=1.0, settings=None, chains=None, kind="brief"
):
    from radar.analysis import eligible_note, size_note_payload
    from radar.models import SizeNote, WeeklyBrief
    from radar.pipeline import (
        Meter,
        Settings,
        brief_payload,
        build_chains,
        call_writer,
        supported_brief,
    )

    if not math.isfinite(budget_inr) or budget_inr <= 0:
        raise ValueError("Writer replay budget must be finite and positive.")
    if kind not in {"brief", "size_note"}:
        raise ValueError("Writer replay kind must be brief or size_note.")
    source_path = Path(run_report)
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    if settings is None:
        load_dotenv(ROOT / ".env", override=True)
        settings = Settings.from_env()
    temperature = 0.3 if kind == "brief" else 0.4
    if (
        settings.writer_model != source["models"]["writing"]
        or source["temperatures"][kind] != temperature
    ):
        raise ValueError(
            "Writer model/temperature differs from the saved run; refusing a changed replay."
        )
    if kind == "brief":
        payload = brief_payload(source["analysis"])
        if payload is None:
            raise ValueError("Saved run has no fit evidence eligible for a weekly brief.")
        schema = WeeklyBrief
    else:
        groups = sorted(
            [group for group in source["analysis"]["groups"] if group["flagged"]],
            key=lambda group: group["fit_rate"],
            reverse=True,
        )
        if not groups:
            raise ValueError("Saved run has no flagged group eligible for a size note.")
        payload = size_note_payload(groups[0], source["rows"])
        if not payload["evidence"]:
            raise ValueError(
                "Saved run has no current return evidence supporting the size direction."
            )
        schema = SizeNote
    chain, prompt = (chains if chains is not None else build_chains(settings))[kind]
    inputs = {"payload": json.dumps(payload, ensure_ascii=False, allow_nan=False)}
    formatted_prompt = str(prompt.invoke(inputs))
    meter = Meter(settings, budget_inr)
    reservation = meter.reserve(kind, formatted_prompt, settings.writer_max_tokens)
    if not reservation:
        raise ValueError("Writer replay exceeds the estimated budget; no call made.")
    parsed, response, diagnostic = call_writer(chain, inputs, schema)
    meter.record(reservation, response)
    note = None
    if parsed is not None and kind == "brief" and not supported_brief(parsed, payload):
        diagnostic["outcome"] = "unsupported_evidence"
        parsed = None
    elif parsed is not None and kind == "size_note":
        eligible, reason = eligible_note(parsed, source["analysis"], payload["evidence"])
        if parsed.group_id != payload["group"]["group_id"]:
            eligible, reason = False, "Model returned the wrong group ID."
        note = {
            **parsed.model_dump(mode="json"),
            "status": "Pending approval" if eligible else "Withheld",
            "reason": reason,
        }
        if not eligible:
            diagnostic.update(outcome="withheld", gate_reason=reason)
    diagnostic.update(
        {
            "model": settings.writer_model,
            "temperature": temperature,
            "timeout_seconds": settings.writer_timeout_seconds,
            "max_output_tokens": settings.writer_max_tokens,
            "max_retries": 0,
            "api_host": urlparse(settings.base_url).hostname,
            "prompt_sha256": hashlib.sha256(formatted_prompt.encode()).hexdigest(),
        }
    )
    report = {
        "source_run": str(source_path),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "historical_error_recovered": False,
        "replay_notice": "This is a new writer-only request using saved evidence; it cannot recover the previous request's missing exception.",
        "classifier_calls": 0,
        "writer_calls": 1,
        "writer_kind": kind,
        "cost_inr": meter.spent,
        "calls": meter.calls,
        "diagnostic": diagnostic,
        "brief": parsed.model_dump(mode="json") if parsed is not None and kind == "brief" else None,
        "note": note,
    }
    target = folder / "evaluation" / "writer_diagnostics"
    target.mkdir(parents=True, exist_ok=True)
    filename = target / f"writer-replay-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
    filename.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return {
        "report": str(filename),
        "classifier_calls": 0,
        "writer_calls": 1,
        "cost_inr": meter.spent,
        "token_basis": meter.calls[0]["token_basis"],
        "brief_available": parsed is not None and kind == "brief",
        "note_available": note is not None and note["status"] == "Pending approval",
        "diagnostic": diagnostic,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "build",
            "load",
            "verify-db",
            "validate",
            "evaluate",
            "score",
            "score-ui",
            "diagnose-writer",
        ],
    )
    parser.add_argument(
        "--run-report", type=Path, default=DATA / "evaluation" / "ui_run_2026-10-04.json"
    )
    parser.add_argument("--budget-inr", type=float, default=1.0)
    parser.add_argument("--writer-kind", choices=["brief", "size_note"], default="brief")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--database", default="intelligence_radar_eval")
    parser.add_argument("--other-share", type=float, default=0.55)
    args = parser.parse_args()
    if args.action == "build":
        result = build_dataset(args.data_dir, other_share=args.other_share)
    elif args.action == "load":
        result = load_database(args.data_dir, args.database)
    elif args.action == "verify-db":
        result = verify_database(args.data_dir, args.database)
    elif args.action == "diagnose-writer":
        result = diagnose_writer(
            args.run_report, folder=args.data_dir, budget_inr=args.budget_inr, kind=args.writer_kind
        )
    elif args.action == "score-ui":
        result = score_ui_run(args.run_report, args.data_dir)
    elif args.action == "validate":
        checks = check_bad_inputs(args.data_dir)
        result = {"bad_inputs": len(checks), "passed": int(checks["passed"].sum())}
        if not checks["passed"].all():
            raise ValueError("Some malformed-input checks did not produce expected visible errors.")
    else:
        result = (
            evaluate_once(args.data_dir)
            if args.action == "evaluate"
            else write_scores(args.data_dir)
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
