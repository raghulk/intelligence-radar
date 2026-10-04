import json
from dataclasses import dataclass

import pandas as pd


@dataclass
class Options:
    as_of: str
    period_days: int = 28
    maturity_days: int = 14
    min_samples: int = 30
    relative_rate: float = 1.5
    direction_share: float = 0.7
    concurrency: int = 4
    budget_inr: float = 25.0
    max_notes: int = 10


def aggregate(prepared: dict, rows: list[dict], options: Options) -> dict:
    items = prepared["items"]
    results = pd.DataFrame(rows)
    groups = []
    evidence = {}
    current_items = items.loc[items["period"] == "current"]
    records = {record["record_id"]: record for record in prepared["records"]}
    item_groups = {group_id: group for group_id, group in items.groupby("group_id", sort=True)}
    for record in prepared["records"]:
        item_groups.setdefault(record["group_id"], items.iloc[:0])
    for group_id, group in sorted(item_groups.items()):
        if group.empty:
            source = next(
                record for record in prepared["records"] if record["group_id"] == group_id
            )
            metadata = {
                "name": source["vendor"],
                "category": source["category"],
                "size": source["size"],
                "vendor_id": json.loads(group_id)[0],
            }
        else:
            metadata = group.iloc[0]
        relevant = results.loc[results["group_id"] == group_id] if not results.empty else results
        accepted = (
            relevant.loc[relevant["lane"] != "human_review"] if not relevant.empty else relevant
        )
        fit = accepted.loc[accepted["lane"] == "fit"] if not accepted.empty else accepted
        periods = {}
        for period in ["current", "previous"]:
            delivered = int(group["period"].eq(period).sum())
            returned_ids = {
                record_id
                for record_id, record in records.items()
                if record["group_id"] == group_id
                and record["source_type"] == "return"
                and record["period"] == period
            }
            fit_ids = (
                set(fit.loc[fit["record_id"].isin(returned_ids), "record_id"])
                if not fit.empty
                else set()
            )
            unresolved_ids = (
                set(
                    relevant.loc[
                        relevant["record_id"].isin(returned_ids)
                        & relevant["lane"].eq("human_review"),
                        "record_id",
                    ]
                )
                if not relevant.empty
                else set()
            )
            accepted_ids = (
                set(accepted.loc[accepted["record_id"].isin(returned_ids), "record_id"])
                if not accepted.empty
                else set()
            )
            periods[period] = {
                "delivered": delivered,
                "returns": len(returned_ids),
                "fit_returns": len(fit_ids),
                "fit_rate": len(fit_ids) / delivered if delivered else None,
                "unresolved_returns": len(unresolved_ids),
                "coverage": len(accepted_ids) / len(returned_ids) if returned_ids else None,
            }
        directional = (
            fit.loc[(fit["source_type"] == "return") & (fit["period"] == "current")]
            if not fit.empty
            else fit
        )
        directions = []
        if not directional.empty:
            for _, claims in directional.groupby("record_id"):
                unique = set(claims["size_direction"]) - {"none", "unclear"}
                directions.append(next(iter(unique)) if len(unique) == 1 else "unclear")
        direction = "unclear"
        share = 0.0
        if directions:
            frequencies = pd.Series(directions).value_counts()
            direction = str(frequencies.index[0])
            share = float(frequencies.iloc[0] / len(directions))
        supporting = []
        if not fit.empty:
            samples = (
                fit.loc[fit["evidence_quote"].ne("")]
                .sort_values("confidence", ascending=False)
                .drop_duplicates("record_id")
                .head(3)
            )
            supporting = samples.astype(object).where(samples.notna(), None).to_dict("records")
        evidence[group_id] = supporting
        peer_items = current_items.loc[
            current_items["category"].eq(metadata["category"])
            & current_items["size"].eq(metadata["size"])
            & current_items["vendor_id"].ne(metadata["vendor_id"])
        ]
        peer_groups = set(peer_items["group_id"])
        peer_fit = (
            results.loc[
                results["group_id"].isin(peer_groups)
                & results["source_type"].eq("return")
                & results["period"].eq("current")
                & results["lane"].eq("fit")
            ]
            if not results.empty
            else results
        )
        peer_return_ids = {
            record_id
            for record_id, record in records.items()
            if record["group_id"] in peer_groups
            and record["source_type"] == "return"
            and record["period"] == "current"
        }
        peer_accepted = (
            results.loc[
                results["record_id"].isin(peer_return_ids) & results["lane"].ne("human_review"),
                "record_id",
            ].nunique()
            if not results.empty
            else 0
        )
        peer_coverage = peer_accepted / len(peer_return_ids) if peer_return_ids else 1.0
        peer_rate = peer_fit["record_id"].nunique() / len(peer_items) if len(peer_items) else None
        current = periods["current"]
        above_peer = (
            current["fit_rate"] is not None
            and peer_rate is not None
            and current["fit_rate"] > 0
            and current["fit_rate"] > peer_rate * options.relative_rate
        )
        flagged = (
            above_peer
            and current["returns"] >= options.min_samples
            and len(peer_items) >= options.min_samples
            and direction in {"too_small", "too_large"}
            and share >= options.direction_share
            and current["coverage"] is not None
            and current["coverage"] >= 0.8
            and peer_coverage >= 0.8
        )
        status = "Flagged" if flagged else "No flag"
        if current["returns"] < options.min_samples or len(peer_items) < options.min_samples:
            status = "Insufficient data"
        elif (current["coverage"] is not None and current["coverage"] < 0.8) or peer_coverage < 0.8:
            status = "Low coverage"
        previous = periods["previous"]
        change = (
            current["fit_rate"] - previous["fit_rate"]
            if current["fit_rate"] is not None and previous["fit_rate"] is not None
            else None
        )
        groups.append(
            {
                "group_id": group_id,
                "vendor": metadata["name"],
                "category": metadata["category"],
                "size": metadata["size"],
                **current,
                "previous_fit_rate": previous["fit_rate"],
                "change_pp": change * 100 if change is not None else None,
                "peer_fit_rate": peer_rate,
                "peer_coverage": peer_coverage,
                "fit_reviews": int(fit.loc[fit["source_type"] == "review", "record_id"].nunique())
                if not fit.empty
                else 0,
                "direction": direction,
                "direction_share": share,
                "status": status,
                "flagged": bool(flagged),
            }
        )
    total_records = len(prepared["records"])
    accepted_records = (
        results.loc[results["lane"] != "human_review", "record_id"].nunique()
        if not results.empty
        else 0
    )
    unresolved_records = (
        results.loc[results["lane"] == "human_review", "record_id"].nunique()
        if not results.empty
        else 0
    )
    return {
        "groups": groups,
        "evidence": evidence,
        "records": total_records,
        "accepted_records": int(accepted_records),
        "unresolved_records": int(unresolved_records),
        "window": prepared["window"],
    }


