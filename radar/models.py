from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
CONFIDENCE_THRESHOLD = 0.75


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reason(StrEnum):
    TOO_SMALL = "fit_too_small"
    TOO_LARGE = "fit_too_large"
    SHAPE = "fit_length_or_shape"
    QUALITY = "quality_defect"
    LOOK = "colour_or_look_mismatch"
    FABRIC = "fabric_feel"
    WRONG_ITEM = "wrong_or_missing_item"
    DAMAGE = "damaged_in_transit"
    DELAY = "delivery_delay"
    MIND = "changed_mind"
    NO_ISSUE = "no_fit_complaint"
    UNCLEAR = "unclear"


class Claim(Contract):
    reason: Reason
    size_direction: Literal["too_small", "too_large", "none", "unclear"]
    evidence_quote: str = Field(min_length=1)
    confidence: Confidence


class Classification(Contract):
    record_id: str
    claims: list[Claim] = Field(min_length=1, max_length=4)


class Finding(Contract):
    group_id: str
    summary: str = Field(min_length=1, max_length=600)
    suggested_action: str = Field(min_length=1, max_length=300)
    supporting_record_ids: list[str] = Field(min_length=1, max_length=3)


class WeeklyBrief(Contract):
    findings: list[Finding] = Field(max_length=5)


class SizeNote(Contract):
    group_id: str
    note: str = Field(min_length=1, max_length=300)
    supporting_record_ids: list[str] = Field(min_length=1, max_length=3)
    confidence: Confidence


def route_claim(claim: Claim, text: str, source_type: str) -> tuple[str, str]:
    if claim.evidence_quote not in text:
        return "human_review", "Evidence quote does not match source text."
    if claim.confidence <= CONFIDENCE_THRESHOLD:
        return "human_review", "Confidence must be greater than 0.75."
    if claim.reason == Reason.UNCLEAR:
        return "human_review", "Reason is unclear."
    if claim.reason == Reason.NO_ISSUE and source_type != "review":
        return "human_review", "No-fit-complaint is a review-only label."
    expected_direction = {
        Reason.TOO_SMALL: "too_small",
        Reason.TOO_LARGE: "too_large",
    }.get(claim.reason)
    if expected_direction and claim.size_direction != expected_direction:
        return "human_review", "Size direction conflicts with the reason."
    if claim.reason.value.startswith("fit_"):
        return "fit", "Accepted"
    if claim.reason in {Reason.QUALITY, Reason.LOOK, Reason.FABRIC}:
        return "quality", "Accepted"
    if claim.reason in {Reason.WRONG_ITEM, Reason.DAMAGE, Reason.DELAY}:
        return "logistics", "Accepted"
    return "other", "Accepted"
