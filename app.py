import html
import json
import os
import tempfile
import zipfile
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

import gradio as gr
import pandas as pd
from dotenv import load_dotenv

from radar.analysis import Options
from radar.data import TABLES, load_csv_bundle, load_postgres
from radar.pipeline import Settings, run

load_dotenv()


def export_report(result):
    handle = tempfile.NamedTemporaryFile(
        suffix=".json", prefix="radar-report-", delete=False, mode="w"
    )
    with handle:
        json.dump(
            {key: value for key, value in result.items() if key != "cache"},
            handle,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    return handle.name


def export_brief(result):
    handle = tempfile.NamedTemporaryFile(
        suffix=".txt", prefix="weekly-fit-brief-", delete=False, mode="w", encoding="utf-8"
    )
    with handle:
        handle.write("Category Fit Brief\n\n" + render_brief(result) + "\n")
    return handle.name


def template_bundle():
    handle = tempfile.NamedTemporaryFile(suffix=".zip", prefix="radar-csv-template-", delete=False)
    handle.close()
    with zipfile.ZipFile(handle.name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for table, columns in TABLES.items():
            archive.writestr(f"{table}.csv", pd.DataFrame(columns=columns).to_csv(index=False))
    return handle.name


def load_data(source, upload):
    try:
        if source == "Upload data":
            if not upload:
                raise ValueError("Choose a CSV bundle first.")
            dataset = load_csv_bundle(upload)
        else:
            dataset = load_postgres(os.getenv("DATABASE_URL", ""))
        return dataset, dataset.counts(), "Data validated. Ready to run."
    except ValueError as error:
        raise gr.Error(str(error)) from None
    except Exception:
        raise gr.Error(
            "Data loading failed. Check the CSV format or server database configuration."
        ) from None


def describe_periods(as_of, period, maturity):
    try:
        cutoff = pd.to_datetime(as_of, utc=True, errors="raise").to_pydatetime()
        period = int(period)
        maturity = int(maturity)
        if period < 1 or maturity < 0:
            raise ValueError
        end = cutoff - timedelta(days=maturity)
        start = end - timedelta(days=period)
        previous = start - timedelta(days=period)
        return (
            f"Latest: {start:%d %b %Y} to {end - timedelta(days=1):%d %b %Y}\n"
            f"Previous: {previous:%d %b %Y} to {start - timedelta(days=1):%d %b %Y}\n"
            f"Excluded: on or after {end:%d %b %Y}"
        )
    except (ValueError, TypeError, OverflowError):
        return (
            "Enter a valid report date, a positive group length and a nonnegative waiting period."
        )


def display_feedback(rows):
    columns = [
        "Feedback ID",
        "Source",
        "Vendor",
        "Category",
        "Size",
        "Delivery group",
        "Original return reason",
        "Customer comment",
        "Issue",
        "Size signal",
        "Label source",
        "Confidence (%)",
        "Supporting quote",
        "Status",
        "Why review is needed",
    ]
    displayed = []
    for row in rows:
        displayed.append(
            {
                "Feedback ID": row["record_id"],
                "Source": "Return note" if row["source_type"] == "return" else "Customer review",
                "Vendor": row["vendor"],
                "Category": row["category"],
                "Size": row["size"],
                "Delivery group": {
                    "current": "Latest",
                    "previous": "Previous",
                    "supporting": "Supporting review",
                }.get(row.get("period"), "Unknown"),
                "Original return reason": row.get("reason_code", ""),
                "Customer comment": row["text"],
                "Issue": row["reason"].removeprefix("fit_").replace("_", " ").capitalize(),
                "Size signal": {
                    "too_small": "Small fit",
                    "too_large": "Large fit",
                    "none": "No size signal",
                    "unclear": "Unclear",
                }.get(row.get("size_direction"), "Unclear"),
                "Label source": "Return dropdown"
                if row.get("origin") == "dropdown"
                else "Model"
                if pd.notna(row.get("confidence"))
                else "Not classified",
                "Confidence (%)": round(row["confidence"] * 100, 1)
                if pd.notna(row.get("confidence"))
                else None,
                "Supporting quote": row["evidence_quote"],
                "Status": "Needs review" if row["lane"] == "human_review" else "Included",
                "Why review is needed": row["error"],
            }
        )
    return pd.DataFrame(displayed, columns=columns)


def vendor_details(session, vendor="All vendors"):
    rows = [
        row
        for row in (session or {}).get("result", {}).get("rows", [])
        if row["source_type"] == "return" and (vendor == "All vendors" or row["vendor"] == vendor)
    ]
    feedback = display_feedback(rows)
    keys = ["Vendor", "Category", "Size", "Issue", "Status", "Label source"]
    if feedback.empty:
        summary = pd.DataFrame(columns=[*keys, "Returns"])
    else:
        summary = (
            feedback.groupby(keys, dropna=False)["Feedback ID"]
            .nunique()
            .rename("Returns")
            .reset_index()
        )
    analysis = (session or {}).get("result", {}).get("analysis", {"groups": []})
    selected_groups = {
        **analysis,
        "groups": [
            group
            for group in analysis["groups"]
            if vendor == "All vendors" or group["vendor"] == vendor
        ],
    }
    return display_groups(selected_groups), summary, feedback


def display_notes(result):
    groups = {group["group_id"]: group for group in result.get("analysis", {}).get("groups", [])}
    columns = ["Vendor", "Category", "Size", "Suggested wording", "Decision", "Reason"]
    statuses = {
        "Pending approval": "Draft for review",
        "Approved": "Approved in report",
        "Withheld": "Not ready for approval",
    }
    rows = []
    for note in result["notes"]:
        group = groups.get(note["group_id"], {})
        rows.append(
            {
                "Vendor": group.get("vendor", "Unknown"),
                "Category": group.get("category", "Unknown"),
                "Size": group.get("size", "Unknown"),
                "Suggested wording": note["note"],
                "Decision": statuses[note["status"]],
                "Reason": note.get("reason", ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def display_groups(analysis):
    columns = [
        "Vendor",
        "Category",
        "Size",
        "Delivered items",
        "Fit-related returns",
        "Fit-return rate (%)",
        "Rate change (points)",
        "Reviews mentioning fit",
        "Returns needing review",
        "Returns with usable labels (%)",
        "Direction",
        "Status",
    ]
    rows = []
    for group in analysis["groups"]:
        rows.append(
            {
                "Vendor": group["vendor"],
                "Category": group["category"],
                "Size": group["size"],
                "Delivered items": group["delivered"],
                "Fit-related returns": group["fit_returns"],
                "Fit-return rate (%)": round(group["fit_rate"] * 100, 2)
                if group["fit_rate"] is not None
                else None,
                "Rate change (points)": round(group["change_pp"], 2)
                if group["change_pp"] is not None
                else None,
                "Reviews mentioning fit": group["fit_reviews"],
                "Returns needing review": group["unresolved_returns"],
                "Returns with usable labels (%)": round(group["coverage"] * 100, 1)
                if group["coverage"] is not None
                else None,
                "Direction": {
                    "too_small": "Reported small fit",
                    "too_large": "Reported large fit",
                }.get(group["direction"], "No clear direction"),
                "Status": {
                    "Flagged": "Size-note candidate",
                    "No flag": "No size-note flag",
                    "Insufficient data": "Not enough evidence",
                    "Low coverage": "Too much feedback unresolved",
                }.get(group["status"], group["status"]),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def fit_chart(analysis):
    groups = sorted(
        [group for group in analysis["groups"] if group["fit_rate"] is not None],
        key=lambda group: group["fit_rate"],
        reverse=True,
    )[:12]
    if not groups:
        return ""
    maximum = max([group["fit_rate"] or 0 for group in groups] + [0.01])
    bars = []
    for group in groups:
        label = html.escape(f"{group['vendor']} / {group['category']} / {group['size']}")
        rate = group["fit_rate"] or 0
        width = rate / maximum * 100
        bars.append(
            f'<div class="fit-row"><span>{label}</span><div class="track"><div class="bar" style="width:{width:.1f}%"></div></div><strong>{rate:.1%}</strong></div>'
        )
    return '<div class="fit-chart">' + "".join(bars) + "</div>"


def render_brief(result):
    if not result["brief"]:
        return "No brief available. Check findings and run status."
    groups = {group["group_id"]: group for group in result["analysis"]["groups"]}
    records = {
        row["record_id"]: row
        for evidence in result["analysis"]["evidence"].values()
        for row in evidence
    }
    blocks = []
    for finding in result["brief"]["findings"]:
        group = groups[finding["group_id"]]
        title = f"{group['vendor']} | {group['category']} | {group['size']}"
        quotes = [
            f"  {record_id}: {records[record_id]['evidence_quote']}"
            for record_id in finding["supporting_record_ids"]
        ]
        blocks.append(
            "\n".join(
                [title, finding["summary"], "Action: " + finding["suggested_action"], *quotes]
            )
        )
    return "\n\n".join(blocks) or "No findings returned."


def run_ui(
    dataset,
    as_of,
    period,
    maturity,
    minimum,
    budget,
    concurrency,
    max_notes,
    session,
    progress=gr.Progress(),
):
    if dataset is None:
        raise gr.Error("Load and validate data first.")
    try:
        settings = Settings.from_env()
        options = Options(
            as_of=as_of,
            period_days=int(period),
            maturity_days=int(maturity),
            min_samples=int(minimum),
            budget_inr=float(budget),
            concurrency=int(concurrency),
            max_notes=int(max_notes),
        )

        def report_progress(stage, completed, total):
            progress(
                (completed, max(total, 1)),
                desc=f"{stage}: {completed}/{total}" if total > 1 else stage,
            )

        result = run(
            dataset, options, settings, cache=(session or {}).get("cache"), progress=report_progress
        )
        result["options"] = asdict(options)
        result["approvals"] = []
        session = {"cache": result.pop("cache"), "result": result}
        analysis = result["analysis"]
        metrics = (
            f"Feedback considered: {analysis['records']} | With usable labels: {analysis['accepted_records']}\n"
            f"Needs review: {analysis['unresolved_records']} | Model cost: INR {result['cost_inr']:.3f}"
        )
        rows = display_feedback(result["rows"])
        queue = display_feedback([row for row in result["rows"] if row["lane"] == "human_review"])
        groups = {group["group_id"]: group for group in analysis["groups"]}
        choices = [
            (
                f"{groups[note['group_id']]['vendor']} / {groups[note['group_id']]['category']} / {groups[note['group_id']]['size']}",
                note["group_id"],
            )
            for note in result["notes"]
            if note["status"] == "Pending approval"
        ]
        status = "\n".join(result["messages"]) or "Run complete. No automatic publishing."
        _, vendor_issues, vendor_feedback = vendor_details(session)
        return (
            session,
            metrics,
            render_brief(result),
            fit_chart(analysis),
            display_groups(analysis),
            rows,
            queue,
            display_notes(result),
            gr.update(choices=choices, value=None),
            pd.DataFrame(result["calls"]),
            pd.DataFrame(result["weekly_projection"]),
            status,
            export_brief(result),
            export_report(result),
            gr.update(
                choices=[
                    "All vendors",
                    *sorted(
                        {row["vendor"] for row in result["rows"] if row["source_type"] == "return"}
                    ),
                ],
                value="All vendors",
            ),
            vendor_issues,
            vendor_feedback,
        )
    except ValueError as error:
        raise gr.Error(str(error)) from None
    except Exception:
        raise gr.Error(
            "Run failed. Check server configuration and input data; no results were published."
        ) from None


def filter_records(session, lane, search):
    rows = pd.DataFrame((session or {}).get("result", {}).get("rows", []))
    if rows.empty:
        return display_feedback([])
    if lane != "All":
        rows = rows.loc[rows["lane"] == lane]
    if search:
        rows = rows.loc[
            rows["text"].str.contains(search, case=False, regex=False)
            | rows["record_id"].str.contains(search, case=False, regex=False)
        ]
    return display_feedback(rows.to_dict("records"))


def select_note(session, group_id):
    notes = (session or {}).get("result", {}).get("notes", [])
    return next((note["note"] for note in notes if note["group_id"] == group_id), "")


def approve_note(session, group_id, text):
    if not session or not group_id or not text.strip() or len(text) > 300:
        raise gr.Error("Select an eligible note and keep its text within 300 characters.")
    result = session["result"]
    note = next((note for note in result["notes"] if note["group_id"] == group_id), None)
    if not note or note["status"] != "Pending approval":
        raise gr.Error("This note is not eligible for approval.")
    note["note"] = text.strip()
    note["status"] = "Approved"
    note["reason"] = "Note approved for export. Nothing was published."
    result["approvals"].append(
        {
            "group_id": group_id,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "note": text.strip(),
        }
    )
    return (
        session,
        display_notes(result),
        note["reason"],
        export_report(result),
    )


def build_app():
    with gr.Blocks(
        title="Intelligence Radar", analytics_enabled=False, delete_cache=(3600, 86400)
    ) as demo:
        dataset = gr.State(None)
        session = gr.State({})
        gr.Markdown("# Intelligence Radar")
        with gr.Row():
            source = gr.Radio(
                ["Upload data", "Connected database"],
                value="Upload data",
                label="Where is the data?",
            )
            upload = gr.File(
                label="Return and review data (.zip)", file_types=[".zip"], type="filepath"
            )
            with gr.Column(scale=0):
                load_button = gr.Button("Load data")
                gr.DownloadButton("CSV template", value=template_bundle())
        data_status = gr.Textbox(label="Data status", interactive=False)
        with gr.Accordion("Delivery dates to compare", open=True):
            with gr.Row():
                as_of = gr.Textbox(
                    label="Report date (UTC)",
                    value=date.today().isoformat(),
                    info="YYYY-MM-DD. Only feedback before this date is included; this date is excluded.",
                )
                period = gr.Number(
                    label="Days in each delivery group",
                    value=28,
                    minimum=1,
                    maximum=180,
                    precision=0,
                    info="Compare two groups of delivered items, each this many days long. Default: 28 days, about four weeks.",
                )
                maturity = gr.Number(
                    label="Days to wait for returns",
                    value=14,
                    minimum=0,
                    maximum=90,
                    precision=0,
                    info="Exclude the newest deliveries so returns have time to arrive. 14 days is an MVP assumption, not a confirmed return policy.",
                )
            dates = gr.Textbox(
                label="Delivery dates included",
                value=describe_periods(date.today().isoformat(), 28, 14),
                lines=3,
                interactive=False,
                info="Groups use delivery dates, not purchase dates. Reviews support findings but never count as returns.",
            )
        with gr.Accordion("Optional: recommendations and spending limit", open=False):
            with gr.Row():
                minimum = gr.Number(
                    label="Minimum returns to flag",
                    value=30,
                    minimum=1,
                    precision=0,
                    info="A size-note flag needs this many returns in its vendor/category/size group and this many delivered items from peers. Smaller groups remain visible.",
                )
                budget = gr.Number(
                    label="Spending limit for this analysis (INR)",
                    value=25,
                    minimum=0.01,
                    info="Stops new analysis requests near this estimated cost. Unfinished feedback is listed for review. Not a hard cap on your provider's invoice.",
                )
            with gr.Row():
                max_notes = gr.Number(
                    label="Size-note drafts per run",
                    value=0,
                    minimum=0,
                    maximum=50,
                    precision=0,
                    info="Maximum separate writer requests for flagged groups. 0 means brief only; drafts are optional product-page guidance.",
                )
        run_button = gr.Button("Generate weekly brief", variant="primary")
        metrics = gr.Textbox(
            label="Analysis summary",
            lines=2,
            interactive=False,
            info="Counts feedback comments, not orders. A comment can have both a usable issue and another issue needing review. Cost may include estimates.",
        )
        with gr.Tabs():
            with gr.Tab("Weekly brief"):
                brief = gr.Textbox(
                    label="Findings, suggested actions and customer quotes",
                    lines=12,
                    interactive=False,
                    placeholder="No brief generated yet.",
                    info="The brief is ready to read after analysis. No approval is required.",
                )
                chart = gr.HTML()
            with gr.Tab("Vendor information"):
                vendor = gr.Dropdown(choices=["All vendors"], value="All vendors", label="Vendor")
                groups = gr.Dataframe(
                    value=display_groups({"groups": []}),
                    label="Fit returns by vendor, category and size",
                    interactive=False,
                )
                gr.Markdown(
                    "Fit-return rate = accepted fit-related returns / delivered items. A change from 10% to 15% is **5 percentage points**. Reviews are evidence only."
                )
                vendor_issues = gr.Dataframe(
                    value=vendor_details({})[1],
                    label="All return issues by vendor",
                    interactive=False,
                )
                vendor_feedback = gr.Dataframe(
                    value=display_feedback([]),
                    label="All return comments and classification claims",
                    interactive=False,
                )
            with gr.Tab("Source feedback"):
                with gr.Row():
                    lane = gr.Dropdown(
                        [
                            ("All feedback", "All"),
                            ("Fit", "fit"),
                            ("Quality", "quality"),
                            ("Delivery or wrong item", "logistics"),
                            ("Other or no complaint", "other"),
                            ("Needs review", "human_review"),
                        ],
                        value="All",
                        label="Issue group",
                    )
                    search = gr.Textbox(label="Search records")
                explorer = gr.Dataframe(
                    value=display_feedback([]),
                    label="Comments, labels and supporting quotes",
                    interactive=False,
                )
            with gr.Tab("Needs review"):
                queue = gr.Dataframe(
                    value=display_feedback([]),
                    label="Feedback needing a person to check it",
                    interactive=False,
                )
            with gr.Tab("Size-note drafts"):
                notes = gr.Dataframe(
                    value=display_notes({"notes": []}),
                    label="Optional product-page fit guidance",
                    interactive=False,
                )
                selected_note = gr.Dropdown(choices=[], label="Choose a draft to review")
                note_text = gr.Textbox(
                    label="Draft wording",
                    lines=3,
                    max_length=300,
                    info="A size note is proposed shopping guidance, such as a small-fit warning. It is not the weekly brief.",
                )
                approve = gr.Button("Mark draft approved (report only)")
                approval_status = gr.Textbox(
                    label="Decision saved in this session",
                    interactive=False,
                    info="No product page or database is updated. Approval only marks the draft in the downloadable report.",
                )
            with gr.Tab("Input data"):
                counts = gr.Dataframe(
                    value=pd.DataFrame(columns=["table", "rows"]),
                    label="Rows loaded from each input table",
                    interactive=False,
                )
        with gr.Accordion("Technical details for the support team", open=False):
            concurrency = gr.Slider(
                1,
                16,
                value=4,
                step=1,
                label="Parallel feedback requests",
                info="4 means classify up to four comments at once. Higher values can hit provider rate limits; business calculations stay the same.",
            )
            calls = gr.Dataframe(label="Token usage and cost per model request", interactive=False)
            projection = gr.Dataframe(
                label="Planning cost: 11,800 classifications, one brief, 50 optional notes per week",
                interactive=False,
            )
            report = gr.File(
                label="Diagnostic report with evidence and costs (JSON)", interactive=False
            )
        run_status = gr.Textbox(label="Completion status and warnings", interactive=False, lines=3)
        brief_file = gr.File(label="Download category brief (.txt)", interactive=False)
        load_button.click(
            load_data, [source, upload], [dataset, counts, data_status], api_name=False
        )
        run_button.click(
            run_ui,
            [
                dataset,
                as_of,
                period,
                maturity,
                minimum,
                budget,
                concurrency,
                max_notes,
                session,
            ],
            [
                session,
                metrics,
                brief,
                chart,
                groups,
                explorer,
                queue,
                notes,
                selected_note,
                calls,
                projection,
                run_status,
                brief_file,
                report,
                vendor,
                vendor_issues,
                vendor_feedback,
            ],
            concurrency_limit=1,
            api_name=False,
        )
        lane.change(filter_records, [session, lane, search], explorer, api_name=False)
        search.submit(filter_records, [session, lane, search], explorer, api_name=False)
        vendor.change(
            vendor_details,
            [session, vendor],
            [groups, vendor_issues, vendor_feedback],
            api_name=False,
        )
        for control in [as_of, period, maturity]:
            control.change(describe_periods, [as_of, period, maturity], dates, api_name=False)
        selected_note.change(select_note, [session, selected_note], note_text, api_name=False)
        approve.click(
            approve_note,
            [session, selected_note, note_text],
            [session, notes, approval_status, report],
            api_name=False,
        )
    return demo


if __name__ == "__main__":
    credentials = (os.getenv("APP_USERNAME"), os.getenv("APP_PASSWORD"))
    auth = credentials if all(credentials) else None
    build_app().queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        share=False,
        auth=auth,
        show_error=False,
        max_file_size="25mb",
        theme=gr.themes.Soft(
            primary_hue="emerald", neutral_hue="zinc", font=["IBM Plex Sans", "sans-serif"]
        ),
        css=".gradio-container {max-width:1280px!important} .fit-chart{padding:16px 0}.fit-row{display:grid;grid-template-columns:minmax(150px,2fr) 3fr 64px;gap:12px;align-items:center;margin:12px 0}.track{height:12px;background:#e4e4e7}.bar{height:12px;background:#059669}.fit-row span{overflow-wrap:anywhere}@media(max-width:600px){.fit-row{grid-template-columns:minmax(90px,2fr) 2fr 50px;font-size:12px}}",
    )