def size_note_payload(group: dict, rows: list[dict]) -> dict:
    current = [
        row
        for row in rows
        if row["group_id"] == group["group_id"]
        and row["source_type"] == "return"
        and row["period"] == "current"
        and row["lane"] == "fit"
    ]
    directions = {}
    for row in current:
        directions.setdefault(row["record_id"], set()).add(row["size_direction"])
    supporting = sorted(
        [
            row
            for row in current
            if directions[row["record_id"]] - {"none", "unclear"} == {group["direction"]}
            and row["size_direction"] == group["direction"]
            and row["evidence_quote"]
        ],
        key=lambda row: row["confidence"] if row["confidence"] is not None else 0.0,
        reverse=True,
    )
    evidence = {}
    for row in supporting:
        evidence.setdefault(row["record_id"], row)
    return {"group": group, "evidence": list(evidence.values())[:3]}


def eligible_note(note, analysis: dict, evidence=None) -> tuple[bool, str]:
    if note.confidence <= 0.75:
        return False, "Recommendation confidence must be greater than 0.75."
    group = next(
        (group for group in analysis["groups"] if group["group_id"] == note.group_id), None
    )
    if not group or not group["flagged"]:
        return False, "Group does not pass sample, coverage and direction rules."
    allowed = {
        row["record_id"]
        for row in (evidence if evidence is not None else analysis["evidence"][note.group_id])
    }
    if not set(note.supporting_record_ids).issubset(allowed):
        return False, "Size note cites unsupported evidence."
    return True, "Pending approval"
